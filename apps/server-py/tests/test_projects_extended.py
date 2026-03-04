"""Tests for projects router extended endpoints."""

from __future__ import annotations

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


class TestProjectList:
    """Test project listing endpoints."""

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test listing projects when none exist."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        resp = await client.get("/api/projects")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_projects_as_admin(self, admin_client: AsyncClient, mock_db: AsyncMock):
        """Test admin can see all projects."""
        projects = [
            SimpleNamespace(
                id="proj-1",
                user_id="user-1",
                title="Project 1",
                description="Desc 1",
                chapters=[
                    SimpleNamespace(
                        id="ch-1",
                        project_id="proj-1",
                        title="Main Draft",
                        content="Content 1",
                        order_index=0,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                ],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                simulation_requirement=None,
                component_models=None,
            ),
        ]
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = projects
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        resp = await admin_client.get("/api/projects")

        assert resp.status_code == 200


class TestProjectCreate:
    """Test project creation endpoints."""

    @pytest.mark.asyncio
    async def test_create_project_minimal(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test creating project with minimal data."""
        # Track the project that gets added
        added_project = None

        def track_add(obj):
            nonlocal added_project
            added_project = obj
            # Set database-generated fields
            obj.id = "new-project-id"
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)

        mock_db.add = MagicMock(side_effect=track_add)
        mock_db.flush = AsyncMock()

        resp = await client.post(
            "/api/projects",
            json={"title": "New Project"},
        )

        # Endpoint returns 201 CREATED
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "New Project"

    @pytest.mark.asyncio
    async def test_create_project_rejects_legacy_content(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Strict schema should reject legacy content field."""
        resp = await client.post(
            "/api/projects",
            json={"title": "New Project", "content": "Some content"},
        )

        assert resp.status_code == 422


class TestProjectGet:
    """Test project retrieval endpoints."""

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting non-existent project returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.get("/api/projects/nonexistent")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_project_unauthorized(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting another user's project returns 403."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/proj-1")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_project_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting own project succeeds."""
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
            simulation_requirement=None,
            component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/proj-1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Project"


class TestProjectUpdate:
    """Test project update endpoints."""

    @pytest.mark.asyncio
    async def test_update_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test updating non-existent project returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.put(
            "/api/projects/nonexistent",
            json={"title": "Updated"},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_project_unauthorized(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test updating another user's project returns 403."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.put(
            "/api/projects/proj-1",
            json={"title": "Updated"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_project_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test updating own project succeeds."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Old Title",
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
            simulation_requirement=None,
            component_models=None,
            oasis_analysis=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        resp = await client.put(
            "/api/projects/proj-1",
            json={"title": "New Title"},
        )

        assert resp.status_code == 200


class TestProjectDelete:
    """Test project deletion endpoints."""

    @pytest.mark.asyncio
    async def test_delete_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test deleting non-existent project returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.delete("/api/projects/nonexistent")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project_unauthorized(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test deleting another user's project returns 403."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.delete("/api/projects/proj-1")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_project_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test deleting own project succeeds."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.delete("/api/projects/proj-1")

        assert resp.status_code == 204


class TestProjectOperation:
    """Test project operation endpoints."""

    @pytest.mark.asyncio
    async def test_create_operation_unauthorized(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test operation on another user's project returns 403."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/proj-1/operation",
            json={"type": "CREATE", "input": "Test", "model": "gpt-4o-mini"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_operation_invalid_type(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test operation with invalid type returns 400."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/proj-1/operation",
            json={"type": "INVALID", "input": "Test", "model": "gpt-4o-mini"},
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_operation_missing_input(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test operation without input returns 400."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/proj-1/operation",
            json={"type": "CREATE", "model": "gpt-4o-mini"},
        )

        assert resp.status_code == 400
