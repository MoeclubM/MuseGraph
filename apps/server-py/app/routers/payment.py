from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.billing import Order, Plan
from app.models.user import User
from app.services.payment import create_payment_order, process_payment_callback

router = APIRouter()


class CreateOrderRequest(BaseModel):
    type: str  # SUBSCRIPTION / RECHARGE / UPGRADE
    amount: float
    plan_id: Optional[str] = None
    payment_method: Optional[str] = None


@router.post("/create")
async def create_order(
    body: CreateOrderRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.plan_id:
        result = await db.execute(select(Plan).where(Plan.id == body.plan_id, Plan.is_active == True))
        plan = result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    order = await create_payment_order(
        user_id=user.id,
        order_type=body.type,
        amount=body.amount,
        plan_id=body.plan_id,
        payment_method=body.payment_method,
        db=db,
    )
    return {
        "order_no": order.order_no,
        "amount": float(order.amount),
        "status": order.status,
    }


@router.get("/callback")
async def payment_callback(
    order_no: str = Query(...),
    payment_id: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    try:
        order = await process_payment_callback(order_no, payment_id, db)
        return {"status": "ok", "order_no": order.order_no}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/order/{order_no}")
async def get_order(
    order_no: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Order).where(Order.order_no == order_no))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if order.user_id != user.id and user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return {
        "order_no": order.order_no,
        "type": order.type,
        "amount": float(order.amount),
        "status": order.status,
        "payment_method": order.payment_method,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "created_at": order.created_at.isoformat(),
    }


@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Plan).where(Plan.is_active == True).order_by(Plan.sort_order)
    )
    plans = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "display_name": p.display_name,
            "description": p.description,
            "price": float(p.price),
            "original_price": float(p.original_price) if p.original_price else None,
            "duration": p.duration,
            "features": p.features,
            "quotas": p.quotas,
            "allowed_models": p.allowed_models,
        }
        for p in plans
    ]
