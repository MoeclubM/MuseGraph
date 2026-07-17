"""Agent Chat API router — Pi agent + MuseGraph memory/RAG/graph tools."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.database import async_session, get_db
from app.dependencies import get_current_user
from app.models.project import AgentMessage, AgentSession, AgentStep, TextProject
from app.models.user import User
from app.services.ai import OPERATION_MAX_TOKENS, call_llm, get_prompt, llm_billing_scope, resolve_explicit_component_model
from app.services.pi_agent_service import MuseGraphPiAgent, run_pi_agent_flow_background
from app.services.pi_agent_service import request_session_cancel
from app.services.pi_tool_loop import format_tool_result_preview
from app.services.project_access import PROJECT_PERMISSION_RUN_AI, require_project_permission

logger = logging.getLogger(__name__)

router = APIRouter()

def _enrich_step_for_client(step: dict[str, Any]) -> dict[str, Any]:
    """Ensure tool steps expose a human-readable preview in the API."""
    if not isinstance(step, dict):
        return step
    preview = str(step.get("tool_result_preview") or "").strip()
    if preview and not preview.lstrip().startswith("{"):
        return step
    step_type = str(step.get("step_type") or "")
    raw_out = step.get("output")
    if not raw_out:
        return step
    parsed: dict[str, Any] | None = None
    if isinstance(raw_out, dict):
        parsed = raw_out
    elif isinstance(raw_out, str):
        s = raw_out.strip()
        if s.startswith("{"):
            try:
                loaded = json.loads(s)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = None
    if parsed is None:
        return step
    generated = format_tool_result_preview(step_type, parsed)
    if generated:
        step = {**step, "tool_result_preview": generated}
    return step


_agent_sessions: dict[str, dict[str, Any]] = {}
_AGENT_COMPONENT_KEY = "operation_agent_task"
_AGENT_FLOW_TIMEOUT_SECONDS = settings.AGENT_FLOW_TIMEOUT_SECONDS


def _agent_tool_title(record: AgentSession) -> str | None:
    workspace = record.workspace if isinstance(record.workspace, dict) else {}
    if workspace.get("title_source") != "agent_tool":
        return None
    title = str(record.title or "").strip()
    return title or None


async def _persist_session(session: dict[str, Any]) -> None:
    project_id = str(session.get("project_id") or "")
    session_id = str(session.get("session_id") or "")
    if not project_id or not session_id:
        return
    async with async_session() as db:
        record = await db.get(AgentSession, session_id)
        if record is None:
            record = AgentSession(
                id=session_id,
                project_id=project_id,
                user_id=str(session.get("user_id") or ""),
                role=str(session.get("role") or "orchestrator"),
                parent_session_id=session.get("parent_session_id"),
                root_session_id=str(session.get("root_session_id") or session_id),
                parent_step_id=session.get("parent_step_id"),
                model=str(session.get("model") or ""),
            )
            db.add(record)
        _status = str(session.get("status") or "pending").lower()
        if _status == "cancelled":
            _status = "failed"
        record.status = _status
        record.role = str(session.get("role") or record.role or "orchestrator")
        record.parent_session_id = session.get("parent_session_id")
        record.root_session_id = str(session.get("root_session_id") or record.root_session_id or session_id)
        record.parent_step_id = session.get("parent_step_id")
        record.model = str(session.get("model") or "")
        record.workspace = session.get("agent_workspace") if isinstance(session.get("agent_workspace"), dict) else {}
        record.plan = session.get("plan") if isinstance(session.get("plan"), dict) else None
        if "title" in session:
            title = str(session.get("title") or "").strip()
            record.title = title or None

        for msg in session.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            msg_id = str(msg.get("message_id") or msg.get("id") or "").strip()
            if not msg_id:
                continue
            existing = await db.get(AgentMessage, msg_id)
            if existing is None:
                db.add(AgentMessage(
                    id=msg_id,
                    session_id=session_id,
                    role=str(msg.get("role") or "user"),
                    content=str(msg.get("content") or ""),
                    metadata_=msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {},
                ))
            else:
                existing.content = str(msg.get("content") or "")
                existing.metadata_ = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}

        for index, step in enumerate(session.get("steps") or []):
            if not isinstance(step, dict):
                continue
            step_id = str(step.get("step_id") or "").strip() or f"{session_id}:step:{index}"
            child_session_id = str(step.get("child_session_id") or "").strip()
            if child_session_id:
                child = await db.get(AgentSession, child_session_id)
                if child is None:
                    child = AgentSession(
                        id=child_session_id,
                        project_id=project_id,
                        user_id=str(session.get("user_id") or ""),
                        role=str(step.get("agent_role") or "updater"),
                        parent_session_id=session_id,
                        root_session_id=str(session.get("root_session_id") or session_id),
                        parent_step_id=step_id,
                        model=str(step.get("model") or ""),
                        status="pending",
                        workspace={"tool_args": step.get("tool_args")} if isinstance(step.get("tool_args"), dict) else {},
                    )
                    db.add(child)
                elif str(step.get("status") or "").lower() == "failed" and child.status in {"pending", "running"}:
                    child.status = "failed"
            existing = await db.get(AgentStep, step_id)
            metadata = step.get("metadata") if isinstance(step.get("metadata"), dict) else {}
            if existing is not None and existing.session_id != session_id:
                raise RuntimeError(
                    f"Agent step id collision: {step_id} belongs to session {existing.session_id}, not {session_id}"
                )
            if existing is None:
                db.add(AgentStep(
                    id=step_id,
                    session_id=session_id,
                    child_session_id=child_session_id or None,
                    step_index=step.get("step"),
                    total_steps=step.get("total_steps"),
                    step_type=str(step.get("step_type") or "step"),
                    status=str(step.get("status") or "pending").lower(),
                    message=str(step.get("message") or ""),
                    output=str(step.get("output")) if step.get("output") is not None else None,
                    output_preview=str(step.get("output_preview")) if step.get("output_preview") is not None else None,
                    metadata_=metadata,
                    agent_role=step.get("agent_role"),
                    model=step.get("model"),
                    tool_args=step.get("tool_args") if isinstance(step.get("tool_args"), dict) else None,
                    tool_result_preview=step.get("tool_result_preview"),
                ))
            else:
                existing.child_session_id = child_session_id or None
                existing.step_index = step.get("step")
                existing.total_steps = step.get("total_steps")
                existing.step_type = str(step.get("step_type") or existing.step_type)
                existing.status = str(step.get("status") or existing.status).lower()
                existing.message = str(step.get("message") or "")
                existing.output = str(step.get("output")) if step.get("output") is not None else None
                existing.output_preview = str(step.get("output_preview")) if step.get("output_preview") is not None else None
                existing.metadata_ = metadata
                existing.agent_role = step.get("agent_role")
                existing.model = step.get("model")
                existing.tool_args = step.get("tool_args") if isinstance(step.get("tool_args"), dict) else None
                existing.tool_result_preview = step.get("tool_result_preview")
        await db.commit()


def _session_record_to_dict(record: AgentSession) -> dict[str, Any]:
    children = sorted(record.children or [], key=lambda item: str(item.updated_at or item.created_at), reverse=True)
    return {
        "session_id": record.id,
        "project_id": record.project_id,
        "user_id": record.user_id,
        "role": record.role,
        "parent_session_id": record.parent_session_id,
        "root_session_id": record.root_session_id or record.id,
        "parent_step_id": record.parent_step_id,
        "title": _agent_tool_title(record),
        "model": record.model,
        "status": record.status,
        "messages": [
            {
                "message_id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.metadata_ or {},
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            }
            for msg in (record.messages or [])
        ],
        "steps": [
            _enrich_step_for_client({
                "step_id": step.id,
                "step": step.step_index,
                "total_steps": step.total_steps,
                "step_type": step.step_type,
                "status": step.status,
                "message": step.message,
                "output_preview": step.output_preview,
                "output": step.output,
                "metadata": step.metadata_ or {},
                "child_session_id": step.child_session_id,
                "agent_role": step.agent_role,
                "model": step.model,
                "tool_args": step.tool_args,
                "tool_result_preview": step.tool_result_preview,
                "created_at": step.created_at.isoformat() if step.created_at else "",
            })
            for step in (record.steps or [])
        ],
        "children": [
            {
                "session_id": child.id,
                "project_id": child.project_id,
                "role": child.role,
                "parent_session_id": child.parent_session_id,
                "root_session_id": child.root_session_id or child.id,
                "parent_step_id": child.parent_step_id,
                "title": _agent_tool_title(child),
                "status": child.status,
                "model": child.model,
                "message_count": len(child.messages or []),
                "archived_at": child.archived_at.isoformat() if child.archived_at else None,
                "created_at": child.created_at.isoformat() if child.created_at else "",
                "updated_at": child.updated_at.isoformat() if child.updated_at else "",
            }
            for child in children
        ],
        "agent_workspace": record.workspace or {},
        "plan": record.plan,
        "archived_at": record.archived_at.isoformat() if record.archived_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
    }


async def _load_persisted_session(project_id: str, session_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    async with async_session() as db:
        query = (
            select(AgentSession)
            .where(AgentSession.id == session_id)
            .where(AgentSession.project_id == project_id)
        )
        if user_id is not None:
            query = query.where(AgentSession.user_id == user_id)
        result = await db.execute(
            query.options(
                selectinload(AgentSession.messages),
                selectinload(AgentSession.steps),
                selectinload(AgentSession.children).selectinload(AgentSession.messages),
            )
        )
        record = result.scalar_one_or_none()
        return _session_record_to_dict(record) if record else None


async def _list_persisted_session_ids(project_id: str, user_id: str, *, include_archived: bool = False) -> list[str]:
    async with async_session() as db:
        query = (
            select(AgentSession.id)
            .where(AgentSession.project_id == project_id)
            .where(AgentSession.user_id == user_id)
        )
        if not include_archived:
            query = query.where(AgentSession.archived_at.is_(None))
        result = await db.execute(
            query.order_by(AgentSession.updated_at.desc())
        )
        return [str(item) for item in result.scalars().all()]


async def _session_tree_ids(db: AsyncSession, project_id: str, user_id: str, session_id: str) -> set[str]:
    ids = {session_id}
    frontier = [session_id]
    while frontier:
        result = await db.execute(
            select(AgentSession.id)
            .where(AgentSession.project_id == project_id)
            .where(AgentSession.user_id == user_id)
            .where(AgentSession.parent_session_id.in_(frontier))
        )
        children = [str(item) for item in result.scalars().all() if str(item) not in ids]
        ids.update(children)
        frontier = children
    while True:
        before = len(ids)
        for session in _agent_sessions.values():
            if session.get("project_id") != project_id or session.get("user_id") != user_id:
                continue
            parent_id = str(session.get("parent_session_id") or "")
            if parent_id in ids:
                ids.add(str(session.get("session_id")))
        if len(ids) == before:
            break
    return ids


def _summary_from_session(session: dict[str, Any]) -> "AgentSessionSummary":
    return AgentSessionSummary(
        session_id=session["session_id"],
        project_id=session["project_id"],
        role=str(session.get("role") or "orchestrator"),
        parent_session_id=session.get("parent_session_id"),
        root_session_id=session.get("root_session_id") or session["session_id"],
        parent_step_id=session.get("parent_step_id"),
        title=session.get("title"),
        status=session["status"],
        message_count=len(session.get("messages") or []),
        archived_at=session.get("archived_at"),
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )


def _summary_from_record(record: AgentSession) -> "AgentSessionSummary":
    return AgentSessionSummary(
        session_id=record.id,
        project_id=record.project_id,
        role=record.role or "orchestrator",
        parent_session_id=record.parent_session_id,
        root_session_id=record.root_session_id or record.id,
        parent_step_id=record.parent_step_id,
        title=_agent_tool_title(record),
        status=record.status,
        message_count=len(record.__dict__.get("messages") or []),
        archived_at=record.archived_at.isoformat() if record.archived_at else None,
        created_at=record.created_at.isoformat() if record.created_at else "",
        updated_at=record.updated_at.isoformat() if record.updated_at else "",
    )


class AgentChatRequest(BaseModel):
    message: str
    model: str = ""
    session_id: str | None = None
    skill_slug: str | None = None  # @-mention or programmatic preset
    plan_mode: bool = False  # Force plan-before-execute
    effort: str | None = None  # Per-request reasoning effort override: none|minimal|low|medium|high


class AgentChatResponse(BaseModel):
    session_id: str
    message_id: str
    status: str
    created_at: str


class AgentSessionSummary(BaseModel):
    session_id: str
    project_id: str
    role: str = "orchestrator"
    parent_session_id: str | None = None
    root_session_id: str | None = None
    parent_step_id: str | None = None
    title: str | None = None
    status: str
    message_count: int
    archived_at: str | None = None
    created_at: str
    updated_at: str


class AgentSuggestRequest(BaseModel):
    editor_text: str
    cursor_position: int = Field(default=0, ge=0)
    chapter_id: str | None = None
    model: str = ""
    skill_slug: str | None = None


class AgentSuggestResponse(BaseModel):
    suggestions: list[dict[str, Any]]
    memory_queries: list[str] = []
    raw: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

_STALE_RUNNING_GRACE_SECONDS = 120
_ORPHAN_RUNNING_MAX_AGE_SECONDS = 180


def _parse_iso_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _session_is_stale_running(session: dict[str, Any], *, session_id: str | None = None) -> bool:
    status = str(session.get("status") or "").lower()
    if status not in {"running", "pending"}:
        return False
    sid = session_id or str(session.get("session_id") or "")
    in_memory = bool(sid and sid in _agent_sessions)
    updated = _parse_iso_ts(session.get("updated_at"))
    if updated is None:
        return not in_memory
    age = (datetime.now(timezone.utc) - updated.astimezone(timezone.utc)).total_seconds()
    if not in_memory and age > _ORPHAN_RUNNING_MAX_AGE_SECONDS:
        return True
    return age > float(_AGENT_FLOW_TIMEOUT_SECONDS) + _STALE_RUNNING_GRACE_SECONDS


def _reconcile_orphan_running_session(session: dict[str, Any], *, reason: str) -> bool:
    """Mark DB/in-memory running sessions failed when no background worker owns them."""
    if not _session_is_stale_running(session, session_id=str(session.get("session_id") or "")):
        return False
    session["status"] = "failed"
    session["updated_at"] = _now_iso()
    for step in session.get("steps") or []:
        if isinstance(step, dict) and str(step.get("status") or "").lower() == "running":
            step["status"] = "failed"
            step["message"] = str(step.get("message") or "步骤已中断") + f"（{reason}）"
    note = f"Agent 会话已中断：{reason}。请新建会话或重新发送任务。"
    if not any(
        isinstance(m, dict) and m.get("role") == "assistant" and note in str(m.get("content") or "")
        for m in (session.get("messages") or [])
    ):
        _append_message(session, role="assistant", content=note)
    return True


async def reconcile_stale_agent_sessions() -> int:
    """Startup sweep: running/pending rows with no in-process worker become failed."""
    from sqlalchemy import select

    reconciled = 0
    async with async_session() as db:
        result = await db.execute(
            select(AgentSession)
            .where(AgentSession.status.in_(("running", "pending")))
            .options(
                selectinload(AgentSession.messages),
                selectinload(AgentSession.steps),
                selectinload(AgentSession.children).selectinload(AgentSession.messages),
            )
        )
        records = list(result.scalars().unique().all())
        for record in records:
            if record.id in _agent_sessions:
                continue
            session = _session_record_to_dict(record)
            status = str(session.get("status") or "").lower()
            if status not in {"running", "pending"}:
                continue
            if _reconcile_orphan_running_session(session, reason="服务重启后任务未恢复"):
                await _persist_session(session)
                reconciled += 1
    return reconciled



def _resolve_model(project: TextProject, explicit_model: str) -> str:
    candidate = (explicit_model or "").strip()
    if candidate:
        return candidate
    component_models = getattr(project, "component_models", None)
    if isinstance(component_models, dict):
        configured = component_models.get(_AGENT_COMPONENT_KEY)
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
    return ""


async def _get_project(project_id: str, user: User, db: AsyncSession) -> TextProject:
    return await require_project_permission(
        project_id,
        user,
        db,
        PROJECT_PERMISSION_RUN_AI,
        load_options=(selectinload(TextProject.chapters),),
    )


async def _get_session(
    session_id: str,
    project_id: str | None = None,
    *,
    prefer_persisted: bool = False,
    user_id: str | None = None,
) -> dict[str, Any]:
    session = _agent_sessions.get(session_id)
    if session is not None and user_id is not None and str(session.get("user_id") or "") != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent session belongs to another user.")
    # A live in-process session is the authoritative state while it is running;
    # the persisted snapshot lags behind it.
    if session is not None and str(session.get("status") or "").lower() in {"pending", "running"}:
        return session
    if prefer_persisted and project_id:
        if user_id is not None:
            persisted = await _load_persisted_session(project_id, session_id, user_id)
        else:
            persisted = await _load_persisted_session(project_id, session_id)
        if persisted is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent session {session_id} not found")
        _agent_sessions[session_id] = persisted
        return persisted
    if project_id and user_id is not None:
        persisted = await _load_persisted_session(project_id, session_id, user_id)
    elif project_id:
        persisted = await _load_persisted_session(project_id, session_id)
    else:
        persisted = None
    if persisted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent session {session_id} not found")
    if session_id not in _agent_sessions and _reconcile_orphan_running_session(
        persisted, reason="后台任务已丢失或超时"
    ):
        await _persist_session(persisted)
    _agent_sessions[session_id] = persisted
    return persisted


def _init_session(
    *,
    session_id: str,
    project_id: str,
    user_id: str,
    model: str,
    role: str = "orchestrator",
    parent_session_id: str | None = None,
    root_session_id: str | None = None,
    parent_step_id: str | None = None,
) -> dict[str, Any]:
    now = _now_iso()
    return {
        "session_id": session_id,
        "project_id": project_id,
        "user_id": user_id,
        "role": role,
        "parent_session_id": parent_session_id,
        "root_session_id": root_session_id or session_id,
        "parent_step_id": parent_step_id,
        "title": None,
        "model": model,
        "status": "pending",
        "messages": [],
        "steps": [],
        "children": [],
        "agent_workspace": {},
        "plan": None,
        "archived_at": None,
        "created_at": now,
        "updated_at": now,
    }


def _append_message(session: dict[str, Any], *, role: str, content: str, metadata: dict[str, Any] | None = None) -> str:
    message_id = uuid.uuid4().hex
    session["messages"].append({
        "message_id": message_id,
        "role": role,
        "content": content,
        "metadata": metadata or {},
        "created_at": _now_iso(),
    })
    session["updated_at"] = _now_iso()
    return message_id


def _redis_channel(session_id: str) -> str:
    return f"agent:{session_id}"


def _complete_running_plan_step(
    session: dict[str, Any],
    *,
    message: str = "Agent plan generated",
    output: str | None = None,
) -> None:
    for existing in reversed(session.get("steps") or []):
        if existing.get("step_type") == "plan" and existing.get("status") == "running":
            existing["status"] = "completed"
            existing["message"] = message
            if output is not None:
                existing["output"] = output
                existing["output_preview"] = output[:500]
            break


async def _publish_event(session_id: str, event_type: str, data: dict[str, Any]) -> None:
    from app.redis import redis_client

    payload = {"event": event_type, **data}
    await redis_client.publish(_redis_channel(session_id), json.dumps(payload, ensure_ascii=False))


def _sync_session_from_event(session: dict[str, Any], event_type: str, data: dict[str, Any]) -> None:
    if event_type == "plan":
        session["plan"] = data
        session["agent_workspace"].update({
            k: data[k]
            for k in ("text_type", "task_kind", "memory_schema", "structured_memory", "graph", "writing_plan")
            if data.get(k)
        })
        _complete_running_plan_step(
            session,
            message=str(data.get("message") or "Agent plan generated"),
            output=json.dumps(data, ensure_ascii=False, default=str),
        )
    elif event_type == "session_update":
        if "title" in data:
            title = str(data.get("title") or "").strip()
            session["title"] = title or None
            session["agent_workspace"]["title_source"] = "agent_tool"
    elif event_type == "step_start":
        step_type = str(data.get("step_type") or "")
        if step_type == "plan":
            for existing in reversed(session["steps"]):
                if existing.get("step_type") == "plan" and existing.get("status") == "running":
                    break
            else:
                step_record = {
                    "step": data.get("step"),
                    "total_steps": data.get("total_steps"),
                    "step_type": step_type,
                    "status": "running",
                    "message": data.get("message", ""),
                    "created_at": _now_iso(),
                }
                if data.get("step_id"):
                    step_record["step_id"] = data.get("step_id")
                for key in ("child_session_id", "agent_role", "model", "tool_args", "tool_result_preview"):
                    if data.get(key) is not None:
                        step_record[key] = data.get(key)
                session["steps"].append(step_record)
        else:
            _complete_running_plan_step(session, message="Agent plan selected next action")
            step_record = {
                "step": data.get("step"),
                "total_steps": data.get("total_steps"),
                "step_type": step_type,
                "status": "running",
                "message": data.get("message", ""),
                "created_at": _now_iso(),
            }
            if data.get("step_id"):
                step_record["step_id"] = data.get("step_id")
            for key in ("child_session_id", "agent_role", "model", "tool_args", "tool_result_preview"):
                if data.get(key) is not None:
                    step_record[key] = data.get(key)
            session["steps"].append(step_record)
    elif event_type in {"step_complete", "step_failed"}:
        step_num = int(data.get("step") or 0)
        step_type = str(data.get("step_type") or "")
        target = None
        step_id = str(data.get("step_id") or "").strip()
        if step_id:
            for existing in reversed(session["steps"]):
                if existing.get("step_id") == step_id:
                    target = existing
                    break
        if step_num > 0:
            step_index = step_num - 1
            if target is None and 0 <= step_index < len(session["steps"]):
                target = session["steps"][step_index]
        if target is None:
            for existing in reversed(session["steps"]):
                if existing.get("status") == "running" and (
                    not step_type or existing.get("step_type") == step_type
                ):
                    target = existing
                    break
        if target is not None:
            target.update({
                "status": data.get("status", "failed" if event_type == "step_failed" else "completed"),
                "message": data.get("message", ""),
                "output_preview": data.get("output_preview", ""),
                "output": data.get("output"),
            })
            for key in ("child_session_id", "agent_role", "model", "tool_args", "tool_result_preview"):
                if data.get(key) is not None:
                    target[key] = data.get(key)
        else:
            step_record = {
                "step": data.get("step"),
                "total_steps": data.get("total_steps"),
                "step_type": step_type,
                "status": data.get("status", "failed" if event_type == "step_failed" else "completed"),
                "message": data.get("message", ""),
                "output_preview": data.get("output_preview", ""),
                "output": data.get("output"),
                "created_at": _now_iso(),
            }
            if data.get("step_id"):
                step_record["step_id"] = data.get("step_id")
            for key in ("child_session_id", "agent_role", "model", "tool_args", "tool_result_preview"):
                if data.get(key) is not None:
                    step_record[key] = data.get(key)
            session["steps"].append(step_record)
    elif event_type == "complete":
        _complete_running_plan_step(session, message="Agent plan completed")
        session["status"] = data.get("status", "completed")
        output = data.get("output") or data.get("summary") or data.get("output_preview") or ""
        if data.get("structured_memory"):
            session["agent_workspace"]["structured_memory"] = data["structured_memory"]
        if data.get("graph"):
            session["agent_workspace"]["graph"] = data["graph"]
        if output:
            _append_message(session, role="assistant", content=str(output))
    elif event_type == "error":
        session["status"] = "failed"
    session["updated_at"] = _now_iso()


async def run_agent_flow_background(
    session_id: str,
    project_id: str,
    user_id: str,
    message: str,
    model: str,
    skill_slug: str | None = None,
    effort: str | None = None,
) -> None:
    session = _agent_sessions.get(session_id)
    if session is None:
        logger.error("Agent session %s disappeared before flow started", session_id)
        return

    session["status"] = "running"
    await _persist_session(session)

    async def _publish(event_type: str, data: dict[str, Any]) -> None:
        if event_type == "generation_delta":
            # Token deltas are transient UI events; never hit the database for them.
            await _publish_event(session_id, event_type, data)
            return
        if event_type == "thinking_delta":
            await _publish_event(session_id, event_type, data)
            return
        _sync_session_from_event(session, event_type, data)
        await _persist_session(session)
        await _publish_event(session_id, event_type, data)

    history = [
        {"role": m.get("role"), "content": m.get("content")}
        for m in session.get("messages", [])[:-1]
        if isinstance(m, dict) and m.get("content")
    ]

    heartbeat_stop = asyncio.Event()

    async def _session_heartbeat() -> None:
        while not heartbeat_stop.is_set():
            try:
                await asyncio.wait_for(heartbeat_stop.wait(), timeout=20)
                break
            except asyncio.TimeoutError:
                pass
            if str(session.get("status") or "").lower() not in {"running", "pending"}:
                break
            session["updated_at"] = _now_iso()
            await _persist_session(session)

    heartbeat_task = asyncio.create_task(_session_heartbeat())

    try:
        result = await asyncio.wait_for(
            run_pi_agent_flow_background(
                session_id=session_id,
                instruction=message,
                project_id=project_id,
                user_id=user_id,
                model=model,
                publish=_publish,
                conversation_history=history,
                skill_slug=skill_slug,
                effort=effort,
            ),
            timeout=_AGENT_FLOW_TIMEOUT_SECONDS,
        )
        session["status"] = str(result.get("status", "completed")).lower()
        session["agent_workspace"]["last_result"] = result
        plan_result = result.get("plan_result") if isinstance(result.get("plan_result"), dict) else {}
        if plan_result and not session.get("plan"):
            # The Pi tool loop does not emit a dedicated "plan" event; surface its
            # final plan_result so clients always get a session plan snapshot.
            session["plan"] = plan_result
            session["agent_workspace"].update({
                key: plan_result[key]
                for key in ("text_type", "task_kind", "memory_schema", "structured_memory", "graph", "writing_plan")
                if plan_result.get(key)
            })
        session["updated_at"] = _now_iso()
        await _persist_session(session)
        try:
            from app.services.chapter_writeback import ensure_chapter_from_agent_payload

            await ensure_chapter_from_agent_payload(
                project_id=project_id,
                plan_result=plan_result,
                step_results=result.get("steps") if isinstance(result.get("steps"), list) else [],
                messages=session.get("messages") if isinstance(session.get("messages"), list) else [],
                agent_workspace=session.get("agent_workspace") if isinstance(session.get("agent_workspace"), dict) else {},
            )
        except Exception:
            logger.warning("Post-agent chapter writeback failed for session %s", session_id, exc_info=True)
    except asyncio.TimeoutError:
        logger.error("Agent flow timed out for session %s after %ss", session_id, _AGENT_FLOW_TIMEOUT_SECONDS)
        session["status"] = "failed"
        session["updated_at"] = _now_iso()
        err_msg = f"Agent flow timed out after {_AGENT_FLOW_TIMEOUT_SECONDS // 60} minutes"
        _append_message(session, role="assistant", content=f"Agent failed: {err_msg}")
        await _persist_session(session)
        await _publish("error", {"status": "failed", "message": err_msg})
    except asyncio.CancelledError:
        logger.info("Agent flow cancelled for session %s", session_id)
        session["status"] = "cancelled"
        session["updated_at"] = _now_iso()
        _append_message(session, role="assistant", content="Task cancelled by user.")
        await _persist_session(session)
        await _publish("session_snapshot", session)
    except Exception as exc:
        logger.exception("Agent flow failed for session %s", session_id)
        session["status"] = "failed"
        session["updated_at"] = _now_iso()
        err_msg = str(exc) or "Agent flow failed"
        _append_message(session, role="assistant", content=f"Agent failed: {err_msg}")
        await _persist_session(session)
        await _publish("error", {"status": "failed", "message": err_msg})
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat_task
        if str(session.get("status") or "").lower() == "running":
            session["status"] = "failed"
            session["updated_at"] = _now_iso()
            await _persist_session(session)


@router.post("/chat", response_model=AgentChatResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_agent_chat(
    project_id: str,
    body: AgentChatRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    model = _resolve_model(project, body.model)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent model is required (provide 'model' or configure component_models.operation_agent_task).",
        )

    session_id = body.session_id or uuid.uuid4().hex
    session = _agent_sessions.get(session_id)
    if session is None and body.session_id:
        session = await _load_persisted_session(project_id, session_id, user.id)
    if session is not None:
        if session["project_id"] != project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session belongs to a different project.")
        if str(session.get("user_id") or "") != user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent session belongs to another user.")
        session["model"] = model
        _agent_sessions[session_id] = session
    else:
        session = _init_session(session_id=session_id, project_id=project_id, user_id=user.id, model=model)
        _agent_sessions[session_id] = session

    status_lower = str(session.get("status") or "").lower()
    if status_lower == "running":
        if session_id not in _agent_sessions and _reconcile_orphan_running_session(
            session, reason="检测到僵死运行状态，已自动结束"
        ):
            await _persist_session(session)
            status_lower = "failed"
        elif _session_is_stale_running(session):
            _reconcile_orphan_running_session(session, reason="运行超时，已自动结束")
            await _persist_session(session)
            status_lower = "failed"
        if status_lower == "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Agent is still running for this session. Wait for completion or start a new session.",
            )

    message_id = _append_message(session, role="user", content=body.message)
    session["status"] = "pending"
    session["steps"] = []
    session["updated_at"] = _now_iso()
    await _persist_session(session)

    background_tasks.add_task(
        run_agent_flow_background,
        session_id,
        project_id,
        user.id,
        body.message,
        model,
        body.skill_slug,
        body.effort,
    )

    return AgentChatResponse(session_id=session_id, message_id=message_id, status="PENDING", created_at=session["created_at"])


@router.post("/chat/{session_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_agent_chat(
    project_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
):
    session = _agent_sessions.get(session_id)
    if session is None:
        session = await _load_persisted_session(project_id, session_id, user.id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session["project_id"] != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session belongs to a different project.")
    if str(session.get("user_id") or "") != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent session belongs to another user.")

    status_lower = str(session.get("status") or "").lower()
    if status_lower not in {"running", "pending"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not running; nothing to cancel")

    request_session_cancel(session_id)
    session["status"] = "failed"
    session["updated_at"] = _now_iso()
    _append_message(session, role="assistant", content="任务已由用户取消。")
    _agent_sessions[session_id] = session
    await _persist_session(session)
    return None


@router.post("/suggest", response_model=AgentSuggestResponse)
async def agent_suggest(
    project_id: str,
    body: AgentSuggestRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RAG-backed collaborative writing suggestions (code-completion style)."""
    project = await require_project_permission(
        project_id,
        user,
        db,
        PROJECT_PERMISSION_RUN_AI,
        load_options=(
            selectinload(TextProject.chapters),
        ),
    )
    model = _resolve_model(project, body.model)
    if not model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Suggest model is required.")

    # Resolve a skill: explicit @-mention from request wins, otherwise pick
    # the highest sort_order skill whose scope contains "suggest" (e.g. coauthor).
    from app.services.agent.skills import (
        list_project_visible_skills,
        load_active_skill,
    )

    requested_slug = (body.skill_slug or "").strip()
    if not requested_slug:
        suggest_visible = await list_project_visible_skills(project_id, scope="suggest", db=db)
        if suggest_visible:
            requested_slug = suggest_visible[0]["slug"]
    resolved_skill = await load_active_skill(requested_slug, db) if requested_slug else None

    agent = MuseGraphPiAgent()
    try:
        prompt_input = await agent.build_suggest_context(
            project=project,
            editor_text=body.editor_text,
            cursor_position=body.cursor_position,
            chapter_id=body.chapter_id,
            db=db,
            skill_system_prompt=(resolved_skill.system_prompt if resolved_skill else None),
        )
    except Exception as exc:
        logger.warning("Suggest context build failed for project %s: %s", project_id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    prompt = await get_prompt("AGENT_SUGGEST", prompt_input, db, project=project)
    suggest_component_key = (
        resolved_skill.default_model_component if resolved_skill and resolved_skill.default_model_component
        else _AGENT_COMPONENT_KEY
    )
    resolved_model = resolve_explicit_component_model(project, suggest_component_key, model) or model

    try:
        with llm_billing_scope(user_id=user.id, project_id=project.id):
            llm_result = await call_llm(
                resolved_model,
                prompt,
                db,
                max_tokens=OPERATION_MAX_TOKENS.get("AGENT_SUGGEST", 2048),
                billing_user_id=user.id,
                billing_project_id=project.id,
            )
    except Exception as exc:
        logger.warning("Suggest LLM call failed for project %s: %s", project_id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    raw = str(llm_result.get("content") or "")
    suggestions: list[dict[str, Any]] = []
    memory_queries: list[str] = []
    try:
        start = raw.index("{")
        end = raw.rindex("}")
        parsed = json.loads(raw[start : end + 1])
        if isinstance(parsed.get("suggestions"), list):
            suggestions = [s for s in parsed["suggestions"] if isinstance(s, dict)]
        if isinstance(parsed.get("memory_queries"), list):
            memory_queries = [str(q) for q in parsed["memory_queries"]]
    except (ValueError, json.JSONDecodeError):
        if raw.strip():
            suggestions = [{"type": "continuation", "title": "Suggestion", "insert_text": raw.strip()}]

    return AgentSuggestResponse(suggestions=suggestions, memory_queries=memory_queries, raw=raw)


@router.get("/chat/{session_id}/stream")
async def stream_agent_chat(
    project_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    await _get_session(session_id, project_id, user_id=user.id)

    async def event_generator():
        import redis.asyncio as aioredis

        sub_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = sub_client.pubsub()
        channel = _redis_channel(session_id)
        await pubsub.subscribe(channel)
        try:
            snapshot = await _get_session(session_id, project_id, user_id=user.id)
            yield {"event": "session_snapshot", "data": json.dumps(snapshot, ensure_ascii=False)}
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if message is None:
                    yield {"event": "heartbeat", "data": "{}"}
                    continue
                if message.get("type") != "message":
                    continue
                try:
                    data: dict[str, Any] = json.loads(message.get("data"))
                except (json.JSONDecodeError, TypeError):
                    continue
                event_type = data.pop("event", "progress")
                yield {"event": event_type, "data": json.dumps(data, ensure_ascii=False)}
                if event_type in ("complete", "error"):
                    break
        except asyncio.CancelledError:
            logger.info("SSE client disconnected for session %s", session_id)
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                pass
            try:
                await sub_client.aclose()
            except Exception:
                pass

    return EventSourceResponse(event_generator())


@router.get("/chat/{session_id}")
async def get_agent_session(
    project_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    session = await _get_session(session_id, project_id, prefer_persisted=True, user_id=user.id)
    if session["project_id"] != project_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session does not belong to this project.")
    return {
        "session_id": session["session_id"],
        "project_id": session["project_id"],
        "role": session.get("role", "orchestrator"),
        "parent_session_id": session.get("parent_session_id"),
        "root_session_id": session.get("root_session_id") or session["session_id"],
        "parent_step_id": session.get("parent_step_id"),
        "title": session.get("title"),
        "status": session["status"],
        "model": session["model"],
        "messages": session["messages"],
        "steps": [_enrich_step_for_client(dict(s)) if isinstance(s, dict) else s for s in (session.get("steps") or [])],
        "children": session.get("children") or [],
        "agent_workspace": session["agent_workspace"],
        "workspace": session["agent_workspace"],
        "plan": session.get("plan"),
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
    }


@router.get("/sessions", response_model=list[AgentSessionSummary])
async def list_agent_sessions(
    project_id: str,
    include_archived: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    seen: set[str] = set()
    results: list[AgentSessionSummary] = []

    for session_id in await _list_persisted_session_ids(project_id, user.id, include_archived=include_archived):
        session = await _load_persisted_session(project_id, session_id, user.id)
        if not session:
            continue
        seen.add(session_id)
        _agent_sessions[session_id] = session
        results.append(_summary_from_session(session))

    for session in _agent_sessions.values():
        if session["project_id"] != project_id or session["session_id"] in seen:
            continue
        if str(session.get("user_id") or "") != user.id:
            continue
        if not include_archived and session.get("archived_at"):
            continue
        results.append(_summary_from_session(session))

    results.sort(key=lambda s: s.updated_at, reverse=True)
    return results


@router.post("/sessions/{session_id}/archive", response_model=AgentSessionSummary)
async def archive_agent_session(
    project_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    ids = await _session_tree_ids(db, project_id, user.id, session_id)
    result = await db.execute(
        select(AgentSession)
        .where(AgentSession.project_id == project_id)
        .where(AgentSession.user_id == user.id)
        .where(AgentSession.id.in_(ids))
    )
    records = list(result.scalars().all())
    if session_id not in {record.id for record in records} and session_id not in _agent_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent session {session_id} not found")

    archived_at = datetime.now(timezone.utc)
    for record in records:
        record.archived_at = archived_at
    await db.commit()

    for target_id in ids:
        if target_id in _agent_sessions:
            _agent_sessions[target_id]["archived_at"] = archived_at.isoformat()
            _agent_sessions[target_id]["updated_at"] = archived_at.isoformat()

    record = next((item for item in records if item.id == session_id), None)
    if record is not None:
        return _summary_from_record(record)
    session = _agent_sessions[session_id]
    session["archived_at"] = archived_at.isoformat()
    return _summary_from_session(session)


@router.post("/sessions/{session_id}/unarchive", response_model=AgentSessionSummary)
async def unarchive_agent_session(
    project_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    ids = await _session_tree_ids(db, project_id, user.id, session_id)
    result = await db.execute(
        select(AgentSession)
        .where(AgentSession.project_id == project_id)
        .where(AgentSession.user_id == user.id)
        .where(AgentSession.id.in_(ids))
    )
    records = list(result.scalars().all())
    if session_id not in {record.id for record in records} and session_id not in _agent_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent session {session_id} not found")

    updated_at = datetime.now(timezone.utc)
    for record in records:
        record.archived_at = None
    await db.commit()

    for target_id in ids:
        if target_id in _agent_sessions:
            _agent_sessions[target_id]["archived_at"] = None
            _agent_sessions[target_id]["updated_at"] = updated_at.isoformat()

    record = next((item for item in records if item.id == session_id), None)
    if record is not None:
        return _summary_from_record(record)
    session = _agent_sessions[session_id]
    session["archived_at"] = None
    return _summary_from_session(session)


class AgentSessionRenameRequest(BaseModel):
    title: str


@router.patch("/sessions/{session_id}/rename", response_model=AgentSessionSummary)
async def rename_agent_session(
    project_id: str,
    session_id: str,
    body: AgentSessionRenameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    result = await db.execute(
        select(AgentSession)
        .where(AgentSession.project_id == project_id)
        .where(AgentSession.user_id == user.id)
        .where(AgentSession.id == session_id)
    )
    record = result.scalar_one_or_none()
    if record is None and session_id not in _agent_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent session {session_id} not found")

    title = body.title.strip() or None

    if record is not None:
        record.title = title
        await db.commit()
        await db.refresh(record)
        summary = _summary_from_record(record)
    else:
        session = _agent_sessions[session_id]
        session["title"] = title
        summary = _summary_from_session(session)

    if session_id in _agent_sessions:
        _agent_sessions[session_id]["title"] = title

    return summary


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_session(
    project_id: str,
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    ids = await _session_tree_ids(db, project_id, user.id, session_id)
    result = await db.execute(
        select(AgentSession)
        .where(AgentSession.project_id == project_id)
        .where(AgentSession.user_id == user.id)
        .where(AgentSession.id.in_(ids))
    )
    records = list(result.scalars().all())
    if session_id not in {record.id for record in records} and session_id not in _agent_sessions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent session {session_id} not found")

    for record in records:
        await db.delete(record)
    await db.commit()

    for target_id in ids:
        _agent_sessions.pop(target_id, None)
    return None
