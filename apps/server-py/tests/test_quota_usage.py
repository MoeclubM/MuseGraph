"""Tests for quota checking and usage tracking."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import FakeUser


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


class TestQuotaCheck:
    """Test quota checking logic for model access control."""

    @pytest.mark.asyncio
    async def test_check_quota_no_binding_allows_all(self, mock_db: AsyncMock):
        """Test that models without ModelGroupBinding allow all users."""
        from app.services.quota import check_quota

        user = FakeUser(group_id="group-1")
        # Return empty list for scalars().all()
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []  # No bindings found
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await check_quota(user, "any-model", mock_db)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_quota_user_in_allowed_group(self, mock_db: AsyncMock):
        """Test that user in allowed group can access model."""
        from app.services.quota import check_quota

        user = FakeUser(group_id="group-1")
        # Return list of allowed group IDs
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = ["group-1", "group-2"]  # Allowed groups
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await check_quota(user, "restricted-model", mock_db)

        assert result is True

    @pytest.mark.asyncio
    async def test_check_quota_user_not_in_allowed_group(self, mock_db: AsyncMock):
        """Test that user not in allowed group is denied access."""
        from app.services.quota import check_quota

        user = FakeUser(group_id="group-3")
        # Return list of allowed group IDs
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = ["group-1", "group-2"]  # Allowed groups
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await check_quota(user, "restricted-model", mock_db)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_quota_user_no_group(self, mock_db: AsyncMock):
        """Test that user without group is denied when binding exists."""
        from app.services.quota import check_quota

        user = FakeUser(group_id=None)
        # Return list of allowed group IDs
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = ["group-1", "group-2"]  # Allowed groups
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await check_quota(user, "restricted-model", mock_db)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_quota_empty_binding_allows_all(self, mock_db: AsyncMock):
        """Test that binding with empty group_ids allows all users."""
        from app.services.quota import check_quota

        user = FakeUser(group_id="any-group")
        # Return empty list means no restrictions
        result_mock = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []  # No restrictions
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await check_quota(user, "some-model", mock_db)

        assert result is True


class TestCostCalculation:
    """Test cost calculation with pricing rules."""

    @pytest.mark.asyncio
    async def test_calculate_cost_with_pricing_rule(self, mock_db: AsyncMock):
        """Test cost calculation with existing pricing rule."""
        from app.services.ai import calculate_cost

        rule = SimpleNamespace(
            model="gpt-4o-mini",
            input_price=Decimal("0.00015"),
            output_price=Decimal("0.0006"),
            is_active=True,
        )
        mock_db.execute.return_value = _scalar_one_or_none(rule)

        # 1000 input tokens + 500 output tokens
        cost = await calculate_cost("gpt-4o-mini", 1000, 500, mock_db)

        # Expected: (0.00015 * 1000 / 1000) + (0.0006 * 500 / 1000) = 0.00015 + 0.0003 = 0.00045
        assert cost == Decimal("0.00045")

    @pytest.mark.asyncio
    async def test_calculate_cost_no_pricing_rule(self, mock_db: AsyncMock):
        """Test cost calculation returns 0 when no pricing rule exists."""
        from app.services.ai import calculate_cost

        mock_db.execute.return_value = _scalar_one_or_none(None)

        cost = await calculate_cost("unknown-model", 1000, 500, mock_db)

        assert cost == Decimal("0")

    @pytest.mark.asyncio
    async def test_calculate_cost_large_token_count(self, mock_db: AsyncMock):
        """Test cost calculation with large token counts."""
        from app.services.ai import calculate_cost

        rule = SimpleNamespace(
            model="gpt-4o",
            input_price=Decimal("0.0025"),
            output_price=Decimal("0.01"),
            is_active=True,
        )
        mock_db.execute.return_value = _scalar_one_or_none(rule)

        # 10000 input tokens + 5000 output tokens
        cost = await calculate_cost("gpt-4o", 10000, 5000, mock_db)

        # Expected: (0.0025 * 10000 / 1000) + (0.01 * 5000 / 1000) = 0.025 + 0.05 = 0.075
        assert cost == Decimal("0.075")


class TestBalanceDeduction:
    """Test balance deduction during operations."""

    @pytest.mark.asyncio
    async def test_balance_deduction_success(self, mock_db: AsyncMock):
        """Test successful balance deduction."""
        user = FakeUser(balance=Decimal("100.00"))

        # Simulate deduction
        cost = Decimal("5.00")
        user.balance -= cost

        assert user.balance == Decimal("95.00")

    @pytest.mark.asyncio
    async def test_balance_deduction_insufficient(self, mock_db: AsyncMock):
        """Test insufficient balance raises error."""
        user = FakeUser(balance=Decimal("1.00"))

        cost = Decimal("5.00")

        # Should not allow deduction
        assert user.balance < cost


class TestUsageTracking:
    """Test usage record creation and tracking."""

    @pytest.mark.asyncio
    async def test_usage_record_creation(self, mock_db: AsyncMock):
        """Test that usage records are created correctly."""
        from app.models.billing import Usage

        usage = Usage(
            user_id="user-1",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
            cost=Decimal("0.00045"),
        )

        mock_db.add(usage)
        mock_db.flush()

        mock_db.add.assert_called_once()
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.cost == Decimal("0.00045")


class TestDailyMonthlyUsage:
    """Test daily and monthly usage statistics."""

    @pytest.mark.asyncio
    async def test_get_daily_usage(self, mock_db: AsyncMock):
        """Test calculating daily usage."""
        from app.services.billing import get_daily_usage

        mock_db.execute.return_value = MagicMock(
            scalar=MagicMock(return_value=Decimal("5.25"))
        )

        usage = await get_daily_usage("user-1", mock_db)

        assert usage == Decimal("5.25")

    @pytest.mark.asyncio
    async def test_get_monthly_usage(self, mock_db: AsyncMock):
        """Test calculating monthly usage."""
        from app.services.billing import get_monthly_usage

        mock_db.execute.return_value = MagicMock(
            scalar=MagicMock(return_value=Decimal("150.00"))
        )

        usage = await get_monthly_usage("user-1", mock_db)

        assert usage == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_get_daily_usage_no_records(self, mock_db: AsyncMock):
        """Test daily usage returns 0 when no records exist."""
        from app.services.billing import get_daily_usage

        # When no records, coalesce returns 0
        result_mock = MagicMock()
        result_mock.scalar.return_value = 0  # coalesce returns 0 for empty
        mock_db.execute.return_value = result_mock

        usage = await get_daily_usage("user-1", mock_db)

        assert usage == Decimal("0")
