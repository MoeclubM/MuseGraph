"""Create and query usage (billing) detail records."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Usage
from app.models.config import PricingRule
from app.models.project import TextProject
from app.models.user import User
from app.services.ai import _money, calculate_cost
from app.services.usage_retention import enforce_usage_retention


async def resolve_billing_mode(model: str, db: AsyncSession) -> str:
    result = await db.execute(
        select(PricingRule).where(PricingRule.model == model, PricingRule.is_active == True)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        return "TOKEN"
    return str(getattr(rule, "billing_mode", "TOKEN") or "TOKEN").upper()


async def create_usage_record(
    *,
    db: AsyncSession,
    user_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: Decimal | float | None = None,
    project_id: str | None = None,
    operation_id: str | None = None,
    provider: str | None = None,
    billing_mode: str | None = None,
    request_id: str | None = None,
    status: str = "SUCCESS",
    source: str = "llm",
    metadata: dict[str, Any] | None = None,
    deduct_balance: bool = True,
    user_balance_holder: Any | None = None,
) -> tuple[Usage, Decimal]:
    """Persist one usage row and optionally deduct user balance."""
    from app.models.user import User

    safe_input = max(0, int(input_tokens or 0))
    safe_output = max(0, int(output_tokens or 0))
    if cost is None:
        cost_dec = await calculate_cost(model, safe_input, safe_output, db)
    else:
        cost_dec = _money(cost)

    mode = (billing_mode or await resolve_billing_mode(model, db)).upper()

    if deduct_balance:
        if user_balance_holder is not None:
            user = user_balance_holder
        else:
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
        if user is None:
            raise ValueError("Billing user not found")
        current_balance = _money(user.balance)
        next_balance = _money(current_balance - cost_dec)
        if next_balance < Decimal("0"):
            raise ValueError("Insufficient balance")
        user.balance = next_balance

    usage = Usage(
        user_id=user_id,
        project_id=project_id,
        operation_id=operation_id,
        model=model,
        input_tokens=safe_input,
        output_tokens=safe_output,
        cost=cost_dec,
        provider=(str(provider).strip() or None) if provider else None,
        billing_mode=mode,
        request_id=(str(request_id).strip() or None) if request_id else None,
        status=str(status or "SUCCESS").upper(),
        source=str(source or "llm"),
        metadata_json=metadata if isinstance(metadata, dict) else None,
    )
    db.add(usage)
    await db.flush()
    await enforce_usage_retention(db)
    return usage, cost_dec


def serialize_usage_row(
    usage: Usage,
    *,
    user_email: str | None = None,
    user_nickname: str | None = None,
    project_title: str | None = None,
) -> dict[str, Any]:
    meta = usage.metadata_json if isinstance(usage.metadata_json, dict) else None
    return {
        "id": usage.id,
        "user_id": usage.user_id,
        "user_email": user_email,
        "user_nickname": user_nickname,
        "project_id": usage.project_id,
        "project_title": project_title,
        "operation_id": usage.operation_id,
        "model": usage.model,
        "provider": usage.provider,
        "input_tokens": int(usage.input_tokens or 0),
        "output_tokens": int(usage.output_tokens or 0),
        "cost": float(usage.cost or 0),
        "billing_mode": usage.billing_mode,
        "request_id": usage.request_id,
        "status": usage.status,
        "source": usage.source,
        "metadata": meta,
        "created_at": usage.created_at.isoformat() if usage.created_at else None,
    }


async def list_usage_records(
    db: AsyncSession,
    *,
    user_id: str | None = None,
    model: str | None = None,
    project_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
    include_user: bool = False,
    include_project: bool = False,
) -> dict[str, Any]:
    query = select(Usage, User.email, User.nickname, TextProject.title).select_from(Usage)
    if include_user or search:
        query = query.join(User, User.id == Usage.user_id)
    else:
        query = query.outerjoin(User, User.id == Usage.user_id)
    query = query.outerjoin(TextProject, TextProject.id == Usage.project_id)

    if user_id:
        query = query.where(Usage.user_id == user_id)
    if model:
        query = query.where(Usage.model == model.strip())
    if project_id:
        query = query.where(Usage.project_id == project_id)
    if date_from:
        query = query.where(Usage.created_at >= date_from)
    if date_to:
        query = query.where(Usage.created_at <= date_to)
    if search:
        term = f"%{str(search).strip()}%"
        query = query.where(
            or_(
                Usage.model.ilike(term),
                Usage.request_id.ilike(term),
                User.email.ilike(term),
                User.nickname.ilike(term),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(
        query.order_by(Usage.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = result.all()
    records = [
        serialize_usage_row(
            u,
            user_email=email if include_user or search else None,
            user_nickname=nick if include_user or search else None,
            project_title=title if include_project else None,
        )
        for u, email, nick, title in rows
    ]
    return {
        "records": records,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }