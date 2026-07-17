import hashlib
import uuid
from decimal import Decimal
from typing import Any
from urllib.parse import unquote_plus, urlencode

EPAY_TYPE = "epay"

KNOWN_CHANNEL_TYPES = ("alipay", "wxpay", "qqpay")


def normalize_payment_types(value: Any) -> list[str]:
    payment_types: list[str] = []
    for item in value if isinstance(value, list) else []:
        payment_type = str(item or "").strip()
        if payment_type and payment_type not in payment_types:
            payment_types.append(payment_type)
    return payment_types


def sign_epay_params(params: dict[str, str], key: str) -> str:
    sorted_params = dict(sorted(params.items()))
    sign_source = unquote_plus(urlencode(sorted_params)) + key
    return hashlib.md5(sign_source.encode("utf-8")).hexdigest()


def parse_epay_config(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    cfg = raw if isinstance(raw, dict) else {}
    url = str(cfg.get("url") or "").strip()
    pid = str(cfg.get("pid") or "").strip()
    key = str(cfg.get("key") or "").strip()
    payment_types = normalize_payment_types(cfg.get("payment_types"))
    notify_url = str(cfg.get("notify_url") or "").strip()
    return_url = str(cfg.get("return_url") or "").strip()
    if not url or not pid or not key:
        return None
    if not payment_types:
        return None
    return {
        "url": url,
        "pid": pid,
        "key": key,
        "payment_types": payment_types,
        "notify_url": notify_url,
        "return_url": return_url,
    }


def validate_epay_config_for_save(
    *,
    enabled: bool,
    config: dict[str, Any],
    existing_key: str = "",
) -> tuple[dict[str, Any], str | None]:
    url = str(config.get("url") or "").strip()
    pid = str(config.get("pid") or "").strip()
    incoming_key = str(config.get("key") or "").strip()
    key = incoming_key or existing_key
    payment_types = normalize_payment_types(config.get("payment_types"))
    notify_url = str(config.get("notify_url") or "").strip()
    return_url = str(config.get("return_url") or "").strip()

    if enabled:
        if not url or not pid or not key:
            return {}, "enabled=true requires url, pid and key"
        if not payment_types:
            return {}, "enabled=true requires at least one payment type"

    stored = {
        "url": url,
        "pid": pid,
        "key": key,
        "payment_types": payment_types or ["alipay"],
        "notify_url": notify_url,
        "return_url": return_url,
    }
    return stored, None


def build_epay_payment_url(
    *,
    runtime: dict[str, Any],
    order_no: str,
    amount: Decimal,
    notify_url: str,
    return_url: str,
    payment_channel: str,
) -> str:
    params: dict[str, str] = {
        "money": str(amount.quantize(Decimal("0.01"))),
        "name": order_no,
        "notify_url": runtime["notify_url"] or notify_url,
        "return_url": runtime["return_url"] or return_url,
        "out_trade_no": order_no,
        "pid": runtime["pid"],
    }
    channel = (payment_channel or runtime["payment_types"][0]).strip()
    if channel:
        params["type"] = channel
    params["sign"] = sign_epay_params(params, runtime["key"])
    params["sign_type"] = "MD5"
    return f"{runtime['url'].rstrip('/')}/submit.php?{urlencode(params)}"


def verify_epay_callback(params: dict[str, str], runtime: dict[str, Any]) -> tuple[str, str]:
    sign = str(params.get("sign") or "").strip().lower()
    if not sign:
        raise ValueError("Missing sign")

    unsigned_params = {
        str(k): str(v)
        for k, v in params.items()
        if k not in {"sign", "sign_type"} and v is not None
    }
    expected_sign = sign_epay_params(unsigned_params, runtime["key"])
    if sign != expected_sign:
        raise ValueError("Invalid sign")

    order_no = str(unsigned_params.get("out_trade_no") or "").strip()
    if not order_no:
        raise ValueError("Missing out_trade_no")

    trade_status = str(unsigned_params.get("trade_status") or "").strip().upper()
    if trade_status and trade_status not in {"TRADE_SUCCESS", "TRADE_FINISHED", "SUCCESS"}:
        raise ValueError("Payment not successful")

    payment_id = str(unsigned_params.get("trade_no") or "").strip() or f"EPAY-{uuid.uuid4().hex[:12]}"
    return order_no, payment_id


def serialize_epay_admin_config(config: dict[str, Any] | None, *, enabled: bool) -> dict[str, Any]:
    cfg = config if isinstance(config, dict) else {}
    secret_key = str(cfg.get("key") or "")
    return {
        "url": str(cfg.get("url") or ""),
        "pid": str(cfg.get("pid") or ""),
        "key": "",
        "has_key": bool(secret_key),
        "payment_types": normalize_payment_types(cfg.get("payment_types")) or ["alipay"],
        "notify_url": str(cfg.get("notify_url") or ""),
        "return_url": str(cfg.get("return_url") or ""),
        "enabled_fields_ok": parse_epay_config(cfg) is not None,
    }