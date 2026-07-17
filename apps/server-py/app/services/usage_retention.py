"""Usage log retention policy (stored in payment_configs) and cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Usage
from app.models.config import PaymentConfig

USAGE_RETENTION_CONFIG_TYPE = "usage_retention"
USAGE_RETENTION_CONFIG_NAME = "usage_retention"


def default_usage_retention_config() -> dict[str, Any]:
    return {
        "retention_days": None,
        "max_records": None,
    }


def normalize_usage_retention_config(raw: Any) -> dict[str, Any]:
    base = default_usage_retention_config()
    if not isinstance(raw, dict):
        return base

    def _optional_positive_int(key: str) -> int | None:
        value = raw.get(key)
        if value is None or value == "":
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    base["retention_days"] = _optional_positive_int("retention_days")
    base["max_records"] = _optional_positive_int("max_records")
    return base


async def get_usage_retention_config(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        select(PaymentConfig).where(PaymentConfig.type == USAGE_RETENTION_CONFIG_TYPE)
    )
    item = result.scalar_one_or_none()
    cfg = item.config if item and isinstance(item.config, dict) else None
    return normalize_usage_retention_config(cfg)


async def upsert_usage_retention_config(db: AsyncSession, body: dict[str, Any]) -> dict[str, Any]:
    result = await db.execute(
        select(PaymentConfig).where(PaymentConfig.type == USAGE_RETENTION_CONFIG_TYPE)
    )
    item = result.scalar_one_or_none()
    current = (
        item.config
        if item and isinstance(item.config, dict)
        else default_usage_retention_config()
    )
    merged = {**current, **body}
    normalized = normalize_usage_retention_config(merged)

    if not item:
        item = PaymentConfig(
            name=USAGE_RETENTION_CONFIG_NAME,
            type=USAGE_RETENTION_CONFIG_TYPE,
            is_active=True,
        )
        db.add(item)

    item.is_active = True
    item.config = normalized
    await db.flush()
    return normalized


async def enforce_usage_retention(db: AsyncSession) -> dict[str, int]:
    """Delete oldest usage rows when retention_days or max_records limits are exceeded."""
    cfg = await get_usage_retention_config(db)
    retention_days = cfg.get("retention_days")
    max_records = cfg.get("max_records")

    deleted_by_age = 0
    deleted_by_count = 0

    if retention_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(retention_days))
        result = await db.execute(delete(Usage).where(Usage.created_at < cutoff))
        deleted_by_age = int(result.rowcount or 0)

    if max_records is not None:
        total = (await db.execute(select(func.count(Usage.id)))).scalar() or 0
        overflow = int(total) - int(max_records)
        if overflow > 0:
            ids_result = await db.execute(
                select(Usage.id)
                .order_by(Usage.created_at.asc())
                .limit(overflow)
            )
            ids = [row[0] for row in ids_result.all()]
            if ids:
                result = await db.execute(delete(Usage).where(Usage.id.in_(ids)))
                deleted_by_count = int(result.rowcount or 0)

    if deleted_by_age or deleted_by_count:
        await db.flush()

    return {
        "deleted_by_age": deleted_by_age,
        "deleted_by_count": deleted_by_count,
    }