"""Tests for groups router endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


def _scalars_all(items: list):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


class TestGroupsRouter:
    """Test groups router endpoints."""

    @pytest.mark.asyncio
    async def test_list_groups_empty(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test listing groups when none exist."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        resp = await client.get("/api/groups")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_groups_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test listing groups successfully."""
        groups = [
            SimpleNamespace(id="group-1", name="free", description="Free tier"),
            SimpleNamespace(id="group-2", name="pro", description="Pro tier"),
        ]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = groups
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        resp = await client.get("/api/groups")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "free"
        assert data[1]["name"] == "pro"

    @pytest.mark.asyncio
    async def test_get_my_group_no_group(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting my group when user has no group."""
        # fake_user has group_id=None by default
        resp = await client.get("/api/groups/me")

        assert resp.status_code == 200
        assert resp.json()["group"] is None

    @pytest.mark.asyncio
    async def test_get_my_group_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting my group successfully."""
        fake_user.group_id = "group-1"

        group = SimpleNamespace(id="group-1", name="pro", description="Pro tier")
        mock_db.execute.return_value = _scalar_one_or_none(group)

        resp = await client.get("/api/groups/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["group"]["id"] == "group-1"
        assert data["group"]["name"] == "pro"

    @pytest.mark.asyncio
    async def test_get_my_group_group_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting my group when group doesn't exist."""
        fake_user.group_id = "nonexistent"
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.get("/api/groups/me")

        assert resp.status_code == 200
        assert resp.json()["group"] is None
