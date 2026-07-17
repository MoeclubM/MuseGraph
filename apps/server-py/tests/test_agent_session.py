"""Unit tests for agent session merge / refresh helpers."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from datetime import datetime, timezone

from app.models.project import AgentSession
from app.routers import agent as agent_router


def test_agent_router_imports_sqlalchemy_select_for_persisted_session_queries():
    assert callable(agent_router.select)


@pytest.mark.asyncio
async def test_get_session_keeps_running_memory_session(monkeypatch: pytest.MonkeyPatch):
    session_id = "sess-1"
    project_id = "proj-1"
    memory_session = {
        "session_id": session_id,
        "project_id": project_id,
        "status": "running",
        "updated_at": "2026-01-01T00:00:00Z",
        "messages": [],
        "steps": [],
    }
    persisted_session = {
        "session_id": session_id,
        "project_id": project_id,
        "status": "completed",
        "updated_at": "2026-01-01T00:05:00Z",
        "messages": [{"role": "assistant", "content": "done"}],
        "steps": [{"step_type": "generate", "status": "running"}],
    }

    agent_router._agent_sessions[session_id] = memory_session

    async def _fake_load(_project_id: str, _session_id: str):
        return persisted_session

    monkeypatch.setattr(agent_router, "_load_persisted_session", _fake_load)
    result = await agent_router._get_session(session_id, project_id, prefer_persisted=True)

    assert result is memory_session
    assert result["messages"] == []
    agent_router._agent_sessions.pop(session_id, None)


@pytest.mark.asyncio
async def test_get_session_loads_database_history_for_completed_memory_session(monkeypatch: pytest.MonkeyPatch):
    session_id = "sess-2"
    project_id = "proj-1"
    agent_router._agent_sessions[session_id] = {
        "session_id": session_id,
        "project_id": project_id,
        "status": "completed",
        "updated_at": "2026-01-01T00:00:00Z",
        "messages": [],
        "steps": [],
    }
    persisted_session = {
        "session_id": session_id,
        "project_id": project_id,
        "status": "completed",
        "updated_at": "2026-01-01T00:05:00Z",
        "messages": [{"role": "assistant", "content": "done"}],
        "steps": [{"step_type": "generate", "status": "completed"}],
    }

    async def _fake_load(_project_id: str, _session_id: str):
        return persisted_session

    monkeypatch.setattr(agent_router, "_load_persisted_session", _fake_load)
    result = await agent_router._get_session(session_id, project_id, prefer_persisted=True)

    assert result is persisted_session
    assert result["messages"][0]["content"] == "done"
    agent_router._agent_sessions.pop(session_id, None)


@pytest.mark.asyncio
async def test_get_session_rejects_running_session_from_another_user():
    session_id = "sess-user-a"
    agent_router._agent_sessions[session_id] = {
        "session_id": session_id,
        "project_id": "proj-1",
        "user_id": "user-a",
        "status": "running",
        "messages": [],
        "steps": [],
    }

    with pytest.raises(HTTPException) as exc:
        await agent_router._get_session(session_id, "proj-1", user_id="user-b")

    assert exc.value.status_code == 403
    agent_router._agent_sessions.pop(session_id, None)


def test_step_complete_without_running_step_is_persisted_as_completed_step():
    session = {
        "session_id": "sess-context",
        "project_id": "proj-1",
        "status": "running",
        "messages": [],
        "steps": [],
        "agent_workspace": {},
        "updated_at": "2026-01-01T00:00:00Z",
    }

    agent_router._sync_session_from_event(
        session,
        "step_complete",
        {
            "step": 0,
            "total_steps": 8,
            "step_type": "context_snapshot",
            "status": "completed",
            "message": "Loaded document units and Cognee context before Pi planning",
            "output": "Project Context Snapshot",
        },
    )

    assert session["steps"] == [
        {
            "step": 0,
            "total_steps": 8,
            "step_type": "context_snapshot",
            "status": "completed",
            "message": "Loaded document units and Cognee context before Pi planning",
            "output_preview": "",
            "output": "Project Context Snapshot",
            "created_at": session["steps"][0]["created_at"],
        }
    ]


def test_session_record_to_dict_includes_session_and_child_titles():
    record = AgentSession(
        id="sess-title",
        project_id="proj-1",
        user_id="user-1",
        role="orchestrator",
        status="completed",
        title="圣塔创作",
        workspace={"title_source": "agent_tool"},
    )
    child = AgentSession(
        id="child-title",
        project_id="proj-1",
        user_id="user-1",
        role="planner",
        parent_session_id="sess-title",
        status="completed",
        title="规划子代理",
        workspace={"title_source": "agent_tool"},
    )
    record.children = [child]

    payload = agent_router._session_record_to_dict(record)

    assert payload["title"] == "圣塔创作"
    assert payload["children"][0]["title"] == "规划子代理"


def test_session_record_to_dict_hides_non_tool_titles():
    record = AgentSession(
        id="sess-raw-title",
        project_id="proj-1",
        user_id="user-1",
        role="planner",
        status="failed",
        title="raw task copied from old spawn_subagent",
        workspace={"task": "raw task copied from old spawn_subagent"},
    )

    payload = agent_router._session_record_to_dict(record)

    assert payload["title"] is None


def test_session_record_to_dict_includes_archive_timestamp():
    archived_at = datetime(2026, 6, 9, 8, 0, tzinfo=timezone.utc)
    record = AgentSession(
        id="sess-archived",
        project_id="proj-1",
        user_id="user-1",
        role="orchestrator",
        status="completed",
        archived_at=archived_at,
    )

    payload = agent_router._session_record_to_dict(record)

    assert payload["archived_at"] == archived_at.isoformat()


def test_session_update_event_sets_persisted_title_source():
    session = {
        "session_id": "sess-update",
        "project_id": "proj-1",
        "status": "running",
        "messages": [],
        "steps": [],
        "agent_workspace": {},
        "title": None,
        "updated_at": "2026-01-01T00:00:00Z",
    }

    agent_router._sync_session_from_event(
        session,
        "session_update",
        {"session_id": "sess-update", "title": "圣塔规划"},
    )

    assert session["title"] == "圣塔规划"
    assert session["agent_workspace"]["title_source"] == "agent_tool"


def test_non_plan_step_start_completes_running_plan_step():
    session = {
        "session_id": "sess-plan",
        "project_id": "proj-1",
        "status": "running",
        "messages": [],
        "steps": [],
        "agent_workspace": {},
        "updated_at": "2026-01-01T00:00:00Z",
    }

    agent_router._sync_session_from_event(
        session,
        "step_start",
        {
            "step": 0,
            "total_steps": 8,
            "step_type": "plan",
            "status": "running",
            "message": "Pi agent tool loop planning...",
        },
    )
    agent_router._sync_session_from_event(
        session,
        "step_start",
        {
            "step": 1,
            "total_steps": 8,
            "step_type": "store_structured_memory",
            "status": "running",
            "message": "Write memory",
        },
    )

    assert session["steps"][0]["step_type"] == "plan"
    assert session["steps"][0]["status"] == "completed"
    assert session["steps"][0]["message"] == "Agent plan selected next action"
    assert session["steps"][1]["step_type"] == "store_structured_memory"
    assert session["steps"][1]["status"] == "running"


def test_spawn_subagent_step_preserves_child_metadata():
    session = {
        "session_id": "sess-parent",
        "project_id": "proj-1",
        "status": "running",
        "messages": [],
        "steps": [],
        "agent_workspace": {},
        "updated_at": "2026-01-01T00:00:00Z",
    }

    agent_router._sync_session_from_event(
        session,
        "step_start",
        {
            "step": 1,
            "total_steps": 3,
            "step_id": "step-spawn",
            "step_type": "spawn_subagent",
            "status": "running",
            "message": "delegate draft",
            "child_session_id": "child-1",
            "agent_role": "writer",
            "model": "model-writer",
            "tool_args": {"task": "draft", "subagent_role": "writer", "model": "model-writer"},
        },
    )
    agent_router._sync_session_from_event(
        session,
        "step_complete",
        {
            "step": 1,
            "total_steps": 3,
            "step_id": "step-spawn",
            "step_type": "spawn_subagent",
            "status": "completed",
            "message": "done",
            "child_session_id": "child-1",
            "agent_role": "writer",
            "model": "model-writer",
            "tool_result_preview": '{"ok":true}',
        },
    )

    assert session["steps"][0]["child_session_id"] == "child-1"
    assert session["steps"][0]["agent_role"] == "writer"
    assert session["steps"][0]["model"] == "model-writer"
    assert session["steps"][0]["tool_args"]["task"] == "draft"
    assert session["steps"][0]["tool_result_preview"] == '{"ok":true}'
