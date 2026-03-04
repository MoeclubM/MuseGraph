from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import PlainTextResponse

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.billing import Order
from app.models.user import User
from app.services.payment import create_payment_order, process_epay_callback, process_payment_callback

router = APIRouter()


class CreateOrderRequest(BaseModel):
    type: str = "RECHARGE"
    amount: float
    payment_method: Optional[str] = None


@router.post("/create")
async def create_order(
    body: CreateOrderRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.type != "RECHARGE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only RECHARGE orders are supported")

    callback_url = str(request.url_for("payment_callback_epay"))
    return_url = f"{settings.APP_URL.rstrip('/')}/recharge"
    order, payment_url = await create_payment_order(
        user_id=user.id,
        order_type=body.type,
        amount=body.amount,
        payment_method=body.payment_method,
        notify_url=callback_url,
        return_url=return_url,
        db=db,
    )
    return {
        "order_no": order.order_no,
        "amount": float(order.amount),
        "status": order.status,
        "payment_url": payment_url,
    }


def _serialize_order(order: Order) -> dict:
    return {
        "order_no": order.order_no,
        "type": order.type,
        "amount": float(order.amount),
        "status": order.status,
        "payment_method": order.payment_method,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "created_at": order.created_at.isoformat(),
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


@router.api_route("/callback/epay", methods=["GET", "POST"], name="payment_callback_epay")
async def payment_callback_epay(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        if request.method.upper() == "POST":
            form = await request.form()
            params = {str(k): str(v) for k, v in form.items()}
        else:
            params = {str(k): str(v) for k, v in request.query_params.items()}
        await process_epay_callback(params, db)
        return PlainTextResponse("success")
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
    if order.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return _serialize_order(order)


@router.get("/orders")
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    user_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Order).where(Order.type == "RECHARGE")
    if user.is_admin and user_id:
        query = query.where(Order.user_id == user_id)
    elif not user.is_admin:
        query = query.where(Order.user_id == user.id)

    if status_filter:
        query = query.where(Order.status == str(status_filter).strip().upper())

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    orders = result.scalars().all()
    return {
        "orders": [_serialize_order(order) for order in orders],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
