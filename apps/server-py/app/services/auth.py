import uuid
from datetime import datetime, timedelta, timezone

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import Session, User
from app.redis import redis_client

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)


async def create_session(user_id: str, db: AsyncSession) -> str:
    token = uuid.uuid4().hex + uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_EXPIRES_HOURS)
    session = Session(user_id=user_id, token=token, expires_at=expires_at)
    db.add(session)
    await db.flush()
    # Store in Redis for fast lookup
    await redis_client.set(
        f"session:{token}",
        user_id,
        ex=settings.SESSION_EXPIRES_HOURS * 3600,
    )
    return token


async def delete_session(token: str, db: AsyncSession) -> None:
    await redis_client.delete(f"session:{token}")
    result = await db.execute(select(Session).where(Session.token == token))
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)


async def register_user(
    email: str, password: str, nickname: str, db: AsyncSession
) -> User:
    normalized_email = email.strip().lower()

    # Check existing email
    result = await db.execute(select(User).where(User.email == normalized_email))
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError("email already exists")

    display_nickname = nickname.strip()

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        nickname=display_nickname,
    )
    db.add(user)
    await db.flush()
    return user
