"""Explicit development bootstrap. Run after ``alembic upgrade head``."""
import asyncio
import uuid
from decimal import Decimal

from app.config import settings
from app.database import async_session
from app.models.user import User
from app.services.auth import hash_password


async def seed():
    async with async_session() as db:
        from sqlalchemy import select

        print("Seeding database...")
        if not settings.SEED_ADMIN_EMAIL or not settings.SEED_ADMIN_PASSWORD:
            raise RuntimeError(
                "SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD are required for explicit admin bootstrap"
            )
        existing_admin = (
            await db.execute(select(User).where(User.email == settings.SEED_ADMIN_EMAIL))
        ).scalar_one_or_none()
        if existing_admin is None:
            db.add(
                User(
                    id=str(uuid.uuid4()),
                    email=settings.SEED_ADMIN_EMAIL,
                    password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
                    nickname=settings.SEED_ADMIN_NICKNAME,
                    is_admin=True,
                    balance=Decimal("9999"),
                    status="ACTIVE",
                )
            )
            print(f"  Created admin user ({settings.SEED_ADMIN_EMAIL})")
        else:
            existing_admin.password_hash = hash_password(settings.SEED_ADMIN_PASSWORD)
            existing_admin.nickname = settings.SEED_ADMIN_NICKNAME
            existing_admin.is_admin = True
            existing_admin.status = "ACTIVE"
            print(f"  Updated admin user ({settings.SEED_ADMIN_EMAIL})")

        await db.commit()
        print("\nSeeding complete!")


if __name__ == "__main__":
    asyncio.run(seed())
