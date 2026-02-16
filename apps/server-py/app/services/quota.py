from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import ModelPermission
from app.models.user import User, UserQuota


async def check_quota(user: User, model: str, db: AsyncSession) -> bool:
    """Check if user has remaining quota for the given model."""
    result = await db.execute(
        select(UserQuota).where(UserQuota.user_id == user.id, UserQuota.model == model)
    )
    quota = result.scalar_one_or_none()

    if not quota:
        # Check group-level permissions
        if user.group_id:
            result = await db.execute(
                select(ModelPermission).where(
                    ModelPermission.group_id == user.group_id,
                    ModelPermission.model == model,
                    ModelPermission.is_active == True,
                )
            )
            perm = result.scalar_one_or_none()
            if not perm:
                return True  # No restriction = allowed
            # Create user quota from group permission
            now = datetime.now(timezone.utc)
            quota = UserQuota(
                user_id=user.id,
                model=model,
                daily_limit=perm.daily_limit,
                monthly_limit=perm.monthly_limit,
                daily_used=0,
                monthly_used=0,
                last_daily_reset=now,
                last_monthly_reset=now,
            )
            db.add(quota)
            await db.flush()
        else:
            return True  # No group = no restriction

    # Reset counters if needed
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if quota.last_daily_reset and quota.last_daily_reset < today_start:
        quota.daily_used = 0
        quota.last_daily_reset = now

    if quota.last_monthly_reset and quota.last_monthly_reset < month_start:
        quota.monthly_used = 0
        quota.last_monthly_reset = now

    if quota.daily_limit > 0 and quota.daily_used >= quota.daily_limit:
        return False
    if quota.monthly_limit > 0 and quota.monthly_used >= quota.monthly_limit:
        return False

    return True


async def increment_quota(user_id: str, model: str, db: AsyncSession) -> None:
    result = await db.execute(
        select(UserQuota).where(UserQuota.user_id == user_id, UserQuota.model == model)
    )
    quota = result.scalar_one_or_none()
    if quota:
        quota.daily_used += 1
        quota.monthly_used += 1
        await db.flush()
