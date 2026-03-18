from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import require_admin
from app.models.billing import Order, Usage
from app.models.config import AIProviderConfig, PaymentConfig, PricingRule
from app.models.project import TextOperation, TextProject
from app.models.user import User
from app.schemas.admin import StatsResponse, UserListResponse
from app.services.auth import register_user
from app.services.oasis import DEFAULT_OASIS_CONFIG, normalize_oasis_config as normalize_runtime_oasis_config
from app.services.task_state import TaskRecord, TaskStatus, task_manager
from app.services.provider_models import (
    dump_provider_models,
    get_chat_models,
    get_provider_chat_models,
    get_provider_embedding_models,
    get_provider_models,
    set_provider_models,
)
from app.services.provider_type import (
    is_anthropic_provider,
    normalize_provider_type,
    parse_supported_provider_types,
)

router = APIRouter()
SUPPORTED_PROVIDER_TYPES = parse_supported_provider_types(settings.SUPPORTED_PROVIDER_TYPES)
SUPPORTED_BILLING_MODES = {"TOKEN", "REQUEST"}
MONEY_SCALE = Decimal("0.000001")
_RUNNING_TASK_STATUSES = {TaskStatus.PENDING.value, TaskStatus.PROCESSING.value}


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(MONEY_SCALE)
    except Exception:
        return Decimal("0").quantize(MONEY_SCALE)


def _serialize_user(
    u: User,
    *,
    usage: dict[str, Any] | None = None,
    recharge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    usage_payload = usage or {
        "total_requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
    }
    recharge_payload = recharge or {
        "total_orders": 0,
        "paid_orders": 0,
        "total_amount": 0.0,
        "paid_amount": 0.0,
        "last_order_at": None,
    }
    return {
        "id": u.id,
        "email": u.email,
        "nickname": u.nickname,
        "is_admin": bool(u.is_admin),
        "status": u.status,
        "balance": float(u.balance),
        "created_at": u.created_at.isoformat(),
        "usage": usage_payload,
        "recharge": recharge_payload,
    }


def _serialize_pricing_rule(rule: PricingRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "model": rule.model,
        "billing_mode": str(rule.billing_mode or "TOKEN").upper(),
        "input_price": float(rule.input_price),
        "output_price": float(rule.output_price),
        "token_unit": int(rule.token_unit or 1_000_000),
        "request_price": float(rule.request_price or 0),
        "is_active": bool(rule.is_active),
    }


def _serialize_task(task: TaskRecord) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status.value if isinstance(task.status, TaskStatus) else str(task.status or ""),
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "progress": int(task.progress or 0),
        "message": str(task.message or ""),
        "result": task.result if isinstance(task.result, dict) else None,
        "error": str(task.error) if task.error is not None else None,
        "progress_detail": task.progress_detail if isinstance(task.progress_detail, dict) else None,
        "metadata": task.metadata if isinstance(task.metadata, dict) else {},
    }


def _normalize_task_status_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized not in {status.value for status in TaskStatus}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid task status filter",
        )
    return normalized


def _normalize_provider_type(value: str) -> str:
    try:
        return normalize_provider_type(value, supported=SUPPORTED_PROVIDER_TYPES)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


def _normalize_billing_mode(value: Any) -> str:
    mode = str(value or "TOKEN").strip().upper()
    if mode not in SUPPORTED_BILLING_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="billing_mode must be TOKEN or REQUEST",
        )
    return mode


def _validate_pricing_payload(
    *,
    billing_mode: str,
    input_price: Any,
    output_price: Any,
    token_unit: Any,
    request_price: Any,
) -> tuple[Decimal, Decimal, int, Decimal]:
    in_price = _money(input_price)
    out_price = _money(output_price)
    tok_unit = 1_000_000
    req_price = _money(request_price)

    if billing_mode == "TOKEN":
        if in_price < 0 or out_price < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input_price/output_price must be >= 0")
        req_price = _money(0)
    else:
        if req_price < 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request_price must be >= 0")
        in_price = _money(0)
        out_price = _money(0)
        tok_unit = 1_000_000

    return in_price, out_price, tok_unit, req_price


@router.get("/stats", response_model=StatsResponse)
async def get_stats(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    last_24h_start = now - timedelta(days=1)
    last_7d_start = now - timedelta(days=7)
    last_30d_start = now - timedelta(days=30)
    trend_start = now - timedelta(days=6)

    total_users = int((await db.execute(select(func.count(User.id)))).scalar() or 0)
    total_projects = int((await db.execute(select(func.count(TextProject.id)))).scalar() or 0)
    total_operations = int((await db.execute(select(func.count(TextOperation.id)))).scalar() or 0)
    completed_operations = int(
        (await db.execute(select(func.count(TextOperation.id)).where(TextOperation.status == "COMPLETED"))).scalar() or 0
    )
    failed_operations = int(
        (await db.execute(select(func.count(TextOperation.id)).where(TextOperation.status == "FAILED"))).scalar() or 0
    )

    total_revenue = float(
        (await db.execute(select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == "PAID"))).scalar() or 0
    )

    balance_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(User.balance), 0),
                func.coalesce(func.avg(User.balance), 0),
            )
        )
    ).one()
    total_balance = float(balance_row[0] or 0)
    average_balance = float(balance_row[1] or 0)

    usage_total_row = (
        await db.execute(
            select(
                func.coalesce(func.count(Usage.id), 0),
                func.coalesce(func.sum(Usage.input_tokens), 0),
                func.coalesce(func.sum(Usage.output_tokens), 0),
                func.coalesce(func.sum(Usage.cost), 0),
            )
        )
    ).one()
    total_request_count = int(usage_total_row[0] or 0)
    total_input_tokens = int(usage_total_row[1] or 0)
    total_output_tokens = int(usage_total_row[2] or 0)
    total_usage_cost = float(usage_total_row[3] or 0)
    total_tokens = total_input_tokens + total_output_tokens

    usage_24h_row = (
        await db.execute(
            select(
                func.coalesce(func.count(Usage.id), 0),
                func.coalesce(func.sum(Usage.input_tokens), 0),
                func.coalesce(func.sum(Usage.output_tokens), 0),
                func.coalesce(func.sum(Usage.cost), 0),
                func.coalesce(func.count(func.distinct(Usage.user_id)), 0),
            ).where(Usage.created_at >= last_24h_start)
        )
    ).one()
    last_24h_request_count = int(usage_24h_row[0] or 0)
    last_24h_input_tokens = int(usage_24h_row[1] or 0)
    last_24h_output_tokens = int(usage_24h_row[2] or 0)
    last_24h_cost = float(usage_24h_row[3] or 0)
    daily_active = int(usage_24h_row[4] or 0)
    last_24h_tokens = last_24h_input_tokens + last_24h_output_tokens

    last_7d_cost = float(
        (await db.execute(select(func.coalesce(func.sum(Usage.cost), 0)).where(Usage.created_at >= last_7d_start))).scalar()
        or 0
    )
    last_30d_cost = float(
        (await db.execute(select(func.coalesce(func.sum(Usage.cost), 0)).where(Usage.created_at >= last_30d_start))).scalar()
        or 0
    )

    top_users_result = await db.execute(
        select(
            User.id,
            User.email,
            User.nickname,
            func.coalesce(func.count(Usage.id), 0).label("request_count"),
            func.coalesce(func.sum(Usage.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(Usage.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(Usage.cost), 0).label("cost"),
        )
        .join(Usage, Usage.user_id == User.id, isouter=True)
        .group_by(User.id, User.email, User.nickname)
        .order_by(desc(func.coalesce(func.sum(Usage.cost), 0)), desc(func.coalesce(func.count(Usage.id), 0)))
        .limit(10)
    )
    top_users = [
        {
            "user_id": row[0],
            "email": row[1],
            "nickname": row[2],
            "request_count": int(row[3] or 0),
            "input_tokens": int(row[4] or 0),
            "output_tokens": int(row[5] or 0),
            "total_tokens": int(row[4] or 0) + int(row[5] or 0),
            "cost": float(row[6] or 0),
        }
        for row in top_users_result.all()
        if int(row[3] or 0) > 0
    ]

    top_models_result = await db.execute(
        select(
            Usage.model,
            func.coalesce(func.count(Usage.id), 0).label("request_count"),
            func.coalesce(func.sum(Usage.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(Usage.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(Usage.cost), 0).label("cost"),
        )
        .where(and_(Usage.model.is_not(None), Usage.model != ""))
        .group_by(Usage.model)
        .order_by(desc(func.coalesce(func.sum(Usage.cost), 0)), desc(func.coalesce(func.count(Usage.id), 0)))
        .limit(10)
    )
    top_models = [
        {
            "model": str(row[0]),
            "request_count": int(row[1] or 0),
            "input_tokens": int(row[2] or 0),
            "output_tokens": int(row[3] or 0),
            "total_tokens": int(row[2] or 0) + int(row[3] or 0),
            "cost": float(row[4] or 0),
        }
        for row in top_models_result.all()
    ]

    trend_result = await db.execute(
        select(
            func.date(Usage.created_at).label("day"),
            func.coalesce(func.count(Usage.id), 0).label("request_count"),
            func.coalesce(func.count(func.distinct(Usage.user_id)), 0).label("active_users"),
            func.coalesce(func.sum(Usage.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(Usage.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(Usage.cost), 0).label("cost"),
        )
        .where(Usage.created_at >= trend_start)
        .group_by(func.date(Usage.created_at))
        .order_by(func.date(Usage.created_at).asc())
    )
    trend_map: dict[str, dict[str, float | int]] = {}
    for row in trend_result.all():
        day_str = str(row[0])
        in_tokens = int(row[3] or 0)
        out_tokens = int(row[4] or 0)
        trend_map[day_str] = {
            "request_count": int(row[1] or 0),
            "active_users": int(row[2] or 0),
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "total_tokens": in_tokens + out_tokens,
            "cost": float(row[5] or 0),
        }

    daily_usage: list[dict[str, Any]] = []
    for i in range(7):
        day = (trend_start + timedelta(days=i)).date().isoformat()
        point = trend_map.get(day) or {
            "request_count": 0,
            "active_users": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0,
        }
        daily_usage.append(
            {
                "date": day,
                "request_count": int(point["request_count"]),
                "active_users": int(point["active_users"]),
                "input_tokens": int(point["input_tokens"]),
                "output_tokens": int(point["output_tokens"]),
                "total_tokens": int(point["total_tokens"]),
                "cost": float(point["cost"]),
            }
        )

    usage_without_operation = int(
        (await db.execute(select(func.count(Usage.id)).where(Usage.operation_id.is_(None)))).scalar() or 0
    )
    usage_without_project = int(
        (await db.execute(select(func.count(Usage.id)).where(Usage.project_id.is_(None)))).scalar() or 0
    )
    usage_with_missing_operation_record = int(
        (
            await db.execute(
                select(func.count(Usage.id))
                .select_from(Usage)
                .outerjoin(TextOperation, TextOperation.id == Usage.operation_id)
                .where(and_(Usage.operation_id.is_not(None), TextOperation.id.is_(None)))
            )
        ).scalar()
        or 0
    )
    usage_with_missing_project_record = int(
        (
            await db.execute(
                select(func.count(Usage.id))
                .select_from(Usage)
                .outerjoin(TextProject, TextProject.id == Usage.project_id)
                .where(and_(Usage.project_id.is_not(None), TextProject.id.is_(None)))
            )
        ).scalar()
        or 0
    )
    usage_with_project_user_mismatch = int(
        (
            await db.execute(
                select(func.count(Usage.id))
                .select_from(Usage)
                .join(TextProject, TextProject.id == Usage.project_id)
                .where(TextProject.user_id != Usage.user_id)
            )
        ).scalar()
        or 0
    )
    usage_with_operation_user_mismatch = int(
        (
            await db.execute(
                select(func.count(Usage.id))
                .select_from(Usage)
                .join(TextOperation, TextOperation.id == Usage.operation_id)
                .join(TextProject, TextProject.id == TextOperation.project_id)
                .where(TextProject.user_id != Usage.user_id)
            )
        ).scalar()
        or 0
    )
    usage_operation_value_mismatch = int(
        (
            await db.execute(
                select(func.count(Usage.id))
                .select_from(Usage)
                .join(TextOperation, TextOperation.id == Usage.operation_id)
                .where(
                    or_(
                        Usage.input_tokens != TextOperation.input_tokens,
                        Usage.output_tokens != TextOperation.output_tokens,
                        Usage.cost != TextOperation.cost,
                    )
                )
            )
        ).scalar()
        or 0
    )
    negative_balance_users = int(
        (await db.execute(select(func.count(User.id)).where(User.balance < Decimal("0")))).scalar() or 0
    )

    return StatsResponse(
        total_users=total_users,
        total_projects=total_projects,
        total_operations=total_operations,
        completed_operations=completed_operations,
        failed_operations=failed_operations,
        total_revenue=total_revenue,
        total_usage_cost=total_usage_cost,
        total_balance=total_balance,
        average_balance=average_balance,
        total_request_count=total_request_count,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_tokens=total_tokens,
        daily_active_users=daily_active,
        last_24h_request_count=last_24h_request_count,
        last_24h_cost=last_24h_cost,
        last_24h_input_tokens=last_24h_input_tokens,
        last_24h_output_tokens=last_24h_output_tokens,
        last_24h_tokens=last_24h_tokens,
        last_7d_cost=last_7d_cost,
        last_30d_cost=last_30d_cost,
        top_users=top_users,
        top_models=top_models,
        daily_usage=daily_usage,
        usage_audit={
            "usage_without_operation": usage_without_operation,
            "usage_without_project": usage_without_project,
            "usage_with_missing_operation_record": usage_with_missing_operation_record,
            "usage_with_missing_project_record": usage_with_missing_project_record,
            "usage_with_project_user_mismatch": usage_with_project_user_mismatch,
            "usage_with_operation_user_mismatch": usage_with_operation_user_mismatch,
            "usage_operation_value_mismatch": usage_operation_value_mismatch,
            "negative_balance_users": negative_balance_users,
        },
    )


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
    is_admin: bool | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    if search:
        query = query.where(
            User.email.ilike(f"%{search}%")
            | User.nickname.ilike(f"%{search}%")
        )
    if is_admin is not None:
        query = query.where(User.is_admin == is_admin)
    if status_filter:
        normalized_status = str(status_filter).strip().upper()
        if normalized_status not in ("ACTIVE", "SUSPENDED", "DELETED"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status filter")
        query = query.where(User.status == normalized_status)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().all()
    user_ids = [u.id for u in users]

    usage_map: dict[str, dict[str, Any]] = {}
    recharge_map: dict[str, dict[str, Any]] = {}
    if user_ids:
        usage_result = await db.execute(
            select(
                Usage.user_id,
                func.coalesce(func.count(Usage.id), 0).label("total_requests"),
                func.coalesce(func.sum(Usage.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(Usage.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(Usage.cost), 0).label("total_cost"),
            )
            .where(Usage.user_id.in_(user_ids))
            .group_by(Usage.user_id)
        )
        for row in usage_result.all():
            input_tokens = int(row[2] or 0)
            output_tokens = int(row[3] or 0)
            usage_map[str(row[0])] = {
                "total_requests": int(row[1] or 0),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "total_cost": float(row[4] or 0),
            }

        recharge_result = await db.execute(
            select(
                Order.user_id,
                func.coalesce(func.count(Order.id), 0).label("total_orders"),
                func.coalesce(func.sum(case((Order.status == "PAID", 1), else_=0)), 0).label("paid_orders"),
                func.coalesce(func.sum(Order.amount), 0).label("total_amount"),
                func.coalesce(
                    func.sum(case((Order.status == "PAID", Order.amount), else_=0)),
                    0,
                ).label("paid_amount"),
                func.max(Order.created_at).label("last_order_at"),
            )
            .where(
                Order.user_id.in_(user_ids),
                Order.type == "RECHARGE",
            )
            .group_by(Order.user_id)
        )
        for row in recharge_result.all():
            last_order_at = row[5].isoformat() if row[5] else None
            recharge_map[str(row[0])] = {
                "total_orders": int(row[1] or 0),
                "paid_orders": int(row[2] or 0),
                "total_amount": float(row[3] or 0),
                "paid_amount": float(row[4] or 0),
                "last_order_at": last_order_at,
            }

    return UserListResponse(
        users=[
            _serialize_user(
                u,
                usage=usage_map.get(u.id),
                recharge=recharge_map.get(u.id),
            )
            for u in users
        ],
        total=total, page=page, page_size=page_size,
    )


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", "")).strip()
    nickname = str(body.get("nickname", "")).strip()
    if not email or not password or not nickname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email/password/nickname are required")

    try:
        user = await register_user(email, password, nickname, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    user.is_admin = bool(body.get("is_admin", False))
    if "status" in body:
        status_value = str(body.get("status") or "").strip().upper()
        if status_value not in ("ACTIVE", "SUSPENDED", "DELETED"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
        user.status = status_value
    if "balance" in body:
        user.balance = _money(body.get("balance"))
    await db.flush()
    return _serialize_user(user)


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if "email" in body:
        next_email = str(body.get("email") or "").strip().lower()
        if not next_email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")
        if next_email != user.email:
            exists = await db.execute(select(User.id).where(User.email == next_email))
            if exists.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")
            user.email = next_email
    if "nickname" in body:
        user.nickname = str(body.get("nickname") or "").strip() or None
    if "is_admin" in body:
        next_is_admin = bool(body.get("is_admin"))
        if user.id == admin.id and not next_is_admin:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove your own admin permission")
        user.is_admin = next_is_admin
    if "status" in body:
        status_value = str(body.get("status") or "").strip().upper()
        if status_value not in ("ACTIVE", "SUSPENDED", "DELETED"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
        user.status = status_value
    if "balance" in body:
        user.balance = _money(body.get("balance"))
    await db.flush()
    return _serialize_user(user)


@router.post("/users/{user_id}/balance")
async def add_user_balance(
    user_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    amount = _money(body.get("amount"))
    if amount == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="amount cannot be 0")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.balance = _money(user.balance) + amount
    await db.flush()
    return _serialize_user(user)


@router.get("/users/{user_id}/orders")
async def list_user_orders(
    user_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user_result = await db.execute(select(User.id).where(User.id == user_id))
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    query = select(Order).where(
        Order.user_id == user_id,
        Order.type == "RECHARGE",
    )
    if status_filter:
        query = query.where(Order.status == str(status_filter).strip().upper())

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    orders = result.scalars().all()

    return {
        "orders": [
            {
                "id": o.id,
                "order_no": o.order_no,
                "user_id": o.user_id,
                "type": o.type,
                "amount": float(o.amount),
                "status": o.status,
                "payment_method": o.payment_method,
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                "created_at": o.created_at.isoformat(),
            }
            for o in orders
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete current admin user")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.delete(user)
    return None


@router.get("/tasks")
async def list_tasks(
    task_type: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    normalized_status = _normalize_task_status_filter(status_filter)
    tasks = task_manager.list_tasks(
        task_type=str(task_type or "").strip() or None,
        project_id=str(project_id or "").strip() or None,
        limit=limit,
    )
    if user_id:
        target_user_id = str(user_id).strip()
        tasks = [t for t in tasks if str((t.metadata or {}).get("user_id") or "") == target_user_id]
    if normalized_status:
        tasks = [
            t
            for t in tasks
            if (t.status.value if isinstance(t.status, TaskStatus) else str(t.status or "").lower()) == normalized_status
        ]

    return {
        "tasks": [_serialize_task(task) for task in tasks],
        "total": len(tasks),
        "limit": limit,
    }


@router.get("/tasks/{task_id}")
async def get_task_detail(
    task_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return {
        "task": _serialize_task(task),
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    current_status = task.status.value if isinstance(task.status, TaskStatus) else str(task.status or "").lower()
    if current_status in _RUNNING_TASK_STATUSES:
        task = task_manager.cancel_task(task_id, message="Task cancelled by admin") or task
    return {
        "task": _serialize_task(task),
    }


def _serialize_provider(provider: AIProviderConfig) -> dict[str, Any]:
    return {
        "id": provider.id,
        "name": provider.name,
        "provider": provider.provider,
        "base_url": provider.base_url,
        "models": get_provider_chat_models(provider),
        "embedding_models": get_provider_embedding_models(provider),
        "is_active": provider.is_active,
        "priority": provider.priority,
    }


def _normalize_models(raw_models: Any) -> list[str]:
    # Backward-compatible helper kept for existing tests/imports.
    return get_chat_models(raw_models)


async def _get_provider_or_404(provider_id: str, db: AsyncSession) -> AIProviderConfig:
    result = await db.execute(select(AIProviderConfig).where(AIProviderConfig.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


async def _discover_models_for_provider(provider: AIProviderConfig) -> list[str]:
    provider_type = _normalize_provider_type(provider.provider)
    api_key = (provider.api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider API key is empty")

    try:
        if is_anthropic_provider(provider_type):
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key, base_url=provider.base_url or None)
            response = await client.models.list()
            entries = getattr(response, "data", []) or []
            return sorted({item.id for item in entries if getattr(item, "id", None)})

        import openai
        client = openai.AsyncOpenAI(api_key=api_key, base_url=provider.base_url or None)
        response = await client.models.list()
        entries = getattr(response, "data", []) or []
        return sorted({item.id for item in entries if getattr(item, "id", None)})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to discover models from provider: {exc}",
        ) from exc


@router.get("/providers")
async def list_providers(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIProviderConfig).order_by(AIProviderConfig.priority.desc()))
    providers = result.scalars().all()
    return [_serialize_provider(p) for p in providers]


def _provider_model_field(kind: str) -> str:
    return "embedding_models" if kind == "embedding" else "models"


def _provider_model_response(provider: AIProviderConfig, models: list[str], kind: str) -> dict[str, Any]:
    return {
        "provider_id": provider.id,
        _provider_model_field(kind): models,
    }


async def _list_provider_models_by_kind(
    provider_id: str,
    *,
    kind: str,
    db: AsyncSession,
) -> dict[str, Any]:
    provider = await _get_provider_or_404(provider_id, db)
    current = get_provider_models(provider, "embedding" if kind == "embedding" else "chat")
    return _provider_model_response(provider, current, kind)


async def _add_provider_model_by_kind(
    provider_id: str,
    *,
    kind: str,
    body: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    model = str(body.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model is required")

    provider = await _get_provider_or_404(provider_id, db)
    current = get_provider_models(provider, "embedding" if kind == "embedding" else "chat")
    if model not in current:
        current.append(model)
    set_provider_models(provider, "embedding" if kind == "embedding" else "chat", current)
    await db.flush()
    return _provider_model_response(provider, current, kind)


async def _remove_provider_model_by_kind(
    provider_id: str,
    *,
    kind: str,
    model: str,
    db: AsyncSession,
) -> dict[str, Any]:
    provider = await _get_provider_or_404(provider_id, db)
    current = get_provider_models(provider, "embedding" if kind == "embedding" else "chat")
    next_models = [item for item in current if item != model]
    set_provider_models(provider, "embedding" if kind == "embedding" else "chat", next_models)
    await db.flush()
    return _provider_model_response(provider, next_models, kind)


async def _discover_provider_models_by_kind(
    provider_id: str,
    *,
    kind: str,
    persist: bool,
    db: AsyncSession,
) -> dict[str, Any]:
    provider = await _get_provider_or_404(provider_id, db)
    discovered = await _discover_models_for_provider(provider)

    current = get_provider_models(provider, "embedding" if kind == "embedding" else "chat")
    if persist:
        merged = sorted(set(current).union(discovered))
        set_provider_models(provider, "embedding" if kind == "embedding" else "chat", merged)
        await db.flush()
        current = get_provider_models(provider, "embedding" if kind == "embedding" else "chat")

    return {
        "provider_id": provider.id,
        "provider_name": provider.name,
        "discovered": discovered,
        _provider_model_field(kind): current,
        "persisted": persist,
    }


@router.get("/providers/{provider_id}/models")
async def list_provider_models(
    provider_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _list_provider_models_by_kind(provider_id, kind="chat", db=db)


@router.post("/providers/{provider_id}/models")
async def add_provider_model(
    provider_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _add_provider_model_by_kind(provider_id, kind="chat", body=body, db=db)


@router.delete("/providers/{provider_id}/models")
async def remove_provider_model(
    provider_id: str,
    model: str = Query(..., min_length=1),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _remove_provider_model_by_kind(provider_id, kind="chat", model=model, db=db)


@router.post("/providers/{provider_id}/models/discover")
async def discover_provider_models(
    provider_id: str,
    persist: bool = Query(False),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _discover_provider_models_by_kind(provider_id, kind="chat", persist=persist, db=db)


@router.get("/providers/{provider_id}/embedding-models")
async def list_provider_embedding_models(
    provider_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _list_provider_models_by_kind(provider_id, kind="embedding", db=db)


@router.post("/providers/{provider_id}/embedding-models")
async def add_provider_embedding_model(
    provider_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _add_provider_model_by_kind(provider_id, kind="embedding", body=body, db=db)


@router.delete("/providers/{provider_id}/embedding-models")
async def remove_provider_embedding_model(
    provider_id: str,
    model: str = Query(..., min_length=1),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _remove_provider_model_by_kind(provider_id, kind="embedding", model=model, db=db)


@router.post("/providers/{provider_id}/embedding-models/discover")
async def discover_provider_embedding_models(
    provider_id: str,
    persist: bool = Query(False),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _discover_provider_models_by_kind(provider_id, kind="embedding", persist=persist, db=db)


@router.post("/providers")
async def create_provider(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if "models" in body or "embedding_models" in body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "models/embedding_models must be managed via "
                "/api/admin/providers/{provider_id}/models or /embedding-models"
            ),
        )
    provider_type = _normalize_provider_type(body.get("provider", ""))
    provider = AIProviderConfig(
        name=body["name"],
        provider=provider_type,
        api_key=body["api_key"],
        base_url=body.get("base_url"),
        models=dump_provider_models(models=[], embedding_models=[]),
        is_active=body.get("is_active", True),
        priority=body.get("priority", 0),
    )
    db.add(provider)
    await db.flush()
    return _serialize_provider(provider)


@router.put("/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if "models" in body or "embedding_models" in body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "models/embedding_models must be managed via "
                "/api/admin/providers/{provider_id}/models or /embedding-models"
            ),
        )
    result = await db.execute(select(AIProviderConfig).where(AIProviderConfig.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    for key in ("name", "provider", "api_key", "base_url", "is_active", "priority"):
        if key in body:
            if key == "provider":
                setattr(provider, key, _normalize_provider_type(body[key]))
            else:
                setattr(provider, key, body[key])
    await db.flush()
    return _serialize_provider(provider)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AIProviderConfig).where(AIProviderConfig.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    await db.delete(provider)
    return None


def _oasis_default_payload() -> dict[str, Any]:
    return dict(DEFAULT_OASIS_CONFIG)


def _normalize_oasis_config(raw: Any) -> dict[str, Any]:
    return normalize_runtime_oasis_config(raw)


def _serialize_oasis_config(raw: Any) -> dict[str, Any]:
    cfg = raw if isinstance(raw, dict) else {}
    return _normalize_oasis_config(cfg)


@router.get("/oasis-config")
async def get_oasis_config(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PaymentConfig).where(PaymentConfig.type == "oasis"))
    item = result.scalar_one_or_none()
    cfg = item.config if item and isinstance(item.config, dict) else None
    return _serialize_oasis_config(cfg)


@router.put("/oasis-config")
async def upsert_oasis_config(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PaymentConfig).where(PaymentConfig.type == "oasis"))
    item = result.scalar_one_or_none()
    current = item.config if item and isinstance(item.config, dict) else {}
    merged = {**current, **body}
    normalized = _normalize_oasis_config(merged)

    if not item:
        item = PaymentConfig(name="oasis", type="oasis", is_active=True)
        db.add(item)

    item.is_active = True
    item.config = normalized
    await db.flush()
    return _serialize_oasis_config(item.config)


def _epay_default_payload() -> dict[str, Any]:
    return {
        "enabled": False,
        "url": "",
        "pid": "",
        "has_key": False,
        "key": "",
        "payment_type": "alipay",
        "notify_url": "",
        "return_url": "",
    }


def _serialize_epay_config(item: PaymentConfig | None) -> dict[str, Any]:
    if not item:
        return _epay_default_payload()

    cfg = item.config if isinstance(item.config, dict) else {}
    secret_key = str(cfg.get("key") or "")
    return {
        "enabled": bool(item.is_active),
        "url": str(cfg.get("url") or ""),
        "pid": str(cfg.get("pid") or ""),
        "key": "",
        "has_key": bool(secret_key),
        "payment_type": str(cfg.get("payment_type") or "alipay"),
        "notify_url": str(cfg.get("notify_url") or ""),
        "return_url": str(cfg.get("return_url") or ""),
    }


@router.get("/payment-config")
async def get_payment_config(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PaymentConfig).where(PaymentConfig.type == "epay"))
    item = result.scalar_one_or_none()
    return _serialize_epay_config(item)


@router.put("/payment-config")
async def upsert_payment_config(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    enabled = bool(body.get("enabled", False))
    url = str(body.get("url") or "").strip()
    pid = str(body.get("pid") or "").strip()
    incoming_key = str(body.get("key") or "").strip()
    payment_type = str(body.get("payment_type") or "alipay").strip() or "alipay"
    notify_url = str(body.get("notify_url") or "").strip()
    return_url = str(body.get("return_url") or "").strip()

    result = await db.execute(select(PaymentConfig).where(PaymentConfig.type == "epay"))
    item = result.scalar_one_or_none()
    current_cfg = item.config if item and isinstance(item.config, dict) else {}
    current_key = str(current_cfg.get("key") or "")
    key = incoming_key or current_key

    if enabled and (not url or not pid or not key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="enabled=true requires url, pid and key",
        )

    if not item:
        item = PaymentConfig(name="epay", type="epay")
        db.add(item)

    item.is_active = enabled
    item.config = {
        "url": url,
        "pid": pid,
        "key": key,
        "payment_type": payment_type,
        "notify_url": notify_url,
        "return_url": return_url,
    }
    await db.flush()
    return _serialize_epay_config(item)


@router.get("/pricing")
async def list_pricing(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PricingRule).order_by(PricingRule.model.asc()))
    rules = result.scalars().all()
    return [_serialize_pricing_rule(r) for r in rules]


@router.post("/pricing")
async def create_pricing(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    model = str(body.get("model") or "").strip()
    if not model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model is required")

    billing_mode = _normalize_billing_mode(body.get("billing_mode"))
    input_price, output_price, token_unit, request_price = _validate_pricing_payload(
        billing_mode=billing_mode,
        input_price=body.get("input_price"),
        output_price=body.get("output_price"),
        token_unit=body.get("token_unit"),
        request_price=body.get("request_price"),
    )

    rule = PricingRule(
        model=model,
        billing_mode=billing_mode,
        input_price=input_price,
        output_price=output_price,
        token_unit=token_unit,
        request_price=request_price,
        is_active=bool(body.get("is_active", True)),
    )
    db.add(rule)
    await db.flush()
    return _serialize_pricing_rule(rule)


@router.put("/pricing/{rule_id}")
async def update_pricing(
    rule_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PricingRule).where(PricingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing rule not found")

    billing_mode = _normalize_billing_mode(body.get("billing_mode", rule.billing_mode))
    input_price, output_price, token_unit, request_price = _validate_pricing_payload(
        billing_mode=billing_mode,
        input_price=body.get("input_price", rule.input_price),
        output_price=body.get("output_price", rule.output_price),
        token_unit=body.get("token_unit", rule.token_unit),
        request_price=body.get("request_price", rule.request_price),
    )

    if "model" in body:
        model = str(body.get("model") or "").strip()
        if not model:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model cannot be empty")
        rule.model = model

    rule.billing_mode = billing_mode
    rule.input_price = input_price
    rule.output_price = output_price
    rule.token_unit = token_unit
    rule.request_price = request_price
    if "is_active" in body:
        rule.is_active = bool(body.get("is_active"))

    await db.flush()
    return _serialize_pricing_rule(rule)


@router.delete("/pricing/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pricing(
    rule_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PricingRule).where(PricingRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pricing rule not found")
    await db.delete(rule)
    return None


@router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    order_type: str = Query(default="RECHARGE", alias="type"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order)
    if user_id:
        query = query.where(Order.user_id == user_id)
    if status_filter:
        query = query.where(Order.status == str(status_filter).strip().upper())
    if order_type:
        query = query.where(Order.type == str(order_type).strip().upper())

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    orders = result.scalars().all()
    return {
        "orders": [
            {
                "id": o.id, "order_no": o.order_no, "user_id": o.user_id,
                "type": o.type, "amount": float(o.amount), "status": o.status,
                "payment_method": o.payment_method,
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                "created_at": o.created_at.isoformat(),
            }
            for o in orders
        ],
        "total": total, "page": page, "page_size": page_size,
    }
