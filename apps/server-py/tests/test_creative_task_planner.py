"""Tests for adaptive creative task planner."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.creative_task_planner import (
    build_adaptive_plan,
    build_analysis_plan,
    build_generation_plan,
    infer_task_intent,
    infer_text_type,
)


def _chapter(chapter_id: str, title: str, content: str, order_index: int = 0):
    return SimpleNamespace(id=chapter_id, title=title, content=content, order_index=order_index)


def _project(chapters=None, workspace=None, ontology=None):
    return SimpleNamespace(
        chapters=chapters or [],
        creative_state={"agent_workspace": workspace or {}},
        ontology_schema=ontology or {},
    )


def test_infer_text_type_from_ontology():
    project = _project(ontology={"text_type": "product_doc"})
    assert infer_text_type(project, "analyze this") == "product_doc"


def test_infer_text_type_does_not_default_to_novel():
    project = _project()
    assert infer_text_type(project, "summarize quarterly metrics") == "other"


def test_analysis_plan_uses_adaptive_path():
    project = _project(chapters=[_chapter("ch-1", "星港余烬 节选", "A" * 120)])
    instruction = "请分析项目中已导入的章节《星港余烬 节选》，写入 structured_memory 与 graph。"

    plan = build_analysis_plan(project, instruction)

    assert plan is not None
    assert plan["_fast_path"] == "adaptive_analysis"
    assert plan["task_kind"] == "content_analysis"
    assert plan["plan"][0]["step_type"] == "extract"
    assert plan["plan"][-1]["step_type"] == "store_structured_memory"
    assert "do NOT assume fiction" in plan["plan"][0]["description"]


def test_analysis_allows_suggestion_phrase():
    project = _project(chapters=[_chapter("ch-1", "节选", "B" * 120)])
    instruction = "请分析导入章节，写入 structured_memory 与 graph，并给出续写建议。"

    plan = build_adaptive_plan(project, instruction)
    assert plan is not None
    assert plan["task_kind"] == "content_analysis"


def test_generation_plan_when_structured_memory_exists():
    project = _project(
        chapters=[_chapter("ch-1", "Intro", "C" * 200, 0)],
        workspace={"structured_memory": {"worldview": "mars", "characters": ["Lin"]}},
    )
    instruction = "基于 structured_memory 续写下一章（约800字）。"

    plan = build_generation_plan(project, instruction, conversation_history=None)

    assert plan is not None
    assert plan["_fast_path"] == "adaptive_generation"
    assert plan["task_kind"] == "content_generation"
    assert [step["step_type"] for step in plan["plan"]] == [
        "memory_search",
        "generate",
        "write_chapter",
    ]


def test_infer_intent_skips_pure_continuation_without_memory():
    project = _project(chapters=[_chapter("ch-1", "Intro", "B" * 120)])
    instruction = "基于分析结果续写下一章（约800字）。"
    assert infer_task_intent(instruction, project) is None