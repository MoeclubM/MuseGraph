import hashlib
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import unquote_plus, urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Deposit, Order
from app.models.config import PaymentConfig
from app.models.user import User

EPAY_CONFIG_TYPE = "epay"
MONEY_SCALE = Decimal("0.000001")


def _money(value: Decimal | float | int | str | None) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(MONEY_SCALE)
    except Exception:
        return Decimal("0").quantize(MONEY_SCALE)


def generate_order_no() -> str:
    return f"MG{int(time.time() * 1000)}{uuid.uuid4().hex[:6].upper()}"


def _sign_epay_params(params: dict[str, str], key: str) -> str:
    sorted_params = dict(sorted(params.items()))
    sign_source = unquote_plus(urlencode(sorted_params)) + key
    return hashlib.md5(sign_source.encode("utf-8")).hexdigest()


def _build_epay_url(
    *,
    gateway_url: str,
    pid: str,
    key: str,
    order_no: str,
    amount: Decimal,
    notify_url: str,
    return_url: str,
    payment_type: str,
) -> str:
    params: dict[str, str] = {
        "money": str(amount.quantize(Decimal("0.01"))),
        "name": order_no,
        "notify_url": notify_url,
        "return_url": return_url,
        "out_trade_no": order_no,
        "pid": pid,
    }
    if payment_type:
        params["type"] = payment_type
    params["sign"] = _sign_epay_params(params, key)
    params["sign_type"] = "MD5"
    return f"{gateway_url.rstrip('/')}/submit.php?{urlencode(params)}"


async def get_active_epay_config(db: AsyncSession) -> dict[str, str] | None:
    result = await db.execute(
        select(PaymentConfig).where(
            PaymentConfig.type == EPAY_CONFIG_TYPE,
            PaymentConfig.is_active == True,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        return None
    cfg = item.config if isinstance(item.config, dict) else {}
    url = str(cfg.get("url") or "").strip()
    pid = str(cfg.get("pid") or "").strip()
    key = str(cfg.get("key") or "").strip()
    payment_type = str(cfg.get("payment_type") or "alipay").strip() or "alipay"
    notify_url = str(cfg.get("notify_url") or "").strip()
    return_url = str(cfg.get("return_url") or "").strip()
    if not url or not pid or not key:
        return None
    return {
        "url": url,
        "pid": pid,
        "key": key,
        "payment_type": payment_type,
        "notify_url": notify_url,
        "return_url": return_url,
    }


async def create_payment_order(
    user_id: str,
    order_type: str,
    amount: float,
    payment_method: str | None,
    notify_url: str,
    return_url: str,
    db: AsyncSession,
) -> tuple[Order, str | None]:
    order = Order(
        user_id=user_id,
        order_no=generate_order_no(),
        type=order_type,
        amount=_money(amount),
        payment_method=payment_method,
        status="PENDING",
    )
    db.add(order)
    await db.flush()

    payment_url: str | None = None
    epay = await get_active_epay_config(db)
    if epay:
        payment_url = _build_epay_url(
            gateway_url=epay["url"],
            pid=epay["pid"],
            key=epay["key"],
            order_no=order.order_no,
            amount=_money(amount),
            notify_url=epay["notify_url"] or notify_url,
            return_url=epay["return_url"] or return_url,
            payment_type=(payment_method or epay["payment_type"]).strip() or epay["payment_type"],
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


async def process_epay_callback(params: dict[str, str], db: AsyncSession) -> Order:
    config = await get_active_epay_config(db)
    if not config:
        raise ValueError("EPay is not configured")

    sign = str(params.get("sign") or "").strip().lower()
    if not sign:
        raise ValueError("Missing sign")

    unsigned_params = {
        str(k): str(v)
        for k, v in params.items()
        if k not in {"sign", "sign_type"} and v is not None
    }
    expected_sign = _sign_epay_params(unsigned_params, config["key"])
    if sign != expected_sign:
        raise ValueError("Invalid sign")

    order_no = str(unsigned_params.get("out_trade_no") or "").strip()
    if not order_no:
        raise ValueError("Missing out_trade_no")

    trade_status = str(unsigned_params.get("trade_status") or "").strip().upper()
    if trade_status and trade_status not in {"TRADE_SUCCESS", "TRADE_FINISHED", "SUCCESS"}:
        raise ValueError("Payment not successful")

    payment_id = str(unsigned_params.get("trade_no") or "").strip() or f"EPAY-{uuid.uuid4().hex[:12]}"
    return await process_payment_callback(order_no, payment_id, db)
