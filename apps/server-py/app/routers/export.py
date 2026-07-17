from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import (
    ProjectChapter,
    ProjectFact,
    TextProject,
)
from app.models.user import User
from app.services.export import export_project_bundle
from app.services.project_access import PROJECT_PERMISSION_VIEW, require_project_permission

router = APIRouter()


@router.post("/bundle")
async def export_bundle(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(
        project_id,
        user,
        db,
        PROJECT_PERMISSION_VIEW,
        load_options=(
            selectinload(TextProject.chapters),
            selectinload(TextProject.facts),
        ),
    )

    try:
        content_bytes, content_type, filename = await export_project_bundle(
            project,
            list(project.chapters),
            list(project.facts),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return Response(
        content=content_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
