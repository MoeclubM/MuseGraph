import inspect
import json
from types import SimpleNamespace
from typing import get_args

import pytest
from pydantic import ValidationError

from app.schemas.agent_configuration import ProjectAgentUpdate, PromptTemplateUpdate
from app.schemas.runtime import (
    AgentFinish,
    AgentRunRequest,
    AgentToolName,
    ChangeSet,
    ConstraintRecord,
    CreationPlan,
    CreationPlanStep,
    CreativeBlueprint,
    EntityRecord,
    FactRecord,
    KnowledgeUpsert,
    RelationRecord,
    SourceRef,
)
from app.services.agent.pack_core import list_packs, load_pack
from app.services.agent.skill_catalog import ALL_AGENT_TOOLS, BUILTIN_SKILL_MAP
from app.services.agent.skills import (
    ROLE_NAMES,
    validate_pack_skill_references,
    validate_skill_definition,
)
from app.services.agent.tool_registry import TOOL_REGISTRY
from app.services.agent_engine import (
    AgentAction,
    _agent_action_schema,
    _creation_plan_schema,
    _validate_changes,
)
from app.services.agent_workspace import apply_knowledge_operations
from app.services import ai, memory_client, memory_config


def test_tool_registry_schema_handler_and_role_contracts_are_complete():
    assert set(TOOL_REGISTRY) == ALL_AGENT_TOOLS
    assert set(get_args(AgentToolName)) == set(TOOL_REGISTRY)
    assert {"web_search", "fetch_url"}.isdisjoint(TOOL_REGISTRY)
    for name, definition in TOOL_REGISTRY.items():
        assert definition.name == name
        assert inspect.iscoroutinefunction(definition.handler)
        assert definition.roles
        assert definition.roles <= ROLE_NAMES
        schema = definition.json_schema()
        assert schema["name"] == name
        assert schema["parameters"]["additionalProperties"] is False
    assert TOOL_REGISTRY["write_file"].roles == {"writer", "reviser"}
    assert TOOL_REGISTRY["knowledge_upsert"].roles == {
        "updater",
        "memory_builder",
        "graph_extractor",
    }


def test_all_text_packs_have_strict_complete_creation_metadata():
    validate_pack_skill_references()
    descriptors = list_packs()
    assert {item["text_type"] for item in descriptors} == {
        "generic",
        "novel",
        "article",
        "paper",
        "screenplay",
        "product_doc",
    }
    for descriptor in descriptors:
        pack = load_pack(descriptor["text_type"])
        assert set(pack.control_docs) == {"intent", "focus", "rules", "bible"}
        assert pack.auditor_dimensions
        assert pack.knowledge_types
        assert pack.unit["name"]
        assert set(pack.default_skills.values()) <= set(BUILTIN_SKILL_MAP)


def test_custom_skill_cannot_override_builtin_or_expand_registry():
    with pytest.raises(ValueError, match="cannot override"):
        validate_skill_definition(
            slug="general",
            scopes=["write"],
            roles=["writer"],
            allowed_tools=["write_file"],
            default_model_component=None,
            params_schema={"type": "object"},
        )
    with pytest.raises(ValueError, match="Unknown or disallowed tools"):
        validate_skill_definition(
            slug="unsafe",
            scopes=["write"],
            roles=["writer"],
            allowed_tools=["shell"],
            default_model_component=None,
            params_schema={"type": "object"},
        )


def test_public_runtime_models_reject_unknown_fields():
    with pytest.raises(ValidationError):
        AgentRunRequest(
            instruction="Analyze the project",
            mode="analyze",
            unexpected=True,
        )
    with pytest.raises(ValidationError):
        CreationPlan(
            objective="Write",
            steps=[
                CreationPlanStep(
                    goal="Draft",
                    role="writer",
                    tool="write_file",
                    plan_unit_ids=["outline"],
                    target_refs=["chapter.md"],
                    output_ref="chapter.md",
                )
            ],
            legacy_finish=True,
        )
    with pytest.raises(ValidationError):
        AgentAction.model_validate(
            {
                "action": "tool_call",
                "role": "writer",
                "tool": "write_file",
                "arguments": {"path": "chapter.md", "content": "text"},
            }
        )
    with pytest.raises(ValidationError):
        AgentAction.model_validate(
            {
                "action": "tool_call",
                "role": "writer",
                "tool": "write_file1",
                "arguments": {},
            }
        )
    action = AgentAction.model_validate(
        {
            "action": "write_file",
            "reason": "Draft the chapter",
            "arguments": {"path": "chapter.md", "content": "text"},
        }
    )
    assert action.root.action == "write_file"
    finish = AgentAction.model_validate(
        {
            "action": "finish",
            "summary": "Done",
            "changed_files": ["chapter.md"],
            "knowledge_operations": 0,
            "used_knowledge_ids": ["character-liu-ruyan"],
            "unresolved_issues": [],
        }
    )
    assert finish.root.summary == "Done"
    schema = AgentAction.model_json_schema()
    assert schema["discriminator"]["propertyName"] == "action"
    writer_schema = json.dumps(
        _agent_action_schema({"list_files", "read_file", "write_file"}).model_json_schema()
    )
    assert '"write_file"' in writer_schema
    assert '"knowledge_upsert"' not in writer_schema
    assert '"role"' not in writer_schema
    with pytest.raises(ValidationError):
        _agent_action_schema(
            {"write_file"},
            include_finish=False,
        ).model_validate(
            {
                "action": "finish",
                "output": {
                    "summary": "Skipped",
                    "changed_files": [],
                    "knowledge_operations": 0,
                    "used_knowledge_ids": [],
                    "unresolved_issues": [],
                },
            }
        )


def test_planner_schema_only_accepts_resolved_tools_and_engine_owned_roles():
    schema = _creation_plan_schema({"writer"}, {"write_file"})
    plan = schema.model_validate(
        {
            "objective": "Write the outline",
            "steps": [
                {
                    "goal": "Draft",
                    "tool": "write_file",
                    "plan_unit_ids": ["outline"],
                    "target_refs": ["outline.md"],
                    "output_ref": "outline.md",
                }
            ],
            "required_knowledge_ids": [],
        }
    )
    assert plan.steps[0].tool == "write_file"
    with pytest.raises(ValidationError):
        schema.model_validate(
            {
                "objective": "Expand memory",
                "steps": [
                    {
                        "goal": "Store knowledge",
                        "tool": "knowledge_upsert",
                        "plan_unit_ids": ["memory"],
                        "target_refs": [],
                        "output_ref": None,
                    }
                ],
                "required_knowledge_ids": [],
            }
        )
    with pytest.raises(ValidationError, match="output_ref"):
        schema.model_validate(
            {
                "objective": "Write the outline",
                "steps": [
                    {
                        "goal": "Draft",
                        "tool": "write_file",
                        "plan_unit_ids": ["outline"],
                        "target_refs": [],
                        "output_ref": None,
                    }
                ],
                "required_knowledge_ids": [],
            }
        )
    role_tool_schema = _creation_plan_schema(
        {"writer", "memory_builder"},
        {"write_file", "knowledge_upsert"},
    )
    with pytest.raises(ValidationError):
        role_tool_schema.model_validate(
            {
                "objective": "Invalid role/tool pairing",
                "steps": [
                    {
                        "goal": "Store knowledge",
                        "role": "writer",
                        "tool": "knowledge_upsert",
                        "plan_unit_ids": ["knowledge"],
                        "target_refs": [],
                        "output_ref": None,
                    }
                ],
                "required_knowledge_ids": [],
            }
        )


def test_knowledge_union_requires_sources_and_relation_integrity():
    source = SourceRef(kind="file", ref="bible.md")
    hero = EntityRecord(
        id="entity:hero",
        kind="entity",
        title="Hero",
        content="The protagonist",
        entity_type="character",
        source_refs=[source],
    )
    city = EntityRecord(
        id="entity:city",
        kind="entity",
        title="City",
        content="Primary setting",
        entity_type="place",
        source_refs=[source],
    )
    relation = RelationRecord(
        id="relation:hero-city",
        kind="relation",
        title="Hero lives in city",
        content="The hero lives in the city",
        source_id=hero.id,
        target_id=city.id,
        predicate="lives_in",
        source_refs=[source],
    )
    records = apply_knowledge_operations(
        [],
        [
            KnowledgeUpsert(record=hero),
            KnowledgeUpsert(record=city),
            KnowledgeUpsert(record=relation),
        ],
        "revision-1",
    )
    assert [record["id"] for record in records] == [
        "entity:city",
        "entity:hero",
        "relation:hero-city",
    ]
    with pytest.raises(ValueError, match="Relation source does not exist"):
        apply_knowledge_operations(
            [],
            [KnowledgeUpsert(record=relation)],
            "revision-1",
        )
    with pytest.raises(ValidationError):
        FactRecord(
            id="fact:missing-source",
            kind="fact",
            title="No source",
            content="Invalid",
            source_refs=[],
        )


def test_finish_must_prove_planned_knowledge_and_required_constraints_were_used():
    finish = AgentFinish(
        summary="Drafted",
        changed_files=["chapter.md"],
        knowledge_operations=0,
        used_knowledge_ids=["fact:weather"],
        used_plan_unit_ids=["chapter-1"],
    )
    validation = _validate_changes(
        SimpleNamespace(mode="write"),
        finish,
        ChangeSet(
            files=[
                {
                    "path": "chapter.md",
                    "change_type": "modified",
                    "before_hash": "before",
                    "after_hash": "after",
                    "diff": "changed",
                }
            ]
        ),
        {"fact:weather", "constraint:voice"},
        {"constraint:voice"},
        {"fact:weather"},
        {"chapter-1"},
    )
    assert validation.passed is False
    failed = {check["name"] for check in validation.checks if not check["passed"]}
    assert failed == {"required_constraints_used"}


def test_creative_blueprint_requires_resolvable_dependencies_and_threads():
    blueprint = CreativeBlueprint.model_validate(
        {
            "objective": "Write two connected chapters",
            "scope": "Opening arc",
            "strategy": "Set up and reverse the conflict",
            "units": [
                {
                    "id": "chapter_1",
                    "title": "Setup",
                    "purpose": "Introduce the conflict",
                    "summary": "The protagonist discovers the problem.",
                    "target_ref": "chapters/01.md",
                    "depends_on_ids": [],
                    "knowledge_ids": ["entity:hero"],
                    "acceptance_criteria": ["Conflict is explicit"],
                },
                {
                    "id": "chapter_2",
                    "title": "Reversal",
                    "purpose": "Escalate the conflict",
                    "summary": "The first solution creates a larger problem.",
                    "target_ref": "chapters/02.md",
                    "depends_on_ids": ["chapter_1"],
                    "knowledge_ids": ["entity:hero"],
                    "acceptance_criteria": ["Uses the result of chapter 1"],
                },
            ],
            "threads": [
                {
                    "id": "main_arc",
                    "kind": "character_arc",
                    "description": "The hero becomes proactive.",
                    "introduced_in": ["chapter_1"],
                    "developed_in": ["chapter_2"],
                    "resolved_in": [],
                }
            ],
            "global_constraints": ["Keep point of view consistent"],
            "required_knowledge_ids": ["entity:hero"],
        }
    )
    assert blueprint.units[1].depends_on_ids == ["chapter_1"]
    with pytest.raises(ValidationError, match="unknown dependencies"):
        CreativeBlueprint.model_validate(
            {
                **blueprint.model_dump(),
                "units": [
                    {
                        **blueprint.units[0].model_dump(),
                        "depends_on_ids": ["missing"],
                    }
                ],
                "threads": [],
            }
        )
    with pytest.raises(ValidationError, match="thread IDs must be unique"):
        CreativeBlueprint.model_validate(
            {
                **blueprint.model_dump(),
                "threads": [
                    blueprint.threads[0].model_dump(),
                    blueprint.threads[0].model_dump(),
                ],
            }
        )


def test_configuration_updates_reject_null_database_fields():
    with pytest.raises(ValidationError, match="Prompt template field cannot be null"):
        PromptTemplateUpdate(name=None)
    with pytest.raises(ValidationError, match="Project Agent field cannot be null"):
        ProjectAgentUpdate(enabled=None)
    assert ProjectAgentUpdate(model=None).model_dump(exclude_unset=True) == {"model": None}


@pytest.mark.asyncio
async def test_cognee_uses_native_openai_compatible_embedding_engine(monkeypatch):
    providers = {
        False: SimpleNamespace(
            provider="openai_compatible",
            base_url="https://provider.example/v1",
            api_key="encrypted-chat-key",
        ),
        True: SimpleNamespace(
            provider="openai_compatible",
            base_url="https://provider.example/v1",
            api_key="encrypted-embedding-key",
        ),
    }
    captured: dict[str, object] = {}

    async def provider_for_model(_db, _model, *, embedding):
        return providers[embedding]

    async def start_instance(project_id, *, llm, embedding):
        captured.update(project_id=project_id, llm=llm, embedding=embedding)

    monkeypatch.setattr(memory_config, "_provider_for_model", provider_for_model)
    monkeypatch.setattr(memory_config, "start_project_memory_instance", start_instance)
    monkeypatch.setattr(memory_config, "decrypt_secret", lambda value: f"plain:{value}")

    await memory_config.ensure_project_memory_instance(
        SimpleNamespace(
            id="project-1",
            component_models={
                "memory_llm": "deepseek-v4-flash",
                "memory_embedding": "Qwen3-Embedding-0.6B",
                "memory_embedding_dimensions": "1024",
            },
        ),
        SimpleNamespace(),
        require_models=True,
    )

    assert captured["llm"] == {
        "llm_provider": "openai",
        "llm_model": "openai/deepseek-v4-flash",
        "llm_endpoint": "https://provider.example/v1",
        "llm_api_key": "plain:encrypted-chat-key",
        "llm_max_completion_tokens": memory_config.settings.COGNEE_LLM_MAX_TOKENS,
        "llm_args": {
            "extra_body": {"thinking": {"type": "disabled"}},
        },
    }
    assert captured["embedding"] == {
        "embedding_provider": "openai_compatible",
        "embedding_model": "Qwen3-Embedding-0.6B",
        "embedding_endpoint": "https://provider.example/v1",
        "embedding_api_key": "plain:encrypted-embedding-key",
        "embedding_dimensions": 1024,
    }


@pytest.mark.asyncio
async def test_cognee_model_resolution_uses_highest_priority_chat_provider():
    anthropic = SimpleNamespace(
        provider="anthropic_compatible",
        models=["deepseek-v4-flash"],
    )
    openai = SimpleNamespace(
        provider="openai_compatible",
        models=["deepseek-v4-flash"],
    )

    class Result:
        def scalars(self):
            return [anthropic, openai]

    class Database:
        async def execute(self, _statement):
            return Result()

    assert (
        await memory_config._provider_for_model(
            Database(),
            "deepseek-v4-flash",
            embedding=False,
        )
        is anthropic
    )


@pytest.mark.asyncio
async def test_cognee_routes_anthropic_compatible_llm_through_custom_endpoint(monkeypatch):
    providers = {
        False: SimpleNamespace(
            provider="anthropic_compatible",
            base_url="https://provider.example/v1",
            api_key="encrypted-chat-key",
        ),
        True: SimpleNamespace(
            provider="openai_compatible",
            base_url="https://provider.example/v1",
            api_key="encrypted-embedding-key",
        ),
    }
    captured: dict[str, object] = {}

    async def provider_for_model(_db, _model, *, embedding):
        return providers[embedding]

    async def start_instance(project_id, *, llm, embedding):
        captured.update(project_id=project_id, llm=llm, embedding=embedding)

    monkeypatch.setattr(memory_config, "_provider_for_model", provider_for_model)
    monkeypatch.setattr(memory_config, "start_project_memory_instance", start_instance)
    monkeypatch.setattr(memory_config, "decrypt_secret", lambda value: f"plain:{value}")

    await memory_config.ensure_project_memory_instance(
        SimpleNamespace(
            id="project-1",
            component_models={
                "memory_llm": "deepseek-v4-flash",
                "memory_embedding": "Qwen3-Embedding-0.6B",
                "memory_embedding_dimensions": "1024",
            },
        ),
        SimpleNamespace(),
        require_models=True,
    )

    assert captured["llm"] == {
        "llm_provider": "custom",
        "llm_model": "anthropic/deepseek-v4-flash",
        "llm_endpoint": "https://provider.example",
        "llm_api_key": "plain:encrypted-chat-key",
        "llm_max_completion_tokens": memory_config.settings.COGNEE_LLM_MAX_TOKENS,
        "llm_args": {
            "thinking": {"type": "disabled"},
            "allowed_openai_params": ["thinking"],
        },
    }


@pytest.mark.asyncio
async def test_reranker_orders_traceable_knowledge_records(monkeypatch):
    provider = SimpleNamespace(
        provider="openai_compatible",
        base_url="https://provider.example/v1/",
        api_key="encrypted-reranker-key",
        models={
            "models": [],
            "embedding_models": [],
            "reranker_models": ["Qwen3-Reranker-0.6B"],
        },
    )

    class ProviderResult:
        def scalars(self):
            return [provider]

    class Database:
        async def execute(self, _statement):
            return ProviderResult()

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.4},
                ]
            }

    request: dict[str, object] = {}

    class Client:
        def __init__(self, *, timeout):
            request["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def post(self, url, *, headers, json):
            request.update(url=url, headers=headers, json=json)
            return Response()

    async def runtime_config(_db):
        return {"llm_request_timeout_seconds": 45}

    monkeypatch.setattr(ai, "_runtime_config", runtime_config)
    monkeypatch.setattr(ai.httpx, "AsyncClient", Client)
    monkeypatch.setattr(ai, "decrypt_secret", lambda _value: "private-key")

    records = [
        {"id": "fact:first", "title": "First", "content": "Less relevant"},
        {"id": "fact:second", "title": "Second", "content": "Most relevant"},
    ]
    ranked = await ai.rerank_knowledge_records(
        "Qwen3-Reranker-0.6B",
        "Find the most relevant fact",
        records,
        Database(),
    )

    assert [record["id"] for record, _score in ranked] == [
        "fact:second",
        "fact:first",
    ]
    assert request["url"] == "https://provider.example/v1/rerank"
    assert request["json"] == {
        "model": "Qwen3-Reranker-0.6B",
        "query": "Find the most relevant fact",
        "documents": [
            "fact:first\nFirst\nLess relevant",
            "fact:second\nSecond\nMost relevant",
        ],
        "top_n": 2,
    }


@pytest.mark.asyncio
async def test_openai_compatible_model_receives_explicit_reasoning_effort(monkeypatch):
    provider = SimpleNamespace(
        name="Protected provider",
        provider="openai_compatible",
        base_url="https://provider.example/v1",
        api_key="encrypted-chat-key",
        models=["deepseek-v4-flash"],
    )

    class ProviderResult:
        def scalars(self):
            return [provider]

    class EmptyResult:
        def scalar_one_or_none(self):
            return None

    class Database:
        def __init__(self):
            self.results = iter([ProviderResult(), EmptyResult(), EmptyResult()])

        async def execute(self, _statement):
            return next(self.results)

    request: dict[str, object] = {}

    async def completion(**kwargs):
        request.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))],
            usage={},
        )

    monkeypatch.setattr(ai.litellm, "acompletion", completion)
    monkeypatch.setattr(ai, "decrypt_secret", lambda _value: "private-key")

    response = await ai.call_llm(
        "deepseek-v4-flash",
        "Reply with OK.",
        Database(),
        reasoning_effort_override="low",
    )

    assert response["content"] == "OK"
    assert request["reasoning_effort"] == "low"
    assert request["allowed_openai_params"] == ["reasoning_effort"]
    assert request["extra_headers"] == {"User-Agent": "MuseGraph/1.0"}
    assert isinstance(request["client"], ai.AsyncOpenAI)


@pytest.mark.asyncio
async def test_anthropic_compatible_base_url_does_not_duplicate_v1(monkeypatch):
    provider = SimpleNamespace(
        name="Agent provider",
        provider="anthropic_compatible",
        base_url="https://provider.example/v1",
        api_key="encrypted-chat-key",
        models=["deepseek-v4-flash"],
    )

    class ProviderResult:
        def scalars(self):
            return [provider]

    class EmptyResult:
        def scalar_one_or_none(self):
            return None

    class Database:
        def __init__(self):
            self.results = iter([ProviderResult(), EmptyResult(), EmptyResult()])

        async def execute(self, _statement):
            return next(self.results)

    request: dict[str, object] = {}

    async def completion(**kwargs):
        request.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))],
            usage={},
        )

    monkeypatch.setattr(ai.litellm, "acompletion", completion)
    monkeypatch.setattr(ai, "decrypt_secret", lambda _value: "private-key")

    response = await ai.call_llm(
        "deepseek-v4-flash",
        "Reply with OK.",
        Database(),
    )

    assert response["content"] == "OK"
    assert request["api_base"] == "https://provider.example"
    assert request["custom_llm_provider"] == "anthropic"
    assert request["thinking"] == {"type": "disabled"}
    assert request["allowed_openai_params"] == ["thinking"]
    assert "client" not in request


@pytest.mark.asyncio
async def test_anthropic_structured_output_uses_json_prefill(monkeypatch):
    provider = SimpleNamespace(
        name="Agent provider",
        provider="anthropic_compatible",
        base_url="https://provider.example/v1",
        api_key="encrypted-chat-key",
        models=["deepseek-v4-flash"],
    )

    class ProviderResult:
        def scalars(self):
            return [provider]

    class EmptyResult:
        def scalar_one_or_none(self):
            return None

    class Database:
        def __init__(self):
            self.results = iter([ProviderResult(), EmptyResult(), EmptyResult()])

        async def execute(self, _statement):
            return next(self.results)

    request: dict[str, object] = {}
    arguments = AgentFinish(
        summary="done",
        changed_files=["chapters/01.md"],
        used_knowledge_ids=["character-liu-ruyan"],
    ).model_dump_json()

    async def completion(**kwargs):
        request.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=arguments,
                    )
                )
            ],
            usage={},
        )

    monkeypatch.setattr(ai.litellm, "acompletion", completion)
    monkeypatch.setattr(ai, "decrypt_secret", lambda _value: "private-key")

    response = await ai.call_llm(
        "deepseek-v4-flash",
        "Finish the run.",
        Database(),
        response_schema=AgentFinish,
    )

    assert response["content"] == arguments
    assert '"used_knowledge_ids"' in request["messages"][0]["content"]
    assert request["messages"][1] == {"role": "assistant", "content": "{"}
    assert "extra_body" not in request


@pytest.mark.asyncio
async def test_openai_compatible_structured_output_uses_forced_tool(monkeypatch):
    provider = SimpleNamespace(
        name="Agent provider",
        provider="openai_compatible",
        base_url="https://provider.example/v1",
        api_key="encrypted-chat-key",
        models=["deepseek-v4-flash"],
    )

    class ProviderResult:
        def scalars(self):
            return [provider]

    class EmptyResult:
        def scalar_one_or_none(self):
            return None

    class Database:
        def __init__(self):
            self.results = iter([ProviderResult(), EmptyResult(), EmptyResult()])

        async def execute(self, _statement):
            return next(self.results)

    request: dict[str, object] = {}
    arguments = AgentFinish(
        summary="done",
        changed_files=["chapters/01.md"],
        used_knowledge_ids=["character-liu-ruyan"],
    ).model_dump_json()

    async def completion(**kwargs):
        request.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                function=SimpleNamespace(
                                    name="submit_AgentFinish",
                                    arguments=arguments,
                                )
                            )
                        ],
                    )
                )
            ],
            usage={},
        )

    monkeypatch.setattr(ai.litellm, "acompletion", completion)
    monkeypatch.setattr(ai, "decrypt_secret", lambda _value: "private-key")
    monkeypatch.setattr(ai, "AsyncOpenAI", lambda **_kwargs: object())

    response = await ai.call_llm(
        "deepseek-v4-flash",
        "Finish the run.",
        Database(),
        response_schema=AgentFinish,
    )

    assert response["content"] == arguments
    assert request["tools"][0]["function"]["parameters"] == AgentFinish.model_json_schema()
    assert request["tools"][0]["function"]["strict"] is True
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert request["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_AgentFinish"},
    }
    assert "response_format" not in request


@pytest.mark.asyncio
async def test_openai_sdk_telemetry_headers_are_removed_at_provider_boundary():
    request = ai.httpx.Request(
        "POST",
        "https://provider.example/v1/chat/completions",
        headers={
            "User-Agent": "AsyncOpenAI/Python 2.46.0",
            "x-stainless-lang": "python",
            "x-stainless-runtime": "CPython",
            "x-stainless-raw-response": "true",
        },
    )

    await ai._sanitize_openai_sdk_headers(request)

    assert request.headers["User-Agent"] == "MuseGraph/1.0"
    assert "x-stainless-lang" not in request.headers
    assert "x-stainless-runtime" not in request.headers
    assert request.headers["x-stainless-raw-response"] == "true"


@pytest.mark.asyncio
async def test_long_running_memory_operations_have_no_client_side_cap(monkeypatch):
    timeouts: list[object] = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": []}

    class Client:
        def __init__(self, *, base_url, timeout):
            timeouts.append(timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return None

        async def post(self, _path, *, headers, json):
            return Response()

    monkeypatch.setattr(memory_client.httpx, "AsyncClient", Client)
    monkeypatch.setattr(memory_client, "_headers", lambda: {"Authorization": "internal"})

    await memory_client.remember_knowledge_dataset(
        "project-1",
        "dataset-1",
        [{"id": "fact:one"}],
    )
    await memory_client.recall_knowledge(
        "project-1",
        "dataset-1",
        "Find fact one",
    )

    assert timeouts == [None, None]
