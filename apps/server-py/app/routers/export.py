from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
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
    )
    content, filename = await export_project_bundle(project)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
