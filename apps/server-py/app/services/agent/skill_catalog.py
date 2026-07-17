from dataclasses import dataclass


READ_TOOLS = frozenset(
    {
        "list_files",
        "read_file",
        "knowledge_search",
        "knowledge_get",
    }
)
WRITE_TOOLS = frozenset(
    {
        "write_file",
        "delete_file",
        "knowledge_upsert",
        "knowledge_delete",
    }
)
ALL_AGENT_TOOLS = READ_TOOLS | WRITE_TOOLS


@dataclass(frozen=True)
class BuiltinSkill:
    slug: str
    name: str
    description: str
    instructions: str
    scopes: frozenset[str]
    roles: frozenset[str]
    allowed_tools: frozenset[str]
    default_model_component: str | None = None
    version: int = 1


BUILTIN_SKILLS: tuple[BuiltinSkill, ...] = (
    BuiltinSkill(
        slug="general",
        name="General",
        description="通用文本创作、分析和建议。",
        instructions=(
            "先读取项目目标、控制文档和相关知识，再决定行动。"
            "写作必须通过文件工具保存；结论必须说明使用了哪些知识记录。"
        ),
        scopes=frozenset({"write", "analyze", "suggest"}),
        roles=frozenset(
            {
                "planner",
                "composer",
                "writer",
                "auditor",
                "reviser",
                "evaluator",
                "updater",
                "memory_builder",
                "graph_extractor",
            }
        ),
        allowed_tools=ALL_AGENT_TOOLS,
    ),
    BuiltinSkill(
        slug="analyzer",
        name="Analyzer",
        description="分析结构、证据、实体、关系和风险。",
        instructions="只基于项目文件与结构化知识分析，所有结论保留来源引用。",
        scopes=frozenset({"analyze"}),
        roles=frozenset({"planner", "composer", "auditor", "evaluator"}),
        allowed_tools=READ_TOOLS,
        default_model_component="operation_analyze",
    ),
    BuiltinSkill(
        slug="continuation",
        name="Continuation",
        description="依据现有文本和知识继续写作。",
        instructions=(
            "延续已有语气、视角、时态、术语和事实；写作前读取目标文件和相关知识，"
            "禁止发明与 required 约束冲突的内容。"
        ),
        scopes=frozenset({"write", "suggest"}),
        roles=frozenset({"planner", "composer", "writer", "auditor", "reviser"}),
        allowed_tools=ALL_AGENT_TOOLS,
        default_model_component="operation_continue",
    ),
    BuiltinSkill(
        slug="rewriter",
        name="Rewriter",
        description="在不改变事实的前提下重写文本。",
        instructions="保留原意与知识约束，根据用户要求调整结构、语气、长度和清晰度。",
        scopes=frozenset({"write"}),
        roles=frozenset({"composer", "writer", "auditor", "reviser"}),
        allowed_tools=READ_TOOLS | frozenset({"write_file"}),
        default_model_component="operation_rewrite",
    ),
    BuiltinSkill(
        slug="outliner",
        name="Outliner",
        description="建立与文本类型匹配的可执行大纲。",
        instructions="为每个结构单元给出目标、所需知识和预期产出，并将大纲写入项目文件。",
        scopes=frozenset({"write", "analyze"}),
        roles=frozenset({"planner", "composer", "writer", "auditor"}),
        allowed_tools=READ_TOOLS | frozenset({"write_file"}),
        default_model_component="operation_agent_task",
    ),
    BuiltinSkill(
        slug="critic",
        name="Critic",
        description="审查文本一致性、证据、结构与意图对齐。",
        instructions="只读审查，问题必须包含严重性、证据来源和具体修订建议。",
        scopes=frozenset({"analyze"}),
        roles=frozenset({"auditor", "evaluator"}),
        allowed_tools=READ_TOOLS,
        default_model_component="operation_analyze",
    ),
    BuiltinSkill(
        slug="knowledge-builder",
        name="Knowledge Builder",
        description="提取有来源的事实、实体、关系、事件与约束。",
        instructions=(
            "每条知识必须是严格类型、稳定 ID，并至少包含一个真实来源引用；"
            "不得把推测写成 fact。"
        ),
        scopes=frozenset({"write", "analyze"}),
        roles=frozenset({"planner", "composer", "updater", "memory_builder", "graph_extractor"}),
        allowed_tools=READ_TOOLS | frozenset({"knowledge_upsert", "knowledge_delete"}),
        default_model_component="operation_agent_task",
    ),
    BuiltinSkill(
        slug="coauthor",
        name="Co-author",
        description="提供短小、可直接插入编辑器的建议。",
        instructions="只返回与当前位置衔接的短建议，不重写整篇文本。",
        scopes=frozenset({"suggest"}),
        roles=frozenset({"composer", "writer", "auditor"}),
        allowed_tools=READ_TOOLS,
        default_model_component="operation_agent_suggest",
    ),
)

BUILTIN_SKILL_MAP = {skill.slug: skill for skill in BUILTIN_SKILLS}
