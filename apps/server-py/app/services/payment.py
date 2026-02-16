import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Deposit, Order, Plan, Subscription
from app.models.config import PaymentConfig
from app.models.user import User, UserGroup


def generate_order_no() -> str:
    return f"MG{int(time.time() * 1000)}{uuid.uuid4().hex[:6].upper()}"


async def create_payment_order(
    user_id: str, order_type: str, amount: float, plan_id: str | None, payment_method: str | None, db: AsyncSession
) -> Order:
    order = Order(
        user_id=user_id,
        order_no=generate_order_no(),
        type=order_type,
        plan_id=plan_id,
        amount=Decimal(str(amount)),
        payment_method=payment_method,
        status="PENDING",
    )
    db.add(order)
    await db.flush()
    return order


async def process_payment_callback(order_no: str, payment_id: str, db: AsyncSession) -> Order:
    result = await db.execute(select(Order).where(Order.order_no == order_no))
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Order not found")
    if order.status != "PENDING":
        raise ValueError("Order already processed")

    order.status = "PAID"
    order.payment_id = payment_id
    order.paid_at = datetime.now(timezone.utc)

    result = await db.execute(select(User).where(User.id == order.user_id))
    user = result.scalar_one()

    if order.type == "RECHARGE":
        user.balance += order.amount
        deposit = Deposit(
            user_id=user.id,
            amount=order.amount,
            status="COMPLETED",
            payment_method=order.payment_method,
            payment_id=payment_id,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(deposit)

    elif order.type in ("SUBSCRIPTION", "UPGRADE"):
        if order.plan_id:
            result = await db.execute(select(Plan).where(Plan.id == order.plan_id))
            plan = result.scalar_one_or_none()
            if plan:
                now = datetime.now(timezone.utc)
                subscription = Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    status="ACTIVE",
                    start_at=now,
                    expire_at=now + timedelta(days=plan.duration),
                )
                db.add(subscription)
                if plan.target_group_id:
                    user.group_id = plan.target_group_id

    await db.flush()
    return order
