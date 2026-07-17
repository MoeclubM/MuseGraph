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


def _mk_project(fake_user):
    return SimpleNamespace(
        id="proj-1",
        user_id=fake_user.id,
        visibility="private",
        members=[],
        title="Test Project",
        description="Description",
        component_models=None,
        operation_prompts=None,
        ontology_schema=None,
        creative_state=None,
        memory_id=None,
        chapters=[
            SimpleNamespace(
                id="ch-1",
                project_id="proj-1",
                title="Main Draft",
                status="draft",
                blueprint=None,
                plan=None,
                summary=None,
                continuity_notes=None,
                content="Content",
                order_index=0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ],
        facts=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestExportRouter:
    """Test export router endpoints."""

    @pytest.mark.asyncio
    async def test_export_project_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test export non-existent project returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.post("/api/projects/proj-1/export/bundle")

        assert resp.status_code == 404
        assert "Project not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_project_unauthorized(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test export another user's project returns 403."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
            visibility="private",
            members=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post("/api/projects/proj-1/export/bundle")

        assert resp.status_code == 403
        assert "Access denied" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_bundle_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test successful bundle export."""
        project = _mk_project(fake_user)
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch(
            "app.routers.export.export_project_bundle",
            new_callable=AsyncMock,
            return_value=(b"PK\x03\x04", "application/zip", "Test Project.zip"),
        ):
            resp = await client.post("/api/projects/proj-1/export/bundle")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/zip")

    @pytest.mark.asyncio
    async def test_export_has_content_disposition(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test export response has content disposition header."""
        project = _mk_project(fake_user)
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch(
            "app.routers.export.export_project_bundle",
            new_callable=AsyncMock,
            return_value=(b"zip", "application/zip", "Test Project.zip"),
        ):
            resp = await client.post("/api/projects/proj-1/export/bundle")

        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]
