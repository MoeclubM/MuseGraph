from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_adapter import PaymentAdapter
from app.services.payment_adapters import epay as epay_adapter

ADAPTER_TYPES: dict[str, dict[str, str]] = {
    epay_adapter.EPAY_TYPE: {
        "label": "易支付 (EPay)",
        "description": "MD5 签名的易支付网关，支持 alipay / wxpay / qqpay 等渠道",
    },
}


def _serialize_public_adapter(item: PaymentAdapter, runtime: dict[str, Any]) -> dict[str, Any]:
    channels = [
        {"id": ch, "label": ch}
        for ch in runtime.get("payment_types", [])
    ]
    return {
        "id": item.id,
        "type": item.adapter_type,
        "display_name": item.display_name,
        "sort_order": item.sort_order,
        "channels": channels,
    }


async def list_enabled_adapters(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(
        select(PaymentAdapter)
        .where(PaymentAdapter.enabled == True)  # noqa: E712
        .order_by(PaymentAdapter.sort_order.asc(), PaymentAdapter.created_at.asc())
    )
    items = result.scalars().all()
    public: list[dict[str, Any]] = []
    for item in items:
        runtime = get_adapter_runtime(item)
        if runtime:
            public.append(_serialize_public_adapter(item, runtime))
    return public


def get_adapter_runtime(item: PaymentAdapter) -> dict[str, Any] | None:
    cfg = item.config if isinstance(item.config, dict) else {}
    if item.adapter_type == epay_adapter.EPAY_TYPE:
        return epay_adapter.parse_epay_config(cfg)
    return None


async def get_adapter_by_id(db: AsyncSession, adapter_id: str) -> PaymentAdapter | None:
    result = await db.execute(select(PaymentAdapter).where(PaymentAdapter.id == adapter_id))
    return result.scalar_one_or_none()


def validate_adapter_config(
    adapter_type: str,
    *,
    enabled: bool,
    config: dict[str, Any],
    existing_key: str = "",
) -> tuple[dict[str, Any], str | None]:
    if adapter_type not in ADAPTER_TYPES:
        return {}, f"Unsupported adapter type: {adapter_type}"
    if adapter_type == epay_adapter.EPAY_TYPE:
        return epay_adapter.validate_epay_config_for_save(
            enabled=enabled,
            config=config,
            existing_key=existing_key,
        )
    return {}, f"Unsupported adapter type: {adapter_type}"


def serialize_adapter_admin(item: PaymentAdapter) -> dict[str, Any]:
    cfg = item.config if isinstance(item.config, dict) else {}
    type_meta = ADAPTER_TYPES.get(item.adapter_type, {"label": item.adapter_type, "description": ""})
    payload: dict[str, Any] = {
        "id": item.id,
        "adapter_type": item.adapter_type,
        "adapter_type_label": type_meta["label"],
        "display_name": item.display_name,
        "enabled": bool(item.enabled),
        "sort_order": int(item.sort_order or 0),
        "config": {},
        "valid": get_adapter_runtime(item) is not None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
    if item.adapter_type == epay_adapter.EPAY_TYPE:
        payload["config"] = epay_adapter.serialize_epay_admin_config(cfg, enabled=item.enabled)
    else:
        payload["config"] = cfg
    return payload


def build_payment_url(
    *,
    item: PaymentAdapter,
    order_no: str,
    amount: Decimal,
    notify_url: str,
    return_url: str,
    payment_channel: str | None,
) -> str | None:
    runtime = get_adapter_runtime(item)
    if not runtime:
        return None
    if item.adapter_type == epay_adapter.EPAY_TYPE:
        channel = (payment_channel or "").strip()
        if channel and channel not in runtime["payment_types"]:
            raise ValueError(f"Payment channel {channel!r} is not enabled for this adapter")
        return epay_adapter.build_epay_payment_url(
            runtime=runtime,
            order_no=order_no,
            amount=amount,
            notify_url=notify_url,
            return_url=return_url,
            payment_channel=channel or runtime["payment_types"][0],
        )
    return None


async def process_adapter_callback(
    adapter_type: str,
    params: dict[str, str],
    db: AsyncSession,
    *,
    adapter_id: str | None = None,
) -> tuple[str, str]:
    """Verify callback and return (order_no, payment_id)."""
    if adapter_type != epay_adapter.EPAY_TYPE:
        raise ValueError(f"Unsupported callback type: {adapter_type}")

    runtime: dict[str, Any] | None = None
    if adapter_id:
        item = await get_adapter_by_id(db, adapter_id)
        if not item or not item.enabled:
            raise ValueError("Payment adapter not found or disabled")
        runtime = get_adapter_runtime(item)
    else:
        result = await db.execute(
            select(PaymentAdapter).where(
                PaymentAdapter.adapter_type == epay_adapter.EPAY_TYPE,
                PaymentAdapter.enabled == True,  # noqa: E712
            )
        )
        for candidate in result.scalars().all():
            candidate_runtime = get_adapter_runtime(candidate)
            if not candidate_runtime:
                continue
            try:
                return epay_adapter.verify_epay_callback(params, candidate_runtime)
            except ValueError as exc:
                if str(exc) == "Invalid sign":
                    continue
                raise

    if not runtime:
        raise ValueError("EPay is not configured")
    return epay_adapter.verify_epay_callback(params, runtime)