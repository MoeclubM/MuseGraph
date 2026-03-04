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
        # Check if already seeded
        from sqlalchemy import select, func
        count = (await db.execute(select(func.count(User.id)))).scalar()
        if count and count > 0:
            print("Database already seeded. Skipping.")
            return

        print("Seeding database...")

        # 1. Optional admin user (requires explicit email/password env vars)
        if (
            settings.SEED_ADMIN_EMAIL
            and settings.SEED_ADMIN_PASSWORD
        ):
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
            print("  Skipped admin user creation (set SEED_ADMIN_EMAIL + SEED_ADMIN_PASSWORD to enable)")

        # 2. Pricing Rules
        pricing_rules = [
            PricingRule(
                model="gpt-4o-mini",
                billing_mode="TOKEN",
                input_price=0.15,
                output_price=0.6,
                token_unit=1_000_000,
                request_price=0,
                is_active=True,
            ),
            PricingRule(
                model="gpt-4o",
                billing_mode="TOKEN",
                input_price=2.5,
                output_price=10,
                token_unit=1_000_000,
                request_price=0,
                is_active=True,
            ),
            PricingRule(
                model="claude-3-5-sonnet-20241022",
                billing_mode="TOKEN",
                input_price=3,
                output_price=15,
                token_unit=1_000_000,
                request_price=0,
                is_active=True,
            ),
        ]
        db.add_all(pricing_rules)
        await db.flush()
        print("  Created pricing rules")

        # 3. Prompt Templates
        templates = [
            PromptTemplate(
                name="create_default", type="CREATE",
                template="You are a creative writing assistant. Based on the following prompt, create original content in the same language as the input:\n\n{input}",
                variables={"input": "User's creative prompt"},
                is_active=True,
            ),
            PromptTemplate(
                name="continue_default", type="CONTINUE",
                template="You are a creative writing assistant. Continue the following text naturally, maintaining the same style, tone, and narrative logic. Ensure character consistency and plot coherence. Write in the same language as the input:\n\n{input}",
                variables={"input": "Existing text to continue"},
                is_active=True,
            ),
            PromptTemplate(
                name="analyze_default", type="ANALYZE",
                template="You are a text analysis expert. Provide a detailed analysis of the following text, including themes, style, structure, and key insights. Respond in the same language as the input:\n\n{input}",
                variables={"input": "Text to analyze"},
                is_active=True,
            ),
            PromptTemplate(
                name="rewrite_default", type="REWRITE",
                template="You are a professional editor. Rewrite the following text to improve clarity, style, and readability while preserving the original meaning. Write in the same language as the input:\n\n{input}",
                variables={"input": "Text to rewrite"},
                is_active=True,
            ),
            PromptTemplate(
                name="summarize_default", type="SUMMARIZE",
                template="You are a summarization expert. Provide a concise but comprehensive summary of the following text. Respond in the same language as the input:\n\n{input}",
                variables={"input": "Text to summarize"},
                is_active=True,
            ),
        ]
        db.add_all(templates)
        await db.flush()
        print("  Created prompt templates")

        await db.commit()
        print("\nSeeding complete!")


if __name__ == "__main__":
    asyncio.run(seed())
