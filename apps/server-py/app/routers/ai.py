from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.ai import get_available_embedding_models, get_available_models

router = APIRouter()


@router.get("/models")
async def list_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    models = await get_available_models(db)
    return {"models": models}


@router.get("/embedding-models")
async def list_embedding_models(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    models = await get_available_embedding_models(db)
    return {"models": models}
