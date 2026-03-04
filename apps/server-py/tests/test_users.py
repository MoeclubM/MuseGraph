"""Tests for user endpoints: /api/users/*"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from tests.conftest import FakeUser, TEST_USER_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# GET /api/users/:id
# ---------------------------------------------------------------------------


class TestGetUser:

    @pytest.mark.asyncio
    async def test_get_user(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """A user can fetch their own profile."""
        mock_db.execute.return_value = _scalar_one_or_none(fake_user)

        resp = await client.get(f"/api/users/{fake_user.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == fake_user.id
        assert body["email"] == fake_user.email

    @pytest.mark.asyncio
    async def test_get_user_forbidden(self, client: AsyncClient, mock_db: AsyncMock):
        """A regular user cannot fetch another user's profile."""
        other_id = str(uuid.uuid4())

        resp = await client.get(f"/api/users/{other_id}")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """Return 404 when the user does not exist in the database."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.get(f"/api/users/{fake_user.id}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_user_as_admin(
        self, admin_client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser
    ):
        """An admin can fetch any user's profile."""
        mock_db.execute.return_value = _scalar_one_or_none(fake_user)

        resp = await admin_client.get(f"/api/users/{fake_user.id}")

        assert resp.status_code == 200
        assert resp.json()["id"] == fake_user.id


# ---------------------------------------------------------------------------
# GET /api/users/:id/usage
# ---------------------------------------------------------------------------


class TestGetUserUsage:

    @pytest.mark.asyncio
    async def test_get_user_usage(self, client: AsyncClient, mock_db: AsyncMock, fake_user: FakeUser):
        """A user can fetch their own usage stats."""

        # The endpoint makes 3 separate db.execute calls:
        # 1. total stats  -> row with (count, tokens, cost)
        # 2. daily count  -> scalar
        # 3. monthly count -> scalar

        total_row = MagicMock()
        total_row.__getitem__ = lambda self, idx: [5, 1200, 0.05][idx]
        total_result = MagicMock()
        total_result.one.return_value = total_row

        daily_result = MagicMock()
        daily_result.scalar.return_value = 2

        monthly_result = MagicMock()
        monthly_result.scalar.return_value = 5

        mock_db.execute.side_effect = [total_result, daily_result, monthly_result]

        resp = await client.get(f"/api/users/{fake_user.id}/usage")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_requests"] == 5
        assert body["total_tokens"] == 1200
        assert body["total_cost"] == 0.05
        assert body["daily_requests"] == 2
        assert body["monthly_requests"] == 5

    @pytest.mark.asyncio
    async def test_get_user_usage_forbidden(self, client: AsyncClient, mock_db: AsyncMock):
        """A regular user cannot fetch another user's usage."""
        other_id = str(uuid.uuid4())

        resp = await client.get(f"/api/users/{other_id}/usage")

        assert resp.status_code == 403
