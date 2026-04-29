"""Database seed script. Run with: python seed.py"""
import asyncio
import uuid
from decimal import Decimal

from app.config import settings
from app.database import Base, engine, async_session
from app.models import *  # noqa: F403 - import all models to register them
from app.services.auth import hash_password


async def seed():
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        from sqlalchemy import select

        print("Seeding database...")

        # 1. Ensure admin user when explicit bootstrap credentials are present
        if (
            settings.SEED_ADMIN_EMAIL
            and settings.SEED_ADMIN_PASSWORD
        ):
            existing_admin = (
                await db.execute(select(User).where(User.email == settings.SEED_ADMIN_EMAIL))
            ).scalar_one_or_none()
            if existing_admin is None:
                admin_user = User(
                    id=str(uuid.uuid4()),
                    email=settings.SEED_ADMIN_EMAIL,
                    password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
                    nickname=settings.SEED_ADMIN_NICKNAME or "Administrator",
                    is_admin=True,
                    balance=Decimal("9999"),
                    status="ACTIVE",
                )
                db.add(admin_user)
                await db.flush()
                print(f"  Created admin user ({settings.SEED_ADMIN_EMAIL})")
            else:
                existing_admin.password_hash = hash_password(settings.SEED_ADMIN_PASSWORD)
                existing_admin.nickname = settings.SEED_ADMIN_NICKNAME or existing_admin.nickname or "Administrator"
                existing_admin.is_admin = True
                if existing_admin.balance is None:
                    existing_admin.balance = Decimal("9999")
                if not existing_admin.status:
                    existing_admin.status = "ACTIVE"
                await db.flush()
                print(f"  Updated admin user ({settings.SEED_ADMIN_EMAIL})")
        else:
            print("  Skipped admin user creation (set SEED_ADMIN_EMAIL + SEED_ADMIN_PASSWORD to enable)")

        # 2. Ensure prompt templates exist
        existing_templates = {
            template.name: template
            for template in (
                await db.execute(select(PromptTemplate))
            ).scalars()
        }
        templates = [
            PromptTemplate(
                name="create_default", type="CREATE",
                template="{input}",
                variables={"input": "User's creative prompt"},
                is_active=True,
            ),
            PromptTemplate(
                name="continue_default", type="CONTINUE",
                template="{input}",
                variables={"input": "Existing text to continue"},
                is_active=True,
            ),
            PromptTemplate(
                name="analyze_default", type="ANALYZE",
                template="Analyze the text below.\n\n{input}",
                variables={"input": "Text to analyze"},
                is_active=True,
            ),
            PromptTemplate(
                name="rewrite_default", type="REWRITE",
                template="Rewrite the text below.\n\n{input}",
                variables={"input": "Text to rewrite"},
                is_active=True,
            ),
            PromptTemplate(
                name="summarize_default", type="SUMMARIZE",
                template="Summarize the text below.\n\n{input}",
                variables={"input": "Text to summarize"},
                is_active=True,
            ),
        ]
        created_templates = 0
        updated_templates = 0
        for template in templates:
            existing = existing_templates.get(template.name)
            if existing is None:
                db.add(template)
                created_templates += 1
                continue
            changed = False
            for key in ("type", "template", "variables", "is_active"):
                next_value = getattr(template, key)
                if getattr(existing, key) != next_value:
                    setattr(existing, key, next_value)
                    changed = True
            if changed:
                updated_templates += 1
        await db.flush()
        if created_templates or updated_templates:
            print(f"  Prompt templates synced (created {created_templates}, updated {updated_templates})")
        else:
            print("  Prompt templates already present")

        await db.commit()
        print("\nSeeding complete!")


if __name__ == "__main__":
    asyncio.run(seed())
