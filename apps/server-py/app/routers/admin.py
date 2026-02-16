from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone

from app.database import get_db
from app.dependencies import require_admin
from app.models.billing import Order, Usage
from app.models.config import AIProviderConfig, ModelPermission, PricingRule, PaymentConfig, PromptTemplate
from app.models.project import TextOperation, TextProject
from app.models.user import User, UserGroup
from app.models.billing import Plan
from app.schemas.admin import StatsResponse, UserListResponse

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
async def get_stats(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_projects = (await db.execute(select(func.count(TextProject.id)))).scalar() or 0
    total_operations = (await db.execute(select(func.count(TextOperation.id)))).scalar() or 0
    total_revenue = float((await db.execute(select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == "PAID"))).scalar())

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    daily_active = (await db.execute(
        select(func.count(func.distinct(Usage.user_id))).where(Usage.created_at >= yesterday)
    )).scalar() or 0

    return StatsResponse(
        total_users=total_users,
        total_projects=total_projects,
        total_operations=total_operations,
        total_revenue=total_revenue,
        daily_active_users=daily_active,
    )


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(""),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(User)
    if search:
        query = query.where(User.email.ilike(f"%{search}%") | User.username.ilike(f"%{search}%"))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().all()
    return UserListResponse(
        users=[
            {
                "id": u.id, "email": u.email, "username": u.username,
                "nickname": u.nickname, "role": u.role, "status": u.status,
                "balance": float(u.balance), "group_id": u.group_id,
                "created_at": u.created_at.isoformat(),
            }
            for u in users
        ],
        total=total, page=page, page_size=page_size,
    )


# --- Groups ---

@router.get("/groups")
async def list_groups(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserGroup).order_by(UserGroup.sort_order))
    groups = result.scalars().all()
    return [
        {
            "id": g.id, "name": g.name, "display_name": g.display_name,
            "description": g.description, "color": g.color, "is_active": g.is_active,
            "is_default": g.is_default, "sort_order": g.sort_order,
            "price": float(g.price) if g.price else None,
            "allowed_models": g.allowed_models, "quotas": g.quotas, "features": g.features,
        }
        for g in groups
    ]


@router.post("/groups")
async def create_group(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    group = UserGroup(
        name=body["name"],
        display_name=body["display_name"],
        description=body.get("description"),
        color=body.get("color"),
        icon=body.get("icon"),
        allowed_models=body.get("allowed_models", []),
        quotas=body.get("quotas"),
        features=body.get("features"),
        price=body.get("price"),
        sort_order=body.get("sort_order", 0),
        is_active=body.get("is_active", True),
        is_default=body.get("is_default", False),
    )
    db.add(group)
    await db.flush()
    return {
        "id": group.id, "name": group.name, "display_name": group.display_name,
        "description": group.description, "color": group.color,
        "is_active": group.is_active, "is_default": group.is_default,
        "sort_order": group.sort_order,
        "price": float(group.price) if group.price else None,
    }


@router.put("/groups/{group_id}")
async def update_group(
    group_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserGroup).where(UserGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    for key in ("name", "display_name", "description", "color", "icon", "allowed_models", "quotas", "features", "price", "sort_order", "is_active", "is_default"):
        if key in body:
            setattr(group, key, body[key])
    await db.flush()
    return {"id": group.id, "name": group.name, "display_name": group.display_name}


@router.post("/groups/user/{user_id}")
async def update_user_group(
    user_id: str, group_id: str = Query(...),
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.group_id = group_id
    await db.flush()
    return {"status": "ok"}


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserGroup).where(UserGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if group.is_default:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete default group")
    await db.delete(group)
    return None


# --- Providers ---

@router.get("/providers")
async def list_providers(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIProviderConfig).order_by(AIProviderConfig.priority.desc()))
    providers = result.scalars().all()
    return [
        {
            "id": p.id, "name": p.name, "provider": p.provider,
            "base_url": p.base_url, "models": p.models,
            "is_active": p.is_active, "priority": p.priority,
        }
        for p in providers
    ]


@router.post("/providers")
async def create_provider(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    provider = AIProviderConfig(
        name=body["name"],
        provider=body["provider"],
        api_key=body["api_key"],
        base_url=body.get("base_url"),
        models=body.get("models", []),
        is_active=body.get("is_active", True),
        priority=body.get("priority", 0),
    )
    db.add(provider)
    await db.flush()
    return {
        "id": provider.id, "name": provider.name, "provider": provider.provider,
        "base_url": provider.base_url, "models": provider.models,
        "is_active": provider.is_active, "priority": provider.priority,
    }


@router.put("/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AIProviderConfig).where(AIProviderConfig.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    for key in ("name", "provider", "api_key", "base_url", "models", "is_active", "priority"):
        if key in body:
            setattr(provider, key, body[key])
    await db.flush()
    return {
        "id": provider.id, "name": provider.name, "provider": provider.provider,
        "base_url": provider.base_url, "models": provider.models,
        "is_active": provider.is_active, "priority": provider.priority,
    }


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


# --- Pricing ---

@router.get("/pricing")
async def list_pricing(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PricingRule))
    rules = result.scalars().all()
    return [
        {
            "id": r.id, "model": r.model,
            "input_price": float(r.input_price), "output_price": float(r.output_price),
            "is_active": r.is_active,
        }
        for r in rules
    ]


@router.post("/pricing")
async def create_pricing(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rule = PricingRule(
        model=body["model"],
        input_price=body["input_price"],
        output_price=body["output_price"],
        is_active=body.get("is_active", True),
    )
    db.add(rule)
    await db.flush()
    return {
        "id": rule.id, "model": rule.model,
        "input_price": float(rule.input_price), "output_price": float(rule.output_price),
        "is_active": rule.is_active,
    }


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
    for key in ("model", "input_price", "output_price", "is_active"):
        if key in body:
            setattr(rule, key, body[key])
    await db.flush()
    return {
        "id": rule.id, "model": rule.model,
        "input_price": float(rule.input_price), "output_price": float(rule.output_price),
        "is_active": rule.is_active,
    }


# --- Plans ---

@router.get("/plans")
async def list_plans(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Plan).order_by(Plan.sort_order))
    plans = result.scalars().all()
    return [
        {
            "id": p.id, "name": p.name, "display_name": p.display_name,
            "description": p.description, "target_group_id": p.target_group_id,
            "price": float(p.price), "original_price": float(p.original_price) if p.original_price else None,
            "duration": p.duration, "features": p.features,
            "quotas": p.quotas, "allowed_models": p.allowed_models,
            "is_active": p.is_active, "sort_order": p.sort_order,
        }
        for p in plans
    ]


@router.post("/plans")
async def create_plan(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    plan = Plan(
        name=body["name"],
        display_name=body["display_name"],
        description=body.get("description"),
        target_group_id=body.get("target_group_id"),
        price=body["price"],
        original_price=body.get("original_price"),
        duration=body["duration"],
        features=body.get("features"),
        quotas=body.get("quotas"),
        allowed_models=body.get("allowed_models"),
        is_active=body.get("is_active", True),
        sort_order=body.get("sort_order", 0),
    )
    db.add(plan)
    await db.flush()
    return {
        "id": plan.id, "name": plan.name, "display_name": plan.display_name,
        "description": plan.description, "target_group_id": plan.target_group_id,
        "price": float(plan.price), "original_price": float(plan.original_price) if plan.original_price else None,
        "duration": plan.duration, "features": plan.features,
        "quotas": plan.quotas, "allowed_models": plan.allowed_models,
        "is_active": plan.is_active, "sort_order": plan.sort_order,
    }


@router.put("/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    for key in ("name", "display_name", "description", "target_group_id", "price", "original_price", "duration", "features", "quotas", "allowed_models", "is_active", "sort_order"):
        if key in body:
            setattr(plan, key, body[key])
    await db.flush()
    return {
        "id": plan.id, "name": plan.name, "display_name": plan.display_name,
        "description": plan.description, "target_group_id": plan.target_group_id,
        "price": float(plan.price), "original_price": float(plan.original_price) if plan.original_price else None,
        "duration": plan.duration, "features": plan.features,
        "quotas": plan.quotas, "allowed_models": plan.allowed_models,
        "is_active": plan.is_active, "sort_order": plan.sort_order,
    }


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    await db.delete(plan)
    return None


# --- Model Permissions ---

@router.get("/model-permissions")
async def list_model_permissions(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ModelPermission).order_by(ModelPermission.group_id, ModelPermission.model))
    perms = result.scalars().all()
    return [
        {
            "id": p.id, "model": p.model, "group_id": p.group_id,
            "daily_limit": p.daily_limit, "monthly_limit": p.monthly_limit,
            "is_active": p.is_active,
        }
        for p in perms
    ]


@router.post("/model-permissions")
async def create_model_permission(
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    perm = ModelPermission(
        model=body["model"],
        group_id=body["group_id"],
        daily_limit=body.get("daily_limit", 0),
        monthly_limit=body.get("monthly_limit", 0),
        is_active=body.get("is_active", True),
    )
    db.add(perm)
    await db.flush()
    return {
        "id": perm.id, "model": perm.model, "group_id": perm.group_id,
        "daily_limit": perm.daily_limit, "monthly_limit": perm.monthly_limit,
        "is_active": perm.is_active,
    }


@router.put("/model-permissions/{perm_id}")
async def update_model_permission(
    perm_id: str,
    body: dict,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ModelPermission).where(ModelPermission.id == perm_id))
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model permission not found")
    for key in ("model", "group_id", "daily_limit", "monthly_limit", "is_active"):
        if key in body:
            setattr(perm, key, body[key])
    await db.flush()
    return {
        "id": perm.id, "model": perm.model, "group_id": perm.group_id,
        "daily_limit": perm.daily_limit, "monthly_limit": perm.monthly_limit,
        "is_active": perm.is_active,
    }


@router.delete("/model-permissions/{perm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_permission(
    perm_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ModelPermission).where(ModelPermission.id == perm_id))
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model permission not found")
    await db.delete(perm)
    return None


# --- Orders ---

@router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(Order.id)))).scalar() or 0
    result = await db.execute(
        select(Order).order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
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
