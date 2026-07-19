from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.services.http_client import create_async_http_client
from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import require_admin
from app.models.billing import Order, Usage
from app.models.config import AIProviderConfig, PaymentConfig, PricingRule
from app.models.payment_adapter import PaymentAdapter
from app.models.project import TextProject
from app.models.runtime import AgentRun, AuditLog
from app.models.user import User
from app.redis import redis_client
from app.schemas.admin import StatsResponse, UserListResponse
from app.services.auth import create_user, hash_password, revoke_user_sessions
from app.services.llm_runtime import merge_llm_runtime_config, normalize_llm_runtime_config
from app.services.payment_adapters.registry import (
    ADAPTER_TYPES,
    serialize_adapter_admin,
    validate_adapter_config,
)
from app.services.pricing_catalog import collect_pricing_catalog
from app.services.provider_models import (
    build_provider_model_ref,
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
from app.services.provider_usage import provider_model_references_in_use
from app.services.provider_security import validate_provider_base_url
from app.services.secret_crypto import (
    decrypt_secret,
    decrypt_secret_fields,
    encrypt_secret,
    encrypt_secret_fields,
)

router = APIRouter()
SUPPORTED_PROVIDER_TYPES = parse_supported_provider_types(settings.SUPPORTED_PROVIDER_TYPES)
SUPPORTED_BILLING_MODES = {"TOKEN", "REQUEST"}
MONEY_SCALE = Decimal("0.000001")
_RUNNING_TASK_STATUSES = {"queued", "running"}


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


def _serialize_task(task: AgentRun) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "task_type": f"agent:{task.mode}",
        "status": task.status,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "message": str((task.final_output or {}).get("summary") or task.instruction),
        "error": task.error,
        "heartbeat_at": task.heartbeat_at.isoformat() if task.heartbeat_at else None,
        "lease_owner": task.lease_owner,
        "cancel_requested": task.cancel_requested,
        "metadata": {
            "project_id": task.project_id,
            "user_id": task.user_id,
            "base_revision_id": task.base_revision_id,
            "result_revision_id": task.result_revision_id,
        },
    }


def _serialize_audit_log(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": entry.id,
        "actor_user_id": entry.actor_user_id,
        "project_id": entry.project_id,
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "request_id": entry.request_id,
        "ip_address": entry.ip_address,
        "detail": entry.detail,
        "created_at": entry.created_at.isoformat(),
    }


def _normalize_task_status_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    if normalized not in {
        "queued", "running", "awaiting_review", "accepting", "completed",
        "rejected", "conflicted", "failed", "cancelled",
    }:
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


def _normalize_payment_types(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="payment_types must be a list")
    payment_types: list[str] = []
    for item in value:
        payment_type = str(item or "").strip()
        if payment_type and payment_type not in payment_types:
            payment_types.append(payment_type)
    return payment_types


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


def _replace_model_reference(values: list[str], old_model: str, new_model: str) -> list[str]:
    next_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = new_model if value == old_model else value
        if normalized in seen:
            continue
        next_values.append(normalized)
        seen.add(normalized)
    return next_values


def _collect_provider_model_names(provider: AIProviderConfig) -> set[str]:
    return {
        *get_provider_chat_models(provider),
        *get_provider_embedding_models(provider),
        *get_provider_models(provider, "reranker"),
    }


async def _propagate_pricing_model_rename(db: AsyncSession, old_model: str, new_model: str) -> None:
    if old_model == new_model:
        return

    provider_result = await db.execute(
        select(AIProviderConfig).where(AIProviderConfig.user_id.is_(None))
    )
    providers = provider_result.scalars().all()
    for provider in providers:
        changed = False
        for kind in ("chat", "embedding", "reranker"):
            current_models = get_provider_models(provider, kind)
            if old_model not in current_models:
                continue
            set_provider_models(provider, kind, _replace_model_reference(current_models, old_model, new_model))
            changed = True
        if changed:
            db.add(provider)

    project_result = await db.execute(select(TextProject))
    projects = project_result.scalars().all()
    for project in projects:
        component_models = getattr(project, "component_models", None)
        if not isinstance(component_models, dict):
            continue

        changed = False
        next_component_models = dict(component_models)
        for component_key, model_name in component_models.items():
            if model_name != old_model:
                continue
            next_component_models[component_key] = new_model
            changed = True

        if changed:
            project.component_models = next_component_models
            db.add(project)


async def _prune_deleted_provider_model_references(
    db: AsyncSession,
    *,
    provider: AIProviderConfig,
) -> None:
    removed_models = _collect_provider_model_names(provider)
    await _prune_orphan_model_references(db, removed_models=removed_models, excluding_provider_id=provider.id)


async def _prune_orphan_model_references(
    db: AsyncSession,
    *,
    removed_models: set[str],
    excluding_provider_id: str | None = None,
) -> None:
    if not removed_models:
        return

    provider_query = select(AIProviderConfig).where(AIProviderConfig.user_id.is_(None))
    if excluding_provider_id:
        provider_query = provider_query.where(AIProviderConfig.id != excluding_provider_id)

    other_provider_result = await db.execute(provider_query)
    remaining_models: set[str] = set()
    for item in other_provider_result.scalars().all():
        remaining_models.update(_collect_provider_model_names(item))

    orphan_models = removed_models - remaining_models
    if not orphan_models:
        return

    pricing_result = await db.execute(
        select(PricingRule).where(PricingRule.model.in_(sorted(orphan_models)))
    )
    for rule in pricing_result.scalars().all():
        await db.delete(rule)

    project_result = await db.execute(select(TextProject))
    for project in project_result.scalars().all():
        component_models = getattr(project, "component_models", None)
        if not isinstance(component_models, dict):
            continue

        next_component_models = {
            component_key: model_name
            for component_key, model_name in component_models.items()
            if model_name not in orphan_models
        }
        if next_component_models == component_models:
            continue
        project.component_models = next_component_models
        db.add(project)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    last_24h_start = now - timedelta(days=1)
    last_7d_start = now - timedelta(days=7)
    last_30d_start = now - timedelta(days=30)
    trend_start = now - timedelta(days=6)

    total_users = int((await db.execute(select(func.count(User.id)))).scalar() or 0)
    total_projects = int((await db.execute(select(func.count(TextProject.id)))).scalar() or 0)
    total_operations = int((await db.execute(select(func.count(AgentRun.id)))).scalar() or 0)
    completed_operations = int(
        (await db.execute(select(func.count(AgentRun.id)).where(AgentRun.status == "completed"))).scalar() or 0
    )
    failed_operations = int(
        (await db.execute(select(func.count(AgentRun.id)).where(AgentRun.status == "failed"))).scalar() or 0
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
                .outerjoin(AgentRun, AgentRun.id == Usage.operation_id)
                .where(and_(Usage.operation_id.is_not(None), AgentRun.id.is_(None)))
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
                .join(AgentRun, AgentRun.id == Usage.operation_id)
                .where(AgentRun.user_id != Usage.user_id)
            )
        ).scalar()
        or 0
    )
    usage_operation_value_mismatch = 0
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
        user = await create_user(email, password, nickname, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    user.is_admin = bool(body.get("is_admin", False))
    if "status" in body:
        status_value = str(body.get("status") or "").strip().upper()
        if status_value not in ("ACTIVE", "SUSPENDED", "DELETED"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
        user.status = status_value
        if status_value != "ACTIVE":
            await revoke_user_sessions(user.id, db)
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
        if status_value != "ACTIVE":
            await revoke_user_sessions(user.id, db)
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


@router.post("/users/{user_id}/password")
async def reset_user_password(
    user_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    password = str(body.get("password", "")).strip()
    if len(password) < 12:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password must be at least 12 characters")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.password_hash = hash_password(password)
    await revoke_user_sessions(user.id, db)
    await db.flush()
    return {"ok": True}


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
    filters = []
    if task_type:
        normalized_type = str(task_type).removeprefix("agent:").strip()
        if normalized_type not in {"write", "analyze", "suggest"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid task type filter",
            )
        filters.append(AgentRun.mode == normalized_type)
    if project_id:
        filters.append(AgentRun.project_id == str(project_id).strip())
    if user_id:
        filters.append(AgentRun.user_id == str(user_id).strip())
    if normalized_status:
        filters.append(AgentRun.status == normalized_status)
    query = select(AgentRun).where(*filters).order_by(AgentRun.created_at.desc()).limit(limit)
    tasks = list((await db.execute(query)).scalars())
    total = int(
        (
            await db.execute(
                select(func.count()).select_from(AgentRun).where(*filters)
            )
        ).scalar_one()
    )

    return {
        "tasks": [_serialize_task(task) for task in tasks],
        "total": total,
        "limit": limit,
    }


@router.get("/tasks/{task_id}")
async def get_task_detail(
    task_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(AgentRun, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return {
        "task": _serialize_task(task),
    }


@router.get("/audit-logs")
async def list_audit_logs(
    project_id: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    action: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=200, ge=1, le=1000),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if project_id:
        filters.append(AuditLog.project_id == project_id.strip())
    if actor_user_id:
        filters.append(AuditLog.actor_user_id == actor_user_id.strip())
    if action:
        filters.append(AuditLog.action == action.strip())
    entries = list(
        (
            await db.execute(
                select(AuditLog)
                .where(*filters)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )
    total = int(
        (
            await db.execute(
                select(func.count()).select_from(AuditLog).where(*filters)
            )
        ).scalar_one()
    )
    return {
        "items": [_serialize_audit_log(entry) for entry in entries],
        "total": total,
        "limit": limit,
    }


@router.get("/runtime-health")
async def runtime_health(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    counts = {
        row.status: int(row.count)
        for row in (
            await db.execute(
                select(AgentRun.status, func.count().label("count")).group_by(AgentRun.status)
            )
        )
    }
    stale_workers = int(
        (
            await db.execute(
                select(func.count())
                .select_from(AgentRun)
                .where(
                    AgentRun.status == "running",
                    AgentRun.lease_expires_at < now,
                )
            )
        ).scalar_one()
    )
    await redis_client.ping()
    async with httpx.AsyncClient(
        base_url=settings.MEMORY_SERVICE_URL,
        timeout=10,
    ) as client:
        response = await client.get("/health")
        response.raise_for_status()
        memory = response.json()
    return {
        "status": "ok" if stale_workers == 0 else "degraded",
        "database": "ok",
        "redis": "ok",
        "memory": memory,
        "run_counts": counts,
        "stale_worker_leases": stale_workers,
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(AgentRun, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.status in _RUNNING_TASK_STATUSES:
        task.cancel_requested = True
        if task.status == "queued":
            task.status = "cancelled"
            task.completed_at = datetime.now(timezone.utc)
        await db.flush()
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
        "reranker_models": get_provider_models(provider, "reranker"),
        "is_active": provider.is_active,
        "priority": provider.priority,
        "has_api_key": bool(provider.api_key),
    }


def _normalize_models(raw_models: Any) -> list[str]:
    return get_chat_models(raw_models)


def _model_text_matches_kind(value: str, kind: str) -> bool:
    text = str(value or "").lower()
    if kind == "embedding":
        return ("embedding" in text or "embed" in text) and "rerank" not in text
    if kind == "reranker":
        return "rerank" in text or "re-rank" in text
    return True


def _model_value_matches_kind(value: Any, kind: str) -> bool:
    if isinstance(value, str):
        return _model_text_matches_kind(value, kind)
    if isinstance(value, list):
        return any(_model_value_matches_kind(item, kind) for item in value)
    if isinstance(value, dict):
        return any(
            (_model_text_matches_kind(key, kind) and bool(item))
            or _model_value_matches_kind(item, kind)
            for key, item in value.items()
        )
    return False


def _discovered_model_matches_kind(entry: dict[str, Any], kind: str) -> bool:
    if kind == "chat":
        return True
    model_id = str(entry.get("id") or "")
    if _model_text_matches_kind(model_id, kind):
        return True
    raw = entry.get("raw")
    if not isinstance(raw, dict):
        return False
    for field in (
        "type",
        "kind",
        "model_type",
        "modelType",
        "task",
        "task_type",
        "taskType",
        "mode",
        "purpose",
        "category",
        "capability",
        "capabilities",
        "supported_tasks",
        "supportedTasks",
        "supported_endpoints",
        "supportedEndpoints",
    ):
        if field in raw and _model_value_matches_kind(raw[field], kind):
            return True
    return False


async def _get_provider_or_404(provider_id: str, db: AsyncSession) -> AIProviderConfig:
    result = await db.execute(
        select(AIProviderConfig).where(
            AIProviderConfig.id == provider_id,
            AIProviderConfig.user_id.is_(None),
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


async def _discover_models_for_provider(provider: AIProviderConfig) -> list[dict[str, Any]]:
    provider_type = _normalize_provider_type(provider.provider)
    api_key = decrypt_secret(provider.api_key)
    if not api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider API key is empty")

    try:
        if is_anthropic_provider(provider_type):
            base_url = str(provider.base_url or "https://api.anthropic.com/v1").rstrip("/")
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
        else:
            base_url = str(provider.base_url or "https://api.openai.com/v1").rstrip("/")
            headers = {"Authorization": f"Bearer {api_key}"}

        async with create_async_http_client(timeout=30.0) as client:
            response = await client.get(f"{base_url}/models", headers=headers)
        response.raise_for_status()
        payload = response.json()
        entries = payload.get("data", []) if isinstance(payload, dict) else payload
        if not isinstance(entries, list):
            raise ValueError("provider /models response must contain a data list")
        discovered: dict[str, dict[str, Any]] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or item.get("name") or item.get("model") or "").strip()
            if model_id:
                discovered[model_id] = {"id": model_id, "raw": item}
        return [discovered[model_id] for model_id in sorted(discovered)]
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        detail = f"Provider model discovery returned HTTP {exc.response.status_code}"
        try:
            body = exc.response.json()
            if isinstance(body, dict) and body.get("error"):
                detail = f"{detail}: {body['error']}"
        except Exception:
            text = (exc.response.text or "").strip()
            if text:
                detail = f"{detail}: {text[:240]}"
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to discover models from provider: {exc}",
        ) from exc


@router.get("/providers")
async def list_providers(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AIProviderConfig)
        .where(AIProviderConfig.user_id.is_(None))
        .order_by(AIProviderConfig.priority.desc())
    )
    providers = result.scalars().all()
    return [_serialize_provider(p) for p in providers]


def _provider_model_field(kind: str) -> str:
    if kind == "embedding":
        return "embedding_models"
    if kind == "reranker":
        return "reranker_models"
    return "models"


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
    current = get_provider_models(provider, kind)
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
    current = get_provider_models(provider, kind)
    if model not in current:
        current.append(model)
    set_provider_models(provider, kind, current)
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
    current = get_provider_models(provider, kind)
    next_models = [item for item in current if item != model]
    if (
        model in current
        and build_provider_model_ref(provider.id, model)
        in await provider_model_references_in_use(db, provider.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider model is still selected by a project or Agent",
        )
    set_provider_models(provider, kind, next_models)
    if model in current and model not in next_models:
        await _prune_orphan_model_references(db, removed_models={model}, excluding_provider_id=provider.id)
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
    discovered_entries = await _discover_models_for_provider(provider)
    discovered = [str(entry["id"]) for entry in discovered_entries]
    persistable_discovered = [
        str(entry["id"])
        for entry in discovered_entries
        if _discovered_model_matches_kind(entry, kind)
    ]
    persistable_set = set(persistable_discovered)
    not_persisted_discovered = [model for model in discovered if model not in persistable_set]

    current = get_provider_models(provider, kind)
    if persist:
        merged = sorted(set(current).union(persistable_discovered))
        set_provider_models(provider, kind, merged)
        await db.flush()
        current = get_provider_models(provider, kind)

    return {
        "provider_id": provider.id,
        "provider_name": provider.name,
        "discovered": discovered,
        "persistable_discovered": persistable_discovered,
        "not_persisted_discovered": not_persisted_discovered if persist else [],
        "not_persisted_reason": "model_kind_not_confirmed" if persist and not_persisted_discovered else None,
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


@router.get("/providers/{provider_id}/reranker-models")
async def list_provider_reranker_models(
    provider_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _list_provider_models_by_kind(provider_id, kind="reranker", db=db)


@router.post("/providers/{provider_id}/reranker-models")
async def add_provider_reranker_model(
    provider_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _add_provider_model_by_kind(provider_id, kind="reranker", body=body, db=db)


@router.delete("/providers/{provider_id}/reranker-models")
async def remove_provider_reranker_model(
    provider_id: str,
    model: str = Query(..., min_length=1),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _remove_provider_model_by_kind(provider_id, kind="reranker", model=model, db=db)


@router.post("/providers/{provider_id}/reranker-models/discover")
async def discover_provider_reranker_models(
    provider_id: str,
    persist: bool = Query(False),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await _discover_provider_models_by_kind(provider_id, kind="reranker", persist=persist, db=db)


@router.post("/providers")
async def create_provider(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if "models" in body or "embedding_models" in body or "reranker_models" in body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "models/embedding_models/reranker_models must be managed via "
                "/api/admin/providers/{provider_id}/models, /embedding-models, or /reranker-models"
            ),
        )
    provider_type = _normalize_provider_type(body.get("provider", ""))
    try:
        base_url = await validate_provider_base_url(body.get("base_url"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    provider = AIProviderConfig(
        user_id=None,
        name=body["name"],
        provider=provider_type,
        api_key=encrypt_secret(str(body["api_key"])),
        base_url=base_url,
        models=dump_provider_models(models=[], embedding_models=[], reranker_models=[]),
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
    if "models" in body or "embedding_models" in body or "reranker_models" in body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "models/embedding_models/reranker_models must be managed via "
                "/api/admin/providers/{provider_id}/models, /embedding-models, or /reranker-models"
            ),
        )
    result = await db.execute(
        select(AIProviderConfig).where(
            AIProviderConfig.id == provider_id,
            AIProviderConfig.user_id.is_(None),
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    for key in ("name", "provider", "api_key", "base_url", "is_active", "priority"):
        if key in body:
            if key == "provider":
                setattr(provider, key, _normalize_provider_type(body[key]))
            elif key == "api_key":
                setattr(provider, key, encrypt_secret(str(body[key])))
            elif key == "base_url":
                try:
                    provider.base_url = await validate_provider_base_url(body[key])
                except ValueError as exc:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=str(exc),
                    ) from exc
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
    result = await db.execute(
        select(AIProviderConfig).where(
            AIProviderConfig.id == provider_id,
            AIProviderConfig.user_id.is_(None),
        )
    )
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    if await provider_model_references_in_use(db, provider.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider is still selected by a project or Agent",
        )
    await _prune_deleted_provider_model_references(db, provider=provider)
    await db.delete(provider)
    return None


def _serialize_llm_runtime_config(raw: Any) -> dict[str, Any]:
    cfg = raw if isinstance(raw, dict) else {}
    return normalize_llm_runtime_config(cfg)


async def _load_llm_runtime_payment_config(db: AsyncSession) -> PaymentConfig | None:
    result = await db.execute(select(PaymentConfig).where(PaymentConfig.type == "llm_runtime"))
    return result.scalar_one_or_none()


@router.get("/llm-runtime-config")
async def get_llm_runtime_config(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    item = await _load_llm_runtime_payment_config(db)
    cfg = item.config if item and isinstance(item.config, dict) else None
    return _serialize_llm_runtime_config(cfg)


@router.put("/llm-runtime-config")
async def upsert_llm_runtime_config(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    item = await _load_llm_runtime_payment_config(db)
    current = item.config if item and isinstance(item.config, dict) else {}
    normalized = merge_llm_runtime_config(current, body)

    if not item:
        item = PaymentConfig(name="llm_runtime", type="llm_runtime", is_active=True)
        db.add(item)

    item.is_active = True
    item.config = normalized
    await db.flush()
    return _serialize_llm_runtime_config(item.config)


@router.get("/payment-adapter-types")
async def list_payment_adapter_types(admin: User = Depends(require_admin)):
    return {
        "types": [
            {"id": type_id, **meta}
            for type_id, meta in ADAPTER_TYPES.items()
        ]
    }


@router.get("/payment-adapters")
async def list_payment_adapters(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PaymentAdapter).order_by(
            PaymentAdapter.sort_order.asc(),
            PaymentAdapter.created_at.asc(),
        )
    )
    items = result.scalars().all()
    return {"adapters": [serialize_adapter_admin(item) for item in items]}


@router.post("/payment-adapters")
async def create_payment_adapter(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    adapter_type = str(body.get("adapter_type") or "").strip()
    display_name = str(body.get("display_name") or "").strip()
    enabled = bool(body.get("enabled", False))
    sort_order = int(body.get("sort_order") or 0)
    incoming_config = body.get("config") if isinstance(body.get("config"), dict) else {}

    if adapter_type not in ADAPTER_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid adapter_type")
    if not display_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="display_name is required")

    stored_config, err = validate_adapter_config(adapter_type, enabled=enabled, config=incoming_config)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    item = PaymentAdapter(
        adapter_type=adapter_type,
        display_name=display_name,
        config=encrypt_secret_fields(stored_config),
        enabled=enabled,
        sort_order=sort_order,
    )
    db.add(item)
    await db.flush()
    return serialize_adapter_admin(item)


@router.put("/payment-adapters/{adapter_id}")
async def update_payment_adapter(
    adapter_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PaymentAdapter).where(PaymentAdapter.id == adapter_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment adapter not found")

    if "display_name" in body:
        display_name = str(body.get("display_name") or "").strip()
        if not display_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="display_name is required")
        item.display_name = display_name
    if "enabled" in body:
        item.enabled = bool(body.get("enabled"))
    if "sort_order" in body:
        item.sort_order = int(body.get("sort_order") or 0)

    if "config" in body:
        incoming_config = body.get("config") if isinstance(body.get("config"), dict) else {}
        current_cfg = decrypt_secret_fields(item.config if isinstance(item.config, dict) else {})
        existing_key = str(current_cfg.get("key") or "")
        stored_config, err = validate_adapter_config(
            item.adapter_type,
            enabled=item.enabled,
            config=incoming_config,
            existing_key=existing_key,
        )
        if err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
        item.config = encrypt_secret_fields(stored_config)
    elif item.enabled:
        current_cfg = decrypt_secret_fields(item.config if isinstance(item.config, dict) else {})
        existing_key = str(current_cfg.get("key") or "")
        _, err = validate_adapter_config(
            item.adapter_type,
            enabled=True,
            config=current_cfg,
            existing_key=existing_key,
        )
        if err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    await db.flush()
    return serialize_adapter_admin(item)


@router.delete("/payment-adapters/{adapter_id}")
async def delete_payment_adapter(
    adapter_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(PaymentAdapter).where(PaymentAdapter.id == adapter_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment adapter not found")
    await db.delete(item)
    await db.flush()
    return {"ok": True}


@router.get("/pricing")
async def list_pricing(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return await collect_pricing_catalog(db, provider_active_only=False, pricing_active_only=False)


@router.post("/pricing")
async def create_pricing(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    model = str(body.get("model") or "").strip()
    if not model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model is required")

    existing = (await db.execute(select(PricingRule).where(PricingRule.model == model))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pricing rule for this model already exists")

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
    original_model = str(rule.model or "").strip()

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
        if model != original_model:
            existing = (
                await db.execute(select(PricingRule).where(PricingRule.model == model, PricingRule.id != rule_id))
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Pricing rule for this model already exists",
                )
        rule.model = model
        await _propagate_pricing_model_rename(db, original_model, model)

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
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    order_type: str = Query(default="RECHARGE", alias="type"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(
            Order,
            User.email.label("user_email"),
            User.nickname.label("user_nickname"),
            PaymentAdapter.display_name.label("payment_adapter_name"),
        )
        .join(User, User.id == Order.user_id)
        .outerjoin(PaymentAdapter, PaymentAdapter.id == Order.payment_adapter_id)
    )
    if user_id:
        query = query.where(Order.user_id == user_id)
    if search:
        term = f"%{str(search).strip()}%"
        query = query.where(
            or_(
                Order.order_no.ilike(term),
                User.email.ilike(term),
                User.nickname.ilike(term),
            )
        )
    if status_filter:
        query = query.where(Order.status == str(status_filter).strip().upper())
    if order_type:
        query = query.where(Order.type == str(order_type).strip().upper())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    rows = result.all()
    return {
        "orders": [
            {
                "id": o.id,
                "order_no": o.order_no,
                "user_id": o.user_id,
                "user_email": user_email,
                "user_nickname": user_nickname,
                "type": o.type,
                "amount": float(o.amount),
                "status": o.status,
                "payment_method": o.payment_method,
                "payment_adapter_id": o.payment_adapter_id,
                "payment_adapter_name": payment_adapter_name,
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
                "created_at": o.created_at.isoformat(),
            }
            for o, user_email, user_nickname, payment_adapter_name in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/usage-records")
async def admin_list_usage_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str | None = Query(default=None),
    model: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.usage_records import list_usage_records

    return await list_usage_records(
        db,
        user_id=user_id,
        model=model,
        project_id=project_id,
        search=search,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        include_user=True,
        include_project=True,
    )


@router.get("/usage-retention-config")
async def get_usage_retention_config_admin(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.usage_retention import get_usage_retention_config

    return await get_usage_retention_config(db)


@router.put("/usage-retention-config")
async def upsert_usage_retention_config_admin(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.usage_retention import upsert_usage_retention_config

    return await upsert_usage_retention_config(db, body)


@router.post("/usage-records/cleanup")
async def run_usage_retention_cleanup(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.usage_retention import enforce_usage_retention

    return await enforce_usage_retention(db)
