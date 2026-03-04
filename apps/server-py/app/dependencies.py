from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.redis import get_redis


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = (
        request.cookies.get("session_token")
        or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    r = await get_redis()
    user_id = await r.get(f"session:{token}")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin required"
        )
    return user
