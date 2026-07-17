from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import TextProject
from app.models.runtime import AgentRun, ProjectRevision
from app.models.user import User
from app.services.agent_workspace import current_project_commit
from app.services.project_access import (
    PROJECT_PERMISSION_EDIT,
    PROJECT_PERMISSION_VIEW,
    require_project_permission,
)
from app.services.project_files import (
    ALLOWED_PROJECT_FILE_EXTENSIONS,
    create_project_file,
    delete_project_file,
    list_project_files,
    read_project_file,
    rename_project_file,
    save_project_file_from_path,
    update_project_file,
)
from app.services.rate_limit import enforce_rate_limit

router = APIRouter()


class ProjectFileResponse(BaseModel):
    path: str
    name: str
    size: int
    content_type: str
    modified_at: str
    text_extractable: bool


class ProjectFileListResponse(BaseModel):
    files: list[ProjectFileResponse]


class ProjectFileContentResponse(ProjectFileResponse):
    content: str


class ProjectFileWriteRequest(BaseModel):
    path: str
    content: str = ""


class ProjectFileRenameRequest(BaseModel):
    path: str
    new_path: str


async def _record_revision(
    project: TextProject,
    user: User,
    db: AsyncSession,
    message: str,
) -> None:
    current = (
        await db.execute(
            select(ProjectRevision)
            .where(ProjectRevision.id == project.active_revision_id)
            .with_for_update()
        )
    ).scalar_one()
    current.status = "superseded"
    revision = ProjectRevision(
        project_id=project.id,
        parent_revision_id=current.id,
        git_commit=current_project_commit(project.id),
        knowledge_dataset=current.knowledge_dataset,
        status="active",
        message=message,
    )
    db.add(revision)
    await db.flush()
    project.active_revision_id = revision.id


async def _lock_project_for_write(
    project_id: str,
    db: AsyncSession,
) -> TextProject:
    project = (
        await db.execute(
            select(TextProject).where(TextProject.id == project_id).with_for_update()
        )
    ).scalar_one()
    accepting_run = (
        await db.execute(
            select(AgentRun.id).where(
                AgentRun.project_id == project_id,
                AgentRun.status == "accepting",
            )
        )
    ).scalar_one_or_none()
    if accepting_run:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project revision is being published by Agent run {accepting_run}",
        )
    return project


@router.get("", response_model=ProjectFileListResponse)
async def list_files(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    return list_project_files(project_id)


@router.post("", response_model=ProjectFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    project_id: str,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    project = await _lock_project_for_write(project_id, db)
    await enforce_rate_limit(
        f"upload:{user.id}:{project_id}",
        settings.UPLOAD_RATE_LIMIT_PER_MINUTE,
    )
    temporary_path: Path | None = None
    size = 0
    try:
        with tempfile.NamedTemporaryFile(delete=False) as temporary:
            temporary_path = Path(temporary.name)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Upload exceeds 50 MiB",
                    )
                temporary.write(chunk)
        item = save_project_file_from_path(
            project_id,
            file.filename or "upload.txt",
            temporary_path,
            file.content_type,
        )
        await _record_revision(project, user, db, f"Upload {item['path']}")
        return item
    except ValueError as exc:
        allowed = ", ".join(sorted(ALLOWED_PROJECT_FILE_EXTENSIONS))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{exc}. Allowed: {allowed}") from exc
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


@router.post("/manual", response_model=ProjectFileResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_file(
    project_id: str,
    body: ProjectFileWriteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    project = await _lock_project_for_write(project_id, db)
    try:
        item = create_project_file(project_id, body.path, body.content)
        await _record_revision(project, user, db, f"Create {item['path']}")
        return item
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/content", response_model=ProjectFileResponse)
async def update_file_content(
    project_id: str,
    body: ProjectFileWriteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    project = await _lock_project_for_write(project_id, db)
    try:
        item = update_project_file(project_id, body.path, body.content)
        await _record_revision(project, user, db, f"Update {item['path']}")
        return item
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/rename", response_model=ProjectFileResponse)
async def rename_file(
    project_id: str,
    body: ProjectFileRenameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    project = await _lock_project_for_write(project_id, db)
    try:
        item = rename_project_file(project_id, body.path, body.new_path)
        await _record_revision(project, user, db, f"Rename {body.path} to {item['path']}")
        return item
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("")
async def delete_file(
    project_id: str,
    path: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    project = await _lock_project_for_write(project_id, db)
    try:
        delete_project_file(project_id, path)
        await _record_revision(project, user, db, f"Delete {path}")
        return {"ok": True, "path": path}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/content", response_model=ProjectFileContentResponse)
async def read_file_content(
    project_id: str,
    path: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    try:
        return read_project_file(project_id, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
