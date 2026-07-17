from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import TextProject
from app.models.user import User
from app.services.project_access import PROJECT_PERMISSION_EDIT, PROJECT_PERMISSION_VIEW, require_project_permission
from app.services.project_git import create_project_record_point, list_project_record_points
from app.services.project_versions import restore_project_record_point
from app.services.project_workspace import write_project_workspace_snapshot

router = APIRouter()


class ProjectRecordPoint(BaseModel):
    id: str
    label: str
    created_at: str


class ProjectVersionHistoryResponse(BaseModel):
    current_record_point: str | None = None
    record_points: list[ProjectRecordPoint]
    pending_changes_count: int = 0


class ProjectRecordPointRequest(BaseModel):
    message: str


class ProjectRestoreRequest(BaseModel):
    record_point_id: str


def _loaded_items(project: TextProject, attr: str) -> list[Any]:
    return list(project.__dict__.get(attr) or [])


def _write_loaded_project_snapshot(project: TextProject) -> None:
    write_project_workspace_snapshot(
        project,
        _loaded_items(project, "chapters"),
        _loaded_items(project, "facts"),
    )


def _load_options() -> tuple[Any, ...]:
    return (
        selectinload(TextProject.chapters),
        selectinload(TextProject.facts),
    )


@router.get("", response_model=ProjectVersionHistoryResponse)
async def read_project_version_history(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    try:
        return list_project_record_points(project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/record-points", response_model=ProjectVersionHistoryResponse)
async def create_project_version_record_point(
    project_id: str,
    body: ProjectRecordPointRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(
        project_id,
        user,
        db,
        PROJECT_PERMISSION_EDIT,
        load_options=_load_options(),
    )
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Record point message is required")
    try:
        _write_loaded_project_snapshot(project)
        return create_project_record_point(project_id, message)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/restore", response_model=ProjectVersionHistoryResponse)
async def restore_project_version_record_point(
    project_id: str,
    body: ProjectRestoreRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(
        project_id,
        user,
        db,
        PROJECT_PERMISSION_EDIT,
        load_options=_load_options(),
    )
    record_point_id = body.record_point_id.strip()
    if not record_point_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Record point id is required")
    try:
        return await restore_project_record_point(project, db, record_point_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
