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
        count = (await db.execute(select(func.count(UserGroup.id)))).scalar()
        if count and count > 0:
            print("Database already seeded. Skipping.")
            return

        print("Seeding database...")

        # 1. User Groups
        free_group = UserGroup(
            id=str(uuid.uuid4()),
            name="free",
            display_name="Free",
            description="Free tier with basic features",
            color="#6B7280",
            icon="user",
            allowed_models=["gpt-4o-mini"],
            quotas={"daily_requests": 20, "monthly_requests": 200},
            features={"max_projects": 5, "export": False, "graph": False},
            price=Decimal("0"),
            sort_order=0,
            is_active=True,
            is_default=True,
        )
        basic_group = UserGroup(
            id=str(uuid.uuid4()),
            name="basic",
            display_name="Basic",
            description="Basic plan with more features",
            color="#3B82F6",
            icon="star",
            allowed_models=["gpt-4o-mini", "gpt-4o"],
            quotas={"daily_requests": 100, "monthly_requests": 2000},
            features={"max_projects": 20, "export": True, "graph": True},
            price=Decimal("9.99"),
            sort_order=1,
            is_active=True,
            is_default=False,
        )
        pro_group = UserGroup(
            id=str(uuid.uuid4()),
            name="pro",
            display_name="Pro",
            description="Professional plan with all features",
            color="#8B5CF6",
            icon="crown",
            allowed_models=["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet-20241022"],
            quotas={"daily_requests": 500, "monthly_requests": 10000},
            features={"max_projects": -1, "export": True, "graph": True},
            price=Decimal("29.99"),
            sort_order=2,
            is_active=True,
            is_default=False,
        )
        enterprise_group = UserGroup(
            id=str(uuid.uuid4()),
            name="enterprise",
            display_name="Enterprise",
            description="Enterprise plan with unlimited access",
            color="#F59E0B",
            icon="building",
            allowed_models=["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
            quotas={"daily_requests": -1, "monthly_requests": -1},
            features={"max_projects": -1, "export": True, "graph": True, "priority_support": True},
            price=Decimal("99.99"),
            sort_order=3,
            is_active=True,
            is_default=False,
        )
        db.add_all([free_group, basic_group, pro_group, enterprise_group])
        await db.flush()
        print("  Created user groups")

        # 2. Optional admin user (requires explicit env vars)
        if (
            settings.SEED_ADMIN_EMAIL
            and settings.SEED_ADMIN_USERNAME
            and settings.SEED_ADMIN_PASSWORD
        ):
            admin_user = User(
                id=str(uuid.uuid4()),
                email=settings.SEED_ADMIN_EMAIL,
                username=settings.SEED_ADMIN_USERNAME,
                password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
                nickname=settings.SEED_ADMIN_NICKNAME or "Administrator",
                role="ADMIN",
                group_id=enterprise_group.id,
                balance=Decimal("9999"),
                status="ACTIVE",
            )
            db.add(admin_user)
            await db.flush()
            print(f"  Created admin user ({settings.SEED_ADMIN_EMAIL})")
        else:
            print("  Skipped admin user creation (set SEED_ADMIN_* env vars to enable)")

        # 3. Plans
        plans = [
            Plan(
                name="basic_monthly", display_name="Basic Monthly",
                description="Basic plan billed monthly",
                target_group_id=basic_group.id,
                price=Decimal("9.99"), original_price=Decimal("14.99"),
                duration=30, is_active=True, sort_order=0,
                features={"max_projects": 20, "export": True, "graph": True},
                quotas={"daily_requests": 100, "monthly_requests": 2000},
                allowed_models=["gpt-4o-mini", "gpt-4o"],
            ),
            Plan(
                name="pro_monthly", display_name="Pro Monthly",
                description="Pro plan billed monthly",
                target_group_id=pro_group.id,
                price=Decimal("29.99"), original_price=Decimal("39.99"),
                duration=30, is_active=True, sort_order=1,
                features={"max_projects": -1, "export": True, "graph": True},
                quotas={"daily_requests": 500, "monthly_requests": 10000},
                allowed_models=["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet-20241022"],
            ),
            Plan(
                name="enterprise_monthly", display_name="Enterprise Monthly",
                description="Enterprise plan billed monthly",
                target_group_id=enterprise_group.id,
                price=Decimal("99.99"),
                duration=30, is_active=True, sort_order=2,
                features={"max_projects": -1, "export": True, "graph": True, "priority_support": True},
                quotas={"daily_requests": -1, "monthly_requests": -1},
                allowed_models=["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
            ),
        ]
        db.add_all(plans)
        await db.flush()
        print("  Created plans")

        # 4. Pricing Rules
        pricing_rules = [
            PricingRule(model="gpt-4o-mini", input_price=0.00015, output_price=0.0006, is_active=True),
            PricingRule(model="gpt-4o", input_price=0.0025, output_price=0.01, is_active=True),
            PricingRule(model="claude-3-5-sonnet-20241022", input_price=0.003, output_price=0.015, is_active=True),
            PricingRule(model="claude-3-opus-20240229", input_price=0.015, output_price=0.075, is_active=True),
        ]
        db.add_all(pricing_rules)
        await db.flush()
        print("  Created pricing rules")

        # 5. Prompt Templates
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
