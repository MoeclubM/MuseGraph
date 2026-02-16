"""Tests for billing endpoints: /api/billing/*"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from tests.conftest import FakeUser, TEST_USER_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scalars_all(items: list):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _scalar_result(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _make_fake_pricing_rule(
    *,
    rule_id: str | None = None,
    model: str = "gpt-4o-mini",
    input_price: float = 0.00015,
    output_price: float = 0.0006,
    is_active: bool = True,
):
    r = MagicMock()
    r.id = rule_id or str(uuid.uuid4())
    r.model = model
    r.input_price = Decimal(str(input_price))
    r.output_price = Decimal(str(output_price))
    r.is_active = is_active
    r.created_at = datetime.now(timezone.utc)
    r.updated_at = datetime.now(timezone.utc)
    return r


def _make_fake_deposit(
    *,
    deposit_id: str | None = None,
    user_id: str = TEST_USER_ID,
    amount: Decimal = Decimal("50.0000"),
    status: str = "PENDING",
):
    d = MagicMock()
    d.id = deposit_id or str(uuid.uuid4())
    d.user_id = user_id
    d.amount = amount
    d.status = status
    d.payment_method = None
    d.created_at = datetime.now(timezone.utc)
    return d


# ---------------------------------------------------------------------------
# GET /api/billing/pricing
# ---------------------------------------------------------------------------


class TestGetPricing:

    @pytest.mark.asyncio
    async def test_get_pricing(self, client: AsyncClient, mock_db: AsyncMock):
        rules = [
            _make_fake_pricing_rule(model="gpt-4o-mini"),
            _make_fake_pricing_rule(model="claude-3-haiku", input_price=0.00025, output_price=0.00125),
        ]
        mock_db.execute.return_value = _scalars_all(rules)

        resp = await client.get("/api/billing/pricing")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["model"] == "gpt-4o-mini"
        assert body[1]["model"] == "claude-3-haiku"

    @pytest.mark.asyncio
    async def test_get_pricing_empty(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalars_all([])

        resp = await client.get("/api/billing/pricing")

        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/billing/balance
# ---------------------------------------------------------------------------


class TestGetBalance:

    @pytest.mark.asyncio
    async def test_get_balance(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_result(Decimal("1.50")),
                _scalar_result(Decimal("25.00")),
            ]
        )
        resp = await client.get("/api/billing/balance")

        assert resp.status_code == 200
        body = resp.json()
        assert body["balance"] == float(fake_user.balance)
        assert body["daily_usage"] == 1.50
        assert body["monthly_usage"] == 25.00


# ---------------------------------------------------------------------------
# POST /api/billing/deposit
# ---------------------------------------------------------------------------


class TestCreateDeposit:

    @pytest.mark.asyncio
    async def test_create_deposit(self, client: AsyncClient, mock_db: AsyncMock):
        def _side_effect_add(obj):
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(timezone.utc)
            if getattr(obj, "status", None) is None:
                obj.status = "PENDING"

        mock_db.add.side_effect = _side_effect_add
        resp = await client.post("/api/billing/deposit", json={
            "amount": 100.0,
            "payment_method": "alipay",
        })

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["id"], str) and len(body["id"]) > 0
        assert body["amount"] == 100.0
        assert body["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_create_deposit_no_payment_method(self, client: AsyncClient, mock_db: AsyncMock):
        def _side_effect_add(obj):
            if getattr(obj, "id", None) is None:
                obj.id = str(uuid.uuid4())
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.now(timezone.utc)
            if getattr(obj, "status", None) is None:
                obj.status = "PENDING"

        mock_db.add.side_effect = _side_effect_add
        resp = await client.post("/api/billing/deposit", json={
            "amount": 50.0,
        })

        assert resp.status_code == 200
        body = resp.json()
        assert body["amount"] == 50.0
