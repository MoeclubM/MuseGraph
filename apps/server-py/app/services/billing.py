from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Deposit, Usage


async def get_daily_usage(user_id: str, db: AsyncSession) -> Decimal:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(Usage.cost), 0)).where(
            Usage.user_id == user_id, Usage.created_at >= today_start
        )
    )
    return Decimal(str(result.scalar()))


async def get_monthly_usage(user_id: str, db: AsyncSession) -> Decimal:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.coalesce(func.sum(Usage.cost), 0)).where(
            Usage.user_id == user_id, Usage.created_at >= month_start
        )
    )
    return Decimal(str(result.scalar()))


async def create_deposit(user_id: str, amount: float, payment_method: str | None, db: AsyncSession) -> Deposit:
    deposit = Deposit(
        user_id=user_id,
        amount=Decimal(str(amount)),
        payment_method=payment_method,
        status="PENDING",
    )
    db.add(deposit)
    await db.flush()
    return deposit
