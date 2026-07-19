from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import TextProject
from app.models.runtime import AgentEvent, AgentRun, AuditLog, ProjectRevision
from app.models.user import User
from app.redis import redis_client
from app.schemas.runtime import (
    AgentReviewRequest,
    AgentRunRequest,
    AgentRunResponse,
    ChangeSet,
    FileChange,
    KnowledgeOperation,
    ProjectRevisionResponse,
)
from app.services.agent.skills import resolve_project_skill
from app.services.agent.configuration import resolve_project_agent
from app.services.agent_engine import append_agent_event
from app.services.agent_workspace import (
    apply_knowledge_operations,
    delete_run_workspace,
    publish_file_changes,
)
from app.services.memory_client import (
    forget_knowledge_dataset,
    list_knowledge_records,
    remember_knowledge_dataset,
)
from app.services.memory_config import ensure_project_memory_instance
from app.services.project_access import (
    PROJECT_PERMISSION_EDIT,
    PROJECT_PERMISSION_VIEW,
    require_project_permission,
)
from app.services.rate_limit import enforce_rate_limit
from app.services.project_git import restore_project_git_commit

router = APIRouter()
TERMINAL_STATUSES = {"completed", "rejected", "conflicted", "failed", "cancelled"}
knowledge_operations_adapter = TypeAdapter(list[KnowledgeOperation])


async def _get_run(
    project_id: str,
    run_id: str,
    user: User,
    db: AsyncSession,
    *,
    edit: bool = False,
) -> AgentRun:
    await require_project_permission(
        project_id,
        user,
        db,
        PROJECT_PERMISSION_EDIT if edit else PROJECT_PERMISSION_VIEW,
    )
    result = await db.execute(
        select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.project_id == project_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return run


@router.post("/runs", response_model=AgentRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_agent_run(
    project_id: str,
    body: AgentRunRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permission = PROJECT_PERMISSION_EDIT if body.mode == "write" else PROJECT_PERMISSION_VIEW
    project = await require_project_permission(project_id, user, db, permission)
    await enforce_rate_limit(
        f"agent:start:{user.id}:{project_id}",
        settings.AGENT_RATE_LIMIT_PER_MINUTE,
    )
    if not project.active_revision_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has no active revision",
        )
    role = {"write": "writer", "analyze": "auditor", "suggest": "writer"}[body.mode]
    try:
        project_agent, agent_snapshot = await resolve_project_agent(
            db,
            project=project,
            mode=body.mode,
            requested_agent_id=body.agent_id,
        )
        skill = await resolve_project_skill(
            db,
            project_id=project_id,
            pack_slug=project.pack_slug,
            operation=body.mode,
            role=role,
            requested_slug=body.skill_slug,
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    run = AgentRun(
        project_id=project_id,
        user_id=user.id,
        base_revision_id=project.active_revision_id,
        agent_id=project_agent.id,
        mode=body.mode,
        status="queued",
        instruction=body.instruction,
        model=agent_snapshot.model,
        effort=agent_snapshot.effort,
        target_refs=body.target_refs,
        skill_snapshot=skill.model_dump(mode="json"),
        agent_snapshot=agent_snapshot.model_dump(mode="json"),
        change_set=ChangeSet().model_dump(mode="json"),
    )
    db.add(run)
    await db.flush()
    db.add(
        AuditLog(
            actor_user_id=user.id,
            project_id=project_id,
            action="agent.run.create",
            target_type="agent_run",
            target_id=run.id,
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
            detail={
                "mode": body.mode,
                "skill": skill.slug,
                "agent_id": project_agent.id,
                "agent_version": project_agent.version,
            },
        )
    )
    await db.commit()
    await append_agent_event(
        run.id,
        "queued",
        {"mode": run.mode, "skill": skill.slug, "agent_id": project_agent.id},
    )
    await db.refresh(run)
    return AgentRunResponse.model_validate(run)


@router.get("/runs", response_model=list[AgentRunResponse])
async def list_agent_runs(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.project_id == project_id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
    )
    return [AgentRunResponse.model_validate(run) for run in result.scalars()]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_agent_run(
    project_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return AgentRunResponse.model_validate(await _get_run(project_id, run_id, user, db))


@router.get("/runs/{run_id}/changes", response_model=ChangeSet)
async def get_agent_changes(
    project_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(project_id, run_id, user, db)
    return ChangeSet.model_validate(run.change_set)


async def _event_rows(run_id: str, after: int) -> list[AgentEvent]:
    from app.database import async_session

    async with async_session() as db:
        result = await db.execute(
            select(AgentEvent)
            .where(AgentEvent.run_id == run_id, AgentEvent.sequence > after)
            .order_by(AgentEvent.sequence)
        )
        return list(result.scalars())


async def _run_status(run_id: str) -> str:
    from app.database import async_session

    async with async_session() as db:
        result = await db.execute(select(AgentRun.status).where(AgentRun.id == run_id))
        return str(result.scalar_one())


@router.get("/runs/{run_id}/events")
async def stream_agent_events(
    project_id: str,
    run_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    after: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_run(project_id, run_id, user, db)
    cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else after

    async def events() -> AsyncIterator[dict[str, str]]:
        nonlocal cursor
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"agent-run:{run_id}")
        try:
            while True:
                rows = await _event_rows(run_id, cursor)
                for row in rows:
                    cursor = row.sequence
                    yield {
                        "id": str(row.sequence),
                        "event": row.event_type,
                        "data": json.dumps(row.data, ensure_ascii=False),
                    }
                current_status = await _run_status(run_id)
                if current_status in TERMINAL_STATUSES or current_status == "awaiting_review":
                    return
                if await request.is_disconnected():
                    return
                await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                await asyncio.sleep(0)
        finally:
            await pubsub.unsubscribe(f"agent-run:{run_id}")
            await pubsub.aclose()

    return EventSourceResponse(events())


@router.post("/runs/{run_id}/cancel", response_model=AgentRunResponse)
async def cancel_agent_run(
    project_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await _get_run(project_id, run_id, user, db, edit=True)
    if run.status not in {"queued", "running"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel run in status {run.status}",
        )
    run.cancel_requested = True
    if run.status == "queued":
        run.status = "cancelled"
        run.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await append_agent_event(run.id, "cancel_requested", {})
    await db.refresh(run)
    return AgentRunResponse.model_validate(run)


@router.post("/runs/{run_id}/review", response_model=AgentRunResponse)
async def review_agent_run(
    project_id: str,
    run_id: str,
    body: AgentReviewRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    dataset_created = False
    git_published = False
    dataset_name = ""
    base_git_commit = ""
    try:
        async with db.begin_nested():
            run_result = await db.execute(
                select(AgentRun)
                .where(AgentRun.id == run_id, AgentRun.project_id == project_id)
                .with_for_update()
            )
            run = run_result.scalar_one_or_none()
            if run is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
            if run.status != "awaiting_review":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Run is not awaiting review: {run.status}",
                )
            project_result = await db.execute(
                select(TextProject).where(TextProject.id == project_id).with_for_update()
            )
            project = project_result.scalar_one()
            if body.decision == "reject":
                run.status = "rejected"
                run.completed_at = datetime.now(timezone.utc)
                delete_run_workspace(run.id)
                db.add(
                    AuditLog(
                        actor_user_id=user.id,
                        project_id=project_id,
                        action="agent.run.reject",
                        target_type="agent_run",
                        target_id=run.id,
                        request_id=getattr(request.state, "request_id", None),
                        ip_address=request.client.host if request.client else None,
                        detail={},
                    )
                )
            elif project.active_revision_id != run.base_revision_id:
                run.status = "conflicted"
                run.completed_at = datetime.now(timezone.utc)
            else:
                run.status = "accepting"
                await db.flush()
                revision_id = str(uuid.uuid4())
                base_revision = (
                    await db.execute(
                        select(ProjectRevision).where(ProjectRevision.id == run.base_revision_id)
                    )
                ).scalar_one()
                await ensure_project_memory_instance(project, db)
                base_git_commit = base_revision.git_commit
                base_records = await list_knowledge_records(
                    project_id,
                    base_revision.knowledge_dataset,
                )
                if base_records:
                    await ensure_project_memory_instance(project, db, require_models=True)
                operations = knowledge_operations_adapter.validate_python(
                    run.change_set.get("knowledge") or []
                )
                records = apply_knowledge_operations(base_records, operations, revision_id)
                dataset_name = f"project:{project_id}:revision:{revision_id}"
                await remember_knowledge_dataset(project_id, dataset_name, records)
                dataset_created = True
                changes = [
                    FileChange.model_validate(item)
                    for item in (run.change_set.get("files") or [])
                ]
                git_commit = publish_file_changes(
                    project_id,
                    run.id,
                    changes,
                    f"Accept Agent run {run.id[:12]}",
                )
                git_published = bool(changes)
                base_revision.status = "superseded"
                revision = ProjectRevision(
                    id=revision_id,
                    project_id=project_id,
                    parent_revision_id=base_revision.id,
                    git_commit=git_commit,
                    knowledge_dataset=dataset_name,
                    created_by_run_id=run.id,
                    status="active",
                    message=f"Accept Agent run {run.id[:12]}",
                )
                db.add(revision)
                await db.flush()
                project.active_revision_id = revision.id
                run.status = "completed"
                run.result_revision_id = revision.id
                run.completed_at = datetime.now(timezone.utc)
                db.add(
                    AuditLog(
                        actor_user_id=user.id,
                        project_id=project_id,
                        action="agent.run.accept",
                        target_type="agent_run",
                        target_id=run.id,
                        request_id=getattr(request.state, "request_id", None),
                        ip_address=request.client.host if request.client else None,
                        detail={"revision_id": revision.id},
                    )
                )
        await db.commit()
    except Exception:
        await db.rollback()
        if git_published:
            restore_project_git_commit(project_id, base_git_commit)
        if dataset_created:
            await forget_knowledge_dataset(project_id, dataset_name)
        raise
    delete_run_workspace(run.id)
    await append_agent_event(
        run.id,
        run.status,
        {"result_revision_id": run.result_revision_id},
    )
    await db.refresh(run)
    return AgentRunResponse.model_validate(run)


@router.get("/revisions", response_model=list[ProjectRevisionResponse])
async def list_project_revisions(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    result = await db.execute(
        select(ProjectRevision)
        .where(ProjectRevision.project_id == project_id)
        .order_by(ProjectRevision.created_at.desc())
    )
    return [ProjectRevisionResponse.model_validate(item) for item in result.scalars()]
