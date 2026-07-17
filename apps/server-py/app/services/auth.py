import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import Session, User
from app.redis import redis_client

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)


def hash_session_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def create_session(user_id: str, db: AsyncSession) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_EXPIRES_HOURS)
    session = Session(
        user_id=user_id,
        token_hash=hash_session_secret(token),
        csrf_token_hash=hash_session_secret(csrf_token),
        expires_at=expires_at,
    )
    db.add(session)
    await db.flush()
    await redis_client.set(
        f"session:{session.token_hash}",
        session.id,
        ex=settings.SESSION_EXPIRES_HOURS * 3600,
    )
    return token, csrf_token


async def delete_session(token: str, db: AsyncSession) -> None:
    token_hash = hash_session_secret(token)
    await redis_client.delete(f"session:{token_hash}")
    result = await db.execute(select(Session).where(Session.token_hash == token_hash))
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)


async def revoke_user_sessions(user_id: str, db: AsyncSession) -> None:
    result = await db.execute(select(Session.token_hash).where(Session.user_id == user_id))
    token_hashes = list(result.scalars())
    if token_hashes:
        await redis_client.delete(*(f"session:{token_hash}" for token_hash in token_hashes))
    await db.execute(delete(Session).where(Session.user_id == user_id))


async def register_user(
    email: str,
    password: str,
    nickname: str,
    db: AsyncSession,
) -> User:
    if settings.REGISTRATION_MODE != "open":
        raise PermissionError("Registration is not open")
    return await create_user(email, password, nickname, db)


async def create_user(
    email: str,
    password: str,
    nickname: str,
    db: AsyncSession,
) -> User:
    normalized_email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == normalized_email))
    if result.scalar_one_or_none():
        raise ValueError("email already exists")
    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        nickname=nickname.strip(),
    )
    db.add(user)
    await db.flush()
    return user
