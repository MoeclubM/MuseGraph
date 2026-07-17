"""
JSON-based Pi tool loop for MuseGraph Agent.

LLM returns structured actions; the runtime executes MuseGraph tools and
feeds results back until the model emits action=finish or max iterations.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.llm_json import extract_json_object
from app.services.agent.subagent_profiles import (
    SubagentProfile,
    SUBAGENT_PROFILES,
    WRITE_BACK_TOOLS,
)

logger = logging.getLogger(__name__)

PI_SYSTEM_PROMPT = """你是 MuseGraph 创作 Agent（Pi 模式）。
不要假设项目是小说——根据用户目标与已有资料自行判断文本类型与任务。
你可调用工具完成：分析/拆解文本、规划记忆结构、读写事实库、写入结构化记忆与图谱、检索 RAG、读写文档单元、生成正文、spawn 子代理处理专项任务。
每种任务由你决定需要提取/存储哪些结构化字段，并写入记忆与图谱供后续创作调用。

通用写作流程（适用于小说/报告/演讲稿/文案等任何文本类型）：
1. 理解用户目标 → 判断 text_type 与 task_kind → 决定结构化字段
2. 必要时先 store_structured_memory 落盘结构化数据（worldview/characters/timeline/claims/evidence 等，字段由你自定）
3. 生成正文：自己写出内容，用 write_document_unit(content=正文) 落盘
4. 写完后 build_project_memory 构建 cognee 记忆与图谱
5. 可选 spawn_subagent(graph_extractor) 提取实体与关系
6. 后续内容通过 memory_search 检索已构建的记忆

批量多章节/多段落生成：
- 首先 store_structured_memory
- 逐章/逐段自己写正文并 write_document_unit 落盘
- 每写完一章/一段立即 build_project_memory
- 最后可选一次全局 build_project_memory

绝对不要中断流程向用户提问、要求确认或要求用户执行任何操作。
始终使用用户输入的语言回复。用户写中文就用中文输出，用户写英文就用英文输出。"""

MUSEGRAPH_TOOLS: list[dict[str, Any]] = [
    {
        "name": "set_session_title",
        "description": "为当前 Agent 会话设置模型生成的短标题；用于会话列表与子代理导航",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "根据用户目标与项目上下文概括生成的短标题，不要直接复制完整用户输入",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "find_skills",
        "description": (
            "在本项目启用的 skill 池中按描述/标签模糊检索；返回 slug + name + 短描述。"
            "命中后用 load_skill 切换。仅 orchestrator 可见。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "关键字；可空（返回前 N 条）"},
                "scope": {
                    "type": "string",
                    "enum": ["chat", "suggest", "operation"],
                    "default": "chat",
                },
                "limit": {"type": "integer", "default": 8},
            },
        },
    },
    {
        "name": "load_skill",
        "description": (
            "切换当前会话激活的 skill：后续轮次的 system prompt、工具白名单、"
            "默认模型组件按该 skill 重新解析。slug 必须来自本项目可见的启用列表。"
            "仅 orchestrator 可见。"
        ),
        "parameters": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    },
    {
        "name": "unload_skill",
        "description": "退出当前 skill，回到通用 orchestrator 模式。仅 orchestrator 可见。",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "memory_search",
        "description": "RAG 检索项目记忆，返回相关片段与关系上下文",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索查询"},
                "top_k": {"type": "integer", "description": "返回条数", "default": 6},
            },
            "required": ["query"],
        },
    },
    {
        "name": "store_structured_memory",
        "description": "将 Agent 决定的结构化记忆/图谱写入 cognee",
        "parameters": {
            "type": "object",
            "properties": {
                "text_type": {"type": "string"},
                "task_kind": {"type": "string"},
                "memory_schema": {"type": "object"},
                "structured_memory": {"type": "object"},
                "graph": {"type": "object"},
            },
            "required": ["structured_memory"],
        },
    },
    {
        "name": "list_facts",
        "description": "列出项目事实库记录，含同步状态、实体与关系摘要",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "read_fact",
        "description": "读取单条项目事实的完整内容、实体和关系",
        "parameters": {
            "type": "object",
            "properties": {"fact_id": {"type": "string"}},
            "required": ["fact_id"],
        },
    },
    {
        "name": "create_fact",
        "description": "在项目事实库创建事实，并自动启动 cognee/图谱同步任务",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "source_kind": {"type": "string", "default": "agent"},
                "source_ref": {"type": "object"},
                "metadata": {"type": "object"},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "update_fact",
        "description": "更新项目事实库记录，并自动启动明确的项目记忆重建任务",
        "parameters": {
            "type": "object",
            "properties": {
                "fact_id": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "source_kind": {"type": "string"},
                "source_ref": {"type": "object"},
                "metadata": {"type": "object"},
            },
            "required": ["fact_id"],
        },
    },
    {
        "name": "sync_fact_memory",
        "description": "手动启动指定事实的 cognee/图谱同步任务",
        "parameters": {
            "type": "object",
            "properties": {"fact_id": {"type": "string"}},
            "required": ["fact_id"],
        },
    },
    {
        "name": "search_entities",
        "description": "搜索项目实体（事实提取、结构化记忆、事实图谱），可按类型过滤",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "entity_type": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "batch_update_entities",
        "description": "批量更新事实实体/关系，可选合并 structured_memory，并触发记忆同步",
        "parameters": {
            "type": "object",
            "properties": {
                "updates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "fact_id": {"type": "string"},
                            "title": {"type": "string"},
                            "content": {"type": "string"},
                            "entities": {"type": "array", "items": {"type": "object"}},
                            "relationships": {"type": "array", "items": {"type": "object"}},
                            "metadata": {"type": "object"},
                        },
                        "required": ["fact_id"],
                    },
                },
                "structured_memory": {"type": "object"},
                "sync_memory": {"type": "boolean", "default": True},
            },
            "required": ["updates"],
        },
    },
    {
        "name": "spawn_subagent",
        "description": "启动持久化子代理处理专项任务；必须由编排者明确选择子代理模型",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "subagent_role": {
                    "type": "string",
                    "enum": [
                        "writer",
                        "auditor",
                        "evaluator",
                        "planner",
                        "composer",
                        "reviser",
                        "updater",
                        "memory_builder",
                        "graph_extractor",
                    ],
                },
                "model": {"type": "string", "description": "子代理使用的已配置可用聊天模型 ID"},
                "target_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选：需要让子代理聚焦的具体引用（document_unit_id、fact_id、文件路径或 RAG 节点 id）",
                },
                "context_scope": {
                    "type": "string",
                    "enum": ["full", "intent_only", "targeted"],
                    "description": "可选：覆盖 profile 默认 context_scope，控制传递给子代理的上下文体量",
                },
            },
            "required": ["task", "subagent_role", "model"],
        },
    },
    {
        "name": "list_document_units",
        "description": "列出项目文档单元",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_project_files",
        "description": "列出项目真实工作区目录中的文件，返回相对路径、大小、类型和工作区根目录",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "read_project_file",
        "description": "读取项目真实工作区目录中的文本文件内容（txt/md/json/docx/pdf）",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "项目工作区内的相对路径"}},
            "required": ["path"],
        },
    },
    {
        "name": "read_document_unit",
        "description": "读取指定文档单元内容",
        "parameters": {
            "type": "object",
            "properties": {"document_unit_id": {"type": "string"}},
            "required": ["document_unit_id"],
        },
    },
    {
        "name": "write_document_unit",
        "description": (
            "写入文档单元（小说章节/论文章节/文档段落等）。"
            "传 content 参数写入完整正文。mode=create 新建，replace 替换，append 追加。"
            "正文由你自己（agent）在 content 里写出，不要传空或占位文本。"
            "写作前可用 memory_search 检索项目记忆，用 read_document_unit 读取前文保持衔接。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_unit_id": {"type": "string", "description": "目标文档单元 id；新建时省略"},
                "title": {"type": "string", "description": "文档单元标题（新建时必填）"},
                "content": {"type": "string", "description": "完整正文文本，由 agent 自己写出"},
                "mode": {"type": "string", "enum": ["append", "replace", "create"], "default": "create"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "get_memory_graph",
        "description": "获取记忆可视化图谱 nodes/edges",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "build_project_memory",
        "description": "将项目文档单元文本全量构建/同步到 cognee 向量库与关系图谱，无需参数",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "report_finding",
        "description": (
            "子代理审阅/评估专用：把一条结构化结论写入 agent_workspace.findings，"
            "供主代理或后续步骤消费。不修改项目文档、事实或记忆。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                "title": {"type": "string"},
                "evidence": {
                    "type": "string",
                    "description": "具体证据引用：document_unit_id / fact_id / 文件路径 + 局部摘要",
                },
                "suggestion": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["severity", "title"],
        },
    },
    {
        "name": "propose_state_delta",
        "description": (
            "子代理 updater 专用：把建议的状态变更写入 agent_workspace.proposed_state_deltas，"
            "由主代理决定是否 apply。不直接修改 ProjectFact / structured_memory。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "目标域：fact / structured_memory / graph",
                },
                "op": {"type": "string", "enum": ["create", "update", "delete", "merge"]},
                "path": {
                    "type": "string",
                    "description": "受影响实体的引用：fact:<id> 或 structured_memory.<key>",
                },
                "value": {"type": ["object", "array", "string", "number", "boolean", "null"]},
                "evidence": {"type": "string"},
            },
            "required": ["target", "op", "path"],
        },
    },
    {
        "name": "apply_state_deltas",
        "description": (
            "审阅并应用 agent_workspace.proposed_state_deltas 中的若干条 delta。"
            "每条 delta 必须通过 schema 校验；失败的整批回滚。仅 orchestrator 可见。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "delta_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "格式：<session_id>:delta:<index>",
                },
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["delta_ids"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "用 DuckDuckGo 搜索网络，返回标题/URL/摘要列表。用于论文研究、事实核查、"
            "获取最新信息。搜索结果不等于事实——交叉验证后再写入事实库或正文。"
            "仅在需要外部信息时调用，不要滥用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询词"},
                "max_results": {"type": "integer", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": (
            "下载 URL 内容到项目工作区。图片（png/jpg/jpeg/gif/webp/svg）直接保存到 uploads/ 并返回文件路径；"
            "文本/HTML 返回提取后的正文内容（截断到 8000 字符）。用于获取网络图片或网页文本。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要下载的完整 URL（http/https）"},
                "filename": {"type": "string", "description": "保存文件名（可选，未指定时从 URL 推断）"},
            },
            "required": ["url"],
        },
    },
]

PI_TOOL_ACTION_PROMPT = """{system}

可用工具（JSON Schema）：
{tools_json}

每次回复必须是单个 JSON 对象，两种动作之一：
1) 调用工具：{{"action":"tool_call","tool":"<name>","args":{{...}},"reason":"..."}}
2) 结束任务：{{"action":"finish","output":"给用户的中文摘要","text_type":"...","task_kind":"...","memory_schema":{{}},"structured_memory":{{}},"graph":{{"nodes":[],"edges":[]}},"next_actions":[]}}

规则：
- 不要假设文本类型；先使用 Project Context Snapshot、list_project_files/read_project_file、list_document_units/read_document_unit 或 memory_search 再决定提取维度。
- 如果对话中已经包含 Project Context Snapshot，优先使用其中的文档单元、cognee RAG 节点与关系图谱；信息足够时可以直接 finish，不要为了确认已给出的上下文而重复调用工具。
- 项目文件来自真实工作区目录；用户提到上传文件或文件路径时，优先 list_project_files/read_project_file 读取原文，再分析、入库或创作。
- 事实类任务：使用 list_facts/read_fact/create_fact/update_fact/sync_fact_memory/search_entities/batch_update_entities 管理项目级事实库与实体；事实或实体变更会自动进入记忆同步任务。
{role_rules}
- 你的回复是控制器 JSON action，必须短小。
- 一次只做一个 action；收到 tool_result 后再决定下一步。

finish 中的 output 字段要求：
- output 是你对已完成工作的简明总结，供用户快速理解执行结果
- 用中文输出（除非用户使用英文），包含：做了什么、产出了什么、下一步建议
- 类似 AI 对话中的"thinking summary"，帮助用户追踪 agent 的决策轨迹
- 不要放 raw JSON 或工具调用细节到 output 中
"""

MAX_TOOL_RESULT_CHARS = 12000

PI_ACTION_RESPONSE_SCHEMA: dict[str, Any] = {
    "x_musegraph_response_format": "json_object",
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["tool_call", "finish"]},
        "tool": {"type": "string"},
        "args": {"type": "object"},
        "reason": {"type": "string"},
        "output": {"type": "string"},
        "text_type": {"type": "string"},
        "task_kind": {"type": "string"},
        "memory_schema": {"type": "object"},
        "structured_memory": {"type": "object"},
        "graph": {"type": "object"},
        "next_actions": {"type": "array", "items": {}},
    },
    "required": ["action"],
    "additionalProperties": False,
}

TOOL_STEP_MESSAGES = {
    "set_session_title": "正在为当前会话生成标题",
    "find_skills": "正在检索可用 skill",
    "load_skill": "正在加载 skill",
    "unload_skill": "正在退出当前 skill",
    "memory_search": "正在检索项目记忆与关系上下文",
    "store_structured_memory": "正在写入结构化记忆与图谱",
    "build_project_memory": "正在同步项目文档到 cognee 记忆与图谱",
    "spawn_subagent": "正在启动子代理处理专项任务",
    "list_project_files": "正在读取项目工作区文件列表",
    "read_project_file": "正在读取项目文件内容",
    "list_document_units": "正在读取项目文档单元列表",
    "read_document_unit": "正在读取文档单元内容",
    "write_document_unit": "正在写入文档单元",
    "list_facts": "正在读取项目事实库",
    "read_fact": "正在读取项目事实详情",
    "create_fact": "正在创建项目事实并触发记忆同步",
    "update_fact": "正在更新项目事实并触发记忆同步",
    "sync_fact_memory": "正在同步事实到项目记忆",
    "search_entities": "正在搜索项目实体",
    "batch_update_entities": "正在批量更新实体与事实",
    "get_memory_graph": "正在读取记忆图谱",
    "report_finding": "子代理记录审阅结论",
    "propose_state_delta": "子代理提交状态变更建议",
    "apply_state_deltas": "正在批量应用 state delta",
    "web_search": "正在搜索网络",
    "fetch_url": "正在下载网络资源",
}


def build_tools_json(
    *,
    role: str = "orchestrator",
    profile: SubagentProfile | None = None,
    skill_allowed_tools: frozenset[str] | None = None,
) -> str:
    """Render the tool catalogue visible to the LLM.

    Orchestrator sees every tool except the subagent-only output channels
    (``report_finding`` / ``propose_state_delta``) — those are not for the
    main agent to call directly. Subagents see only the tools their
    profile allows; the dispatcher enforces the same whitelist server-side.

    Skill management tools (``find_skills``/``load_skill``/``unload_skill``)
    are *always* present for the orchestrator, even when an active skill's
    ``allowed_tools`` whitelist would otherwise hide them — otherwise a
    skill could trap itself with no way out.
    """

    skill_management_tools = {"find_skills", "load_skill", "unload_skill"}
    is_orchestrator = str(role or "orchestrator").strip() == "orchestrator"
    if is_orchestrator:
        tools = [
            tool for tool in MUSEGRAPH_TOOLS
            if tool.get("name") not in {"report_finding", "propose_state_delta"}
        ]
        if skill_allowed_tools:
            tools = [
                tool for tool in tools
                if tool.get("name") in skill_allowed_tools
                or tool.get("name") in skill_management_tools
            ]
        return json.dumps(tools, ensure_ascii=False, indent=2)

    if profile is None:
        profile = SUBAGENT_PROFILES.get(role)
    if profile is None:
        # Unknown role: fall back to safest read-only base.
        tools = [
            tool for tool in MUSEGRAPH_TOOLS
            if tool.get("name") not in ({"spawn_subagent"} | skill_management_tools)
        ]
        return json.dumps(tools, ensure_ascii=False, indent=2)

    # Subagents never see skill management tools, even if their profile
    # somehow listed them.
    tools = [
        tool for tool in MUSEGRAPH_TOOLS
        if tool.get("name") in profile.allowed_tools
        and tool.get("name") not in skill_management_tools
    ]
    return json.dumps(tools, ensure_ascii=False, indent=2)


def build_initial_messages(
    instruction: str,
    *,
    memory_block: str = "",
    session_title: str | None = None,
    available_models: list[str] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if history:
        for msg in history[-8:]:
            role = str(msg.get("role") or "user")
            if role not in {"user", "assistant"}:
                role = "user"
            content = str(msg.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content[:4000]})
    user_parts = [
        "Session metadata:\n"
        f"- current_title: {session_title.strip() if session_title else '<unset>'}\n"
        f"- available_chat_models: {json.dumps(available_models or [], ensure_ascii=False)}",
        f"User instruction:\n{instruction}",
    ]
    if memory_block:
        user_parts.append(f"Creative memory context:\n{memory_block}")
    messages.append({"role": "user", "content": "\n\n".join(user_parts)})
    return messages


def build_loop_system_prompt(
    *,
    role: str = "orchestrator",
    profile: SubagentProfile | None = None,
    skill_system_prompt: str | None = None,
    skill_allowed_tools: frozenset[str] | None = None,
    skill_menu: str | None = None,
    active_skill_slug: str | None = None,
    pipeline_kind: str | None = None,
    active_pack_display: str | None = None,
) -> str:
    is_orchestrator = str(role or "orchestrator").strip() == "orchestrator"
    if not is_orchestrator and profile is None:
        profile = SUBAGENT_PROFILES.get(role)
    role_rules = (
        "- 当 Session metadata 显示 current_title 为空时，第一步必须调用 set_session_title。标题由你根据用户目标和项目上下文概括生成，不要复制完整用户输入；已有标题时不要重复改名，除非用户明确要求重命名。\n"
        "- 生成类任务（章节、续写、长文案）：先 memory_search 检索项目记忆，再自己写出完整正文，然后用 write_document_unit(content=正文) 落盘。正文写在 content 参数里。\n"
        "- 创作第一章时不要使用默认的 Main Draft 文本，而是新建文本（省略 document_unit_id，传入 title 如「第一章 xxx」）。\n"
        "- 多章节任务：逐章自己写正文并 write_document_unit(content=正文) 落盘，每章写前 read_document_unit 读取前文。\n"
        "- 项目初始化、长篇规划、结构设计：必须先 store_structured_memory 写入世界观/角色/大纲等结构化记忆，再逐章自己写正文并 write_document_unit 落盘；特别复杂时才 spawn_subagent(planner)。新项目写作前先 build_project_memory（如有正文）或 store_structured_memory 建立项目记忆基底。\n"
        "- 分析类任务：先读取真实文件或文档单元；复杂分析可 spawn_subagent(planner 或 graph_extractor)，再 store_structured_memory → 可选 build_project_memory。\n"
        "- 子代理是重型操作（每个子代理是完整的 Agent 循环），仅在任务确实需要独立分工时使用；简单任务直接用工具完成。\n"
        "- 启动子代理时必须提供 subagent_role 与 model；model 必须从 Session metadata.available_chat_models 中选择一个原样填写，不要编造、改写或省略 model。可选择性带上 target_refs（document_unit_id/fact_id 等）让子代理只看必要上下文。子代理职责由系统提示词注入，不要把角色说明写进 task。\n"
        "- write_document_unit 用于落盘你写好的正文（content 参数）。\n"
        "- 在选择动作前可先用 find_skills 检索本项目启用的 skill；命中后用 load_skill(slug) 切换；不再需要时用 unload_skill 恢复通用模式。"
        "- 创作/生成任务开始时不要先调用 get_memory_graph 摸底；按任务需要 store_structured_memory、memory_search、write_document_unit 推进；仅在用户明确要求查看关系图或排查记忆时再 get_memory_graph。"
        if is_orchestrator
        else _build_subagent_role_rules(role=role, profile=profile)
    )
    if is_orchestrator and pipeline_kind == "long_form_write":
        role_rules += (
            "\n- 长文写作：逐章自己写正文并用 write_document_unit 落盘，每章写完后 build_project_memory 构建项目记忆。"
            "需要审计时 spawn_subagent(auditor)；需要修订时 spawn_subagent(reviser)。不要中断流程向用户提问。"
        )
    elif is_orchestrator and pipeline_kind == "fact_extraction":
        role_rules += (
            "\n- 事实抽取管线：可 spawn_subagent(updater) 收集并提交 propose_state_delta，"
            "再由你用 apply_state_deltas 批量审阅落盘。不要让 updater 直接修改事实。"
        )
    elif is_orchestrator and pipeline_kind == "review_only":
        role_rules += (
            "\n- 仅审阅：spawn_subagent(auditor) 进行结构化审计，把 issues 与 dimensions 返回给用户。不要修改文档或事实。"
        )
    system_text = PI_SYSTEM_PROMPT
    if not is_orchestrator and profile is not None:
        system_text = profile.system_prompt
    if is_orchestrator and skill_system_prompt:
        system_text = f"{skill_system_prompt.strip()}\n\n{system_text}"
    if is_orchestrator and active_pack_display and active_pack_display != "通用文本":
        system_text = (
            f"{system_text}\n\n"
            f"本项目文本类型：<{active_pack_display}>。"
        )
    if is_orchestrator and skill_menu:
        active = (active_skill_slug or "general").strip() or "general"
        system_text = (
            f"{system_text}\n\n"
            "本项目启用的 skill（可用 find_skills/load_skill 切换；@slug 已自动加载）：\n"
            f"{skill_menu.strip()}\n"
            f"当前激活：{active}"
        )
    return PI_TOOL_ACTION_PROMPT.format(
        system=system_text,
        tools_json=build_tools_json(
            role=role,
            profile=profile,
            skill_allowed_tools=skill_allowed_tools if is_orchestrator else None,
        ),
        role_rules=role_rules,
    )


def _build_subagent_role_rules(
    *,
    role: str,
    profile: SubagentProfile | None,
) -> str:
    base_rules = (
        "- 你是子代理，不是主编排者；不要调用 spawn_subagent。\n"
        "- 工具白名单由系统在服务端强制；不在白名单内的工具会被拒绝执行。\n"
        "- 收到 target_refs 时只关注这些引用对应的内容；其它内容仅作背景。\n"
        "- finish.output 必须严格符合本 role 的 output_schema；缺字段会被退回重试。\n"
    )
    if profile is None:
        return base_rules + "- 未识别的 role：仅使用只读工具，禁止任何写回。"
    schema_required = (profile.output_schema or {}).get("required") or []
    schema_hint = (
        f"- finish.output 必填字段：{', '.join(schema_required)}\n"
        if schema_required else ""
    )
    write_hint = (
        "- 你具有写回权限：可调用本 role 白名单中的写入类工具，但仅限于本 role 的职责范围。\n"
        if profile.can_write_back else
        "- 你没有写回权限：禁止调用任何 store_structured_memory / build_project_memory / "
        "write_document_unit / create_fact / update_fact / "
        "sync_fact_memory / batch_update_entities。\n"
    )
    scope_hint = (
        "- context_scope=targeted：仅基于 target_refs 与必要 RAG 检索决策，"
        "不要扩展到无关的项目内容。\n"
        if profile.context_scope == "targeted" else
        "- context_scope=intent_only：仅基于 user instruction 与候选概要做判断，"
        "不主动拉取额外上下文。\n"
        if profile.context_scope == "intent_only" else
        "- context_scope=full：可以使用 Project Context Snapshot 中的全部信息。\n"
    )
    return base_rules + schema_hint + write_hint + scope_hint


def parse_pi_action(raw: str) -> dict[str, Any] | None:
    parsed = extract_json_object(raw)
    if not parsed:
        return None
    tool_names = {str(item.get("name") or "") for item in MUSEGRAPH_TOOLS}
    if isinstance(parsed.get("tool_call"), dict):
        tool_call = parsed["tool_call"]
        parsed = {
            "action": "tool_call",
            "tool": tool_call.get("tool") or tool_call.get("name"),
            "args": tool_call.get("args") if "args" in tool_call else tool_call.get("arguments", {}),
            "reason": parsed.get("reason") or tool_call.get("reason") or "",
        }
    if "arguments" in parsed and "args" not in parsed:
        parsed["args"] = parsed["arguments"]
    if "tool" not in parsed and str(parsed.get("name") or "") in tool_names:
        parsed["tool"] = parsed["name"]
    if isinstance(parsed.get("args"), str):
        try:
            args_value = json.loads(parsed["args"])
        except json.JSONDecodeError:
            return None
        if not isinstance(args_value, dict):
            return None
        parsed["args"] = args_value
    action = str(parsed.get("action") or "").strip().lower()
    if action in tool_names and "tool" not in parsed:
        parsed["tool"] = action
        parsed["args"] = {
            key: value
            for key, value in parsed.items()
            if key not in {"action", "tool", "reason", "args", "arguments"}
        }
        parsed["action"] = "tool_call"
        return parsed
    if action not in {"tool_call", "finish"}:
        if parsed.get("tool") and str(parsed.get("tool")) in tool_names:
            if "args" not in parsed:
                parsed["args"] = {}
            parsed["action"] = "tool_call"
            return parsed
        if parsed.get("output") or parsed.get("structured_memory"):
            parsed["action"] = "finish"
            return parsed
        return None
    return parsed




def format_tool_result_preview(tool_name: str, result: dict[str, Any]) -> str:
    """Human-readable preview for chat timeline (not raw JSON dumps)."""
    if not isinstance(result, dict):
        return truncate_tool_result({"value": result})
    if not result.get("ok", True) and result.get("error"):
        return f"失败：{result.get('error')}"
    name = str(tool_name or "").strip()
    if name == "write_document_unit":
        title = str(result.get("title") or "").strip()
        cid = str(result.get("document_unit_id") or result.get("chapter_id") or "").strip()
        length = result.get("content_length")
        mode = str(result.get("mode") or "").strip()
        parts = ["已写入文档单元"]
        if title:
            parts.append(f"《{title}》")
        if isinstance(length, int) and length > 0:
            parts.append(f"{length} 字")
        if mode:
            parts.append(f"({mode})")
        if cid:
            parts.append(f"id={cid[:8]}…")
        return " ".join(parts)
    if name == "store_structured_memory":
        sm = result.get("structured_memory")
        if isinstance(sm, dict) and sm:
            keys = list(sm.keys())[:6]
            return "已写入结构化记忆：" + "、".join(str(k) for k in keys)
        return "已写入结构化记忆"
    if name == "get_memory_graph":
        g = result.get("graph") if isinstance(result.get("graph"), dict) else {}
        nodes = len(g.get("nodes") or []) if isinstance(g, dict) else 0
        edges = len(g.get("edges") or []) if isinstance(g, dict) else 0
        return f"已读取记忆图谱（节点 {nodes}，边 {edges}）"
    if name == "set_session_title":
        t = str(result.get("session_title") or "").strip()
        return f"会话标题：{t}" if t else "已更新会话标题"
    return truncate_tool_result(result)[:1000]

def truncate_tool_result(result: dict[str, Any]) -> str:
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + "...(truncated)"


def action_to_step_record(
    *,
    step_index: int,
    action: dict[str, Any],
    status: str,
    output: str | None = None,
    role_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if action.get("action") == "tool_call":
        step_type = str(action.get("tool") or "tool")
        message = TOOL_STEP_MESSAGES.get(step_type) or str(action.get("reason") or f"Tool {step_type}")
    else:
        step_type = "finalize"
        message = "Task complete"
    metadata: dict[str, Any] = {"pi_loop": True, "action": action}
    if role_meta:
        metadata["role_meta"] = role_meta
    record = {
        "step_id": f"pi-loop-{step_index}",
        "step_type": step_type,
        "status": status,
        "message": message,
        "output": output,
        "metadata": metadata,
    }
    if role_meta:
        record["role_meta"] = role_meta
    args = action.get("args") if isinstance(action.get("args"), dict) else {}
    if action.get("action") == "tool_call":
        record["tool_args"] = args
        if step_type == "spawn_subagent":
            record["agent_role"] = args.get("subagent_role")
            record["model"] = args.get("model")
    return record


def role_meta_for(role: str) -> dict[str, Any] | None:
    """Render a compact role descriptor for UI consumption.

    Returns ``None`` for the orchestrator and for unknown roles — only
    sub-agent steps get a ``role_meta`` block so the user can see *how*
    each child differs (tool whitelist, scope, write-back).
    """

    profile = SUBAGENT_PROFILES.get((role or "").strip())
    if profile is None:
        return None
    return {
        "role": profile.role,
        "scope": profile.context_scope,
        "can_write_back": profile.can_write_back,
        "tool_whitelist": sorted(profile.allowed_tools),
        "max_iterations": profile.max_iterations,
        "default_model_component": profile.default_model_component,
    }
