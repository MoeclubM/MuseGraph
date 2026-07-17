"""Tests for Payment operations: order creation, callbacks, EPay integration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all(items: list):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _make_epay_adapter(*, enabled: bool = True, adapter_id: str | None = None):
    return SimpleNamespace(
        id=adapter_id or str(uuid.uuid4()),
        adapter_type="epay",
        display_name="Main EPay",
        enabled=enabled,
        sort_order=0,
        config={
            "url": "https://pay.example.com",
            "pid": "10001",
            "key": "secret-key",
            "payment_types": ["alipay", "wxpay"],
            "notify_url": "",
            "return_url": "",
        },
    )


class TestPaymentOrderCreation:
    @pytest.mark.asyncio
    async def test_create_recharge_order(self, client: AsyncClient, mock_db: AsyncMock):
        adapter = _make_epay_adapter()
        mock_db.execute.return_value = _scalar_one_or_none(adapter)

        resp = await client.post(
            "/api/payment/create",
            json={
                "type": "RECHARGE",
                "amount": 100.0,
                "payment_adapter_id": adapter.id,
                "payment_method": "alipay",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "order_no" in body
        assert "payment_url" in body
        assert body["payment_url"] is not None

    @pytest.mark.asyncio
    async def test_create_non_recharge_order_rejected(self, client: AsyncClient, mock_db: AsyncMock):
        resp = await client.post(
            "/api/payment/create",
            json={
                "type": "SUBSCRIPTION",
                "amount": 29.99,
                "payment_adapter_id": str(uuid.uuid4()),
                "payment_method": "alipay",
            },
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_order_missing_adapter(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.post(
            "/api/payment/create",
            json={
                "type": "RECHARGE",
                "amount": 100.0,
                "payment_adapter_id": str(uuid.uuid4()),
                "payment_method": "alipay",
            },
        )

        assert resp.status_code == 400


class TestPaymentMethods:
    @pytest.mark.asyncio
    async def test_list_payment_methods_only_enabled_valid(self, client: AsyncClient, mock_db: AsyncMock):
        valid = _make_epay_adapter()
        invalid = _make_epay_adapter(adapter_id=str(uuid.uuid4()))
        invalid.config = {"url": "", "pid": "", "key": ""}
        mock_db.execute.return_value = _scalars_all([valid, invalid])

        resp = await client.get("/api/payment/methods")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["adapters"]) == 1
        assert body["adapters"][0]["id"] == valid.id
        assert body["adapters"][0]["channels"] == [
            {"id": "alipay", "label": "alipay"},
            {"id": "wxpay", "label": "wxpay"},
        ]


class TestPaymentCallback:
    @pytest.mark.asyncio
    async def test_epay_callback_success(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.get(
            "/api/payment/callback/epay",
            params={
                "out_trade_no": "ORD20240101120000",
                "trade_no": "EPAY123456",
                "trade_status": "TRADE_SUCCESS",
                "money": "100.00",
                "sign": "anysign",
                "sign_type": "MD5",
            },
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_epay_callback_invalid_signature(self, client: AsyncClient, mock_db: AsyncMock):
        adapter = _make_epay_adapter()
        mock_db.execute.return_value = _scalar_one_or_none(adapter)

        with patch("app.services.payment_adapters.epay.sign_epay_params") as mock_sign:
            mock_sign.return_value = "correct_signature"

            resp = await client.get(
                "/api/payment/callback/epay",
                params={
                    "adapter_id": adapter.id,
                    "out_trade_no": "ORD20240101120000",
                    "trade_no": "EPAY123456",
                    "trade_status": "TRADE_SUCCESS",
                    "money": "100.00",
                    "sign": "wrong_signature",
                    "sign_type": "MD5",
                },
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_epay_callback_order_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        adapter = _make_epay_adapter()

        mock_db.execute.side_effect = [
            _scalar_one_or_none(adapter),
            _scalar_one_or_none(None),
        ]

        with patch("app.services.payment_adapters.epay.sign_epay_params") as mock_sign:
            mock_sign.return_value = "anysign"

            resp = await client.get(
                "/api/payment/callback/epay",
                params={
                    "adapter_id": adapter.id,
                    "out_trade_no": "NONEXISTENT",
                    "trade_no": "EPAY123456",
                    "trade_status": "TRADE_SUCCESS",
                    "money": "100.00",
                    "sign": "anysign",
                },
            )

        assert resp.status_code == 400


class TestOrderStatus:
    @pytest.mark.asyncio
    async def test_get_order_status_owner(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        order = SimpleNamespace(
            id="order-1",
            order_no="ORD20240101120000",
            user_id=fake_user.id,
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PAID",
            payment_adapter_id="adapter-1",
            payment_method="alipay",
            created_at=datetime.now(timezone.utc),
            paid_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(order)

        resp = await client.get("/api/payment/order/ORD20240101120000")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "PAID"

    @pytest.mark.asyncio
    async def test_get_order_status_not_owner(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        order = SimpleNamespace(
            id="order-1",
            order_no="ORD20240101120000",
            user_id="different-user-id",
            status="PAID",
        )
        mock_db.execute.return_value = _scalar_one_or_none(order)

        resp = await client.get("/api/payment/order/ORD20240101120000")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_order_status_admin(self, admin_client: AsyncClient, mock_db: AsyncMock):
        order = SimpleNamespace(
            id="order-1",
            order_no="ORD20240101120000",
            user_id="any-user-id",
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PAID",
            payment_adapter_id="adapter-1",
            payment_method="alipay",
            created_at=datetime.now(timezone.utc),
            paid_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(order)

        resp = await admin_client.get("/api/payment/order/ORD20240101120000")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.get("/api/payment/order/NONEXISTENT")

        assert resp.status_code == 404


class TestOrdersList:
    @pytest.mark.asyncio
    async def test_list_orders_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        order = SimpleNamespace(
            order_no="ORD-LIST-1",
            user_id=fake_user.id,
            type="RECHARGE",
            amount=Decimal("8.88"),
            status="PENDING",
            payment_adapter_id="adapter-1",
            payment_method="alipay",
            paid_at=None,
            created_at=datetime.now(timezone.utc),
        )
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = _scalars_all([order])
        mock_db.execute.side_effect = [count_result, list_result]

        resp = await client.get("/api/payment/orders")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["orders"][0]["order_no"] == "ORD-LIST-1"
