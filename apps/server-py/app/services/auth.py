import uuid
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import Session, User, UserGroup
from app.redis import redis_client

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


async def create_session(user_id: str, db: AsyncSession) -> str:
    token = uuid.uuid4().hex + uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRES_HOURS)
    session = Session(user_id=user_id, token=token, expires_at=expires_at)
    db.add(session)
    await db.flush()
    # Store in Redis for fast lookup
    await redis_client.set(
        f"session:{token}",
        user_id,
        ex=settings.JWT_EXPIRES_HOURS * 3600,
    )
    return token


async def delete_session(token: str, db: AsyncSession) -> None:
    await redis_client.delete(f"session:{token}")
    result = await db.execute(select(Session).where(Session.token == token))
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)


async def register_user(
    email: str, username: str, password: str, nickname: str | None, db: AsyncSession
) -> User:
    # Check existing
    result = await db.execute(select(User).where((User.email == email) | (User.username == username)))
    existing = result.scalar_one_or_none()
    if existing:
        field = "email" if existing.email == email else "username"
        raise ValueError(f"{field} already exists")

    # Get default group (use first() in case multiple are marked default)
    result = await db.execute(
        select(UserGroup).where(UserGroup.is_default == True).order_by(UserGroup.created_at)
    )
    default_group = result.scalars().first()

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        nickname=nickname or username,
        group_id=default_group.id if default_group else None,
    )
    db.add(user)
    await db.flush()
    return user
