from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
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
    save_project_file,
)

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


class ProjectFileCreateRequest(BaseModel):
    path: str
    content: str = ""


class ProjectFileRenameRequest(BaseModel):
    path: str
    new_path: str


class ProjectFileDeleteResponse(BaseModel):
    ok: bool
    path: str


@router.get("", response_model=ProjectFileListResponse)
async def list_files(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    return list_project_files(project_id)


@router.post("", response_model=ProjectFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file_for_agent(
    project_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    data = await file.read()
    try:
        return save_project_file(
            project_id,
            file.filename or "upload.txt",
            data,
            file.content_type or "application/octet-stream",
        )
    except ValueError as exc:
        allowed = ", ".join(sorted(ALLOWED_PROJECT_FILE_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{exc}. Allowed: {allowed}",
        ) from exc


@router.post("/manual", response_model=ProjectFileResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_file(
    project_id: str,
    body: ProjectFileCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    try:
        return create_project_file(project_id, body.path, body.content)
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        allowed = ", ".join(sorted(ALLOWED_PROJECT_FILE_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{exc}. Allowed: {allowed}",
        ) from exc


@router.patch("/rename", response_model=ProjectFileResponse)
async def rename_manual_file(
    project_id: str,
    body: ProjectFileRenameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    try:
        return rename_project_file(project_id, body.path, body.new_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        allowed = ", ".join(sorted(ALLOWED_PROJECT_FILE_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{exc}. Allowed: {allowed}",
        ) from exc


@router.delete("", response_model=ProjectFileDeleteResponse)
async def delete_manual_file(
    project_id: str,
    path: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    try:
        delete_project_file(project_id, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ProjectFileDeleteResponse(ok=True, path=path)


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
