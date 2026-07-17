import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Deposit, Order
from app.models.payment_adapter import PaymentAdapter
from app.models.user import User
from app.services.payment_adapters.registry import (
    build_payment_url,
    get_adapter_by_id,
    get_adapter_runtime,
    process_adapter_callback,
)

MONEY_SCALE = Decimal("0.000001")


def _money(value: Decimal | float | int | str | None) -> Decimal:
    raw = 0 if value is None or value == "" else value
    try:
        return Decimal(str(raw)).quantize(MONEY_SCALE)
    except Exception as exc:
        raise ValueError(f"Invalid money value: {value!r}") from exc


def generate_order_no() -> str:
    return f"MG{int(time.time() * 1000)}{uuid.uuid4().hex[:6].upper()}"


async def create_payment_order(
    user_id: str,
    order_type: str,
    amount: float,
    payment_adapter_id: str,
    payment_method: str | None,
    notify_url: str,
    return_url: str,
    db: AsyncSession,
) -> tuple[Order, str | None]:
    adapter = await get_adapter_by_id(db, payment_adapter_id)
    if not adapter or not adapter.enabled:
        raise ValueError("Payment adapter not found or disabled")
    if not get_adapter_runtime(adapter):
        raise ValueError("Payment adapter is not fully configured")

    order = Order(
        user_id=user_id,
        order_no=generate_order_no(),
        type=order_type,
        amount=_money(amount),
        payment_adapter_id=adapter.id,
        payment_method=payment_method,
        status="PENDING",
    )
    db.add(order)
    await db.flush()

    payment_url = build_payment_url(
        item=adapter,
        order_no=order.order_no,
        amount=_money(amount),
        notify_url=notify_url,
        return_url=return_url,
        payment_channel=payment_method,
    )
    return order, payment_url


async def _mark_order_paid(order: Order, payment_id: str, db: AsyncSession) -> Order:
    if order.status == "PAID":
        return order
    if order.status != "PENDING":
        raise ValueError("Order already processed")

    order.status = "PAID"
    order.payment_id = payment_id
    order.paid_at = datetime.now(timezone.utc)

    result = await db.execute(select(User).where(User.id == order.user_id))
    user = result.scalar_one()

    if order.type == "RECHARGE":
        user.balance = _money(user.balance) + _money(order.amount)
        deposit = Deposit(
            user_id=user.id,
            amount=_money(order.amount),
            status="COMPLETED",
            payment_method=order.payment_method,
            payment_id=payment_id,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(deposit)

    await db.flush()
    return order


async def process_payment_callback(order_no: str, payment_id: str, db: AsyncSession) -> Order:
    result = await db.execute(select(Order).where(Order.order_no == order_no))
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Order not found")
    return await _mark_order_paid(order, payment_id, db)


async def process_epay_callback(
    params: dict[str, str],
    db: AsyncSession,
    *,
    adapter_id: str | None = None,
) -> Order:
    resolved_adapter_id = adapter_id
    if not resolved_adapter_id:
        order_no_hint = str(params.get("out_trade_no") or "").strip()
        if order_no_hint:
            result = await db.execute(select(Order).where(Order.order_no == order_no_hint))
            bound_order = result.scalar_one_or_none()
            if bound_order and bound_order.payment_adapter_id:
                resolved_adapter_id = bound_order.payment_adapter_id

    order_no, payment_id = await process_adapter_callback(
        "epay",
        params,
        db,
        adapter_id=resolved_adapter_id,
    )
    return await process_payment_callback(order_no, payment_id, db)


async def resolve_order_adapter(db: AsyncSession, order: Order) -> PaymentAdapter | None:
    if not order.payment_adapter_id:
        return None
    return await get_adapter_by_id(db, order.payment_adapter_id)