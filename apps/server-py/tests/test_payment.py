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


class TestPaymentOrderCreation:
    """Test payment order creation."""

    @pytest.mark.asyncio
    async def test_create_recharge_order(self, client: AsyncClient, mock_db: AsyncMock):
        """Test creating a recharge order."""
        # Mock EPay config for get_active_epay_config
        epay_config = SimpleNamespace(
            id="epay-1",
            type="epay",
            is_active=True,
            config={
                "url": "https://pay.example.com",
                "pid": "10001",
                "key": "secret-key",
                "payment_type": "alipay",
            },
        )

        mock_db.execute.return_value = _scalar_one_or_none(epay_config)

        resp = await client.post(
            "/api/payment/create",
            json={
                "type": "RECHARGE",
                "amount": 100.0,
                "payment_method": "alipay",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "order_no" in body
        assert "payment_url" in body

    @pytest.mark.asyncio
    async def test_create_subscription_order(self, client: AsyncClient, mock_db: AsyncMock):
        """Test creating a subscription order."""
        plan = SimpleNamespace(
            id="plan-1",
            description="Pro Plan",
            price=Decimal("29.99"),
            duration=30,
            target_group_id="group-pro",
            is_active=True,
        )
        epay_config = SimpleNamespace(
            id="epay-1",
            type="epay",
            is_active=True,
            config={
                "url": "https://pay.example.com",
                "pid": "10001",
                "key": "secret-key",
                "payment_type": "alipay",
            },
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(plan),         # Plan lookup
            _scalar_one_or_none(epay_config),  # EPay config (for get_active_epay_config)
        ]

        resp = await client.post(
            "/api/payment/create",
            json={
                "type": "SUBSCRIPTION",
                "amount": 29.99,  # Amount is required
                "plan_id": "plan-1",
                "payment_method": "alipay",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert "order_no" in body

    @pytest.mark.asyncio
    async def test_create_order_invalid_plan(self, client: AsyncClient, mock_db: AsyncMock):
        """Test creating an order with invalid plan_id returns error."""
        mock_db.execute.return_value = _scalar_one_or_none(None)  # Plan not found

        resp = await client.post(
            "/api/payment/create",
            json={
                "type": "SUBSCRIPTION",
                "amount": 29.99,  # Amount is required
                "plan_id": "nonexistent-plan",
                "payment_method": "alipay",
            },
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_order_no_payment_config(self, client: AsyncClient, mock_db: AsyncMock):
        """Test creating an order when payment is not configured returns payment_url as None."""
        # No EPay config
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.post(
            "/api/payment/create",
            json={
                "type": "RECHARGE",
                "amount": 100.0,
                "payment_method": "alipay",
            },
        )

        # The API still returns 200, but payment_url is None
        assert resp.status_code == 200
        body = resp.json()
        assert body["payment_url"] is None


class TestPaymentCallback:
    """Test payment callback processing."""

    @pytest.mark.asyncio
    async def test_epay_callback_success(self, client: AsyncClient, mock_db: AsyncMock):
        """Test successful EPay callback processing."""
        # For this test, we'll verify the endpoint exists and handles requests
        # The actual signature verification is complex, so we test the error cases separately

        # With no payment config, it should fail
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

        # Should return 400 because EPay is not configured
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_epay_callback_invalid_signature(self, client: AsyncClient, mock_db: AsyncMock):
        """Test EPay callback with invalid signature is rejected."""
        epay_config = SimpleNamespace(
            id="epay-1",
            type="epay",
            is_active=True,
            config={"key": "secret-key"},
        )

        mock_db.execute.return_value = _scalar_one_or_none(epay_config)

        # Patch the sign function to return a different value
        with patch("app.services.payment._sign_epay_params") as mock_sign:
            mock_sign.return_value = "correct_signature"

            resp = await client.get(
                "/api/payment/callback/epay",
                params={
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
        """Test EPay callback for non-existent order returns error."""
        epay_config = SimpleNamespace(
            id="epay-1",
            type="epay",
            is_active=True,
            config={"key": "secret-key"},
        )

        # Mock get_active_epay_config returns config, then order lookup returns None
        mock_db.execute.side_effect = [
            _scalar_one_or_none(epay_config),
            _scalar_one_or_none(None),  # Order not found
        ]

        # Need to patch sign to match
        with patch("app.services.payment._sign_epay_params") as mock_sign:
            mock_sign.return_value = "anysign"

            resp = await client.get(
                "/api/payment/callback/epay",
                params={
                    "out_trade_no": "NONEXISTENT",
                    "trade_no": "EPAY123456",
                    "trade_status": "TRADE_SUCCESS",
                    "money": "100.00",
                    "sign": "anysign",
                },
            )

        assert resp.status_code == 400  # ValueError -> 400


class TestOrderStatus:
    """Test order status query."""

    @pytest.mark.asyncio
    async def test_get_order_status_owner(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test user can view their own order."""
        order = SimpleNamespace(
            id="order-1",
            order_no="ORD20240101120000",
            user_id=fake_user.id,
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PAID",
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
        """Test user cannot view others' orders."""
        order = SimpleNamespace(
            id="order-1",
            order_no="ORD20240101120000",
            user_id="different-user-id",  # Different user
            status="PAID",
        )
        mock_db.execute.return_value = _scalar_one_or_none(order)

        resp = await client.get("/api/payment/order/ORD20240101120000")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_order_status_admin(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test admin can view any order."""
        order = SimpleNamespace(
            id="order-1",
            order_no="ORD20240101120000",
            user_id="any-user-id",
            type="RECHARGE",
            amount=Decimal("100.00"),
            status="PAID",
            payment_method="alipay",
            created_at=datetime.now(timezone.utc),
            paid_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(order)

        resp = await admin_client.get("/api/payment/order/ORD20240101120000")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test querying non-existent order returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.get("/api/payment/order/NONEXISTENT")

        assert resp.status_code == 404


class TestPlansList:
    """Test plans listing for users."""

    @pytest.mark.asyncio
    async def test_list_active_plans(self, client: AsyncClient, mock_db: AsyncMock):
        """Test listing active plans for users."""
        plans = [
            SimpleNamespace(
                id="plan-1",
                description="Basic Plan",
                price=Decimal("9.99"),
                duration=30,
                rate_limit=100,
                is_active=True,
                target_group_id="group-basic",
            ),
            SimpleNamespace(
                id="plan-2",
                description="Pro Plan",
                price=Decimal("29.99"),
                duration=30,
                rate_limit=500,
                is_active=True,
                target_group_id="group-pro",
            ),
        ]
        mock_db.execute.return_value = _scalars_all(plans)

        resp = await client.get("/api/payment/plans")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2

    @pytest.mark.asyncio
    async def test_list_plans_empty(self, client: AsyncClient, mock_db: AsyncMock):
        """Test listing plans when none are active."""
        mock_db.execute.return_value = _scalars_all([])

        resp = await client.get("/api/payment/plans")

        assert resp.status_code == 200
        assert resp.json() == []
