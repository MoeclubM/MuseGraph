"""Tests for payment router - covers missing lines 65-69, 79-80, 84."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


def _get_endpoint_globals(app, endpoint_name: str) -> dict:
    """Get the __globals__ dict of a named endpoint to patch its imports."""
    for route in app.routes:
        if hasattr(route, "endpoint") and getattr(route, "name", "") == endpoint_name:
            return route.endpoint.__globals__
        if hasattr(route, "routes"):
            for sub in route.routes:
                if hasattr(sub, "endpoint") and getattr(sub, "name", "") == endpoint_name:
                    return sub.endpoint.__globals__
    raise RuntimeError(f"Endpoint {endpoint_name!r} not found")


@pytest.fixture()
def _epay_globals():
    """Return the endpoint globals for payment_callback_epay."""
    from tests.conftest import app
    return _get_endpoint_globals(app, "payment_callback_epay")


@pytest.fixture()
def _callback_globals():
    """Return the endpoint globals for payment_callback."""
    from tests.conftest import app
    return _get_endpoint_globals(app, "payment_callback")


class TestEpayCallbackPost:
    """Cover lines 79-80: POST form-based epay callback."""

    @pytest.mark.asyncio
    async def test_epay_post_callback_success(
        self, client: AsyncClient, mock_db: AsyncMock, _epay_globals: dict
    ):
        """POST /api/payment/callback/epay with form data."""
        mock_cb = AsyncMock(return_value=None)
        orig = _epay_globals["process_epay_callback"]
        _epay_globals["process_epay_callback"] = mock_cb
        try:
            resp = await client.post(
                "/api/payment/callback/epay",
                data={
                    "out_trade_no": "ORD001",
                    "trade_no": "T123",
                    "trade_status": "TRADE_SUCCESS",
                    "money": "50.00",
                    "sign": "abc",
                },
            )
        finally:
            _epay_globals["process_epay_callback"] = orig
        assert resp.status_code == 200
        assert resp.text == "success"
        mock_cb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_epay_get_callback_success(
        self, client: AsyncClient, mock_db: AsyncMock, _epay_globals: dict
    ):
        """GET /api/payment/callback/epay with query params."""
        mock_cb = AsyncMock(return_value=None)
        orig = _epay_globals["process_epay_callback"]
        _epay_globals["process_epay_callback"] = mock_cb
        try:
            resp = await client.get(
                "/api/payment/callback/epay",
                params={"out_trade_no": "ORD002", "sign": "xyz"},
            )
        finally:
            _epay_globals["process_epay_callback"] = orig

        assert resp.status_code == 200
        assert resp.text == "success"
        call_params = mock_cb.call_args[0][0]
        assert call_params["out_trade_no"] == "ORD002"


class TestEpayCallbackErrors:
    """Cover line 84: epay callback ValueError path."""

    @pytest.mark.asyncio
    async def test_epay_get_value_error(
        self, client: AsyncClient, mock_db: AsyncMock, _epay_globals: dict
    ):
        mock_cb = AsyncMock(side_effect=ValueError("Invalid signature"))
        orig = _epay_globals["process_epay_callback"]
        _epay_globals["process_epay_callback"] = mock_cb
        try:
            resp = await client.get(
                "/api/payment/callback/epay",
                params={"out_trade_no": "ORD003", "sign": "bad"},
            )
        finally:
            _epay_globals["process_epay_callback"] = orig

        assert resp.status_code == 400
        assert "Invalid signature" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_epay_post_value_error(
        self, client: AsyncClient, mock_db: AsyncMock, _epay_globals: dict
    ):
        mock_cb = AsyncMock(side_effect=ValueError("EPay not configured"))
        orig = _epay_globals["process_epay_callback"]
        _epay_globals["process_epay_callback"] = mock_cb
        try:
            resp = await client.post(
                "/api/payment/callback/epay",
                data={"out_trade_no": "ORD004", "sign": "bad"},
            )
        finally:
            _epay_globals["process_epay_callback"] = orig

        assert resp.status_code == 400
        assert "EPay not configured" in resp.json()["detail"]


class TestGenericCallbackError:
    """Cover lines 65-69: GET /api/payment/callback ValueError path."""

    @pytest.mark.asyncio
    async def test_callback_value_error(
        self, client: AsyncClient, mock_db: AsyncMock, _callback_globals: dict
    ):
        mock_cb = AsyncMock(side_effect=ValueError("Order not found"))
        orig = _callback_globals["process_payment_callback"]
        _callback_globals["process_payment_callback"] = mock_cb
        try:
            resp = await client.get(
                "/api/payment/callback",
                params={"order_no": "ORD005", "payment_id": "PAY999"},
            )
        finally:
            _callback_globals["process_payment_callback"] = orig

        assert resp.status_code == 400
        assert "Order not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_callback_success(
        self, client: AsyncClient, mock_db: AsyncMock, _callback_globals: dict
    ):
        fake_order = SimpleNamespace(order_no="ORD006")
        mock_cb = AsyncMock(return_value=fake_order)
        orig = _callback_globals["process_payment_callback"]
        _callback_globals["process_payment_callback"] = mock_cb
        try:
            resp = await client.get(
                "/api/payment/callback",
                params={"order_no": "ORD006", "payment_id": "PAY100"},
            )
        finally:
            _callback_globals["process_payment_callback"] = orig

        assert resp.status_code == 200
        assert resp.json()["order_no"] == "ORD006"


class TestOrderEndpoint:
    """Cover GET /api/payment/order/{order_no}: success, not found, forbidden."""

    @pytest.mark.asyncio
    async def test_get_order_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        order = SimpleNamespace(
            order_no="ORD100",
            user_id=fake_user.id,
            type="RECHARGE",
            amount=Decimal("50.00"),
            status="PAID",
            payment_method="alipay",
            created_at=datetime.now(timezone.utc),
            paid_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(order)
        resp = await client.get("/api/payment/order/ORD100")
        assert resp.status_code == 200
        assert resp.json()["order_no"] == "ORD100"
        assert resp.json()["status"] == "PAID"

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)
        resp = await client.get("/api/payment/order/MISSING")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_order_forbidden(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        order = SimpleNamespace(
            order_no="ORD200",
            user_id="other-user-id",
            status="PAID",
        )
        mock_db.execute.return_value = _scalar_one_or_none(order)
        resp = await client.get("/api/payment/order/ORD200")
        assert resp.status_code == 403


class TestListPlans:
    """Cover GET /api/payment/plans."""

    @pytest.mark.asyncio
    async def test_list_plans_returns_active(self, client: AsyncClient, mock_db: AsyncMock):
        plans = [
            SimpleNamespace(
                id="p1", description="Basic", price=Decimal("9.99"),
                duration=30, rate_limit=100, target_group_id="g1",
            ),
        ]
        mock_db.execute.return_value = _scalars_all(plans)
        resp = await client.get("/api/payment/plans")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == "p1"
