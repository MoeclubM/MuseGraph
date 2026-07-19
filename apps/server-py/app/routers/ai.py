from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.project_access import require_project_permission
from app.services.ai import (
    get_available_embedding_models,
    get_available_models,
    get_available_reranker_models,
)

router = APIRouter()


@router.get("/models")
async def list_models(
    project_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owner_user_id = (
        (await require_project_permission(project_id, user, db)).user_id
        if project_id
        else user.id
    )
    models = await get_available_models(db, owner_user_id)
    return {"models": models}


@router.get("/embedding-models")
async def list_embedding_models(
    project_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owner_user_id = (
        (await require_project_permission(project_id, user, db)).user_id
        if project_id
        else user.id
    )
    models = await get_available_embedding_models(db, owner_user_id)
    return {"models": models}


@router.get("/reranker-models")
async def list_reranker_models(
    project_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owner_user_id = (
        (await require_project_permission(project_id, user, db)).user_id
        if project_id
        else user.id
    )
    models = await get_available_reranker_models(db, owner_user_id)
    return {"models": models}
