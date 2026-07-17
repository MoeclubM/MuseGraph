"""Subagent profiles.

Each profile is a pure data record describing how a subagent role differs
from the orchestrator and from other roles in concrete, code-enforced ways:

- ``allowed_tools``: hard whitelist enforced by the tool dispatcher.
- ``can_write_back``: gates write-class tools (document/fact/memory writes)
  even if a write tool happens to be allowed.
- ``context_scope``: hint to the runtime about how aggressively the
  pre-prompt context snapshot may be trimmed.
- ``output_schema``: loose JSON schema that the ``finish.output`` payload
  must satisfy.
- ``default_model_component``: project component key used to resolve a
  model when the orchestrator does not pin one explicitly.
- ``system_prompt``: role-specific system prompt body. Replaces the
  previous one-line role hint.

These profiles are intentionally task-shape neutral. MuseGraph is not a
fiction-only system, so profiles describe what a role is allowed to do
and return, not what genre or text type a project must be.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Read-only tools available to every subagent.
READ_ONLY_TOOL_BASE: frozenset[str] = frozenset({
    "memory_search",
    "list_facts",
    "read_fact",
    "search_entities",
    "list_document_units",
    "read_document_unit",
    "list_project_files",
    "read_project_file",
    "get_memory_graph",
})

# Default auditor evaluation dimensions (Phase B). Phase C generalises
# these to per-text-type packs (see ``app/services/agent/packs/``).
AUDITOR_DIMENSIONS: list[str] = [
    "continuity",          # facts already in memory match the draft
    "evidence_grounding",  # claims have source_ref or document evidence
    "structure",           # heading / pacing / required sections present
    "language_quality",    # AI-trace red flags, repetitive phrasing
    "intent_alignment",    # matches the planner's must-keep / must-avoid
]


def auditor_dimensions_for(project: Any) -> list[str]:
    """Return the auditor dimensions from the project's active pack."""

    from app.services.agent.packs import get_project_pack

    return list(get_project_pack(project).auditor_dimensions)

# Write-class tools that mutate persistent project state (documents, facts,
# memory, graph). Roles with can_write_back=False cannot call any of these
# even if they appear in allowed_tools. Tools that only write into the
# agent workspace (report_finding, propose_state_delta) are *not* listed
# here; those are subagent-output channels, not project-truth mutations.
WRITE_BACK_TOOLS: frozenset[str] = frozenset({
    "store_structured_memory",
    "build_project_memory",
    "write_document_unit",
    "create_fact",
    "update_fact",
    "sync_fact_memory",
    "batch_update_entities",
})


@dataclass(frozen=True)
class SubagentProfile:
    role: str
    description: str
    system_prompt: str
    allowed_tools: frozenset[str]
    output_schema: dict[str, Any] | None
    max_iterations: int = 8
    context_scope: str = "full"  # "full" | "intent_only" | "targeted"
    can_write_back: bool = False
    default_model_component: str | None = None

    def can_use_tool(self, tool_name: str) -> bool:
        if tool_name not in self.allowed_tools:
            return False
        if not self.can_write_back and tool_name in WRITE_BACK_TOOLS:
            return False
        return True


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }


_PLANNER_PROMPT = (
    "You are a MuseGraph subagent acting as planner.\n"
    "Responsibility: produce an executable, structured plan based on project state. "
    "Read real workspace files, document units, the fact store, and memory; decide "
    "text_type/task_kind/memory_schema and a list of next actions. Do not write to "
    "documents, do not modify facts, do not build memory.\n"
    "IMPORTANT: Always respond in the same language as the user's input. "
    "If the user writes in Chinese, output Chinese. If they write in English, "
    "output English. Never switch to a different language.\n"
    "finish.output MUST be JSON: {plan:[{step,goal,tool_hint?,target_refs?}], "
    "rationale, risks?}."
)

_COMPOSER_PROMPT = (
    "你是 MuseGraph 的作曲家（composer）子代理。\n"
    "职责：为 writer 挑选并组装上下文。阅读项目文件、文档单元、事实库、"
    "control docs（intent.md/focus.md/rules.md/bible.md，如果有的话）以及相关 cognee RAG 片段。"
    "从项目上下文中识别文本类型（小说、文章、论文、剧本、产品文档等），"
    "据此调整 selected_context。输出紧凑的 selected_context、"
    "优先级排序的 rule_stack（最高优先级在前），以及 writer 应该聚焦的 target_refs。"
    "不要写正文；不要修改事实库；不要 spawn 其他子代理。\n"
    "重要：始终使用用户输入的语言回复。用户写中文就用中文输出，用户写英文就用英文输出。不要切换语言。\n"
    "finish.output 必须是 JSON：{selected_context:{...}, rule_stack:[...], "
    "target_refs:[...], summary}。"
)

_WRITER_PROMPT = (
    "你是 MuseGraph 的作家（writer）子代理。\n"
    "职责：根据提供的 target_refs 和意图生成或扩展文档内容。根据项目的文本类型"
    "（小说、文章、剧本等）调整写作风格、语气和结构。\n"
    "对于长篇叙事：保持角色风格、展示而非讲述、节奏得当。\n"
    "对于文章：清晰的论点、有证据支持的主张、逻辑流畅。\n"
    "对于剧本：场景标题、角色提示、对话格式。\n"
    "先 memory_search 检索项目记忆，自己写出完整正文，然后用 write_document_unit(content=正文) 落盘。\n"
    "不要修改事实库，不要构建记忆，不要 spawn 其他子代理。\n"
    "重要：始终使用用户输入的语言回复。用户写中文就用中文输出，用户写英文就用英文输出。不要切换语言。\n"
    "finish.output 必须是 JSON：{document_unit_id, mode, summary}。"
)

_AUDITOR_PROMPT = (
    "你是 MuseGraph 的审计师（auditor）子代理。\n"
    "职责：对提供的 target_refs 按配置的维度进行审计："
    "连续性（continuity）、证据支撑（evidence_grounding）、结构（structure）、"
    "语言质量（language_quality）、意图对齐（intent_alignment）"
    "（以及文本类型特定的维度）。\n"
    "对于叙事文本，还需检查：角色一致性、节奏、对话自然度、时态/视角一致性。\n"
    "对于非虚构文本：引用准确性、论点连贯性、章节完整性。\n"
    "对每个维度打分并给出具体问题（含证据）。不要编辑正文；不要修改事实库。\n"
    "重要：始终使用用户输入的语言回复。用户写中文就用中文输出，用户写英文就用英文输出。不要切换语言。\n"
    "finish.output 必须是 JSON：{dimensions:{<dim>:{score,status,notes}}, "
    "issues:[{severity,evidence,suggestion}], pass:boolean, summary}。"
)

_REVISER_PROMPT = (
    "你是 MuseGraph 的修订师（reviser）子代理。\n"
    "职责：接收草稿（target_refs 包含 document_unit_id）和审计师的 issues，"
    "输出修订版以解决每个关键问题。保留作者风格和文本类型惯例。\n"
    "自己写出重写后的完整正文，用 write_document_unit(mode=replace, content=正文) 落盘。"
    "不要修改事实库或记忆。\n"
    "重要：始终使用用户输入的语言回复。用户写中文就用中文输出，用户写英文就用英文输出。不要切换语言。\n"
    "finish.output 必须是 JSON：{document_unit_id, issues_fixed:[...], summary}。"
)

_EVALUATOR_PROMPT = (
    "You are a MuseGraph subagent acting as evaluator.\n"
    "Responsibility: compare candidates or directions, return quantitative scores "
    "and a final recommendation. Consider the project's text type when scoring. "
    "Do not write documents, do not modify facts.\n"
    "IMPORTANT: Always respond in the same language as the user's input. "
    "If the user writes in Chinese, output Chinese. If they write in English, "
    "output English. Never switch to a different language.\n"
    "finish.output MUST be JSON: {scores:{<dimension>:number}, recommendation, "
    "rationale, summary}."
)

_UPDATER_PROMPT = (
    "You are a MuseGraph subagent acting as updater.\n"
    "Responsibility: update facts and entities using explicit source evidence. "
    "For narrative projects, extract character traits, plot events, setting details, "
    "and timeline facts. For non-fiction, extract claims, citations, data points, "
    "and argument relationships. Allowed tools include create_fact/update_fact/"
    "batch_update_entities. You may also use propose_state_delta to forward a "
    "suggested change for the orchestrator to apply. Do not write documents, do not "
    "build full memory.\n"
    "IMPORTANT: Always respond in the same language as the user's input. "
    "If the user writes in Chinese, output Chinese. If they write in English, "
    "output English. Never switch to a different language.\n"
    "finish.output MUST be JSON: {updated:[fact_id...], created:[fact_id...], "
    "proposed_deltas?:[...], summary}."
)

_MEMORY_BUILDER_PROMPT = (
    "You are a MuseGraph subagent acting as memory_builder.\n"
    "Responsibility: based on existing documents and facts, decide a memory_schema "
    "and structured_memory and write them into cognee and the graph. Choose a "
    "schema appropriate to the project's text type: for fiction, consider characters, "
    "locations, plot arcs; for articles, consider topics, arguments, evidence; for "
    "screenplays, consider scenes, characters, props. Allowed "
    "tools: store_structured_memory, build_project_memory. Do not modify facts, do "
    "not write documents.\n"
    "IMPORTANT: Always respond in the same language as the user's input. "
    "If the user writes in Chinese, output Chinese. If they write in English, "
    "output English. Never switch to a different language.\n"
    "finish.output MUST be JSON: {schema:{...}, structured_memory_keys:[...], "
    "built:boolean, summary}."
)

_GRAPH_EXTRACTOR_PROMPT = (
    "You are a MuseGraph subagent acting as graph_extractor.\n"
    "Responsibility: extract entities and relationships from the supplied "
    "target_refs and store them in structured_memory.graph for downstream "
    "visualization and RAG. Adapt entity types to the project's text type: "
    "for fiction, extract characters, locations, objects, events with narrative "
    "relationships; for non-fiction, extract concepts, people, organizations with "
    "argument/dependency edges. Do not write documents, do not modify facts, do not "
    "build full project memory.\n"
    "IMPORTANT: Always respond in the same language as the user's input. "
    "If the user writes in Chinese, output Chinese. If they write in English, "
    "output English. Never switch to a different language.\n"
    "finish.output MUST be JSON: {nodes:[...], edges:[...], target_refs:[...], "
    "summary}."
)


SUBAGENT_PROFILES: dict[str, SubagentProfile] = {
    "planner": SubagentProfile(
        role="planner",
        description="Plan execution, structure, and memory schema based on project facts.",
        system_prompt=_PLANNER_PROMPT,
        allowed_tools=READ_ONLY_TOOL_BASE,
        output_schema=_schema(
            {
                "plan": {"type": "array"},
                "rationale": {"type": "string"},
                "risks": {"type": "array"},
            },
            ["plan"],
        ),
        max_iterations=8,
        context_scope="full",
        can_write_back=False,
        default_model_component="operation_agent_task",
    ),
    "writer": SubagentProfile(
        role="writer",
        description="Generate document content aligned with project facts and intent.",
        system_prompt=_WRITER_PROMPT,
        allowed_tools=READ_ONLY_TOOL_BASE | frozenset({
            "write_document_unit",
        }),
        output_schema=_schema(
            {
                "document_unit_id": {"type": "string"},
                "mode": {"type": "string"},
                "summary": {"type": "string"},
            },
            ["document_unit_id", "summary"],
        ),
        max_iterations=8,
        context_scope="targeted",
        can_write_back=True,
        default_model_component="operation_continue",
    ),
    "auditor": SubagentProfile(
        role="auditor",
        description="Audit content across configured dimensions; do not edit.",
        system_prompt=_AUDITOR_PROMPT,
        allowed_tools=READ_ONLY_TOOL_BASE | frozenset({"report_finding"}),
        output_schema=_schema(
            {
                "dimensions": {"type": "object"},
                "issues": {"type": "array"},
                "pass": {"type": "boolean"},
                "summary": {"type": "string"},
            },
            ["dimensions", "issues", "pass", "summary"],
        ),
        max_iterations=6,
        context_scope="targeted",
        can_write_back=False,
        default_model_component="operation_analyze",
    ),
    "composer": SubagentProfile(
        role="composer",
        description="Select & assemble context (no writing, no fact mutation).",
        system_prompt=_COMPOSER_PROMPT,
        allowed_tools=READ_ONLY_TOOL_BASE | frozenset({"report_finding"}),
        output_schema=_schema(
            {
                "selected_context": {"type": "object"},
                "rule_stack": {"type": "array"},
                "target_refs": {"type": "array"},
                "summary": {"type": "string"},
            },
            ["selected_context", "rule_stack", "target_refs", "summary"],
        ),
        max_iterations=8,
        context_scope="full",
        can_write_back=False,
        default_model_component="operation_agent_task",
    ),
    "reviser": SubagentProfile(
        role="reviser",
        description="Revise a unit using auditor issues; bounded retry.",
        system_prompt=_REVISER_PROMPT,
        allowed_tools=READ_ONLY_TOOL_BASE | frozenset({
            "write_document_unit",
        }),
        output_schema=_schema(
            {
                "document_unit_id": {"type": "string"},
                "issues_fixed": {"type": "array"},
                "summary": {"type": "string"},
            },
            ["document_unit_id", "summary"],
        ),
        max_iterations=6,
        context_scope="targeted",
        can_write_back=True,
        default_model_component="operation_continue",
    ),
    "evaluator": SubagentProfile(
        role="evaluator",
        description="Evaluate alternatives or quality and recommend a choice.",
        system_prompt=_EVALUATOR_PROMPT,
        allowed_tools=READ_ONLY_TOOL_BASE,
        output_schema=_schema(
            {
                "scores": {"type": "object"},
                "recommendation": {"type": "string"},
                "rationale": {"type": "string"},
                "summary": {"type": "string"},
            },
            ["scores", "recommendation"],
        ),
        max_iterations=4,
        context_scope="intent_only",
        can_write_back=False,
        default_model_component="operation_analyze",
    ),
    "updater": SubagentProfile(
        role="updater",
        description="Update project facts and entities using explicit source evidence.",
        system_prompt=_UPDATER_PROMPT,
        allowed_tools=READ_ONLY_TOOL_BASE | frozenset({
            "create_fact",
            "update_fact",
            "batch_update_entities",
            "sync_fact_memory",
            "propose_state_delta",
        }),
        output_schema=_schema(
            {
                "updated": {"type": "array"},
                "created": {"type": "array"},
                "proposed_deltas": {"type": "array"},
                "summary": {"type": "string"},
            },
            ["summary"],
        ),
        max_iterations=8,
        context_scope="targeted",
        can_write_back=True,
        default_model_component="operation_agent_task",
    ),
    "memory_builder": SubagentProfile(
        role="memory_builder",
        description="Plan memory schema and write structured memory to cognee.",
        system_prompt=_MEMORY_BUILDER_PROMPT,
        allowed_tools=READ_ONLY_TOOL_BASE | frozenset({
            "store_structured_memory",
            "build_project_memory",
        }),
        output_schema=_schema(
            {
                "schema": {"type": "object"},
                "structured_memory_keys": {"type": "array"},
                "built": {"type": "boolean"},
                "summary": {"type": "string"},
            },
            ["summary"],
        ),
        max_iterations=6,
        context_scope="full",
        can_write_back=True,
        default_model_component="operation_agent_task",
    ),
    "graph_extractor": SubagentProfile(
        role="graph_extractor",
        description="Extract entities and relationships into structured_memory.graph.",
        system_prompt=_GRAPH_EXTRACTOR_PROMPT,
        allowed_tools=READ_ONLY_TOOL_BASE | frozenset({"store_structured_memory"}),
        output_schema=_schema(
            {
                "nodes": {"type": "array"},
                "edges": {"type": "array"},
                "target_refs": {"type": "array"},
                "summary": {"type": "string"},
            },
            ["nodes", "edges"],
        ),
        max_iterations=6,
        context_scope="targeted",
        can_write_back=True,
        default_model_component="operation_agent_task",
    ),
}


SUBAGENT_ROLES: frozenset[str] = frozenset(SUBAGENT_PROFILES.keys())


def get_profile(role: str) -> SubagentProfile:
    """Return the profile for ``role`` or raise ``KeyError`` with a helpful message."""

    profile = SUBAGENT_PROFILES.get((role or "").strip())
    if profile is None:
        available = ", ".join(sorted(SUBAGENT_PROFILES.keys()))
        raise KeyError(f"Unknown subagent role: {role!r}. Available: {available}")
    return profile


def validate_finish_output(profile: SubagentProfile, payload: Any) -> list[str]:
    """Light-weight validation of finish.output against profile.output_schema.

    Returns a list of human-readable issues. Empty list means the payload
    satisfies the loose schema. We deliberately keep this loose: required
    keys must exist, but values can be empty/typed loosely so the schema
    stays useful across heterogeneous text types.
    """

    issues: list[str] = []
    schema = profile.output_schema or {}
    if schema.get("type") == "object" and not isinstance(payload, dict):
        issues.append(f"finish.output for role {profile.role} must be a JSON object")
        return issues
    required = schema.get("required") or []
    for key in required:
        if not isinstance(payload, dict) or key not in payload or payload[key] in (None, "", [], {}):
            issues.append(f"finish.output missing required field: {key}")
    return issues
