from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import ProjectFact, TextProject
from app.models.user import User
from app.schemas.fact import (
    ProjectFactBatchUpdateRequest,
    ProjectFactBatchUpdateResponse,
    ProjectFactCreate,
    ProjectFactListResponse,
    ProjectFactResponse,
    ProjectFactSyncResponse,
    ProjectFactUpdate,
    ProjectEntitySearchRequest,
    ProjectEntitySearchResponse,
    ProjectEntitySearchResult,
)
from app.services.fact_entities import (
    collect_project_entities,
    group_entities_by_type,
    merge_structured_memory,
    search_project_entities,
)
from app.services.fact_memory import apply_fact_hash, schedule_fact_memory_sync
from app.services.project_access import (
    PROJECT_PERMISSION_EDIT,
    PROJECT_PERMISSION_RUN_AI,
    PROJECT_PERMISSION_VIEW,
    require_project_permission,
)
from app.services.project_files import extract_text_from_file, save_project_file
from app.services.project_workspace import (
    delete_project_fact_file,
    write_project_fact_file,
    write_project_manifest,
)


router = APIRouter()


def _fact_response(fact: ProjectFact) -> ProjectFactResponse:
    return ProjectFactResponse(
        id=fact.id,
        project_id=fact.project_id,
        created_by_user_id=fact.created_by_user_id,
        created_by_agent_session_id=fact.created_by_agent_session_id,
        source_kind=fact.source_kind,
        source_ref=fact.source_ref,
        title=fact.title,
        content=fact.content,
        metadata=fact.metadata_,
        ontology_snapshot=fact.ontology_snapshot,
        entities=fact.entities,
        relationships=fact.relationships,
        content_hash=fact.content_hash,
        memory_status=fact.memory_status,
        memory_task_id=fact.memory_task_id,
        memory_error=fact.memory_error,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
    )


async def _load_fact(project_id: str, fact_id: str, db: AsyncSession) -> ProjectFact:
    result = await db.execute(
        select(ProjectFact)
        .where(ProjectFact.project_id == project_id)
        .where(ProjectFact.id == fact_id)
    )
    fact = result.scalar_one_or_none()
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    return fact


async def _load_project_for_workspace(
    project_id: str,
    user: User,
    db: AsyncSession,
    permission: str,
) -> TextProject:
    return await require_project_permission(
        project_id,
        user,
        db,
        permission,
        load_options=(
            selectinload(TextProject.chapters),
            selectinload(TextProject.facts),
        ),
    )


def _workspace_facts(project: TextProject, fact: ProjectFact | None = None, deleted_fact_id: str | None = None) -> list[ProjectFact]:
    facts = [item for item in project.__dict__.get("facts") or [] if item.id != deleted_fact_id]
    if fact is not None and all(item.id != fact.id for item in facts):
        facts.append(fact)
    return facts


def _write_fact_workspace(project: TextProject, fact: ProjectFact) -> None:
    write_project_fact_file(project.id, fact)
    write_project_manifest(
        project,
        project.__dict__.get("chapters") or [],
        _workspace_facts(project, fact),
    )
    from app.services.project_git import commit_project_git, push_project_git_branch, stage_project_git_paths

    stage_project_git_paths(project.id)
    snapshot = commit_project_git(project.id, "Update project fact")
    push_project_git_branch(project.id, "origin", snapshot["branch"])


def _delete_fact_workspace(project: TextProject, fact_id: str) -> None:
    delete_project_fact_file(project.id, fact_id)
    write_project_manifest(
        project,
        project.__dict__.get("chapters") or [],
        _workspace_facts(project, deleted_fact_id=fact_id),
    )
    from app.services.project_git import commit_project_git, push_project_git_branch, stage_project_git_paths

    stage_project_git_paths(project.id)
    snapshot = commit_project_git(project.id, "Delete project fact")
    push_project_git_branch(project.id, "origin", snapshot["branch"])


async def _schedule_sync_after_commit(
    *,
    project_id: str,
    user_id: str,
    action: str,
    fact_id: str | None,
    db: AsyncSession,
) -> str:
    await db.commit()
    task_id = schedule_fact_memory_sync(
        project_id=project_id,
        user_id=user_id,
        action=action,
        fact_id=fact_id,
    )
    if fact_id:
        fact = await _load_fact(project_id, fact_id, db)
        fact.memory_task_id = task_id
        fact.memory_status = "syncing"
        fact.memory_error = None
        await db.commit()
        await db.refresh(fact)
    return task_id


@router.get("", response_model=ProjectFactListResponse)
async def list_project_facts(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_project_for_workspace(project_id, user, db, PROJECT_PERMISSION_VIEW)
    result = await db.execute(
        select(ProjectFact)
        .where(ProjectFact.project_id == project_id)
        .order_by(ProjectFact.updated_at.desc())
    )
    return ProjectFactListResponse(facts=[_fact_response(fact) for fact in result.scalars().all()])


@router.post("", response_model=ProjectFactResponse, status_code=status.HTTP_201_CREATED)
async def create_project_fact(
    project_id: str,
    body: ProjectFactCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _load_project_for_workspace(project_id, user, db, PROJECT_PERMISSION_EDIT)
    fact = ProjectFact(
        id=str(uuid4()),
        project_id=project_id,
        created_by_user_id=user.id,
        source_kind=body.source_kind.strip() or "manual",
        source_ref=body.source_ref,
        title=body.title.strip(),
        content=body.content,
        metadata_=body.metadata,
        memory_status="pending",
    )
    apply_fact_hash(fact)
    db.add(fact)
    await db.flush()
    fact_id = fact.id
    await _schedule_sync_after_commit(
        project_id=project_id,
        user_id=user.id,
        action="create",
        fact_id=fact_id,
        db=db,
    )
    fact = await _load_fact(project_id, fact_id, db)
    _write_fact_workspace(project, fact)
    return _fact_response(fact)


@router.post("/upload", response_model=ProjectFactResponse, status_code=status.HTTP_201_CREATED)
async def upload_project_fact(
    project_id: str,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _load_project_for_workspace(project_id, user, db, PROJECT_PERMISSION_EDIT)
    data = await file.read()
    filename = file.filename or "upload.txt"
    try:
        content = extract_text_from_file(filename, data)
        saved = save_project_file(
            project_id,
            filename,
            data,
            file.content_type or "application/octet-stream",
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    fact = ProjectFact(
        id=str(uuid4()),
        project_id=project_id,
        created_by_user_id=user.id,
        source_kind="upload",
        source_ref={
            "filename": filename,
            "path": saved.get("path"),
            "content_type": saved.get("content_type"),
            "size": saved.get("size"),
        },
        title=(title or saved.get("name") or filename).strip(),
        content=content,
        metadata_={"upload": saved},
        memory_status="pending",
    )
    apply_fact_hash(fact)
    db.add(fact)
    await db.flush()
    fact_id = fact.id
    await _schedule_sync_after_commit(
        project_id=project_id,
        user_id=user.id,
        action="upload",
        fact_id=fact_id,
        db=db,
    )
    fact = await _load_fact(project_id, fact_id, db)
    _write_fact_workspace(project, fact)
    return _fact_response(fact)


def _workspace_context(project: TextProject) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    state = dict(project.creative_state or {})
    workspace = dict(state.get("agent_workspace") or {})
    structured_memory = workspace.get("structured_memory") if isinstance(workspace.get("structured_memory"), dict) else {}
    memory_schema = workspace.get("memory_schema") if isinstance(workspace.get("memory_schema"), dict) else {}
    fact_graph = workspace.get("fact_graph") if isinstance(workspace.get("fact_graph"), dict) else {}
    return structured_memory, memory_schema, fact_graph


@router.post("/entities/search", response_model=ProjectEntitySearchResponse)
async def search_project_entities_endpoint(
    project_id: str,
    body: ProjectEntitySearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _load_project_for_workspace(project_id, user, db, PROJECT_PERMISSION_VIEW)
    structured_memory, memory_schema, fact_graph = _workspace_context(project)
    entities = collect_project_entities(
        facts=list(project.facts or []),
        ontology=project.ontology_schema if isinstance(project.ontology_schema, dict) else None,
        structured_memory=structured_memory,
        fact_graph=fact_graph,
        memory_schema=memory_schema,
    )
    results = search_project_entities(
        entities,
        query=body.query,
        entity_type=body.entity_type,
        limit=body.limit,
    )
    return ProjectEntitySearchResponse(
        query=body.query,
        total=len(results),
        results=[
            ProjectEntitySearchResult(
                id=str(item.get("id") or ""),
                name=str(item.get("name") or ""),
                type=str(item.get("type") or "Entity"),
                summary=str(item.get("summary") or ""),
                source=str(item.get("source") or ""),
                fact_id=item.get("fact_id"),
                attributes=item.get("attributes") if isinstance(item.get("attributes"), dict) else {},
            )
            for item in results
        ],
        categories=group_entities_by_type(entities),
    )


@router.post("/batch", response_model=ProjectFactBatchUpdateResponse)
async def batch_update_project_facts(
    project_id: str,
    body: ProjectFactBatchUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _load_project_for_workspace(project_id, user, db, PROJECT_PERMISSION_EDIT)
    updated_facts: list[ProjectFact] = []
    for item in body.updates:
        fact = await _load_fact(project_id, item.fact_id, db)
        if "title" in item.model_fields_set and item.title is not None:
            fact.title = item.title.strip()
        if "content" in item.model_fields_set and item.content is not None:
            fact.content = item.content
        if "entities" in item.model_fields_set:
            fact.entities = item.entities or []
        if "relationships" in item.model_fields_set:
            fact.relationships = item.relationships or []
        if "metadata" in item.model_fields_set:
            fact.metadata_ = item.metadata
        fact.memory_status = "pending"
        fact.memory_error = None
        apply_fact_hash(fact)
        updated_facts.append(fact)

    if body.structured_memory is not None:
        state = dict(project.creative_state or {})
        workspace = dict(state.get("agent_workspace") or {})
        existing = workspace.get("structured_memory") if isinstance(workspace.get("structured_memory"), dict) else {}
        workspace["structured_memory"] = merge_structured_memory(existing, body.structured_memory)
        state["agent_workspace"] = workspace
        project.creative_state = state

    await db.flush()
    task_id: str | None = None
    if body.sync_memory:
        task_id = await _schedule_sync_after_commit(
            project_id=project_id,
            user_id=user.id,
            action="batch_update",
            fact_id=updated_facts[0].id if updated_facts else None,
            db=db,
        )
    else:
        await db.commit()

    for fact in updated_facts:
        fact = await _load_fact(project_id, fact.id, db)
        _write_fact_workspace(project, fact)

    refreshed = [
        await _load_fact(project_id, fact.id, db)
        for fact in updated_facts
    ]
    return ProjectFactBatchUpdateResponse(
        updated_count=len(refreshed),
        task_id=task_id,
        facts=[_fact_response(fact) for fact in refreshed],
    )


@router.get("/{fact_id}", response_model=ProjectFactResponse)
async def get_project_fact(
    project_id: str,
    fact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_project_for_workspace(project_id, user, db, PROJECT_PERMISSION_VIEW)
    return _fact_response(await _load_fact(project_id, fact_id, db))


@router.patch("/{fact_id}", response_model=ProjectFactResponse)
async def update_project_fact(
    project_id: str,
    fact_id: str,
    body: ProjectFactUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _load_project_for_workspace(project_id, user, db, PROJECT_PERMISSION_EDIT)
    fact = await _load_fact(project_id, fact_id, db)
    update_data = body.model_dump(exclude_unset=True)
    if "title" in update_data:
        fact.title = str(update_data["title"]).strip()
    if "content" in update_data:
        fact.content = str(update_data["content"])
    if "source_kind" in update_data:
        fact.source_kind = str(update_data["source_kind"]).strip() or "manual"
    if "source_ref" in update_data:
        fact.source_ref = update_data["source_ref"]
    if "metadata" in update_data:
        fact.metadata_ = update_data["metadata"]
    fact.memory_status = "pending"
    fact.memory_error = None
    apply_fact_hash(fact)
    await db.flush()
    await _schedule_sync_after_commit(
        project_id=project_id,
        user_id=user.id,
        action="update",
        fact_id=fact_id,
        db=db,
    )
    fact = await _load_fact(project_id, fact_id, db)
    _write_fact_workspace(project, fact)
    return _fact_response(fact)


@router.delete("/{fact_id}", response_model=ProjectFactSyncResponse)
async def delete_project_fact(
    project_id: str,
    fact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _load_project_for_workspace(project_id, user, db, PROJECT_PERMISSION_EDIT)
    fact = await _load_fact(project_id, fact_id, db)
    _delete_fact_workspace(project, fact_id)
    await db.delete(fact)
    task_id = await _schedule_sync_after_commit(
        project_id=project_id,
        user_id=user.id,
        action="delete",
        fact_id=None,
        db=db,
    )
    return ProjectFactSyncResponse(status="accepted", task_id=task_id, fact_id=fact_id)


@router.post("/{fact_id}/sync", response_model=ProjectFactSyncResponse)
async def sync_project_fact(
    project_id: str,
    fact_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _load_project_for_workspace(project_id, user, db, PROJECT_PERMISSION_RUN_AI)
    fact = await _load_fact(project_id, fact_id, db)
    fact.memory_status = "pending"
    fact.memory_error = None
    await db.flush()
    task_id = await _schedule_sync_after_commit(
        project_id=project_id,
        user_id=user.id,
        action="sync",
        fact_id=fact_id,
        db=db,
    )
    fact = await _load_fact(project_id, fact_id, db)
    _write_fact_workspace(project, fact)
    return ProjectFactSyncResponse(status="accepted", task_id=task_id, fact_id=fact_id)
