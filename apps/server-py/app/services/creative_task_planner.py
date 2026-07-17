"""
Adaptive creative task planner for MuseGraph Pi Agent.

Replaces hardcoded novel/chapter fast paths with intent-driven plans where
the agent (via extract/generate prompts) decides text_type, memory_schema,
and structured extraction dimensions per task.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Heuristic hints — used only to pick fast-path intent, not to fix schema.
_ANALYSIS_HINTS = (
    "分析", "导入", "章节", "节选", "提取", "结构化", "伏笔", "拆解", "理解",
    "analyze", "import", "imported", "chapter", "extract", "structured", "ingest",
)
_GENERATION_HINTS = (
    "续写下一章", "续写下一", "继续写", "接着写", "创作", "生成", "撰写", "起草",
    "continue writing", "write the next", "generate", "draft", "compose",
)
_ANALYSIS_EXCLUSIONS = (
    "续写建议", "continuation suggestions", "续写方向",
)
_CONTINUATION_EXCLUSIONS = _ANALYSIS_EXCLUSIONS

_TEXT_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "fiction": ("小说", "故事", "章节", "叙事", "novel", "story", "chapter", "fiction"),
    "screenplay": ("剧本", "场景", "对白", "screenplay", "script"),
    "nonfiction": ("非虚构", "纪实", "散文", "essay", "nonfiction"),
    "academic": ("论文", "研究", "学术", "academic", "thesis"),
    "business": ("商业", "方案", "报告", "business", "proposal"),
    "product_doc": ("产品", "需求", "prd", "功能", "product"),
    "technical": ("技术", "api", "架构", "technical", "documentation"),
    "marketing": ("营销", "文案", "广告", "marketing", "copy"),
    "resume": ("简历", "履历", "resume", "cv"),
    "poetry": ("诗", "诗歌", "poetry", "verse"),
}


@dataclass
class ContentUnit:
    """Generic document unit (maps to ProjectChapter today)."""

    unit_id: str
    title: str
    content: str
    order_index: int = 0


def _instruction_matches(instruction: str, hints: tuple[str, ...]) -> bool:
    text = instruction.casefold()
    return any(h.casefold() in text for h in hints)


def _chapters_with_content(project: Any) -> list[ContentUnit]:
    chapters = sorted(getattr(project, "chapters", None) or [], key=lambda c: c.order_index)
    units: list[ContentUnit] = []
    for ch in chapters:
        content = (getattr(ch, "content", None) or "").strip()
        if not content:
            continue
        units.append(
            ContentUnit(
                unit_id=str(ch.id),
                title=str(getattr(ch, "title", None) or ""),
                content=content,
                order_index=int(getattr(ch, "order_index", 0) or 0),
            )
        )
    return units


def _agent_workspace(project: Any) -> dict[str, Any]:
    state = getattr(project, "creative_state", None) or {}
    workspace = state.get("agent_workspace") if isinstance(state, dict) else {}
    return dict(workspace) if isinstance(workspace, dict) else {}


def _pick_target_unit(units: list[ContentUnit], instruction: str) -> ContentUnit | None:
    if not units:
        return None
    for unit in units:
        if unit.title and unit.title in instruction:
            return unit
    return units[0]


def infer_text_type(
    project: Any,
    instruction: str,
    content_sample: str = "",
) -> str:
    """Infer text type from ontology, workspace, instruction, or content — never default to novel."""
    ontology = getattr(project, "ontology_schema", None) or {}
    if isinstance(ontology, dict):
        declared = str(ontology.get("text_type") or "").strip()
        if declared and declared != "other":
            return declared

    workspace = _agent_workspace(project)
    ws_type = str(workspace.get("text_type") or "").strip()
    if ws_type and ws_type != "other":
        return ws_type

    haystack = f"{instruction}\n{content_sample[:2000]}".casefold()
    scores: dict[str, int] = {}
    for text_type, hints in _TEXT_TYPE_HINTS.items():
        scores[text_type] = sum(1 for h in hints if h.casefold() in haystack)
    best = max(scores, key=scores.get) if scores else "other"
    return best if scores.get(best, 0) > 0 else "other"


def infer_task_intent(
    instruction: str,
    project: Any,
    conversation_history: list[dict[str, Any]] | None = None,
) -> str | None:
    """
    Classify high-level intent without assuming fiction.

    Returns: content_analysis | content_generation | None (use full LLM planner)
    """
    if _instruction_matches(instruction, _CONTINUATION_EXCLUSIONS):
        if _instruction_matches(instruction, _ANALYSIS_HINTS):
            return "content_analysis"

    if _instruction_matches(instruction, _GENERATION_HINTS):
        if not _instruction_matches(instruction, _CONTINUATION_EXCLUSIONS):
            workspace = _agent_workspace(project)
            structured = workspace.get("structured_memory")
            has_structured = isinstance(structured, dict) and bool(structured)
            has_history = bool(conversation_history)
            if has_structured or has_history:
                return "content_generation"

    units = _chapters_with_content(project)
    if units and _instruction_matches(instruction, _ANALYSIS_HINTS):
        if not _instruction_matches(instruction, _GENERATION_HINTS):
            return "content_analysis"

    return None


def _build_content_context(unit: ContentUnit, instruction: str) -> dict[str, Any]:
    return {
        "unit_id": unit.unit_id,
        "chapter_id": unit.unit_id,
        "title": unit.title,
        "content": unit.content[:14000],
        "user_focus": instruction,
    }


def _analysis_extract_description(unit: ContentUnit, text_type: str) -> str:
    return (
        f"Analyze document «{unit.title}» (text_type hint: {text_type or 'infer from content'}). "
        "You must first infer the actual text_type and design memory_schema: list the extraction "
        "dimensions appropriate to this content (do NOT assume fiction). "
        "Examples: fiction → worldview, characters, locations, timeline, plot_threads; "
        "nonfiction → thesis, claims, evidence, sources; product_doc → features, users, metrics; "
        "resume → experience, skills, achievements. "
        "Then populate structured_memory and graph (nodes with id/type/name/summary, "
        "edges with source/target/type/evidence). "
        "Return JSON with: text_type, text_type_analysis, task_kind, memory_schema, "
        "memory_schema_justification, structured_memory, graph, output, retrieval_queries."
    )


def build_analysis_plan(project: Any, instruction: str) -> dict[str, Any] | None:
    """Fast adaptive plan for import/analyze/extract tasks."""
    units = _chapters_with_content(project)
    if not units:
        return None

    target = _pick_target_unit(units, instruction)
    if target is None or len(target.content) < 50:
        return None

    text_type = infer_text_type(project, instruction, target.content)
    content_context = _build_content_context(target, instruction)
    component_models = getattr(project, "component_models", None)
    agent_model = component_models.get("operation_agent_task", "") if isinstance(component_models, dict) else ""

    return {
        "output": "",
        "text_type": text_type,
        "task_kind": "content_analysis",
        "content_context": content_context,
        "chapter_context": content_context,
        "plan": [
            {
                "step_type": "extract",
                "description": _analysis_extract_description(target, text_type),
                "operation_type": "AGENT_TASK",
            },
            {
                "step_type": "spawn_subagent",
                "description": "Delegate graph relationship refinement to graph_extractor subagent",
                "operation_type": "AGENT_TASK",
                "tool_args": {
                    "subagent_role": "graph_extractor",
                    "model": agent_model,
                    "task": (
                        "Refine and merge graph nodes/edges from the extraction step. "
                        "Ensure entity relationships are explicit and evidence-linked."
                    ),
                },
            },
            {
                "step_type": "store_structured_memory",
                "description": "Persist agent-decided structured_memory, memory_schema, and graph to cognee",
                "operation_type": "AGENT_TASK",
            },
        ],
        "memory_schema": {},
        "structured_memory": {},
        "graph": {},
        "retrieval_queries": [],
        "writing_plan": [],
        "next_actions": [],
        "_llm_result": {},
        "_fast_path": "adaptive_analysis",
    }


def build_generation_plan(
    project: Any,
    instruction: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Fast adaptive plan for continuation/generation tasks."""
    workspace = _agent_workspace(project)
    structured = workspace.get("structured_memory")
    has_structured = isinstance(structured, dict) and bool(structured)
    has_history = bool(conversation_history)
    if not has_structured and not has_history:
        return None

    units = _chapters_with_content(project)
    unit_hint = ""
    if units:
        latest = units[-1]
        unit_hint = (
            f"\nLatest document «{latest.title}» ({len(latest.content)} chars). "
            "Continue in the same format and voice."
        )

    text_type = str(workspace.get("text_type") or infer_text_type(project, instruction) or "other")
    generate_desc = (
        "Generate new content using structured_memory, graph, and prior context. "
        "Match the inferred text_type and user's instruction; do not assume a novel chapter. "
        "Return JSON with output/content (prose or structured draft) and optional structured_memory updates.\n"
        f"User instruction:\n{instruction}"
        f"{unit_hint}"
    )

    return {
        "output": "",
        "text_type": text_type,
        "task_kind": "content_generation",
        "plan": [
            {
                "step_type": "memory_search",
                "description": instruction[:400] or text_type,
                "operation_type": "AGENT_TASK",
            },
            {
                "step_type": "generate",
                "description": generate_desc,
                "operation_type": "AGENT_TASK",
            },
            {
                "step_type": "write_chapter",
                "description": "Persist generated content into project document unit",
                "operation_type": "AGENT_TASK",
            },
        ],
        "memory_schema": workspace.get("memory_schema") if isinstance(workspace.get("memory_schema"), dict) else {},
        "structured_memory": structured if isinstance(structured, dict) else {},
        "graph": workspace.get("graph") if isinstance(workspace.get("graph"), dict) else {},
        "retrieval_queries": [instruction[:200]] if instruction else [],
        "writing_plan": [],
        "next_actions": [],
        "_llm_result": {},
        "_fast_path": "adaptive_generation",
    }


def build_adaptive_plan(
    project: Any,
    instruction: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Entry: pick adaptive fast plan by intent, or None for full LLM planning."""
    intent = infer_task_intent(instruction, project, conversation_history)
    if intent == "content_generation":
        plan = build_generation_plan(project, instruction, conversation_history)
        if plan is not None:
            plan["pipeline_kind"] = infer_pipeline_kind(plan.get("task_kind"), instruction)
        return plan
    if intent == "content_analysis":
        plan = build_analysis_plan(project, instruction)
        if plan is not None:
            plan["pipeline_kind"] = infer_pipeline_kind(plan.get("task_kind"), instruction)
        return plan
    return None


# ---------------------------------------------------------------------------
# Pipeline classification (Phase B)
# ---------------------------------------------------------------------------

_LONG_FORM_HINTS = (
    "章", "扩写", "续写", "写一", "写段", "写篇", "写个", "创作",
    "生成正文", "长文", "draft", "write chapter", "write a", "write an",
    "continue the", "扩章", "next chapter", "next section", "下一章",
    "开篇", "故事", "小说", "描写", "段落", "创作一",
)
_BATCH_CHAPTER_HINTS = (
    "写N章", "生成N章", "N章小说", "批量创作",
    "write N chapters", "generate N chapters",
    "10章", "10 章", "5章", "5 章", "20章", "20 章",
    "十章", "十章", "五章",
)
_FACT_EXTRACTION_HINTS = ("抽取事实", "提取", "入库", "extract facts", "build facts")
_REVIEW_HINTS = ("审", "audit", "review", "check", "检审", "校对")


def infer_pipeline_kind(task_kind: str | None, instruction: str) -> str:
    """Classify a task into a pipeline shape.

    Returns one of:
    - ``long_form_write``: chapter / long article / draft — must run
      composer → writer → auditor → (optional reviser) under Phase B's
      prompt-mandated pipeline (Phase C: server-side runner).
    - ``fact_extraction``: extract/build facts.
    - ``review_only``: audit/review/check only.
    - ``simple``: orchestrator stays autonomous (current behaviour).
    """

    kind = (task_kind or "").strip().lower()
    instr = (instruction or "").lower()
    # Batch chapter detection — if the user asks for N chapters,
    # force long_form_write pipeline
    if any(h in instr for h in _BATCH_CHAPTER_HINTS):
        return "long_form_write"
    if any(h in instr for h in _LONG_FORM_HINTS) or kind in {
        "chapter_write", "long_form_write", "draft", "content_generation",
    }:
        return "long_form_write"
    if any(h in instr for h in _FACT_EXTRACTION_HINTS) or kind in {
        "extract_facts", "build_facts", "fact_extraction",
    }:
        return "fact_extraction"
    if any(h in instr for h in _REVIEW_HINTS) or kind in {
        "analyze", "audit", "review",
    }:
        return "review_only"
    return "simple"

