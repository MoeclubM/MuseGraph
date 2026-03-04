"""Tests for export router endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


class TestExportRouter:
    """Test export router endpoints."""

    @pytest.mark.asyncio
    async def test_export_unsupported_format(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test export with unsupported format returns 400."""
        resp = await client.post("/api/projects/proj-1/export/xyz")

        assert resp.status_code == 400
        assert "Unsupported format" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_project_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test export non-existent project returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.post("/api/projects/proj-1/export/txt")

        assert resp.status_code == 404
        assert "Project not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_project_unauthorized(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test export another user's project returns 403."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post("/api/projects/proj-1/export/txt")

        assert resp.status_code == 403
        assert "Access denied" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_txt_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test successful txt export."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test Project",
            description="Description",
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post("/api/projects/proj-1/export/txt")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")

    @pytest.mark.asyncio
    async def test_export_json_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test successful json export."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test Project",
            description="Description",
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post("/api/projects/proj-1/export/json")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")

    @pytest.mark.asyncio
    async def test_export_md_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test successful markdown export."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test Project",
            description="Description",
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post("/api/projects/proj-1/export/md")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/markdown")

    @pytest.mark.asyncio
    async def test_export_html_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test successful html export."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test Project",
            description="Description",
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post("/api/projects/proj-1/export/html")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")

    @pytest.mark.asyncio
    async def test_export_has_content_disposition(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test export response has content disposition header."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test Project",
            description="Description",
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post("/api/projects/proj-1/export/txt")

        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]
