"""Tests for payment service functions."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_adapter():
    return SimpleNamespace(
        id=str(uuid.uuid4()),
        adapter_type="epay",
        display_name="EPay",
        enabled=True,
        sort_order=0,
        config={
            "url": "https://pay.example.com",
            "pid": "1001",
            "key": "secret_key",
            "payment_types": ["alipay"],
            "notify_url": "https://example.com/notify",
            "return_url": "https://example.com/return",
        },
    )


class TestPaymentServiceFunctions:
    def test_generate_order_no(self):
        from app.services.payment import generate_order_no

        order_no = generate_order_no()
        assert order_no.startswith("MG")
        assert len(order_no) > 10

    def test_sign_epay_params(self):
        from app.services.payment_adapters.epay import sign_epay_params

        params = {
            "pid": "1001",
            "type": "alipay",
            "out_trade_no": "ORD123",
            "notify_url": "https://example.com/notify",
            "return_url": "https://example.com/return",
            "name": "Test Order",
            "money": "100.00",
        }
        sign = sign_epay_params(params, "secret_key")
        assert sign is not None
        assert len(sign) == 32

    def test_build_epay_url(self):
        from app.services.payment_adapters.epay import build_epay_payment_url

        url = build_epay_payment_url(
            runtime={
                "url": "https://pay.example.com",
                "pid": "1001",
                "key": "secret_key",
                "payment_types": ["alipay"],
                "notify_url": "https://example.com/notify",
                "return_url": "https://example.com/return",
            },
            order_no="ORD123",
            amount=Decimal("100.00"),
            notify_url="https://example.com/notify",
            return_url="https://example.com/return",
            payment_channel="alipay",
        )

        assert "https://pay.example.com/submit.php" in url
        assert "pid=1001" in url
        assert "out_trade_no=ORD123" in url
        assert "sign=" in url
        assert "sign_type=MD5" in url

    @pytest.mark.asyncio
    async def test_create_payment_order(self):
        from app.services.payment import create_payment_order

        mock_db = _mock_db()
        adapter = _make_adapter()

        with patch("app.services.payment.get_adapter_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = adapter
            order, payment_url = await create_payment_order(
                user_id="user-1",
                order_type="RECHARGE",
                amount=100.0,
                payment_adapter_id=adapter.id,
                payment_method="alipay",
                notify_url="https://example.com/notify",
                return_url="https://example.com/return",
                db=mock_db,
            )

        assert order is not None
        assert order.order_no is not None
        assert payment_url is not None

    @pytest.mark.asyncio
    async def test_create_payment_order_missing_adapter(self):
        from app.services.payment import create_payment_order

        mock_db = _mock_db()

        with patch("app.services.payment.get_adapter_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            with pytest.raises(ValueError, match="not found or disabled"):
                await create_payment_order(
                    user_id="user-1",
                    order_type="RECHARGE",
                    amount=100.0,
                    payment_adapter_id=str(uuid.uuid4()),
                    payment_method=None,
                    notify_url="https://example.com/notify",
                    return_url="https://example.com/return",
                    db=mock_db,
                )

    @pytest.mark.asyncio
    async def test_mark_order_paid_recharge(self):
        from app.services.payment import _mark_order_paid

        mock_db = _mock_db()
        order = SimpleNamespace(
            id="order-1",
            order_no="ORD123",
            user_id="user-1",
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PENDING",
            payment_id=None,
            paid_at=None,
            payment_method="alipay",
        )
        user = SimpleNamespace(id="user-1", balance=Decimal("0.00"))
        mock_user_result = MagicMock()
        mock_user_result.scalar_one.return_value = user
        mock_db.execute.return_value = mock_user_result

        result = await _mark_order_paid(order, "PAYMENT-123", mock_db)

        assert result.status == "PAID"
        assert user.balance == Decimal("100.00")
        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_process_epay_callback_valid(self):
        from app.services.payment import process_epay_callback
        from app.services.payment_adapters.epay import sign_epay_params

        mock_db = _mock_db()
        adapter = _make_adapter()
        params = {
            "pid": "1001",
            "trade_no": "EPAY123",
            "out_trade_no": "ORD123",
            "type": "alipay",
            "money": "100.00",
            "trade_status": "TRADE_SUCCESS",
        }
        params["sign"] = sign_epay_params(params, "secret_key")
        params["sign_type"] = "MD5"

        order = SimpleNamespace(
            id="order-1",
            order_no="ORD123",
            user_id="user-1",
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PENDING",
            payment_id=None,
            paid_at=None,
            payment_method="alipay",
            payment_adapter_id=adapter.id,
        )
        user = SimpleNamespace(id="user-1", balance=Decimal("0.00"))

        mock_order_lookup = MagicMock()
        mock_order_lookup.scalar_one_or_none.return_value = order
        mock_order_fetch = MagicMock()
        mock_order_fetch.scalar_one_or_none.return_value = order
        mock_user_result = MagicMock()
        mock_user_result.scalar_one.return_value = user

        with patch("app.services.payment_adapters.registry.get_adapter_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = adapter
            mock_db.execute.side_effect = [mock_order_lookup, mock_order_fetch, mock_user_result]
            result = await process_epay_callback(params, mock_db)

        assert result is not None
        assert result.status == "PAID"
