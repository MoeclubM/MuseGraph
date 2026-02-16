"""Tests for project endpoints: /api/projects/*"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from tests.conftest import FakeUser, TEST_USER_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_project(
    *,
    project_id: str | None = None,
    user_id: str = TEST_USER_ID,
    title: str = "Test Project",
    description: str | None = "A test project",
    content: str | None = "Some content",
    cognee_dataset_id: str | None = None,
):
    """Return a lightweight object that behaves like a ``TextProject`` row."""
    return SimpleNamespace(
        id=project_id or str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        description=description,
        content=content,
        simulation_requirement=None,
        component_models=None,
        ontology_schema=None,
        oasis_analysis=None,
        cognee_dataset_id=cognee_dataset_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _scalars_all(items: list):
    """Mock ``result.scalars().all()`` to return *items*."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# POST /api/projects
# ---------------------------------------------------------------------------


class TestCreateProject:

    @pytest.mark.asyncio
    async def test_create_project(self, client: AsyncClient, mock_db: AsyncMock):
        now = datetime.now(timezone.utc)

        # When db.add() is called, stamp the object with an id and timestamps
        def _side_effect_add(obj):
            obj.id = str(uuid.uuid4())
            obj.user_id = TEST_USER_ID
            obj.created_at = now
            obj.updated_at = now
            obj.cognee_dataset_id = None

        mock_db.add.side_effect = _side_effect_add

        resp = await client.post("/api/projects", json={
            "title": "My Novel",
            "description": "A great story",
            "content": "Chapter 1...",
        })

        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "My Novel"
        assert body["description"] == "A great story"
        assert body["content"] == "Chapter 1..."
        assert body["user_id"] == TEST_USER_ID


# ---------------------------------------------------------------------------
# GET /api/projects
# ---------------------------------------------------------------------------


class TestListProjects:

    @pytest.mark.asyncio
    async def test_list_projects(self, client: AsyncClient, mock_db: AsyncMock):
        projects = [
            _make_fake_project(title="Project A"),
            _make_fake_project(title="Project B"),
        ]
        mock_db.execute.return_value = _scalars_all(projects)

        resp = await client.get("/api/projects")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["title"] == "Project A"
        assert body[1]["title"] == "Project B"


# ---------------------------------------------------------------------------
# GET /api/projects/:id
# ---------------------------------------------------------------------------


class TestGetProject:

    @pytest.mark.asyncio
    async def test_get_project(self, client: AsyncClient, mock_db: AsyncMock):
        project = _make_fake_project(title="Single Project")
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get(f"/api/projects/{project.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Single Project"
        assert body["id"] == project.id

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.get(f"/api/projects/{uuid.uuid4()}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_project_forbidden(self, client: AsyncClient, mock_db: AsyncMock):
        other_user_project = _make_fake_project(
            user_id=str(uuid.uuid4()),  # different owner
            title="Other's Project",
        )
        mock_db.execute.return_value = _scalar_one_or_none(other_user_project)

        resp = await client.get(f"/api/projects/{other_user_project.id}")

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PUT /api/projects/:id
# ---------------------------------------------------------------------------


class TestUpdateProject:

    @pytest.mark.asyncio
    async def test_update_project(self, client: AsyncClient, mock_db: AsyncMock):
        project = _make_fake_project(title="Old Title")
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.put(f"/api/projects/{project.id}", json={
            "title": "New Title",
        })

        assert resp.status_code == 200
        # The router mutates the object in-place, so the mock's title is updated
        assert project.title == "New Title"

    @pytest.mark.asyncio
    async def test_update_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.put(f"/api/projects/{uuid.uuid4()}", json={
            "title": "Nope",
        })

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/projects/:id
# ---------------------------------------------------------------------------


class TestDeleteProject:

    @pytest.mark.asyncio
    async def test_delete_project(self, client: AsyncClient, mock_db: AsyncMock):
        project = _make_fake_project()
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.delete(f"/api/projects/{project.id}")

        assert resp.status_code == 204
        mock_db.delete.assert_awaited_once_with(project)

    @pytest.mark.asyncio
    async def test_delete_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.delete(f"/api/projects/{uuid.uuid4()}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project_forbidden(self, client: AsyncClient, mock_db: AsyncMock):
        other_project = _make_fake_project(user_id=str(uuid.uuid4()))
        mock_db.execute.return_value = _scalar_one_or_none(other_project)

        resp = await client.delete(f"/api/projects/{other_project.id}")

        assert resp.status_code == 403
