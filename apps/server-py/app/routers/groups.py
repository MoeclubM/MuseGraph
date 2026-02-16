from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserGroup

router = APIRouter()


@router.get("")
async def list_groups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserGroup).where(UserGroup.is_active == True).order_by(UserGroup.sort_order)
    )
    groups = result.scalars().all()
    return [
        {
            "id": g.id,
            "name": g.name,
            "display_name": g.display_name,
            "description": g.description,
            "color": g.color,
            "icon": g.icon,
            "price": float(g.price) if g.price else None,
            "features": g.features,
        }
        for g in groups
    ]


@router.get("/me")
async def get_my_group(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.group_id:
        return {"group": None}
    result = await db.execute(
        select(UserGroup).where(UserGroup.id == user.group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        return {"group": None}
    return {
        "group": {
            "id": group.id,
            "name": group.name,
            "display_name": group.display_name,
            "description": group.description,
            "color": group.color,
            "icon": group.icon,
            "features": group.features,
            "quotas": group.quotas,
            "allowed_models": group.allowed_models,
        }
    }
