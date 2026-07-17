from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.creative_memory import (
    build_creative_memory_pack,
    build_reference_memory,
    get_creative_memory_enhanced_prompt,
    render_creative_memory_block,
)
from app.services.creative_workflow import chapter_memory_hash


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def test_reference_memory_ranks_explicit_cards_and_aliases():
    memory = build_reference_memory(
        {
            "characters": [
                {"id": "c1", "name": "林默", "role": "侦探", "profile": "调查回声井"},
                {"id": "c2", "name": "旁观者", "role": "路人"},
            ],
            "glossary_terms": [
                {"id": "g1", "term": "回声井", "aliases": ["回声点"], "definition": "地下设施"},
            ],
            "worldbook_entries": [],
            "explicit_character_ids": ["c1"],
            "explicit_glossary_term_ids": ["g1"],
        },
        focus_text="林默调查回声点",
    )

    assert memory["characters"][0].startswith("- 林默")
    assert memory["glossary_terms"][0].startswith("- 回声井")
    assert memory["alias_expansions"] == ["回声点 -> 回声井"]


def test_reference_memory_limits_empty_focus_to_seed_cards():
    memory = build_reference_memory(
        {
            "characters": [
                {"id": f"c{i}", "name": f"角色{i}", "role": "配角"}
                for i in range(1, 8)
            ],
            "glossary_terms": [],
            "worldbook_entries": [],
        },
        focus_text="",
    )

    assert len(memory["characters"]) == 4


@pytest.mark.asyncio
async def test_creative_memory_pack_uses_text_type_strategy_without_memory():
    project = SimpleNamespace(
        id="p1",
        title="品牌方案",
        description="新品发布，面向专业用户，强调可信证据。",
        memory_id=None,
        chapters=[],
        ontology_schema={
            "text_type": "marketing",
            "text_type_confidence": 0.92,
            "text_type_reason": "Contains product, audience, and conversion language.",
            "entity_types": [{"name": "PRODUCT"}, {"name": "AUDIENCE"}],
            "edge_types": [{"name": "TARGETS", "source_type": "PRODUCT", "target_type": "AUDIENCE"}],
            "analysis_summary": "Marketing schema",
        },
    )

    memory = await build_creative_memory_pack(
        project=project,
        project_id="p1",
        op_type="REWRITE",
        input_text="重写发布文案，保持可信感。",
        db=AsyncMock(),
        reference_cards=None,
    )
    block = render_creative_memory_block(memory)

    assert memory["text_type"] == "marketing"
    assert "audience, product, pain points" in memory["retrieval_strategy"]["type_focus"]
    assert "Marketing / brand writing" in block
    assert "TARGETS" in block
    assert "Preserve brand voice" in block


@pytest.mark.asyncio
async def test_creative_memory_prompt_rejects_unsupported_operation():
    with pytest.raises(ValueError, match="Unsupported creative memory operation"):
        await get_creative_memory_enhanced_prompt(
            "p1",
            "EXPORT",
            "text",
            "BASE",
            AsyncMock(),
        )


@pytest.mark.asyncio
async def test_creative_memory_prompt_requires_existing_project():
    db = AsyncMock()
    db.execute.return_value = _scalar_one_or_none(None)

    with pytest.raises(RuntimeError, match="Project not found"):
        await get_creative_memory_enhanced_prompt(
            "missing",
            "CONTINUE",
            "text",
            "BASE",
            db,
        )


@pytest.mark.asyncio
async def test_creative_memory_prompt_uses_project_description_without_memory():
    project = SimpleNamespace(
        id="p1",
        title="Story",
        description="must keep tone realistic",
        ontology_schema={},
        memory_id=None,
        chapters=[],
    )
    db = AsyncMock()
    db.execute.return_value = _scalar_one_or_none(project)

    prompt = await get_creative_memory_enhanced_prompt(
        "p1",
        "CREATE",
        "I arrived late to the station.",
        "BASE_PROMPT",
        db,
    )

    assert prompt.startswith("BASE_PROMPT")
    assert "Creative Memory Context" in prompt
    assert "Description: must keep tone realistic" in prompt


@pytest.mark.asyncio
async def test_creative_memory_prompt_uses_reference_cards_without_memory():
    project = SimpleNamespace(
        id="p2",
        title="Story",
        description="desc",
        ontology_schema={"text_type": "fiction"},
        memory_id=None,
        chapters=[],
    )
    db = AsyncMock()
    db.execute.return_value = _scalar_one_or_none(project)

    prompt = await get_creative_memory_enhanced_prompt(
        "p2",
        "CONTINUE",
        "林默调查回声点",
        "BASE_PROMPT",
        db,
        reference_cards={
            "characters": [{"id": "c1", "name": "林默", "role": "侦探"}],
            "glossary_terms": [
                {"id": "g1", "term": "回声井", "aliases": ["回声点"], "definition": "地下设施"}
            ],
            "explicit_character_ids": ["c1"],
            "explicit_glossary_term_ids": ["g1"],
        },
    )

    assert "Structured reference memory" in prompt
    assert "回声井" in prompt
    assert "Retrieval query plan" in prompt


@pytest.mark.asyncio
async def test_creative_memory_pack_exposes_invalid_memory_search_shape(monkeypatch: pytest.MonkeyPatch):
    project = SimpleNamespace(
        id="p3",
        title="Story",
        description="desc",
        ontology_schema={"text_type": "fiction"},
        memory_id="memory-1",
        chapters=[],
    )

    async def _bad_retrieve(*_args, **_kwargs):
        return {
            "submemory": "",
            "typed_insights": {"not": "a list"},
            "relationships": [],
            "source_evidence": [],
            "summaries": [],
            "generation_hints": [],
        }

    monkeypatch.setattr("app.services.memory_backend.retrieve", _bad_retrieve)

    with pytest.raises(TypeError, match="Memory search returned non-list result"):
        await build_creative_memory_pack(
            project=project,
            project_id="p3",
            op_type="CONTINUE",
            input_text="next",
            db=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_creative_memory_pack_requires_fresh_memory_for_persisted_text(monkeypatch: pytest.MonkeyPatch):
    project = SimpleNamespace(
        id="p4",
        title="Story",
        description="desc",
        ontology_schema={"text_type": "fiction"},
        creative_state={
            "memory_build_state": {
                "chapter_hashes": {"chapter-1": "old-hash"},
            }
        },
        memory_id="memory-1",
        chapters=[SimpleNamespace(id="chapter-1", content="new chapter text")],
    )

    async def _unexpected_retrieve(*_args, **_kwargs):
        raise AssertionError("stale memory must fail before retrieval")

    monkeypatch.setattr("app.services.memory_backend.retrieve", _unexpected_retrieve)

    with pytest.raises(RuntimeError, match="Cognee project memory is stale"):
        await build_creative_memory_pack(
            project=project,
            project_id="p4",
            op_type="CONTINUE",
            input_text="next",
            db=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_creative_memory_pack_uses_dynamic_retrieval_when_memory_is_fresh(monkeypatch: pytest.MonkeyPatch):
    chapter_text = "林默在回声井发现铜钥匙。"
    chapter = SimpleNamespace(id="chapter-1", content=chapter_text)
    project = SimpleNamespace(
        id="p5",
        title="Story",
        description="desc",
        ontology_schema={"text_type": "fiction"},
        creative_state={
            "memory_build_state": {
                "chapter_hashes": {
                    "chapter-1": chapter_memory_hash(chapter),
                },
            }
        },
        memory_id="memory-1",
        chapters=[chapter],
    )

    async def _retrieve(*_args, **_kwargs):
        return {
            "typed_insights": [{"type": "l5_knowledge", "content": "铜钥匙属于回声井。"}],
            "relationships": [{"type": "l2_fact", "content": "林默 -> 发现 -> 铜钥匙"}],
            "continuity_state": [{"type": "l3_state", "content": "林默知道铜钥匙存在。"}],
            "source_evidence": [],
            "summaries": [],
            "generation_hints": [],
            "style_voice": [],
            "retrieval_context": "[l2_fact] 林默在回声井发现铜钥匙。",
        }

    monkeypatch.setattr("app.services.memory_backend.retrieve", _retrieve)

    memory = await build_creative_memory_pack(
        project=project,
        project_id="p5",
        op_type="CONTINUE",
        input_text="next",
        db=AsyncMock(),
    )

    assert "铜钥匙属于回声井" in memory["dynamic_memory"]["typed_insights"][0]
    assert "林默在回声井发现铜钥匙" in memory["dynamic_memory"]["retrieval_context"]


@pytest.mark.asyncio
async def test_agent_task_can_require_dynamic_memory_rows(monkeypatch: pytest.MonkeyPatch):
    project = SimpleNamespace(
        id="p-agent",
        title="Agent Plan",
        description="desc",
        ontology_schema={"text_type": "business"},
        memory_id="memory-agent",
        chapters=[],
    )

    async def _empty_retrieve(*_args, **_kwargs):
        return {
            "typed_insights": [],
            "relationships": [],
            "continuity_state": [],
            "source_evidence": [],
            "summaries": [],
            "generation_hints": [],
            "style_voice": [],
            "retrieval_context": "",
        }

    monkeypatch.setattr("app.services.memory_backend.retrieve", _empty_retrieve)

    with pytest.raises(RuntimeError, match="Cognee retrieval returned no dynamic memory"):
        await build_creative_memory_pack(
            project=project,
            project_id="p-agent",
            op_type="AGENT_TASK",
            input_text="规划产品介绍",
            db=AsyncMock(),
            reference_cards={"require_dynamic_memory": True},
        )


@pytest.mark.asyncio
async def test_agent_task_can_explicitly_skip_dynamic_memory(monkeypatch: pytest.MonkeyPatch):
    project = SimpleNamespace(
        id="p-agent-plan",
        title="Agent Plan",
        description="desc",
        ontology_schema={"text_type": "novel"},
        memory_id="memory-agent",
        chapters=[],
    )

    async def _unexpected_retrieve(*_args, **_kwargs):
        raise AssertionError("dynamic retrieval must be skipped")

    monkeypatch.setattr("app.services.memory_backend.retrieve", _unexpected_retrieve)

    memory = await build_creative_memory_pack(
        project=project,
        project_id="p-agent-plan",
        op_type="AGENT_TASK",
        input_text="规划两章",
        db=AsyncMock(),
        reference_cards={"skip_dynamic_memory": True},
    )

    assert memory["dynamic_memory"]["enabled"] is False
    assert memory["dynamic_memory"]["skipped"] is True


@pytest.mark.asyncio
async def test_dynamic_memory_skip_cannot_conflict_with_require():
    project = SimpleNamespace(
        id="p-agent-conflict",
        title="Agent Plan",
        description="desc",
        ontology_schema={"text_type": "novel"},
        memory_id="memory-agent",
        chapters=[],
    )

    with pytest.raises(RuntimeError, match="skip_dynamic_memory cannot be combined"):
        await build_creative_memory_pack(
            project=project,
            project_id="p-agent-conflict",
            op_type="AGENT_TASK",
            input_text="规划两章",
            db=AsyncMock(),
            reference_cards={"skip_dynamic_memory": True, "require_dynamic_memory": True},
        )


@pytest.mark.asyncio
async def test_creative_memory_pack_includes_chapter_workflow_state():
    project = SimpleNamespace(
        id="p6",
        title="Story",
        description="desc",
        ontology_schema={"text_type": "fiction"},
        memory_id=None,
        chapters=[
            SimpleNamespace(
                id="chapter-1",
                order_index=0,
                title="雨夜",
                status="draft",
                plan="主角发现密信。",
                summary="林默在雨夜收到密信。",
                content="",
                continuity_notes={"open_threads": ["密信来源未知"]},
            )
        ],
    )

    memory = await build_creative_memory_pack(
        project=project,
        project_id="p6",
        op_type="CONTINUE",
        input_text="继续写密信线索",
        db=AsyncMock(),
        workflow_step="continuation_plan",
    )
    block = render_creative_memory_block(memory)

    assert memory["workflow_memory"]["workflow_step"] == "continuation_plan"
    assert "Creative workflow state" in block
    assert "密信来源未知" in block
    assert any(item["lane"] == "continuity_state" for item in memory["retrieval_strategy"]["query_plan"])


@pytest.mark.asyncio
async def test_creative_memory_pack_marks_selected_chapter_as_workflow_target():
    project = SimpleNamespace(
        id="p-target",
        title="Story",
        description="desc",
        ontology_schema={"text_type": "fiction"},
        memory_id=None,
        chapters=[
            SimpleNamespace(
                id="chapter-1",
                order_index=0,
                title="旧雨",
                status="draft",
                blueprint={},
                plan="",
                summary="林默收到旧地图。",
                content="",
                continuity_notes={"open_threads": ["旧地图来源未知"]},
            ),
            SimpleNamespace(
                id="chapter-2",
                order_index=1,
                title="盐雨",
                status="planned",
                blueprint={
                    "chapter_role": "第二幕推进",
                    "chapter_purpose": "让同盟第一次分裂",
                    "foreshadowing": "导师避谈旧地图",
                },
                plan="林默追查旧地图并与同盟冲突。",
                summary="",
                content="",
                continuity_notes={},
            ),
            SimpleNamespace(
                id="chapter-3",
                order_index=2,
                title="裂城",
                status="planned",
                blueprint={"chapter_role": "后续爆发"},
                plan="同盟分裂后的第一场公开冲突。",
                summary="",
                content="",
                continuity_notes={},
            ),
        ],
    )

    memory = await build_creative_memory_pack(
        project=project,
        project_id="p-target",
        op_type="AGENT_TASK",
        input_text="写第二章",
        db=AsyncMock(),
        reference_cards={"explicit_chapter_ids": ["chapter-2"]},
        workflow_step="draft",
    )
    block = render_creative_memory_block(memory)

    assert memory["workflow_memory"]["target_chapters"][0]["id"] == "chapter-2"
    assert memory["workflow_memory"]["previous_target_chapter"]["id"] == "chapter-1"
    assert memory["workflow_memory"]["next_target_chapter"]["id"] == "chapter-3"
    assert "Target document unit(s) for this operation" in block
    assert "林默追查旧地图并与同盟冲突" in block
    assert "Previous unit state" in block
    assert "旧地图来源未知" in block
    assert "Next unit" in block
    assert "targets=盐雨" in memory["retrieval_strategy"]["query_plan"][0]["query"]


@pytest.mark.asyncio
async def test_creative_memory_pack_includes_structured_architecture_state_and_blueprint():
    project = SimpleNamespace(
        id="p7",
        title="长篇计划",
        description="desc",
        creative_state={
            "agent_workspace": {
                "structured_memory": {
                    "core_seed": "废土城邦争夺失落水源",
                    "story_architecture": {
                        "act1": "发现水源传说",
                        "act2": "同盟破裂",
                        "act3": "公开真相",
                    },
                    "global_summary": "主角已进入城邦。",
                    "character_state": {"林默": "怀疑导师隐瞒水源位置"},
                    "plot_arcs": ["水源是否真实仍未解决"],
                    "foreshadowing_ledger": ["导师避谈旧地图来源"],
                    "canon_rules": ["城邦水源信息不能凭空公开"],
                    "style_guide": {"tone": "冷硬、克制"},
                },
            },
        },
        ontology_schema={"text_type": "fiction"},
        memory_id=None,
        chapters=[
            SimpleNamespace(
                id="chapter-2",
                order_index=1,
                title="盐雨",
                status="planned",
                blueprint={
                    "chapter_role": "第二幕推进",
                    "chapter_purpose": "让同盟第一次分裂",
                    "suspense_level": "高",
                    "foreshadowing": "导师避谈旧地图",
                    "plot_twist_level": "★★★★☆",
                },
                plan="林默追查旧地图。",
                summary="",
                content="",
                continuity_notes={},
            )
        ],
    )

    memory = await build_creative_memory_pack(
        project=project,
        project_id="p7",
        op_type="AGENT_TASK",
        input_text="规划下一章",
        db=AsyncMock(),
        workflow_step="outline",
    )
    block = render_creative_memory_block(memory)

    assert "Creative architecture state" in block
    assert "Structured creative state ledger" in block
    assert "废土城邦争夺失落水源" in block
    assert "导师避谈旧地图来源" in block
    assert "城邦水源信息不能凭空公开" in block
    assert "Planned unit queue" in block
    assert "第二幕推进" in block
    assert memory["retrieval_strategy"]["operation_focus"].startswith("user intent")


@pytest.mark.asyncio
async def test_continue_requires_memory_after_creative_state_exists():
    project = SimpleNamespace(
        id="p8",
        title="Story",
        description="desc",
        creative_state={"global_summary": "已经建立世界观。"},
        ontology_schema={"text_type": "fiction"},
        memory_id=None,
        chapters=[],
    )

    with pytest.raises(RuntimeError, match="Cognee project memory is required"):
        await build_creative_memory_pack(
            project=project,
            project_id="p8",
            op_type="CONTINUE",
            input_text="规划下一章",
            db=AsyncMock(),
        )
