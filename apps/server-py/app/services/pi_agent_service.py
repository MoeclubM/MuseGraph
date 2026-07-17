"""
MuseGraph Pi Agent Service.

Implements a Pi-style minimal agent (short system prompt + focused tools) on top of
the MuseGraph memory/RAG/graph stack. Tool execution delegates to existing services;
the multi-step Pi tool loop is the only production runtime (Phase B removed the
legacy AgentOrchestrator dispatch path).
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Awaitable, Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session
from app.models.project import AgentMessage, AgentSession, AgentStep, ProjectFact, TextOperation, TextProject
from app.models.user import User
from app.services.ai import (
    call_llm,
    component_key_for_operation,
    get_available_models,
    llm_billing_scope,
    resolve_explicit_component_model,
)
from app.services.pi_tool_loop import (
    MUSEGRAPH_TOOLS,
    PI_ACTION_RESPONSE_SCHEMA,
    PI_SYSTEM_PROMPT,
    action_to_step_record,
    build_initial_messages,
    build_loop_system_prompt,
    parse_pi_action,
    role_meta_for,
    truncate_tool_result,
)
from app.services.agent.subagent_profiles import (
    SubagentProfile,
    SUBAGENT_PROFILES,
    SUBAGENT_ROLES,
    WRITE_BACK_TOOLS,
    get_profile,
    validate_finish_output,
)
from app.services.agent.skills import (
    ResolvedSkill,
    find_project_skills,
    list_project_visible_skills,
    load_active_skill,
)
from app.services.chapter_writeback import write_chapter_content
from app.services.creative_memory import build_creative_memory_pack, render_creative_memory_block
from app.services.fact_entities import (
    collect_project_entities,
    group_entities_by_type,
    merge_structured_memory,
    search_project_entities,
)
from app.services.fact_memory import apply_fact_hash, schedule_fact_memory_sync
from app.services.memory_service import memory_rag_query
from app.services.memory_backend import writeback_agent as writeback_agent_memory
from app.services.project_workspace import write_project_workspace_version_snapshot_from_db

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

# In-memory cancellation flags (checked by run_flow on each iteration)
_session_cancel_flags: dict[str, bool] = {}


def request_session_cancel(session_id: str) -> None:
    """Request cancellation of a running agent session."""
    _session_cancel_flags[session_id] = True
    logger.info("Cancel requested for session %s", session_id)


def is_session_cancelled(session_id: str) -> bool:
    """Check whether a session has been requested to cancel."""
    return _session_cancel_flags.pop(session_id, False)


@dataclass
class PiAgentContext:
    project_id: str
    user_id: str
    model: str
    session_id: str
    parent_operation_id: str | None = None
    role: str = "orchestrator"
    root_session_id: str | None = None
    parent_step_id: str | None = None
    current_step_id: str | None = None
    pending_child_session_id: str | None = None
    project: TextProject | None = None
    user: User | None = None
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    emit_progress: ProgressCallback | None = None
    available_chat_models: list[str] = field(default_factory=list)
    workspace_dirty: bool = False
    subagent_profile: SubagentProfile | None = None
    target_refs: list[str] = field(default_factory=list)
    context_scope: str | None = None
    skill_slug: str | None = None
    skill_allowed_tools: frozenset[str] | None = None


class MuseGraphPiAgent:
    """Pi-style agent facade with MuseGraph-native tools."""

    async def _emit(self, cb: ProgressCallback | None, event: str, data: dict[str, Any]) -> None:
        if cb is None:
            return
        payload = {"event": event, **data}
        try:
            await cb(payload)
        except Exception:
            logger.debug("Pi agent progress callback error: %s", traceback.format_exc())

    def _log_tool_result(
        self,
        ctx: PiAgentContext,
        tool_name: str,
        args: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        ctx.tool_log.append({
            "tool": tool_name,
            "args": args,
            "result_preview": json.dumps(result, ensure_ascii=False)[:500],
        })
        return result

    def _fact_payload(self, fact: ProjectFact) -> dict[str, Any]:
        return {
            "id": fact.id,
            "project_id": fact.project_id,
            "created_by_user_id": fact.created_by_user_id,
            "created_by_agent_session_id": fact.created_by_agent_session_id,
            "source_kind": fact.source_kind,
            "source_ref": fact.source_ref,
            "title": fact.title,
            "content": fact.content,
            "metadata": fact.metadata_,
            "ontology_snapshot": fact.ontology_snapshot,
            "entities": fact.entities,
            "relationships": fact.relationships,
            "content_hash": fact.content_hash,
            "memory_status": fact.memory_status,
            "memory_task_id": fact.memory_task_id,
            "memory_error": fact.memory_error,
            "created_at": fact.created_at.isoformat() if fact.created_at else "",
            "updated_at": fact.updated_at.isoformat() if fact.updated_at else "",
        }

    async def _require_available_chat_model(self, model: str, db: AsyncSession) -> None:
        model_id = str(model or "").strip()
        if not model_id:
            raise RuntimeError("spawn_subagent requires model.")
        available = await get_available_models(db)
        available_ids = {str(item.get("id") or "").strip() for item in available if isinstance(item, dict)}
        if model_id not in available_ids:
            raise RuntimeError(f"spawn_subagent model is not configured or active: {model_id}")

    async def _record_child_event(self, session_id: str, event_type: str, data: dict[str, Any]) -> None:
        async with async_session() as db:
            session = await db.get(AgentSession, session_id)
            if session is None:
                raise RuntimeError(f"Child agent session not found: {session_id}")

            if event_type == "plan":
                session.plan = data
                workspace = dict(session.workspace or {})
                for key in ("text_type", "task_kind", "memory_schema", "structured_memory", "graph", "writing_plan"):
                    if data.get(key):
                        workspace[key] = data[key]
                session.workspace = workspace

            if event_type == "session_update":
                if "title" in data:
                    title = str(data.get("title") or "").strip()
                    session.title = title or None

            if event_type in {"step_start", "step_progress", "step_complete", "step_failed"}:
                step_type = str(data.get("step_type") or "step")
                if step_type != "plan":
                    result = await db.execute(
                        select(AgentStep)
                        .where(AgentStep.session_id == session_id)
                        .where(AgentStep.step_type == "plan")
                        .where(AgentStep.status == "running")
                        .order_by(AgentStep.created_at.desc())
                        .limit(1)
                    )
                    running_plan_step = result.scalar_one_or_none()
                    if running_plan_step is not None:
                        running_plan_step.status = "completed"
                        running_plan_step.message = "Agent plan selected next action"
                step_number = data.get("step")
                step_id = str(data.get("step_id") or f"{session_id}:step:{step_number or 0}:{step_type}")
                step = await db.get(AgentStep, step_id)
                if step is not None and step.session_id != session_id:
                    raise RuntimeError(
                        f"Agent step id collision: {step_id} belongs to session {step.session_id}, not {session_id}"
                    )
                if step is None:
                    step = AgentStep(
                        id=step_id,
                        session_id=session_id,
                        step_type=step_type,
                        status="pending",
                        message="",
                    )
                    db.add(step)
                step.step_index = step_number
                step.total_steps = data.get("total_steps")
                step.step_type = step_type
                if event_type == "step_start":
                    step.status = "running"
                elif event_type == "step_failed":
                    step.status = "failed"
                else:
                    step.status = str(data.get("status") or ("completed" if event_type == "step_complete" else step.status)).lower()
                step.message = str(data.get("message") or "")
                step.output = str(data.get("output")) if data.get("output") is not None else step.output
                step.output_preview = str(data.get("output_preview")) if data.get("output_preview") is not None else step.output_preview
                step.metadata_ = data.get("metadata") if isinstance(data.get("metadata"), dict) else step.metadata_
                step.child_session_id = data.get("child_session_id")
                step.agent_role = data.get("agent_role")
                step.model = data.get("model")
                step.tool_args = data.get("tool_args") if isinstance(data.get("tool_args"), dict) else step.tool_args
                step.tool_result_preview = data.get("tool_result_preview")

            if event_type == "complete":
                result = await db.execute(
                    select(AgentStep)
                    .where(AgentStep.session_id == session_id)
                    .where(AgentStep.step_type == "plan")
                    .where(AgentStep.status == "running")
                    .order_by(AgentStep.created_at.desc())
                    .limit(1)
                )
                running_plan_step = result.scalar_one_or_none()
                if running_plan_step is not None:
                    running_plan_step.status = "completed"
                    running_plan_step.message = "Agent plan completed"
                session.status = str(data.get("status") or "completed").lower()
                output = str(data.get("output") or data.get("summary") or data.get("output_preview") or "").strip()
                workspace = dict(session.workspace or {})
                for key in ("structured_memory", "graph", "memory_schema", "text_type", "task_kind"):
                    if data.get(key):
                        workspace[key] = data[key]
                session.workspace = workspace
                if output:
                    db.add(AgentMessage(
                        id=uuid4().hex,
                        session_id=session_id,
                        role="assistant",
                        content=output,
                        metadata_={"event": "complete"},
                    ))

            if event_type == "error":
                session.status = "failed"
                message = str(data.get("message") or "Child agent failed")
                db.add(AgentMessage(
                    id=uuid4().hex,
                    session_id=session_id,
                    role="assistant",
                    content=f"Agent failed: {message}",
                    metadata_={"event": "error"},
                ))

            await db.commit()

    async def build_project_context_snapshot(
        self,
        *,
        project: TextProject,
        project_id: str,
        instruction: str,
        db: AsyncSession,
    ) -> str:
        """Build a compact project/RAG snapshot before the first Pi model call.

        This keeps PI_TOOL_LOOP enabled while avoiding slow first-turn tool chatter:
        the model still decides the task, but it starts with current document units,
        cognee export-backed RAG nodes, and graph edges already visible.
        """
        query_text = " ".join(str(instruction or "").strip().lower().split())
        tokens = []
        seen_tokens: set[str] = set()
        for token in re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{1,8}", query_text):
            if token in seen_tokens:
                continue
            seen_tokens.add(token)
            tokens.append(token)

        def score_text(value: str) -> int:
            haystack = str(value or "").lower()
            score = 0
            if query_text and query_text in haystack:
                score += 100
            for token in tokens:
                if token in haystack:
                    score += max(1, min(12, len(token)))
            return score

        def short(value: Any, limit: int) -> str:
            text = str(value or "").strip()
            return text if len(text) <= limit else text[: max(1, limit - 3)] + "..."

        sections: list[str] = []
        sections.append(
            "Project Context Snapshot\n"
            "This snapshot is loaded before the first Pi action to reduce slow-model tool round trips. "
            "Use it as current project evidence; call tools only when more detail or writeback is needed."
        )
        sections.append(
            "Project:\n"
            f"- id: {project_id}\n"
            f"- title: {short(getattr(project, 'title', ''), 160)}\n"
            f"- description: {short(getattr(project, 'description', ''), 500)}"
        )

        chapters = sorted(getattr(project, "chapters", None) or [], key=lambda c: c.order_index)
        unit_lines = []
        ranked_units = []
        for index, ch in enumerate(chapters):
            content = str(getattr(ch, "content", "") or "")
            title = str(getattr(ch, "title", "") or "")
            unit_lines.append(
                f"- {ch.id} | order={getattr(ch, 'order_index', index)} | status={getattr(ch, 'status', '')} | "
                f"chars={len(content)} | title={short(title, 120)}"
            )
            ranked_units.append((score_text(title + "\n" + content), index, ch))
        if unit_lines:
            sections.append("Document units:\n" + "\n".join(unit_lines))

        ranked_units.sort(key=lambda row: (-row[0], row[1]))
        preview_lines = []
        for _score, _index, ch in ranked_units[:3]:
            content = str(getattr(ch, "content", "") or "")
            if not content.strip():
                continue
            preview_lines.append(
                f"[document_unit id={ch.id} title={short(getattr(ch, 'title', ''), 120)}]\n"
                f"{short(content, 1800)}"
            )
        if preview_lines:
            sections.append("Relevant document unit previews:\n" + "\n\n".join(preview_lines))

        from app.services.project_files import list_project_files, read_project_file

        file_bundle = list_project_files(project_id)
        project_files = file_bundle.get("files")
        if not isinstance(project_files, list):
            raise TypeError("Project workspace file listing returned non-list files")
        if project_files:
            file_lines = []
            ranked_files = []
            for index, item in enumerate(project_files):
                if not isinstance(item, dict):
                    raise TypeError("Project workspace file item is not an object")
                path = str(item.get("path") or "")
                file_lines.append(
                    f"- {path} | size={item.get('size')} | content_type={item.get('content_type')} | "
                    f"text_extractable={item.get('text_extractable')}"
                )
                ranked_files.append((score_text(path), index, item))
            sections.append(
                "Project workspace files:\n"
                + "\n".join(file_lines)
            )

            ranked_files.sort(key=lambda row: (-row[0], row[1]))
            file_preview_lines = []
            for _score, _index, item in ranked_files[:3]:
                if not item.get("text_extractable"):
                    continue
                content = read_project_file(project_id, str(item.get("path") or "")).get("content")
                if not str(content or "").strip():
                    continue
                file_preview_lines.append(
                    f"[project_file path={item.get('path')}]\n{short(content, 1800)}"
                )
            if file_preview_lines:
                sections.append("Relevant project file previews:\n" + "\n\n".join(file_preview_lines))

        ontology = getattr(project, "ontology_schema", None)
        if isinstance(ontology, dict) and ontology:
            sections.append("Ontology schema:\n" + short(json.dumps(ontology, ensure_ascii=False, sort_keys=True), 2400))

        state = getattr(project, "creative_state", None)
        if isinstance(state, dict) and state:
            sections.append("Creative state:\n" + short(json.dumps(state, ensure_ascii=False, sort_keys=True, default=str), 3000))

        if str(getattr(project, "memory_id", "") or "").strip():
            try:
                rag = await memory_rag_query(
                    project_id,
                    str(instruction or "")[:400] or str(getattr(project, "title", "") or "project"),
                    top_k=8,
                    db=db,
                )
            except Exception as exc:
                logger.warning("Context snapshot RAG skipped for project %s: %s", project_id, exc)
                rag = {}

            entities = rag.get("entities") if isinstance(rag.get("entities"), list) else []
            relationships = rag.get("relationships") if isinstance(rag.get("relationships"), list) else []

            node_lines = []
            for node in entities[:10]:
                if not isinstance(node, dict):
                    continue
                node_lines.append(
                    f"- {node.get('id')} | type={node.get('type')} | label={short(node.get('label'), 120)}\n"
                    f"  {short(node.get('content'), 700)}"
                )
            if node_lines:
                sections.append("cognee RAG nodes (vector search):\n" + "\n".join(node_lines))

            edge_lines = []
            for edge in relationships[:16]:
                if not isinstance(edge, dict):
                    continue
                edge_lines.append(
                    f"- {edge.get('source')} -[{edge.get('label') or edge.get('type') or 'related'}]-> {edge.get('target')}"
                )
            if edge_lines:
                sections.append("cognee graph edges:\n" + "\n".join(edge_lines))
        else:
            sections.append(
                "cognee: 项目记忆尚未构建。需要 RAG 时先调用 build_project_memory（项目里已有正文时），"
                "或直接基于文档单元与项目文件工作。"
            )

        return "\n\n".join(section for section in sections if section.strip())

    async def execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        ctx: PiAgentContext,
        db: AsyncSession,
    ) -> dict[str, Any]:
        project = ctx.project
        if project is None:
            raise ValueError("Project not loaded")

        # Subagent tool whitelist. Orchestrator (profile is None) can use
        # any tool except the subagent-only output channels.
        profile = ctx.subagent_profile
        skill_management_tools = {"find_skills", "load_skill", "unload_skill"}
        if profile is None:
            if tool_name in {"report_finding", "propose_state_delta"}:
                raise RuntimeError(
                    f"Tool '{tool_name}' is reserved for subagents (auditor/updater),"
                    " not the orchestrator."
                )
            # When a skill restricts the tool catalog, enforce it — but always
            # allow skill management tools so the orchestrator can switch out.
            if (
                ctx.skill_allowed_tools
                and tool_name not in ctx.skill_allowed_tools
                and tool_name not in skill_management_tools
            ):
                raise RuntimeError(
                    f"Tool '{tool_name}' is not allowed by the active skill '{ctx.skill_slug}'."
                )
        else:
            if tool_name in skill_management_tools:
                raise RuntimeError(
                    f"Tool '{tool_name}' is orchestrator-only; subagent role "
                    f"'{profile.role}' cannot manage skills."
                )
            if tool_name == "spawn_subagent":
                raise RuntimeError(
                    f"Subagent role '{profile.role}' is not allowed to spawn another subagent."
                )
            if not profile.can_use_tool(tool_name):
                if tool_name in WRITE_BACK_TOOLS and not profile.can_write_back:
                    raise RuntimeError(
                        f"Subagent role '{profile.role}' has no write-back permission and cannot call '{tool_name}'."
                    )
                raise RuntimeError(
                    f"Tool '{tool_name}' is not in the allowed_tools whitelist for role '{profile.role}'."
                )

        if tool_name == "find_skills":
            query = str(args.get("query") or "").strip()
            scope = str(args.get("scope") or "chat").strip().lower() or "chat"
            limit = int(args.get("limit") or 8)
            hits = await find_project_skills(
                ctx.project_id, query, scope=scope, limit=limit, db=db,
            )
            payload = [
                {
                    "slug": h["slug"],
                    "name": h["name"],
                    "description": h.get("description") or "",
                    "tags": h.get("tags") or [],
                    "is_builtin": h.get("is_builtin", False),
                }
                for h in hits
            ]
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "skills": payload})

        if tool_name == "load_skill":
            slug = str(args.get("slug") or "").strip()
            if not slug:
                raise RuntimeError("load_skill requires slug.")
            visible = await list_project_visible_skills(ctx.project_id, scope=None, db=db)
            available = {s["slug"] for s in visible}
            if slug not in available:
                raise RuntimeError(
                    f"Skill '{slug}' is not enabled for this project. "
                    f"Available: {', '.join(sorted(available))}"
                )
            resolved = await load_active_skill(slug, db)
            if resolved is None:
                raise RuntimeError(f"Skill '{slug}' is not active.")
            ctx.skill_slug = resolved.slug
            ctx.skill_allowed_tools = resolved.allowed_tools
            session = await db.get(AgentSession, ctx.session_id)
            if session is not None:
                ws = dict(session.workspace or {})
                ws["active_skill_slug"] = resolved.slug
                session.workspace = ws
                await db.flush()
            return self._log_tool_result(ctx, tool_name, args, {
                "ok": True,
                "active_skill_slug": resolved.slug,
                "name": resolved.name,
                "default_model_component": resolved.default_model_component,
            })

        if tool_name == "unload_skill":
            ctx.skill_slug = None
            ctx.skill_allowed_tools = None
            session = await db.get(AgentSession, ctx.session_id)
            if session is not None:
                ws = dict(session.workspace or {})
                ws.pop("active_skill_slug", None)
                session.workspace = ws
                await db.flush()
            return self._log_tool_result(ctx, tool_name, args, {
                "ok": True,
                "active_skill_slug": None,
            })

        if tool_name == "set_session_title":
            title = str(args.get("title") or "").strip()
            if not title:
                raise RuntimeError("set_session_title requires title.")
            if len(title) > 255:
                raise RuntimeError("set_session_title title exceeds database limit of 255 characters.")
            session = await db.get(AgentSession, ctx.session_id)
            if session is None or session.project_id != ctx.project_id or session.user_id != ctx.user_id:
                raise RuntimeError(f"Agent session {ctx.session_id} not found.")
            session.title = title
            workspace = dict(session.workspace or {})
            workspace["title_source"] = "agent_tool"
            session.workspace = workspace
            await db.commit()
            return self._log_tool_result(ctx, tool_name, args, {
                "ok": True,
                "session_id": ctx.session_id,
                "session_title": title,
            })

        if tool_name == "memory_search":
            query = str(args.get("query", "")).strip()
            top_k = int(args.get("top_k") or 6)
            if not str(getattr(project, "memory_id", "") or "").strip():
                return self._log_tool_result(ctx, tool_name, args, {
                    "ok": False,
                    "error": "Project memory is not built yet. Use build_project_memory first, or continue without RAG.",
                })
            try:
                result = await memory_rag_query(
                    ctx.project_id,
                    query,
                    top_k=top_k,
                    db=db,
                    operation_id=ctx.parent_operation_id,
                )
            except Exception as exc:
                logger.warning("memory_search failed for project %s: %s", ctx.project_id, exc)
                return self._log_tool_result(ctx, tool_name, args, {
                    "ok": False,
                    "error": f"memory_search failed: {exc}",
                })
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "result": result})

        if tool_name == "store_structured_memory":
            payload = {
                k: args[k]
                for k in ("text_type", "task_kind", "memory_schema", "structured_memory", "graph")
                if args.get(k)
            }
            if not payload.get("structured_memory"):
                return self._log_tool_result(
                    ctx, tool_name, args, {"ok": False, "error": "structured_memory is required"},
                )
            wb = await writeback_agent_memory(
                ctx.project_id,
                payload,
                operation_id=ctx.parent_operation_id,
                operation_type="AGENT_TASK",
                db=db,
                project=project,
                llm_model_override=ctx.model,
            )
            state = dict(getattr(project, "creative_state", None) or {})
            ws = dict(state.get("agent_workspace") or {})
            ws.update(payload)
            state["agent_workspace"] = ws
            project.creative_state = state
            await db.flush()
            ctx.workspace_dirty = True
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "writeback": wb, "agent_workspace": ws})

        if tool_name == "list_document_units":
            document_units = [
                {
                    "id": ch.id,
                    "title": ch.title,
                    "order_index": ch.order_index,
                    "status": ch.status,
                    "content_length": len(ch.content or ""),
                }
                for ch in sorted(project.chapters or [], key=lambda c: c.order_index)
            ]
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "document_units": document_units})

        if tool_name == "list_project_files":
            from app.services.project_files import list_project_files

            return self._log_tool_result(ctx, tool_name, args, {"ok": True, **list_project_files(ctx.project_id)})

        if tool_name == "read_project_file":
            from app.services.project_files import read_project_file

            path = str(args.get("path") or "").strip()
            if not path:
                raise RuntimeError("read_project_file requires path.")
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "file": read_project_file(ctx.project_id, path)})

        if tool_name == "read_document_unit":
            document_unit_id = str(args.get("document_unit_id", "")).strip()
            for ch in project.chapters or []:
                if ch.id == document_unit_id:
                    return self._log_tool_result(
                        ctx, tool_name, args,
                        {"ok": True, "document_unit": {"id": ch.id, "title": ch.title, "content": ch.content or ""}},
                    )
            raise RuntimeError(f"Document unit {document_unit_id} not found")

        if tool_name == "write_document_unit":
            mode = str(args.get("mode") or "append").strip().lower()
            document_unit_id = str(args.get("document_unit_id", "")).strip()
            if mode != "create" and not document_unit_id:
                raise RuntimeError("write_document_unit requires document_unit_id unless mode is create.")
            wb_result = await write_chapter_content(
                project=project,
                db=db,
                content=str(args.get("content", "")),
                chapter_id=document_unit_id,
                title=str(args.get("title", "")).strip(),
                mode=mode,
            )
            result = wb_result if isinstance(wb_result, dict) else {"ok": True, "result": wb_result}
            if result.get("ok") and result.get("chapter_id"):
                result["document_unit_id"] = result.pop("chapter_id")
                ctx.workspace_dirty = True
            return self._log_tool_result(ctx, tool_name, args, result)

        if tool_name == "generate_document_unit":
            instruction = str(args.get("instruction") or "").strip()
            if not instruction:
                raise RuntimeError("generate_document_unit requires instruction.")
            document_unit_id = str(args.get("document_unit_id") or "").strip()
            mode = str(args.get("mode") or ("append" if document_unit_id else "create")).strip().lower()
            title = str(args.get("title") or "").strip()
            requested_model = str(args.get("model") or "").strip()
            write_model = (
                requested_model
                if requested_model and requested_model in (ctx.available_chat_models or [requested_model])
                else ctx.model
            )

            # Best-effort RAG retrieval; generation must not die on memory issues.
            rag_context = ""
            rag_query = str(args.get("rag_query") or "").strip() or instruction[:300]
            if str(getattr(project, "memory_id", "") or "").strip():
                try:
                    rag = await memory_rag_query(
                        ctx.project_id, rag_query, top_k=6, db=db,
                        operation_id=ctx.parent_operation_id,
                    )
                    rag_context = str(rag.get("context_text") or "")
                except Exception as rag_exc:
                    logger.warning("generate_document_unit RAG skipped: %s", rag_exc)

            chapters = sorted(project.chapters or [], key=lambda c: c.order_index)
            target = next((c for c in chapters if c.id == document_unit_id), None) if document_unit_id else None
            tail_source = target if target is not None else (chapters[-1] if chapters else None)
            previous_tail = str(getattr(tail_source, "content", "") or "")[-3000:] if tail_source is not None else ""

            structured_memory: dict[str, Any] = {}
            creative_state = getattr(project, "creative_state", None)
            if isinstance(creative_state, dict):
                ws_state = creative_state.get("agent_workspace")
                if isinstance(ws_state, dict) and isinstance(ws_state.get("structured_memory"), dict):
                    structured_memory = ws_state["structured_memory"]

            prompt_parts = [
                "你是专业写作引擎。直接输出正文本身；不要输出解释、JSON、Markdown 代码围栏或任何前后缀。",
                f"项目：《{project.title}》\n{str(project.description or '')[:500]}",
            ]
            if structured_memory:
                prompt_parts.append(
                    "项目结构化记忆：\n" + json.dumps(structured_memory, ensure_ascii=False)[:3000]
                )
            if rag_context:
                prompt_parts.append("相关项目记忆（RAG 检索）：\n" + rag_context[:4000])
            if previous_tail:
                prompt_parts.append(f"前文结尾（衔接用）：\n...{previous_tail}")
            prompt_parts.append(f"写作指令：\n{instruction}")
            prompt = "\n\n".join(prompt_parts)

            step_id = ctx.current_step_id or ""
            delta_buffer: list[str] = []
            buffered_chars = 0

            async def _flush_deltas() -> None:
                nonlocal buffered_chars
                if not delta_buffer or ctx.emit_progress is None:
                    delta_buffer.clear()
                    buffered_chars = 0
                    return
                text = "".join(delta_buffer)
                delta_buffer.clear()
                buffered_chars = 0
                try:
                    await ctx.emit_progress({
                        "event": "generation_delta",
                        "step_id": step_id,
                        "delta": text,
                    })
                except Exception:
                    pass

            async def _on_delta(text: str) -> None:
                nonlocal buffered_chars
                delta_buffer.append(text)
                buffered_chars += len(text)
                if buffered_chars >= 120:
                    await _flush_deltas()

            with llm_billing_scope(
                user_id=ctx.user_id, project_id=ctx.project_id, operation_id=ctx.parent_operation_id,
            ):
                llm_result = await call_llm(
                    write_model,
                    prompt,
                    db,
                    max_tokens=16384,
                    billing_user_id=ctx.user_id,
                    billing_project_id=ctx.project_id,
                    billing_operation_id=ctx.parent_operation_id,
                    minimum_timeout_seconds=600,
                    stream_callback=_on_delta,
                )
            await _flush_deltas()

            content = str(llm_result.get("content") or "").strip()
            if not content:
                raise RuntimeError("generate_document_unit produced empty content.")

            wb_result = await write_chapter_content(
                project=project,
                db=db,
                content=content,
                chapter_id=document_unit_id,
                title=title,
                mode=mode,
            )
            result = wb_result if isinstance(wb_result, dict) else {"ok": True}
            unit_id = str(result.pop("chapter_id", "") or document_unit_id)
            ctx.workspace_dirty = True
            return self._log_tool_result(ctx, tool_name, args, {
                "ok": True,
                "document_unit_id": unit_id,
                "title": title or (str(getattr(target, "title", "")) if target is not None else ""),
                "mode": mode,
                "model": write_model,
                "content_chars": len(content),
                "content_preview": content[:400],
                "rag_used": bool(rag_context),
                "input_tokens": llm_result.get("input_tokens", 0),
                "output_tokens": llm_result.get("output_tokens", 0),
            })

        if tool_name == "get_memory_graph":
            from app.services import memory_service

            viz = await memory_service.get_memory_visualization(ctx.project_id, db=db)
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "graph": viz})

        if tool_name == "build_project_memory":
            from app.services import memory_service

            if args:
                raise RuntimeError("build_project_memory does not accept arguments.")
            text = "\n\n".join(
                f"# {ch.title}\n{ch.content or ''}"
                for ch in sorted(project.chapters or [], key=lambda c: c.order_index)
            )
            if not text.strip():
                return self._log_tool_result(ctx, tool_name, args, {"ok": True, "memory_id": getattr(project, "memory_id", None), "warning": "No chapter text yet; memory skipped"})

            memory_build_model = resolve_explicit_component_model(project, "memory_build") or ctx.model
            embedding_model = resolve_explicit_component_model(project, "memory_embedding")
            memory_id = await memory_service.build_memory(
                ctx.project_id,
                text,
                db=db,
                model=memory_build_model,
                embedding_model=embedding_model,
                reset=False,
                operation_id=ctx.parent_operation_id,
            )
            project.memory_id = memory_id
            await db.flush()
            ctx.workspace_dirty = True
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "memory_id": memory_id})

        if tool_name == "list_facts":
            result = await db.execute(
                select(ProjectFact)
                .where(ProjectFact.project_id == ctx.project_id)
                .order_by(ProjectFact.updated_at.desc())
            )
            facts = [self._fact_payload(fact) for fact in result.scalars().all()]
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "facts": facts})

        if tool_name == "read_fact":
            fact_id = str(args.get("fact_id") or "").strip()
            if not fact_id:
                raise RuntimeError("read_fact requires fact_id.")
            fact = await db.get(ProjectFact, fact_id)
            if fact is None or fact.project_id != ctx.project_id:
                raise RuntimeError(f"Fact {fact_id} not found.")
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "fact": self._fact_payload(fact)})

        if tool_name == "create_fact":
            title = str(args.get("title") or "").strip()
            content = str(args.get("content") or "").strip()
            if not title or not content:
                raise RuntimeError("create_fact requires title and content.")
            fact = ProjectFact(
                id=str(uuid4()),
                project_id=ctx.project_id,
                created_by_user_id=ctx.user_id,
                created_by_agent_session_id=ctx.session_id,
                source_kind=str(args.get("source_kind") or "agent").strip(),
                source_ref=args.get("source_ref") if isinstance(args.get("source_ref"), dict) else None,
                title=title,
                content=content,
                metadata_=args.get("metadata") if isinstance(args.get("metadata"), dict) else {"agent_session_id": ctx.session_id},
                memory_status="pending",
            )
            apply_fact_hash(fact)
            db.add(fact)
            await db.flush()
            fact_id = fact.id
            await db.commit()
            task_id = schedule_fact_memory_sync(
                project_id=ctx.project_id,
                user_id=ctx.user_id,
                action="create",
                fact_id=fact_id,
            )
            fact = await db.get(ProjectFact, fact_id)
            if fact is None:
                raise RuntimeError(f"Fact {fact_id} disappeared after create.")
            fact.memory_status = "syncing"
            fact.memory_task_id = task_id
            fact.memory_error = None
            await db.flush()
            ctx.workspace_dirty = True
            await db.commit()
            await db.refresh(fact)
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "task_id": task_id, "fact": self._fact_payload(fact)})

        if tool_name == "update_fact":
            fact_id = str(args.get("fact_id") or "").strip()
            if not fact_id:
                raise RuntimeError("update_fact requires fact_id.")
            fact = await db.get(ProjectFact, fact_id)
            if fact is None or fact.project_id != ctx.project_id:
                raise RuntimeError(f"Fact {fact_id} not found.")
            if "title" in args:
                fact.title = str(args["title"]).strip()
            if "content" in args:
                fact.content = str(args["content"])
            if "source_kind" in args:
                fact.source_kind = str(args["source_kind"]).strip()
            if "source_ref" in args:
                fact.source_ref = args["source_ref"] if isinstance(args["source_ref"], dict) else None
            if "metadata" in args:
                fact.metadata_ = args["metadata"] if isinstance(args["metadata"], dict) else None
            fact.memory_status = "pending"
            fact.memory_error = None
            apply_fact_hash(fact)
            await db.flush()
            await db.commit()
            task_id = schedule_fact_memory_sync(
                project_id=ctx.project_id,
                user_id=ctx.user_id,
                action="update",
                fact_id=fact_id,
            )
            fact = await db.get(ProjectFact, fact_id)
            if fact is None:
                raise RuntimeError(f"Fact {fact_id} disappeared after update.")
            fact.memory_status = "syncing"
            fact.memory_task_id = task_id
            fact.memory_error = None
            await db.flush()
            ctx.workspace_dirty = True
            await db.commit()
            await db.refresh(fact)
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "task_id": task_id, "fact": self._fact_payload(fact)})

        if tool_name == "sync_fact_memory":
            fact_id = str(args.get("fact_id") or "").strip()
            if not fact_id:
                raise RuntimeError("sync_fact_memory requires fact_id.")
            fact = await db.get(ProjectFact, fact_id)
            if fact is None or fact.project_id != ctx.project_id:
                raise RuntimeError(f"Fact {fact_id} not found.")
            fact.memory_status = "pending"
            fact.memory_error = None
            await db.flush()
            await db.commit()
            task_id = schedule_fact_memory_sync(
                project_id=ctx.project_id,
                user_id=ctx.user_id,
                action="sync",
                fact_id=fact_id,
            )
            fact = await db.get(ProjectFact, fact_id)
            if fact is None:
                raise RuntimeError(f"Fact {fact_id} disappeared before sync.")
            fact.memory_status = "syncing"
            fact.memory_task_id = task_id
            fact.memory_error = None
            await db.flush()
            ctx.workspace_dirty = True
            await db.commit()
            await db.refresh(fact)
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "task_id": task_id, "fact": self._fact_payload(fact)})

        if tool_name == "search_entities":
            query = str(args.get("query") or "").strip()
            if not query:
                raise RuntimeError("search_entities requires query.")
            entity_type = str(args.get("entity_type") or "").strip() or None
            limit = int(args.get("limit") or 20)
            state = dict(project.creative_state or {})
            workspace = dict(state.get("agent_workspace") or {})
            structured_memory = workspace.get("structured_memory") if isinstance(workspace.get("structured_memory"), dict) else {}
            memory_schema = workspace.get("memory_schema") if isinstance(workspace.get("memory_schema"), dict) else {}
            fact_graph = workspace.get("fact_graph") if isinstance(workspace.get("fact_graph"), dict) else {}
            entities = collect_project_entities(
                facts=list(project.facts or []),
                ontology=project.ontology_schema if isinstance(project.ontology_schema, dict) else None,
                structured_memory=structured_memory,
                fact_graph=fact_graph,
                memory_schema=memory_schema,
            )
            results = search_project_entities(
                entities,
                query=query,
                entity_type=entity_type,
                limit=limit,
            )
            return self._log_tool_result(ctx, tool_name, args, {
                "ok": True,
                "query": query,
                "total": len(results),
                "results": results,
                "categories": group_entities_by_type(entities),
            })

        if tool_name == "batch_update_entities":
            updates = args.get("updates")
            if not isinstance(updates, list) or not updates:
                raise RuntimeError("batch_update_entities requires a non-empty updates array.")
            updated_facts: list[ProjectFact] = []
            for item in updates:
                if not isinstance(item, dict):
                    raise RuntimeError("batch_update_entities updates items must be objects.")
                fact_id = str(item.get("fact_id") or "").strip()
                if not fact_id:
                    raise RuntimeError("batch_update_entities update item requires fact_id.")
                fact = await db.get(ProjectFact, fact_id)
                if fact is None or fact.project_id != ctx.project_id:
                    raise RuntimeError(f"Fact {fact_id} not found.")
                if "title" in item and item["title"] is not None:
                    fact.title = str(item["title"]).strip()
                if "content" in item and item["content"] is not None:
                    fact.content = str(item["content"])
                if "entities" in item:
                    fact.entities = item["entities"] if isinstance(item["entities"], list) else []
                if "relationships" in item:
                    fact.relationships = item["relationships"] if isinstance(item["relationships"], list) else []
                if "metadata" in item:
                    fact.metadata_ = item["metadata"] if isinstance(item["metadata"], dict) else None
                fact.memory_status = "pending"
                fact.memory_error = None
                apply_fact_hash(fact)
                updated_facts.append(fact)

            structured_memory_patch = args.get("structured_memory")
            if isinstance(structured_memory_patch, dict):
                state = dict(project.creative_state or {})
                workspace = dict(state.get("agent_workspace") or {})
                existing = workspace.get("structured_memory") if isinstance(workspace.get("structured_memory"), dict) else {}
                workspace["structured_memory"] = merge_structured_memory(existing, structured_memory_patch)
                state["agent_workspace"] = workspace
                project.creative_state = state

            await db.flush()
            sync_memory = bool(args.get("sync_memory", True))
            task_id: str | None = None
            if sync_memory:
                await db.commit()
                task_id = schedule_fact_memory_sync(
                    project_id=ctx.project_id,
                    user_id=ctx.user_id,
                    action="batch_update",
                    fact_id=updated_facts[0].id if updated_facts else None,
                )
                for fact in updated_facts:
                    refreshed = await db.get(ProjectFact, fact.id)
                    if refreshed is not None:
                        refreshed.memory_status = "syncing"
                        refreshed.memory_task_id = task_id
                        refreshed.memory_error = None
            ctx.workspace_dirty = True
            await db.commit()
            payloads = []
            for fact in updated_facts:
                refreshed = await db.get(ProjectFact, fact.id)
                if refreshed is not None:
                    await db.refresh(refreshed)
                    payloads.append(self._fact_payload(refreshed))
            return self._log_tool_result(ctx, tool_name, args, {
                "ok": True,
                "updated_count": len(payloads),
                "task_id": task_id,
                "facts": payloads,
            })

        if tool_name == "report_finding":
            severity = str(args.get("severity") or "info").strip().lower()
            if severity not in {"info", "warning", "critical"}:
                raise RuntimeError("report_finding severity must be info|warning|critical.")
            title = str(args.get("title") or "").strip()
            if not title:
                raise RuntimeError("report_finding requires title.")
            entry = {
                "session_id": ctx.session_id,
                "role": (ctx.subagent_profile.role if ctx.subagent_profile else "orchestrator"),
                "severity": severity,
                "title": title,
                "evidence": str(args.get("evidence") or ""),
                "suggestion": str(args.get("suggestion") or ""),
                "tags": list(args.get("tags") or []),
            }
            session = await db.get(AgentSession, ctx.session_id)
            if session is not None:
                ws = dict(session.workspace or {})
                findings = list(ws.get("findings") or [])
                findings.append(entry)
                ws["findings"] = findings
                session.workspace = ws
                await db.flush()
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "finding": entry})

        if tool_name == "propose_state_delta":
            target = str(args.get("target") or "").strip().lower()
            op = str(args.get("op") or "").strip().lower()
            path = str(args.get("path") or "").strip()
            if target not in {"fact", "structured_memory", "graph"}:
                raise RuntimeError("propose_state_delta target must be fact|structured_memory|graph.")
            if op not in {"create", "update", "delete", "merge"}:
                raise RuntimeError("propose_state_delta op must be create|update|delete|merge.")
            if not path:
                raise RuntimeError("propose_state_delta requires path.")
            entry = {
                "session_id": ctx.session_id,
                "role": (ctx.subagent_profile.role if ctx.subagent_profile else "orchestrator"),
                "target": target,
                "op": op,
                "path": path,
                "value": args.get("value"),
                "evidence": str(args.get("evidence") or ""),
            }
            session = await db.get(AgentSession, ctx.session_id)
            if session is not None:
                ws = dict(session.workspace or {})
                deltas = list(ws.get("proposed_state_deltas") or [])
                deltas.append(entry)
                ws["proposed_state_deltas"] = deltas
                session.workspace = ws
                await db.flush()
            return self._log_tool_result(ctx, tool_name, args, {"ok": True, "delta": entry})

        if tool_name == "apply_state_deltas":
            if profile is not None:
                raise RuntimeError("apply_state_deltas is orchestrator-only.")
            delta_ids = list(args.get("delta_ids") or [])
            dry_run = bool(args.get("dry_run") or False)
            if not delta_ids:
                raise RuntimeError("apply_state_deltas requires delta_ids.")
            session = await db.get(AgentSession, ctx.session_id)
            if session is None:
                raise RuntimeError(f"Agent session {ctx.session_id} not found.")
            ws = dict(session.workspace or {})
            deltas = list(ws.get("proposed_state_deltas") or [])
            id_prefix = f"{ctx.session_id}:delta:"
            indexed: dict[str, tuple[int, dict[str, Any]]] = {
                f"{id_prefix}{idx}": (idx, delta)
                for idx, delta in enumerate(deltas)
                if isinstance(delta, dict)
            }
            selected: list[tuple[str, int, dict[str, Any]]] = []
            for did in delta_ids:
                if did not in indexed:
                    raise RuntimeError(f"Unknown delta id: {did}")
                idx, delta = indexed[did]
                selected.append((did, idx, delta))

            applied: list[dict[str, Any]] = []
            try:
                state = dict(project.creative_state or {})
                workspace_state = dict(state.get("agent_workspace") or {})
                structured_memory = (
                    dict(workspace_state.get("structured_memory") or {})
                    if isinstance(workspace_state.get("structured_memory"), dict)
                    else {}
                )

                for did, _idx, delta in selected:
                    target = str(delta.get("target") or "").strip().lower()
                    op = str(delta.get("op") or "").strip().lower()
                    path = str(delta.get("path") or "").strip()
                    value = delta.get("value")
                    if target not in {"fact", "structured_memory", "graph"}:
                        raise RuntimeError(f"Invalid delta target: {target}")
                    if op not in {"create", "update", "delete", "merge"}:
                        raise RuntimeError(f"Invalid delta op: {op}")

                    if target == "fact":
                        if not path.startswith("fact:"):
                            raise RuntimeError(
                                f"fact delta requires path 'fact:<id>', got {path!r}"
                            )
                        fact_id = path.split(":", 1)[1]
                        fact = await db.get(ProjectFact, fact_id)
                        if fact is None or fact.project_id != ctx.project_id:
                            raise RuntimeError(f"Fact {fact_id} not found")
                        if op == "delete":
                            if not dry_run:
                                meta = dict(fact.metadata_ or {})
                                meta["deleted_by_delta"] = did
                                fact.metadata_ = meta
                                fact.memory_status = "pending"
                        else:  # update / merge
                            if not isinstance(value, dict):
                                raise RuntimeError(
                                    f"fact delta {did} requires dict value"
                                )
                            if not dry_run:
                                if "title" in value:
                                    fact.title = str(value["title"]).strip()
                                if "content" in value:
                                    fact.content = str(value["content"])
                                if "metadata" in value and isinstance(value["metadata"], dict):
                                    fact.metadata_ = value["metadata"]
                                fact.memory_status = "pending"
                                apply_fact_hash(fact)
                        applied.append({"delta_id": did, "target": target, "op": op, "ok": True})

                    elif target == "structured_memory":
                        if not path.startswith("structured_memory."):
                            raise RuntimeError(
                                f"structured_memory delta requires path "
                                f"'structured_memory.<key>', got {path!r}"
                            )
                        key = path.split(".", 1)[1]
                        if not key:
                            raise RuntimeError(f"Empty structured_memory key in {did}")
                        if op == "delete":
                            if not dry_run:
                                structured_memory.pop(key, None)
                        elif op == "merge" and isinstance(value, dict):
                            existing = structured_memory.get(key)
                            if isinstance(existing, dict):
                                merged = merge_structured_memory(existing, value)
                                if not dry_run:
                                    structured_memory[key] = merged
                            else:
                                if not dry_run:
                                    structured_memory[key] = value
                        else:  # create / update
                            if not dry_run:
                                structured_memory[key] = value
                        applied.append({"delta_id": did, "target": target, "op": op, "ok": True})

                    elif target == "graph":
                        if not isinstance(value, dict):
                            raise RuntimeError(f"graph delta {did} requires dict value")
                        if not dry_run:
                            await writeback_agent_memory(
                                ctx.project_id,
                                {"graph": value},
                                operation_id=ctx.parent_operation_id,
                                operation_type="AGENT_TASK",
                                db=db,
                                project=project,
                            )
                        applied.append({"delta_id": did, "target": target, "op": op, "ok": True})

                if not dry_run:
                    workspace_state["structured_memory"] = structured_memory
                    state["agent_workspace"] = workspace_state
                    project.creative_state = state
                    ws_applied = list(ws.get("applied_deltas") or [])
                    ws_applied.extend(applied)
                    ws["applied_deltas"] = ws_applied
                    session.workspace = ws
                    await db.flush()
                    ctx.workspace_dirty = True
            except Exception:
                await db.rollback()
                raise

            return self._log_tool_result(ctx, tool_name, args, {
                "ok": True,
                "applied": applied,
                "dry_run": dry_run,
            })

        if tool_name == "spawn_subagent":
            role = str(args.get("subagent_role") or "").strip()
            task = str(args.get("task") or args.get("instruction") or "").strip()
            child_model = str(args.get("model") or "").strip()
            if role not in SUBAGENT_ROLES:
                raise RuntimeError(
                    "spawn_subagent requires subagent_role: " + ", ".join(sorted(SUBAGENT_ROLES))
                )
            if not task:
                raise RuntimeError("spawn_subagent requires task.")
            child_profile = get_profile(role)
            if not child_model and child_profile.default_model_component:
                resolved = resolve_explicit_component_model(
                    project, child_profile.default_model_component, ctx.model,
                )
                child_model = str(resolved or ctx.model or "").strip()
            if not child_model:
                child_model = ctx.model
            await self._require_available_chat_model(child_model, db)
            target_refs = [str(x) for x in (args.get("target_refs") or []) if str(x).strip()]
            context_scope = str(args.get("context_scope") or "").strip().lower() or child_profile.context_scope

            child_session_id = ctx.pending_child_session_id or uuid4().hex
            root_session_id = ctx.root_session_id or ctx.session_id
            parent_step_id = ctx.current_step_id or ctx.parent_step_id
            child_session = await db.get(AgentSession, child_session_id)
            if child_session is None:
                child_session = AgentSession(id=child_session_id, project_id=ctx.project_id, user_id=ctx.user_id)
                db.add(child_session)
            child_session.role = role
            child_session.parent_session_id = ctx.session_id
            child_session.root_session_id = root_session_id
            child_session.parent_step_id = parent_step_id
            child_session.model = child_model
            child_session.status = "running"
            child_session.workspace = {
                "task": task,
                "role": role,
                "target_refs": target_refs,
                "context_scope": context_scope,
            }
            db.add(AgentMessage(
                id=uuid4().hex,
                session_id=child_session_id,
                role="user",
                content=task,
                metadata_={
                    "subagent_role": role,
                    "parent_session_id": ctx.session_id,
                    "parent_step_id": parent_step_id,
                    "target_refs": target_refs,
                    "context_scope": context_scope,
                },
            ))
            await db.commit()

            async def _child_progress(data: dict[str, Any]) -> None:
                event = str(data.get("event") or "progress")
                if event == "generation_delta":
                    return
                payload = {key: value for key, value in data.items() if key != "event"}
                await self._record_child_event(child_session_id, event, payload)

            try:
                child_result = await self.run_flow(
                    session_id=child_session_id,
                    instruction=task,
                    project_id=ctx.project_id,
                    user_id=ctx.user_id,
                    model=child_model,
                    progress_callback=_child_progress,
                    conversation_history=[],
                    role=role,
                    parent_session_id=ctx.session_id,
                    root_session_id=root_session_id,
                    parent_step_id=parent_step_id,
                )
            except Exception as exc:
                await self._record_child_event(child_session_id, "error", {"message": str(exc)})
                raise
            child_plan_result = child_result.get("plan_result") if isinstance(child_result.get("plan_result"), dict) else {}
            child_finish_payload = child_plan_result.get("finish_payload") if isinstance(child_plan_result, dict) else None

            # Persist subagent output into a stable parent workspace slot so
            # multiple subagents do not stomp each other's payloads.
            parent_session = await db.get(AgentSession, ctx.session_id)
            if parent_session is not None:
                parent_ws = dict(parent_session.workspace or {})
                outputs = dict(parent_ws.get("subagent_outputs") or {})
                outputs[child_session_id] = {
                    "role": role,
                    "status": str(child_result.get("status") or "").lower(),
                    "summary": str(child_plan_result.get("output") or "")[:2000] if child_plan_result else "",
                    "finish_payload": child_finish_payload,
                    "target_refs": target_refs,
                    "context_scope": context_scope,
                }
                parent_ws["subagent_outputs"] = outputs
                parent_session.workspace = parent_ws
                await db.flush()

            return self._log_tool_result(ctx, tool_name, args, {
                "ok": True,
                "child_session_id": child_session_id,
                "subagent_role": role,
                "model": child_model,
                "target_refs": target_refs,
                "context_scope": context_scope,
                "status": str(child_result.get("status") or "").lower(),
                "summary": str(child_plan_result.get("output") or "")[:1000] if child_plan_result else "",
                "finish_payload": child_finish_payload,
            })

        raise RuntimeError(f"Unknown tool: {tool_name}")

    async def run_tool_loop_flow(
        self,
        *,
        session_id: str,
        instruction: str,
        project_id: str,
        user_id: str,
        model: str,
        progress_callback: ProgressCallback | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        role: str = "orchestrator",
        parent_session_id: str | None = None,
        root_session_id: str | None = None,
        parent_step_id: str | None = None,
        skill_slug: str | None = None,
    ) -> dict[str, Any]:
        """Pi multi-turn tool loop: LLM decides tools until finish."""
        is_subagent = str(role or "orchestrator").strip() != "orchestrator"
        subagent_profile: SubagentProfile | None = None
        if is_subagent:
            subagent_profile = get_profile(role)
        env_max = int(settings.AGENT_PI_TOOL_LOOP_MAX_ITERATIONS or 8)
        if subagent_profile is not None:
            max_iters = max(1, min(env_max, subagent_profile.max_iterations))
        else:
            max_iters = max(1, min(20, env_max))
        step_records: list[dict[str, Any]] = []
        plan_result: dict[str, Any] = {
            "output": "",
            "text_type": "",
            "task_kind": "pi_tool_loop",
            "plan": [],
            "memory_schema": {},
            "structured_memory": {},
            "graph": {},
            "retrieval_queries": [],
            "writing_plan": [],
            "next_actions": [],
        }

        async with async_session() as db:
            result = await db.execute(
                select(TextProject).where(TextProject.id == project_id).options(
                    selectinload(TextProject.chapters),
                )
            )
            project = result.scalar_one()
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one()
            session_record = await db.get(AgentSession, session_id)
            session_title = str(session_record.title or "").strip() if session_record else ""
            available_model_rows = await get_available_models(db)
            available_chat_models = [
                str(item.get("id") or "").strip()
                for item in available_model_rows
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            ]

            # Load skill (orchestrator-only).
            active_skill: ResolvedSkill | None = None
            if not is_subagent and (skill_slug or "").strip():
                active_skill = await load_active_skill(skill_slug, db)

            memory_block = await self.build_project_context_snapshot(
                project=project,
                project_id=project_id,
                instruction=instruction,
                db=db,
            )
            messages = build_initial_messages(
                instruction,
                memory_block=memory_block,
                session_title=session_title,
                available_models=available_chat_models,
                history=conversation_history,
            )
            if is_subagent:
                session_workspace_pre = session_record.workspace if (session_record is not None and isinstance(session_record.workspace, dict)) else {}
                pre_refs = [str(x) for x in (session_workspace_pre.get("target_refs") or []) if str(x).strip()]
                pre_scope = str(session_workspace_pre.get("context_scope") or "").strip().lower() or (
                    subagent_profile.context_scope if subagent_profile is not None else "full"
                )
                briefing = (
                    "Subagent briefing:\n"
                    f"- role: {role}\n"
                    f"- context_scope: {pre_scope}\n"
                    f"- target_refs: {json.dumps(pre_refs, ensure_ascii=False)}\n"
                    "- 仅在你 role 的 allowed_tools 内调用工具；不要尝试 spawn_subagent。\n"
                    "- finish.output 必须满足你 role 的 output_schema；缺字段会被退回重试。"
                )
                if role == "auditor":
                    from app.services.agent.subagent_profiles import (
                        auditor_dimensions_for,
                    )
                    dims = auditor_dimensions_for(project)
                    briefing += (
                        "\n- 必须审计以下维度并为每个维度打分(0..1)与状态(pass/warn/fail)：\n"
                        + "".join(f"  · {d}\n" for d in dims)
                        + "  其它维度若显著请补充，但上述维度不可遗漏。"
                    )
                messages.append({"role": "user", "content": briefing})

            parent_op = TextOperation(
                id=str(uuid4()),
                project_id=project_id,
                type="AGENT_TASK",
                input=instruction[:480],
                model=model,
                status="PROCESSING",
                progress=5,
                message="Pi tool loop started",
                metadata_={"agent_mode": "pi_tool_loop", "session_id": session_id},
            )
            db.add(parent_op)
            await db.flush()

            session_workspace = (session_record.workspace if session_record is not None else None) or {}
            target_refs_value = session_workspace.get("target_refs") if isinstance(session_workspace, dict) else None
            target_refs = [str(x) for x in (target_refs_value or []) if str(x).strip()]
            ctx_scope_value = session_workspace.get("context_scope") if isinstance(session_workspace, dict) else None
            ctx_scope = str(ctx_scope_value or "").strip().lower() or (
                subagent_profile.context_scope if subagent_profile is not None else None
            )
            ctx = PiAgentContext(
                project_id=project_id,
                user_id=user_id,
                model=model,
                session_id=session_id,
                parent_operation_id=parent_op.id,
                role=role,
                root_session_id=root_session_id or session_id,
                parent_step_id=parent_step_id,
                project=project,
                user=user,
                emit_progress=progress_callback,
                available_chat_models=available_chat_models,
                subagent_profile=subagent_profile,
                target_refs=target_refs,
                context_scope=ctx_scope,
                skill_slug=(active_skill.slug if active_skill else None),
                skill_allowed_tools=(active_skill.allowed_tools if active_skill else None),
            )

            resolved_model = (
                resolve_explicit_component_model(
                    project, component_key_for_operation("AGENT_TASK"), model,
                ) or model
            )

            # Pre-build the project-visible skill menu (orchestrator only).
            # The menu is short (slug · name · 80-char description) and is
            # injected into the system prompt every iteration so the LLM
            # always sees the up-to-date catalogue.
            skill_menu_text: str | None = None
            if not is_subagent:
                visible_skills = await list_project_visible_skills(
                    project_id, scope="chat", db=db,
                )
                if visible_skills:
                    skill_menu_text = "\n".join(
                        f"- {s['slug']} · {s['name']} · {(s.get('description') or '')[:80]}"
                        for s in visible_skills
                    )

            # Pipeline kind drives mandatory orchestration rules
            # (long_form_write → composer→writer→auditor→reviser).
            # Source order: project creative_state.pipeline.kind (set by an
            # earlier orchestrator turn or the planner) → adaptive planner
            # inference → None (simple autonomous mode).
            pipeline_kind: str | None = None
            active_pack_display: str | None = None
            if not is_subagent:
                cs = project.creative_state if isinstance(project.creative_state, dict) else {}
                pipeline_state = cs.get("pipeline") if isinstance(cs.get("pipeline"), dict) else {}
                pipeline_kind = (
                    str(pipeline_state.get("kind") or "").strip().lower() or None
                )
                try:
                    from app.services.agent.packs import get_project_pack
                    pack = get_project_pack(project)
                    active_pack_display = pack.display_name
                except Exception:
                    logger.debug("active pack lookup skipped", exc_info=True)
                if not pipeline_kind:
                    try:
                        from app.services.creative_task_planner import (
                            build_adaptive_plan, infer_pipeline_kind,
                        )
                        adaptive = build_adaptive_plan(
                            project, instruction, conversation_history,
                        )
                        if adaptive and adaptive.get("pipeline_kind"):
                            pipeline_kind = str(adaptive["pipeline_kind"]).strip().lower()
                        else:
                            pipeline_kind = infer_pipeline_kind(None, instruction)
                    except Exception:
                        logger.debug("pipeline_kind inference skipped", exc_info=True)
                        pipeline_kind = None

            def _current_system_prompt() -> str:
                return build_loop_system_prompt(
                    role=role,
                    profile=subagent_profile,
                    skill_system_prompt=(active_skill.system_prompt if active_skill else None),
                    skill_allowed_tools=(active_skill.allowed_tools if active_skill else None),
                    skill_menu=skill_menu_text if not is_subagent else None,
                    active_skill_slug=ctx.skill_slug,
                    pipeline_kind=pipeline_kind if not is_subagent else None,
                    active_pack_display=(active_pack_display if not is_subagent else None),
                )

            system_prompt = _current_system_prompt()

            # Virtual iteration-0 load_skill: when the request pinned a skill
            # via @-mention or programmatic preset, apply it before the LLM
            # gets its first turn so the menu shows it as already active.
            if not is_subagent and skill_slug and (
                active_skill is None or active_skill.slug != skill_slug
            ):
                try:
                    await self.execute_tool("load_skill", {"slug": skill_slug}, ctx, db)
                    active_skill = await load_active_skill(ctx.skill_slug, db)
                    system_prompt = _current_system_prompt()
                except Exception as exc:
                    logger.warning(
                        "Auto load_skill('%s') failed for session %s: %s",
                        skill_slug, session_id, exc,
                    )

            context_step = {
                "step_id": f"{session_id}:pi-context-0",
                "step_type": "context_snapshot",
                "status": "completed",
                "message": "Loaded document units and cognee context before Pi planning",
                "output": memory_block[:12000],
                "metadata": {"pi_loop": True, "prefetch_context": True},
            }
            step_records.append(context_step)
            await self._emit(progress_callback, "step_complete", {
                **context_step,
                "step": 0,
                "total_steps": max_iters,
            })

            finished = False
            consecutive_failures = 0
            schema_retry_used = False
            for iteration in range(max_iters):
                if is_session_cancelled(session_id):
                    ctx.status = "cancelled"
                    return

                # Recompute every iteration: a successful load_skill /
                # unload_skill in the previous turn mutates ctx.skill_slug,
                # which must reach the next system prompt.
                system_prompt = _current_system_prompt()
                await self._emit(progress_callback, "step_start", {
                    "step_id": f"{session_id}:pi-plan-{iteration + 1}",
                    "step_type": "plan",
                    "status": "running",
                    "message": "正在选择下一步执行动作",
                    "total_steps": max_iters,
                })

                prompt_parts = [system_prompt, "--- Conversation ---"]
                for msg in messages:
                    prompt_parts.append(f"{msg['role']}: {msg['content']}")
                prompt_parts.append("assistant:")

                with llm_billing_scope(
                    user_id=user_id,
                    project_id=project_id,
                    operation_id=parent_op.id,
                ):
                    llm_result = await call_llm(
                        resolved_model,
                        "\n\n".join(prompt_parts),
                        db,
                        max_tokens=int(settings.AGENT_PI_TOOL_LOOP_MAX_TOKENS or 8192),
                        billing_user_id=user_id,
                        billing_project_id=project_id,
                        billing_operation_id=parent_op.id,
                        minimum_timeout_seconds=300,
                        response_schema=PI_ACTION_RESPONSE_SCHEMA,
                        response_schema_name="PiToolAction",
                    )

                raw = str(llm_result.get("content") or "")
                parent_op.input_tokens = int(parent_op.input_tokens or 0) + int(llm_result.get("input_tokens") or 0)
                parent_op.output_tokens = int(parent_op.output_tokens or 0) + int(llm_result.get("output_tokens") or 0)
                parent_op.cost = Decimal(str(parent_op.cost or 0)) + Decimal(str(llm_result.get("cost") or 0))
                action = parse_pi_action(raw)
                if action is None:
                    raw_preview = raw[:4000]
                    consecutive_failures += 1
                    failed_step = {
                        "step_id": f"{session_id}:pi-parse-failed-{iteration + 1}",
                        "step": iteration + 1,
                        "total_steps": max_iters,
                        "step_type": "plan",
                        "status": "failed",
                        "message": "模型返回了无法解析的动作，要求重试",
                        "output": raw_preview,
                        "output_preview": raw_preview[:500],
                        "metadata": {
                            "pi_loop": True,
                            "parse_error": True,
                            "raw_model_output": raw_preview,
                        },
                    }
                    step_records.append(failed_step)
                    await self._emit(progress_callback, "step_complete", failed_step)
                    if consecutive_failures >= 3:
                        error = "Pi tool loop aborted: the model returned unparseable output 3 times in a row."
                        parent_op.status = "FAILED"
                        parent_op.progress = 100
                        parent_op.error = error
                        parent_op.message = error
                        parent_op.metadata_ = {
                            **(parent_op.metadata_ or {}),
                            "tool_log": ctx.tool_log,
                            "step_records": step_records,
                            "raw_model_output": raw_preview,
                        }
                        await db.commit()
                        raise RuntimeError(error)
                    messages.append({"role": "assistant", "content": raw[:2000]})
                    messages.append({
                        "role": "user",
                        "content": (
                            "tool_result (error): 你的上一条回复不是合法的 JSON action。"
                            '必须返回单个 JSON 对象：{"action":"tool_call",...} 或 {"action":"finish",...}。'
                        ),
                    })
                    continue
                consecutive_failures = 0

                if action.get("action") == "finish":
                    # Subagent finish payloads must satisfy the profile schema.
                    if subagent_profile is not None:
                        finish_payload = {
                            key: action.get(key)
                            for key in (
                                "output", "text_type", "task_kind", "memory_schema",
                                "structured_memory", "graph", "next_actions",
                            )
                            if action.get(key) not in (None, "", {}, [])
                        }
                        for extra_key in action.keys():
                            if extra_key in {"action", "tool", "args", "arguments", "reason"}:
                                continue
                            if extra_key not in finish_payload:
                                finish_payload[extra_key] = action.get(extra_key)
                        issues = validate_finish_output(subagent_profile, finish_payload)
                        if issues and not schema_retry_used:
                            schema_retry_used = True
                            messages.append({"role": "assistant", "content": raw[:2000]})
                            messages.append({
                                "role": "user",
                                "content": (
                                    "tool_result (error): finish.output 不满足本 role 的 output_schema：\n- "
                                    + "\n- ".join(issues)
                                    + "\n请重新返回符合 schema 的 finish 对象。"
                                ),
                            })
                            continue
                        plan_result["finish_payload"] = finish_payload
                        if issues:
                            plan_result.setdefault("warnings", []).append({
                                "code": "subagent_finish_schema_invalid",
                                "issues": issues,
                            })
                    finished = True
                    for key in (
                        "output", "text_type", "task_kind", "memory_schema",
                        "structured_memory", "graph", "next_actions",
                    ):
                        val = action.get(key)
                        if val not in (None, "", {}, []):
                            plan_result[key] = val
                    step = action_to_step_record(
                        step_index=iteration + 1,
                        action=action,
                        status="completed",
                        output=str(plan_result.get("output") or raw),
                    )
                    step["step_id"] = f"{session_id}:{step['step_id']}"
                    step_records.append(step)
                    await self._emit(progress_callback, "step_complete", {
                        **step,
                        "step": iteration + 1,
                        "total_steps": iteration + 1,
                    })
                    break

                tool_name = str(action.get("tool") or "").strip()
                tool_args = action.get("args") if isinstance(action.get("args"), dict) else {}
                pending_child_session_id = uuid4().hex if tool_name == "spawn_subagent" else None
                spawn_role_meta = (
                    role_meta_for(str(tool_args.get("subagent_role") or ""))
                    if tool_name == "spawn_subagent"
                    else None
                )
                running_step = action_to_step_record(
                    step_index=iteration + 1,
                    action=action,
                    status="running",
                    role_meta=spawn_role_meta,
                )
                running_step["step_id"] = f"{session_id}:{running_step['step_id']}"
                if pending_child_session_id:
                    running_step["child_session_id"] = pending_child_session_id
                    running_step["agent_role"] = tool_args.get("subagent_role")
                    running_step["model"] = tool_args.get("model")
                await self._emit(progress_callback, "step_start", {
                    **running_step,
                    "step": iteration + 1,
                    "total_steps": max_iters,
                })

                try:
                    ctx.current_step_id = running_step["step_id"]
                    ctx.pending_child_session_id = pending_child_session_id
                    tool_result = await self.execute_tool(tool_name, tool_args, ctx, db)
                    ctx.pending_child_session_id = None
                    if tool_result.get("session_title"):
                        await self._emit(progress_callback, "session_update", {
                            "session_id": ctx.session_id,
                            "title": tool_result["session_title"],
                        })
                    # Refresh active_skill after a successful skill switch so
                    # the next iteration's system_prompt picks it up.
                    if tool_name == "load_skill" and ctx.skill_slug:
                        active_skill = await load_active_skill(ctx.skill_slug, db)
                    elif tool_name == "unload_skill":
                        active_skill = None
                    for key in ("structured_memory", "graph", "memory_schema", "text_type", "task_kind"):
                        val = tool_result.get(key) or (tool_result.get("agent_workspace") or {}).get(key)
                        if isinstance(val, dict) and val:
                            existing = plan_result.get(key)
                            if isinstance(existing, dict):
                                merged = dict(existing)
                                merged.update(val)
                                plan_result[key] = merged
                            else:
                                plan_result[key] = val
                except Exception as exc:
                    consecutive_failures += 1
                    completed = action_to_step_record(
                        step_index=iteration + 1,
                        action=action,
                        status="failed",
                        output=str(exc),
                        role_meta=spawn_role_meta,
                    )
                    completed["step_id"] = running_step["step_id"]
                    if pending_child_session_id:
                        completed["child_session_id"] = pending_child_session_id
                        completed["agent_role"] = tool_args.get("subagent_role")
                        completed["model"] = tool_args.get("model")
                    step_records.append(completed)
                    await self._emit(progress_callback, "step_complete", {
                        **completed,
                        "step": iteration + 1,
                        "total_steps": max_iters,
                    })
                    if consecutive_failures >= 3:
                        parent_op.status = "FAILED"
                        parent_op.progress = 100
                        parent_op.error = str(exc)
                        parent_op.message = f"Pi tool {tool_name} failed: {exc}"
                        parent_op.metadata_ = {
                            **(parent_op.metadata_ or {}),
                            "tool_log": ctx.tool_log,
                            "step_records": step_records,
                        }
                        await db.commit()
                        raise
                    logger.warning("Pi tool %s failed (feeding back to model): %s", tool_name, exc)
                    messages.append({"role": "assistant", "content": raw[:4000]})
                    messages.append({
                        "role": "user",
                        "content": f"tool_result ({tool_name}) error: {str(exc)[:1500]}。请调整参数重试或改用其他工具。",
                    })
                    continue
                consecutive_failures = 0

                completed = action_to_step_record(
                    step_index=iteration + 1,
                    action=action,
                    status="completed",
                    output=truncate_tool_result(tool_result),
                    role_meta=spawn_role_meta,
                )
                completed["step_id"] = running_step["step_id"]
                completed["tool_result_preview"] = truncate_tool_result(tool_result)[:1000]
                if tool_name == "spawn_subagent":
                    completed["child_session_id"] = tool_result.get("child_session_id") or pending_child_session_id
                    completed["agent_role"] = tool_result.get("subagent_role") or tool_args.get("subagent_role")
                    completed["model"] = tool_result.get("model") or tool_args.get("model")
                step_records.append(completed)
                await self._emit(progress_callback, "step_complete", {
                    **completed,
                    "step": iteration + 1,
                    "total_steps": len(step_records),
                })

                messages.append({"role": "assistant", "content": raw[:4000]})
                messages.append({
                    "role": "user",
                    "content": f"tool_result ({tool_name}): {truncate_tool_result(tool_result)}",
                })

            if not finished:
                logger.warning("Pi tool loop hit max iterations without finish for session %s", session_id)
                completed_tools = [
                    str(item.get("step_type") or "")
                    for item in step_records
                    if item.get("status") == "completed" and item.get("step_type") not in {"plan", "context_snapshot"}
                ]
                if not plan_result.get("output"):
                    plan_result["output"] = (
                        f"已达到最大迭代次数（{max_iters}），任务部分完成。"
                        + (f"已执行工具：{', '.join(completed_tools)}。" if completed_tools else "")
                        + "可以继续对话让 Agent 接着执行。"
                    )

            if not plan_result.get("output") and step_records:
                plan_result["output"] = str(step_records[-1].get("output") or "")

            if ctx.workspace_dirty:
                try:
                    await write_project_workspace_version_snapshot_from_db(
                        project, db, "Agent session workspace snapshot",
                    )
                except Exception:
                    logger.warning("Workspace snapshot failed at end of agent run", exc_info=True)

            parent_op.status = "COMPLETED"
            parent_op.progress = 100
            parent_op.output = json.dumps(plan_result, ensure_ascii=False)[:50000]
            parent_op.message = f"Pi tool loop completed ({len(step_records)} steps)"
            parent_op.metadata_ = {
                **(parent_op.metadata_ or {}),
                "tool_log": ctx.tool_log,
                "agent_workspace": (project.creative_state or {}).get("agent_workspace"),
            }
            await db.commit()

        if not finished:
            status = "partial"
        else:
            status = "completed" if step_records and step_records[-1].get("status") != "failed" else "partial"
        return {
            "status": status,
            "plan_result": plan_result,
            "steps": step_records,
            "parent_operation_id": parent_op.id,
            "agent_mode": "pi_tool_loop",
        }

    async def run_flow(
        self,
        *,
        session_id: str,
        instruction: str,
        project_id: str,
        user_id: str,
        model: str,
        progress_callback: ProgressCallback | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        role: str = "orchestrator",
        parent_session_id: str | None = None,
        root_session_id: str | None = None,
        parent_step_id: str | None = None,
        skill_slug: str | None = None,
    ) -> dict[str, Any]:
        """Run full Pi agent flow with SSE-friendly events."""

        result = await self.run_tool_loop_flow(
            session_id=session_id,
            instruction=instruction,
            project_id=project_id,
            user_id=user_id,
            model=model,
            progress_callback=progress_callback,
            conversation_history=conversation_history,
            role=role,
            parent_session_id=parent_session_id,
            root_session_id=root_session_id,
            parent_step_id=parent_step_id,
            skill_slug=skill_slug,
        )

        plan_result = result.get("plan_result") or {}
        plan_payload = plan_result if isinstance(plan_result, dict) else {}
        steps = result.get("steps") or []
        total = len(steps)
        output_text = str(plan_payload.get("output") or "").strip()
        await self._emit(progress_callback, "complete", {
            "status": str(result.get("status", "completed")).lower(),
            "summary": output_text or f"Pi agent completed {total} step(s)",
            "output_preview": output_text[:240] if output_text else f"Completed {total} step(s)",
            "output": output_text,
            "structured_memory": plan_payload.get("structured_memory"),
            "graph": plan_payload.get("graph"),
            "parent_operation_id": result.get("parent_operation_id"),
        })

        return result

    async def build_suggest_context(
        self,
        *,
        project: TextProject,
        editor_text: str,
        cursor_position: int,
        chapter_id: str | None,
        db: AsyncSession,
        skill_system_prompt: str | None = None,
    ) -> str:
        """Assemble RAG context for collaborative writing suggestions.

        ``skill_system_prompt`` (if provided) replaces the default Pi system
        prompt — that's how Phase A wires the ``coauthor`` skill into the
        suggest endpoint.
        """
        before = editor_text[: max(0, cursor_position)]
        after = editor_text[cursor_position:]
        local_context = before[-1200:] if before else ""
        query = local_context[-400:] or editor_text[:400] or "current writing context"
        rag = await memory_rag_query(project.id, query, top_k=6, db=db)
        memory_pack = await build_creative_memory_pack(
            project=project,
            project_id=project.id,
            op_type="AGENT_SUGGEST",
            input_text=editor_text,
            db=db,
            reference_cards={"explicit_chapter_ids": [chapter_id]} if chapter_id else None,
        )
        memory_block = render_creative_memory_block(memory_pack)
        head = (skill_system_prompt or "").strip() or PI_SYSTEM_PROMPT
        return (
            f"{head}\n\n"
            f"--- Editor context (before cursor) ---\n{local_context}\n\n"
            f"--- After cursor ---\n{after[:400]}\n\n"
            f"--- RAG hits ---\n{rag.get('context_text', '')}\n\n"
            f"--- Creative memory ---\n{memory_block}\n\n"
            "给出 JSON：{\"suggestions\":[{\"type\":\"continuation|consistency|style|structure|fact\","
            "\"title\":\"...\",\"detail\":\"...\",\"insert_text\":\"...\"}],\"memory_queries\":[\"...\"]}"
        )


async def run_pi_agent_flow_background(
    session_id: str,
    instruction: str,
    project_id: str,
    user_id: str,
    model: str,
    *,
    publish: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
    skill_slug: str | None = None,
    effort: str | None = None,
) -> dict[str, Any]:
    """Background entry for agent router; publishes Redis events when *publish* is provided."""

    agent = MuseGraphPiAgent()

    async def _progress(data: dict[str, Any]) -> None:
        if publish is None:
            return
        event = str(data.get("event", "progress"))
        payload = {k: v for k, v in data.items() if k != "event"}
        await publish(event, payload)

    try:
        return await agent.run_flow(
            session_id=session_id,
            instruction=instruction,
            project_id=project_id,
            user_id=user_id,
            model=model,
            progress_callback=_progress,
            conversation_history=conversation_history,
            skill_slug=skill_slug,
        )
    except Exception as exc:
        logger.exception("Pi agent flow failed for session %s", session_id)
        if publish:
            await publish("error", {"status": "failed", "message": str(exc)})
        raise
