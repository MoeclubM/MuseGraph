"""Tests for Plan and PricingRule admin operations."""

from __future__ import annotations

import uuid
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


class TestPlanCRUD:
    """Test Plan create, read, update, delete operations."""

    @pytest.mark.asyncio
    async def test_list_plans(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test listing all plans."""
        plans = [
            SimpleNamespace(
                id="plan-1",
                description="Basic Plan",
                target_group_id="group-1",
                price=Decimal("9.99"),
                duration=30,
                rate_limit=100,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ),
            SimpleNamespace(
                id="plan-2",
                description="Pro Plan",
                target_group_id="group-2",
                price=Decimal("29.99"),
                duration=30,
                rate_limit=500,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ),
        ]
        mock_db.execute.return_value = _scalars_all(plans)

        resp = await admin_client.get("/api/admin/plans")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["description"] == "Basic Plan"

    @pytest.mark.asyncio
    async def test_create_plan_success(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test creating a new plan."""
        group = SimpleNamespace(id="group-1", name="basic")
        mock_db.execute.return_value = _scalar_one_or_none(group)

        resp = await admin_client.post(
            "/api/admin/plans",
            json={
                "description": "New Plan",
                "target_group_id": "group-1",
                "price": 19.99,
                "duration": 30,
                "rate_limit": 200,
            },
        )

        # API returns 200, not 201
        assert resp.status_code == 200
        body = resp.json()
        assert body["description"] == "New Plan"
        assert float(body["price"]) == 19.99

    @pytest.mark.asyncio
    async def test_create_plan_invalid_group(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test creating a plan with invalid group_id returns error."""
        mock_db.execute.return_value = _scalar_one_or_none(None)  # Group not found

        resp = await admin_client.post(
            "/api/admin/plans",
            json={
                "description": "Test Plan",
                "target_group_id": "nonexistent-group",
                "price": 19.99,
                "duration": 30,
                "rate_limit": 200,
            },
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_plan_success(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test updating a plan."""
        # Using a dict to simulate mutable state
        existing_dict = {
            "id": "plan-1",
            "description": "Old Description",
            "target_group_id": "group-1",
            "price": Decimal("9.99"),
            "duration": 30,
            "rate_limit": 100,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        existing = MagicMock()
        existing.id = existing_dict["id"]
        existing.description = existing_dict["description"]
        existing.target_group_id = existing_dict["target_group_id"]
        existing.price = existing_dict["price"]
        existing.duration = existing_dict["duration"]
        existing.rate_limit = existing_dict["rate_limit"]
        existing.is_active = existing_dict["is_active"]
        existing.created_at = existing_dict["created_at"]
        existing.updated_at = existing_dict["updated_at"]

        group = SimpleNamespace(id="group-1", name="basic")

        mock_db.execute.side_effect = [
            _scalar_one_or_none(existing),  # Plan exists
            _scalar_one_or_none(group),      # Group exists
        ]

        resp = await admin_client.put(
            "/api/admin/plans/plan-1",
            json={
                "description": "Updated Description",
                "price": 14.99,
                "rate_limit": 150,
            },
        )

        assert resp.status_code == 200
        # Verify the price was updated (as float in the API response)
        assert existing.price == 14.99

    @pytest.mark.asyncio
    async def test_delete_plan_success(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test deleting a plan."""
        plan = SimpleNamespace(
            id="plan-1",
            description="To Delete",
            target_group_id="group-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(plan)

        resp = await admin_client.delete("/api/admin/plans/plan-1")

        assert resp.status_code == 204
        mock_db.delete.assert_awaited_once_with(plan)

    @pytest.mark.asyncio
    async def test_delete_plan_not_found(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test deleting a non-existent plan returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await admin_client.delete("/api/admin/plans/nonexistent")

        assert resp.status_code == 404


class TestPricingRuleCRUD:
    """Test PricingRule admin operations."""

    @pytest.mark.asyncio
    async def test_list_all_pricing_rules(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test listing all pricing rules for admin."""
        rules = [
            SimpleNamespace(
                id="rule-1",
                model="gpt-4o-mini",
                input_price=Decimal("0.00015"),
                output_price=Decimal("0.0006"),
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ),
            SimpleNamespace(
                id="rule-2",
                model="claude-3-haiku",
                input_price=Decimal("0.00025"),
                output_price=Decimal("0.00125"),
                is_active=True,
                created_at=datetime.now(timezone.utc),
            ),
        ]
        mock_db.execute.return_value = _scalars_all(rules)

        resp = await admin_client.get("/api/admin/pricing")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2

    @pytest.mark.asyncio
    async def test_create_pricing_rule_success(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test creating a new pricing rule."""
        # API returns 200, not 201
        resp = await admin_client.post(
            "/api/admin/pricing",
            json={
                "model": "new-model",
                "input_price": 0.001,
                "output_price": 0.003,
                "is_active": True,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["model"] == "new-model"
        assert float(body["input_price"]) == 0.001

    @pytest.mark.asyncio
    async def test_update_pricing_rule_success(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test updating a pricing rule."""
        existing = MagicMock()
        existing.id = "rule-1"
        existing.model = "gpt-4o-mini"
        existing.input_price = Decimal("0.00015")
        existing.output_price = Decimal("0.0006")
        existing.is_active = True
        existing.created_at = datetime.now(timezone.utc)
        existing.updated_at = datetime.now(timezone.utc)
        mock_db.execute.return_value = _scalar_one_or_none(existing)

        resp = await admin_client.put(
            "/api/admin/pricing/rule-1",
            json={
                "input_price": 0.0002,
                "output_price": 0.0008,
            },
        )

        assert resp.status_code == 200
        # Price is set as float from the API
        assert existing.input_price == 0.0002

    @pytest.mark.asyncio
    async def test_update_pricing_rule_not_found(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test updating a non-existent pricing rule returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await admin_client.put(
            "/api/admin/pricing/nonexistent",
            json={"input_price": 0.001},
        )

        assert resp.status_code == 404


class TestCostCalculation:
    """Test cost calculation logic."""

    @pytest.mark.asyncio
    async def test_calculate_cost_with_rule(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test cost calculation with pricing rule."""
        from app.services.ai import calculate_cost

        rule = SimpleNamespace(
            model="test-model",
            input_price=Decimal("0.001"),
            output_price=Decimal("0.002"),
            token_unit=1_000_000,
            billing_mode="TOKEN",
            is_active=True,
        )
        mock_db.execute.return_value = _scalar_one_or_none(rule)

        # Calculate cost for 1000 input tokens and 500 output tokens
        cost = await calculate_cost("test-model", 1000, 500, mock_db)

        # Expected: (0.001 * 1000 / 1_000_000) + (0.002 * 500 / 1_000_000) = 0.000002
        assert cost == Decimal("0.000002")

    @pytest.mark.asyncio
    async def test_calculate_cost_no_rule(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test cost calculation returns 0 when no pricing rule exists."""
        from app.services.ai import calculate_cost

        mock_db.execute.return_value = _scalar_one_or_none(None)

        cost = await calculate_cost("unknown-model", 1000, 500, mock_db)

        assert cost == Decimal("0")
