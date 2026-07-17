"""Tests for Pi JSON tool-loop helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.project import AgentSession, AgentStep, ProjectFact
from app.services.agent.subagent_profiles import get_profile
from app.services.pi_agent_service import MuseGraphPiAgent, PiAgentContext
from app.services.pi_tool_loop import (
    MUSEGRAPH_TOOLS,
    PI_ACTION_RESPONSE_SCHEMA,
    action_to_step_record,
    build_initial_messages,
    build_loop_system_prompt,
    parse_pi_action,
    truncate_tool_result,
)


def test_parse_pi_action_tool_call():
    raw = '{"action":"tool_call","tool":"memory_search","args":{"query":"mars"},"reason":"lookup"}'
    parsed = parse_pi_action(raw)
    assert parsed is not None
    assert parsed["action"] == "tool_call"
    assert parsed["tool"] == "memory_search"


def test_parse_pi_action_finish():
    raw = '{"action":"finish","output":"done","structured_memory":{"world":"mars"}}'
    parsed = parse_pi_action(raw)
    assert parsed is not None
    assert parsed["action"] == "finish"
    assert parsed["output"] == "done"


def test_parse_pi_action_infers_finish_from_output():
    raw = '{"output":"summary only","task_kind":"content_analysis"}'
    parsed = parse_pi_action(raw)
    assert parsed is not None
    assert parsed["action"] == "finish"


def test_parse_pi_action_infers_zero_arg_tool_call():
    raw = '{"tool":"list_document_units","args":{},"reason":"read first"}'
    parsed = parse_pi_action(raw)
    assert parsed is not None
    assert parsed["action"] == "tool_call"
    assert parsed["tool"] == "list_document_units"
    assert parsed["args"] == {}


def test_parse_pi_action_accepts_arguments_alias_and_tool_name_action():
    parsed = parse_pi_action('{"action":"memory_search","query":"mars","top_k":3}')
    assert parsed is not None
    assert parsed["action"] == "tool_call"
    assert parsed["tool"] == "memory_search"
    assert parsed["args"] == {"query": "mars", "top_k": 3}

    parsed = parse_pi_action('{"name":"read_document_unit","arguments":"{\\"document_unit_id\\":\\"u1\\"}"}')
    assert parsed is not None
    assert parsed["action"] == "tool_call"
    assert parsed["tool"] == "read_document_unit"
    assert parsed["args"] == {"document_unit_id": "u1"}

    parsed = parse_pi_action('{"tool":"read_document_unit","arguments":"{\\"document_unit_id\\":\\"u1\\"}"}')
    assert parsed is not None
    assert parsed["action"] == "tool_call"
    assert parsed["args"] == {"document_unit_id": "u1"}


def test_build_initial_messages_includes_instruction():
    msgs = build_initial_messages(
        "analyze document unit 1",
        memory_block="ctx",
        session_title="",
        available_models=["gpt-5.5", "model-writer"],
    )
    assert msgs[-1]["role"] == "user"
    assert "analyze document unit 1" in msgs[-1]["content"]
    assert "ctx" in msgs[-1]["content"]
    assert "current_title: <unset>" in msgs[-1]["content"]
    assert 'available_chat_models: ["gpt-5.5", "model-writer"]' in msgs[-1]["content"]


def test_action_to_step_record_for_tool():
    step = action_to_step_record(
        step_index=1,
        action={"action": "tool_call", "tool": "read_document_unit", "reason": "read"},
        status="running",
    )
    assert step["step_type"] == "read_document_unit"
    assert step["status"] == "running"


def test_action_to_step_record_preserves_subagent_metadata():
    step = action_to_step_record(
        step_index=2,
        action={
            "action": "tool_call",
            "tool": "spawn_subagent",
            "args": {"task": "draft", "subagent_role": "writer", "model": "model-writer"},
        },
        status="running",
    )
    assert step["tool_args"]["task"] == "draft"
    assert step["agent_role"] == "writer"
    assert step["model"] == "model-writer"


def test_pi_tools_expose_document_units_facts_and_strict_subagent_model():
    tools = {str(item.get("name")): item for item in MUSEGRAPH_TOOLS}
    names = set(tools)
    assert "set_session_title" in names
    assert {"list_document_units", "read_document_unit", "write_document_unit"}.issubset(names)
    assert {
        "list_facts",
        "read_fact",
        "create_fact",
        "update_fact",
        "sync_fact_memory",
        "search_entities",
        "batch_update_entities",
    }.issubset(names)
    assert "analyze_and_plan" not in names
    assert "list_chapters" not in names
    assert "read_chapter" not in names
    assert "write_chapter" not in names

    spawn = tools["spawn_subagent"]
    assert "model" in spawn["parameters"]["required"]
    roles = set(spawn["parameters"]["properties"]["subagent_role"]["enum"])
    assert {
        "planner",
        "composer",
        "writer",
        "auditor",
        "reviser",
        "evaluator",
        "updater",
        "memory_builder",
        "graph_extractor",
    } == roles

    prompt = build_loop_system_prompt()
    assert "set_session_title" in prompt
    assert "current_title" in prompt
    assert "available_chat_models" in prompt
    assert '"name": "spawn_subagent"' in prompt


def test_subagent_loop_prompt_hides_spawn_subagent_tool():
    prompt = build_loop_system_prompt(role="planner")

    assert '"name": "spawn_subagent"' not in prompt
    assert "你是子代理，不是主编排者" in prompt
    assert "不要调用 spawn_subagent" in prompt


def test_pi_action_response_schema_requests_json_object_actions():
    assert PI_ACTION_RESPONSE_SCHEMA["x_musegraph_response_format"] == "json_object"
    assert PI_ACTION_RESPONSE_SCHEMA["required"] == ["action"]
    assert set(PI_ACTION_RESPONSE_SCHEMA["properties"]["action"]["enum"]) == {"tool_call", "finish"}
    assert PI_ACTION_RESPONSE_SCHEMA["additionalProperties"] is False


def test_subagent_role_contract_is_system_prompt_not_user_task():
    prompt = get_profile("writer").system_prompt

    assert "writer" in prompt
    assert "write_document_unit" in prompt
    assert "不要 spawn 其他子代理" in prompt


def test_truncate_tool_result():
    big = {"data": "x" * 20000}
    text = truncate_tool_result(big)
    assert len(text) <= 12050
    assert text.endswith("...(truncated)")


@pytest.mark.asyncio
async def test_pi_build_project_memory_uses_separate_build_and_embedding_models(monkeypatch):
    agent = MuseGraphPiAgent()
    project = SimpleNamespace(
        id="proj-1",
        component_models={
            "memory_build": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "memory_embedding": "Qwen3-Embedding-0.6B",
        },
        memory_id=None,
        chapters=[
            SimpleNamespace(id="ch-1", title="Source", content="正文" * 80, order_index=0),
        ],
    )
    ctx = PiAgentContext(
        project_id="proj-1",
        user_id="user-1",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        session_id="sess-1",
        parent_operation_id="op-parent",
        project=project,
    )
    captured: dict[str, object] = {}

    async def _build_memory(project_id, text, **kwargs):
        captured["project_id"] = project_id
        captured["text"] = text
        captured.update(kwargs)
        return "memory-1"

    snapshot_mock = AsyncMock()
    monkeypatch.setattr("app.services.memory_service.build_memory", _build_memory)
    monkeypatch.setattr("app.services.pi_agent_service.write_project_workspace_version_snapshot_from_db", snapshot_mock)
    db = SimpleNamespace(flush=AsyncMock())

    result = await agent.execute_tool("build_project_memory", {}, ctx, db)

    assert result["ok"] is True
    assert captured["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert captured["embedding_model"] == "Qwen3-Embedding-0.6B"
    assert captured["operation_id"] == "op-parent"
    assert project.memory_id == "memory-1"
    db.flush.assert_awaited_once()
    # Workspace snapshots are deferred to the end of the agent run.
    snapshot_mock.assert_not_awaited()
    assert ctx.workspace_dirty is True


@pytest.mark.asyncio
async def test_pi_build_project_memory_rejects_removed_unit_scope(monkeypatch):
    agent = MuseGraphPiAgent()
    project = SimpleNamespace(
        id="proj-1",
        component_models={
            "memory_build": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "memory_embedding": "Qwen3-Embedding-0.6B",
        },
        memory_id=None,
        chapters=[
            SimpleNamespace(id="unit-1", title="First", content="first text", order_index=0),
            SimpleNamespace(id="unit-2", title="Second", content="second text", order_index=1),
        ],
    )
    ctx = PiAgentContext(
        project_id="proj-1",
        user_id="user-1",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        session_id="sess-1",
        project=project,
    )
    captured: dict[str, object] = {}

    async def _build_memory(project_id, text, **kwargs):
        captured["project_id"] = project_id
        captured["text"] = text
        captured.update(kwargs)
        return "memory-2"

    snapshot_mock = AsyncMock()
    monkeypatch.setattr("app.services.memory_service.build_memory", _build_memory)
    monkeypatch.setattr("app.services.pi_agent_service.write_project_workspace_version_snapshot_from_db", snapshot_mock)
    db = SimpleNamespace(flush=AsyncMock())

    with pytest.raises(RuntimeError, match="does not accept arguments"):
        await agent.execute_tool("build_project_memory", {"scope": "unit"}, ctx, db)

    result = await agent.execute_tool(
        "build_project_memory",
        {},
        ctx,
        db,
    )

    assert result["ok"] is True
    assert captured["text"] == "# First\nfirst text\n\n# Second\nsecond text"
    assert project.memory_id == "memory-2"
    snapshot_mock.assert_not_awaited()
    assert ctx.workspace_dirty is True


@pytest.mark.asyncio
async def test_pi_write_document_unit_requires_explicit_target_unless_create(monkeypatch):
    agent = MuseGraphPiAgent()
    project = SimpleNamespace(id="proj-1", chapters=[], component_models={})
    ctx = PiAgentContext(
        project_id="proj-1",
        user_id="user-1",
        model="nvidia/nemotron-3-ultra-550b-a55b:free",
        session_id="sess-1",
        project=project,
    )
    db = SimpleNamespace(flush=AsyncMock())

    with pytest.raises(RuntimeError, match="document_unit_id"):
        await agent.execute_tool(
            "write_document_unit",
            {"mode": "append", "content": "正文" * 80},
            ctx,
            db,
        )

    async def _write_chapter_content(**kwargs):
        return {"ok": True, "chapter_id": "unit-created", "title": kwargs["title"], "mode": kwargs["mode"]}

    snapshot_mock = AsyncMock()
    monkeypatch.setattr("app.services.pi_agent_service.write_chapter_content", _write_chapter_content)
    monkeypatch.setattr("app.services.pi_agent_service.write_project_workspace_version_snapshot_from_db", snapshot_mock)

    result = await agent.execute_tool(
        "write_document_unit",
        {"mode": "create", "title": "Unit", "content": "正文" * 80},
        ctx,
        db,
    )

    assert result["ok"] is True
    assert result["document_unit_id"] == "unit-created"
    assert "chapter_id" not in result
    snapshot_mock.assert_not_awaited()
    assert ctx.workspace_dirty is True


class _FactDb:
    def __init__(self) -> None:
        self.facts: dict[str, ProjectFact] = {}
        self.commit_count = 0

    def add(self, obj):
        if isinstance(obj, ProjectFact):
            self.facts[obj.id] = obj

    async def flush(self):
        return None

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, _obj):
        return None

    async def get(self, model, obj_id):
        if model is ProjectFact:
            return self.facts.get(obj_id)
        return None


@pytest.mark.asyncio
async def test_pi_create_fact_schedules_memory_sync(monkeypatch):
    agent = MuseGraphPiAgent()
    project = SimpleNamespace(id="proj-1")
    ctx = PiAgentContext(
        project_id="proj-1",
        user_id="user-1",
        model="model-main",
        session_id="sess-1",
        project=project,
    )
    db = _FactDb()
    scheduled: dict[str, str | None] = {}

    def _schedule_fact_memory_sync(**kwargs):
        scheduled.update(kwargs)
        return "task-fact-1"

    snapshot_mock = AsyncMock()
    monkeypatch.setattr("app.services.pi_agent_service.schedule_fact_memory_sync", _schedule_fact_memory_sync)
    monkeypatch.setattr("app.services.pi_agent_service.write_project_workspace_version_snapshot_from_db", snapshot_mock)

    result = await agent.execute_tool(
        "create_fact",
        {"title": "Copper key", "content": "Lin found the copper key.", "source_kind": "agent"},
        ctx,
        db,
    )

    assert result["ok"] is True
    assert result["task_id"] == "task-fact-1"
    assert result["fact"]["memory_status"] == "syncing"
    assert result["fact"]["created_by_agent_session_id"] == "sess-1"
    assert scheduled == {
        "project_id": "proj-1",
        "user_id": "user-1",
        "action": "create",
        "fact_id": result["fact"]["id"],
    }
    assert db.commit_count == 2
    snapshot_mock.assert_not_awaited()
    assert ctx.workspace_dirty is True


@pytest.mark.asyncio
async def test_pi_spawn_subagent_rejects_unavailable_model(monkeypatch):
    agent = MuseGraphPiAgent()
    ctx = PiAgentContext(
        project_id="proj-1",
        user_id="user-1",
        model="model-main",
        session_id="sess-1",
        project=SimpleNamespace(id="proj-1"),
    )

    async def _available_models(_db):
        return [{"id": "model-a", "name": "model-a"}]

    monkeypatch.setattr("app.services.pi_agent_service.get_available_models", _available_models)

    with pytest.raises(RuntimeError, match="not configured or active"):
        await agent.execute_tool(
            "spawn_subagent",
            {"task": "draft", "subagent_role": "writer", "model": "missing-model"},
            ctx,
            SimpleNamespace(),
        )


class _AgentSessionDb:
    def __init__(self) -> None:
        self.sessions: dict[str, AgentSession] = {}
        self.added: list[object] = []
        self.commit_count = 0
        self.flush_count = 0

    async def get(self, model, obj_id):
        if model is AgentSession:
            return self.sessions.get(obj_id)
        return None

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, AgentSession):
            self.sessions[obj.id] = obj

    async def commit(self):
        self.commit_count += 1

    async def flush(self):
        self.flush_count += 1


@pytest.mark.asyncio
async def test_pi_set_session_title_updates_current_session():
    agent = MuseGraphPiAgent()
    ctx = PiAgentContext(
        project_id="proj-1",
        user_id="user-1",
        model="model-main",
        session_id="session-title",
        project=SimpleNamespace(id="proj-1"),
    )
    db = _AgentSessionDb()
    db.sessions["session-title"] = AgentSession(
        id="session-title",
        project_id="proj-1",
        user_id="user-1",
        role="orchestrator",
    )

    result = await agent.execute_tool(
        "set_session_title",
        {"title": "圣塔规划"},
        ctx,
        db,
    )

    assert result == {"ok": True, "session_id": "session-title", "session_title": "圣塔规划"}
    assert db.sessions["session-title"].title == "圣塔规划"
    assert db.sessions["session-title"].workspace == {"title_source": "agent_tool"}
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_pi_spawn_subagent_links_to_current_parent_step(monkeypatch):
    agent = MuseGraphPiAgent()
    ctx = PiAgentContext(
        project_id="proj-1",
        user_id="user-1",
        model="model-main",
        session_id="parent-session",
        root_session_id="parent-session",
        current_step_id="parent-session:pi-loop-2",
        pending_child_session_id="child-session",
        project=SimpleNamespace(id="proj-1"),
    )
    db = _AgentSessionDb()
    monkeypatch.setattr(agent, "_require_available_chat_model", AsyncMock())

    async def _run_flow(**kwargs):
        assert kwargs["instruction"] == "draft"
        assert "[Subagent:" not in kwargs["instruction"]
        assert kwargs["parent_step_id"] == "parent-session:pi-loop-2"
        return {"status": "COMPLETED", "plan_result": {"output": "child done"}}

    monkeypatch.setattr(agent, "run_flow", _run_flow)

    result = await agent.execute_tool(
        "spawn_subagent",
        {"task": "draft", "subagent_role": "writer", "model": "model-writer"},
        ctx,
        db,
    )

    assert result["ok"] is True
    assert result["child_session_id"] == "child-session"
    assert db.sessions["child-session"].parent_step_id == "parent-session:pi-loop-2"
    assert db.sessions["child-session"].title is None
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_record_child_event_rejects_cross_session_step_id(monkeypatch):
    agent = MuseGraphPiAgent()
    child = AgentSession(id="child-session", project_id="proj-1", user_id="user-1")
    foreign_step = SimpleNamespace(id="child-session:pi-loop-1", session_id="other-session")

    class _NoRunningPlan:
        def scalar_one_or_none(self):
            return None

    class _Db:
        async def execute(self, _query):
            return _NoRunningPlan()

        async def get(self, model, obj_id):
            if model is AgentSession:
                return child
            return foreign_step

    class _SessionCtx:
        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.services.pi_agent_service.async_session", lambda: _SessionCtx())

    with pytest.raises(RuntimeError, match="Agent step id collision"):
        await agent._record_child_event(
            "child-session",
            "step_start",
            {"step_id": "child-session:pi-loop-1", "step_type": "memory_search", "step": 1},
        )


@pytest.mark.asyncio
async def test_record_child_event_completes_running_plan_step(monkeypatch):
    agent = MuseGraphPiAgent()
    child = AgentSession(id="child-session", project_id="proj-1", user_id="user-1", status="running")
    plan_step = AgentStep(
        id="child-session:step:0:plan",
        session_id="child-session",
        step_type="plan",
        status="running",
        message="Pi agent tool loop planning...",
    )
    steps = {plan_step.id: plan_step}

    class _RunningPlan:
        def scalar_one_or_none(self):
            return plan_step

    class _Db:
        async def execute(self, _query):
            return _RunningPlan()

        async def get(self, model, obj_id):
            if model is AgentSession:
                return child
            if model is AgentStep:
                return steps.get(obj_id)
            return None

        def add(self, obj):
            if isinstance(obj, AgentStep):
                steps[obj.id] = obj

        async def commit(self):
            return None

    class _SessionCtx:
        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.services.pi_agent_service.async_session", lambda: _SessionCtx())

    await agent._record_child_event(
        "child-session",
        "step_start",
        {
            "step_id": "child-session:pi-loop-1",
            "step_type": "set_session_title",
            "step": 1,
            "message": "正在为当前会话生成标题",
        },
    )

    assert plan_step.status == "completed"
    assert plan_step.message == "Agent plan selected next action"
    assert steps["child-session:pi-loop-1"].status == "running"


@pytest.mark.asyncio
async def test_pi_context_snapshot_includes_document_units_and_cognee(monkeypatch):
    agent = MuseGraphPiAgent()
    project = SimpleNamespace(
        id="proj-1",
        title="SmokeHarbor",
        description="Transit writing project",
        memory_id="memory-1",
        ontology_schema={"text_type": "business"},
        creative_state={"agent_workspace": {"structured_memory": {"stakeholders": ["Lena"]}}},
        chapters=[
            SimpleNamespace(
                id="unit-1",
                title="Transit Brief",
                content="Lena coordinates late ferry routing. Malik tracks hospital shift gaps.",
                order_index=0,
                status="draft",
            )
        ],
    )

    async def _memory_rag_query(project_id, query, **kwargs):
        return {
            "entities": [
                {
                    "id": "mem-1",
                    "label": "SmokeHarbor memory",
                    "type": "l3_summary",
                    "content": "Lena owns ferry incident routing; Malik owns hospital shift logistics.",
                    "score": 0.92,
                }
            ],
            "relationships": [
                {"source": "mem-1", "target": "agent:memory-1:Lena", "label": "mentions"},
            ],
            "context_text": "Lena owns ferry incident routing",
        }

    monkeypatch.setattr("app.services.pi_agent_service.memory_rag_query", _memory_rag_query)

    snapshot = await agent.build_project_context_snapshot(
        project=project,
        project_id="proj-1",
        instruction="Give next writing suggestions for Lena and Malik",
        db=object(),
    )

    assert "Project Context Snapshot" in snapshot
    assert "Document units" in snapshot
    assert "document_unit id=unit-1" in snapshot
    assert "cognee RAG nodes" in snapshot
    assert "Lena owns ferry incident routing" in snapshot
    assert "mem-1 -[mentions]-> agent:memory-1:Lena" in snapshot


@pytest.mark.asyncio
async def test_pi_context_snapshot_survives_memory_failure_and_notes_missing_memory(monkeypatch):
    agent = MuseGraphPiAgent()
    project = SimpleNamespace(
        id="proj-1",
        title="Project",
        description="",
        memory_id="memory-1",
        ontology_schema={},
        creative_state={},
        chapters=[],
    )

    async def _failing_rag(project_id, query, **kwargs):
        raise RuntimeError("vector store offline")

    monkeypatch.setattr("app.services.pi_agent_service.memory_rag_query", _failing_rag)

    snapshot = await agent.build_project_context_snapshot(
        project=project,
        project_id="proj-1",
        instruction="analyze",
        db=object(),
    )
    assert "Project Context Snapshot" in snapshot

    project_no_memory = SimpleNamespace(
        id="proj-2",
        title="Fresh",
        description="",
        memory_id=None,
        ontology_schema={},
        creative_state={},
        chapters=[],
    )
    snapshot = await agent.build_project_context_snapshot(
        project=project_no_memory,
        project_id="proj-2",
        instruction="analyze",
        db=object(),
    )
    assert "项目记忆尚未构建" in snapshot


@pytest.mark.asyncio
async def test_pi_generate_document_unit_streams_and_writes_chapter(monkeypatch):
    agent = MuseGraphPiAgent()
    project = SimpleNamespace(
        id="proj-1",
        title="星海",
        description="奇幻长篇",
        memory_id=None,
        creative_state={},
        chapters=[
            SimpleNamespace(id="unit-1", title="第一章", content="前文内容。", order_index=0),
        ],
        component_models={},
    )
    events: list[dict] = []

    async def _emit(data):
        events.append(data)

    ctx = PiAgentContext(
        project_id="proj-1",
        user_id="user-1",
        model="mimo-v2.5",
        session_id="sess-1",
        parent_operation_id="op-1",
        current_step_id="sess-1:pi-loop-2",
        project=project,
        emit_progress=_emit,
        available_chat_models=["mimo-v2.5"],
    )

    async def _call_llm(model, prompt, db, **kwargs):
        cb = kwargs.get("stream_callback")
        if cb is not None:
            await cb("新章节正文" * 30)
        assert kwargs.get("max_tokens", 0) >= 8192
        assert "写作指令" in prompt
        assert "前文内容" in prompt
        return {"content": "新章节正文" * 30, "input_tokens": 100, "output_tokens": 500, "cost": 0}

    captured_write: dict = {}

    async def _write_chapter_content(**kwargs):
        captured_write.update(kwargs)
        return {"ok": True, "chapter_id": "unit-2", "title": kwargs.get("title"), "mode": kwargs.get("mode")}

    monkeypatch.setattr("app.services.pi_agent_service.call_llm", _call_llm)
    monkeypatch.setattr("app.services.pi_agent_service.write_chapter_content", _write_chapter_content)

    result = await agent.execute_tool(
        "generate_document_unit",
        {"instruction": "写第二章，800字", "title": "第二章", "mode": "create"},
        ctx,
        SimpleNamespace(flush=AsyncMock()),
    )

    assert result["ok"] is True
    assert result["document_unit_id"] == "unit-2"
    assert result["content_chars"] == len("新章节正文" * 30)
    assert "content" not in result  # full prose must not flow back into the loop context
    assert captured_write["content"] == "新章节正文" * 30
    assert ctx.workspace_dirty is True
    deltas = [e for e in events if e.get("event") == "generation_delta"]
    assert deltas and deltas[0]["step_id"] == "sess-1:pi-loop-2"
