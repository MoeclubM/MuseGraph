"""Tests for project endpoints: /api/projects/*"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services import project_git as project_git_service
from tests.conftest import FakeUser, TEST_USER_ID, patch_app_route_globals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_projects_route_git_globals(monkeypatch: pytest.MonkeyPatch):
    patch_app_route_globals(
        monkeypatch,
        "app.routers.projects",
        {
            "commit_project_git": project_git_service.commit_project_git,
            "delete_project_git_storage": project_git_service.delete_project_git_storage,
            "initialize_project_git_repo": project_git_service.initialize_project_git_repo,
            "push_project_git_branch": project_git_service.push_project_git_branch,
            "stage_project_git_paths": project_git_service.stage_project_git_paths,
            "write_project_workspace_version_snapshot": MagicMock(return_value={}),
        },
    )


def _make_fake_project(
    *,
    project_id: str | None = None,
    user_id: str = TEST_USER_ID,
    title: str = "Test Project",
    description: str | None = "A test project",
    chapter_content: str | None = "Some content",
    memory_id: str | None = None,
):
    """Return a lightweight object that behaves like a ``TextProject`` row."""
    return SimpleNamespace(
        id=project_id or str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        description=description,
        visibility="private",
        members=[],
        chapters=[
            SimpleNamespace(
                id=str(uuid.uuid4()),
                project_id=project_id or "proj-1",
                title="Main Draft",
                content=chapter_content or "",
                status="draft",
                blueprint=None,
                plan=None,
                summary=None,
                continuity_notes=None,
                order_index=0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ],
        facts=[],
        component_models=None,
        operation_prompts=None,
        ontology_schema=None,
        creative_state=None,
        memory_id=memory_id,
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


def _fake_member(*, user_id: str = TEST_USER_ID, role: str = "viewer"):
    return SimpleNamespace(user_id=user_id, role=role)


# ---------------------------------------------------------------------------
# POST /api/projects
# ---------------------------------------------------------------------------


class TestCreateProject:

    @pytest.mark.asyncio
    async def test_create_project(self, client: AsyncClient, mock_db: AsyncMock, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
        now = datetime.now(timezone.utc)

        # When db.add() is called, stamp the object with an id and timestamps
        def _side_effect_add(obj):
            obj.id = str(uuid.uuid4())
            obj.user_id = TEST_USER_ID
            obj.created_at = now
            obj.updated_at = now
            obj.memory_id = None

        mock_db.add.side_effect = _side_effect_add

        resp = await client.post("/api/projects", json={
            "title": "My Novel",
            "description": "A great story",
        })

        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "My Novel"
        assert body["description"] == "A great story"
        assert body["user_id"] == TEST_USER_ID
        assert "content" not in body
        assert isinstance(body.get("chapters"), list)
        workspace = tmp_path / "projects" / body["id"] / "workspace"
        assert (workspace / ".git").is_dir()
        assert (tmp_path / "git-server" / "projects" / f"{body['id']}.git").is_dir()
        assert (workspace / ".musegraph" / "project.json").is_file()
        assert list((workspace / "documents").glob("*.md"))
        snapshot = project_git_service.get_project_git_snapshot(body["id"])
        assert snapshot["files"] == []
        assert snapshot["commits"][0]["subject"] == "Initialize project workspace"


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


class TestListPublicProjects:

    @pytest.mark.asyncio
    async def test_list_public_projects(self, client: AsyncClient, mock_db: AsyncMock):
        public_project = _make_fake_project(
            user_id=str(uuid.uuid4()),
            title="Open Novel",
            description="Shared for reading",
        )
        public_project.visibility = "public"
        public_project.user = SimpleNamespace(nickname="Ada Lovelace", email="ada@example.com")
        mock_db.execute.return_value = _scalars_all([public_project])

        resp = await client.get("/api/projects/public")

        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["title"] == "Open Novel"
        assert body[0]["visibility"] == "public"
        assert body[0]["author_nickname"] == "Ada Lovelace"
        assert body[0]["current_user_role"] == "viewer"
        assert body[0]["current_user_permissions"] == ["view"]
        assert "user_id" not in body[0]
        assert "chapters" not in body[0]
        assert "component_models" not in body[0]
        assert "creative_state" not in body[0]


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
        assert len(body["chapters"]) == 1

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

    @pytest.mark.asyncio
    async def test_get_public_project(self, client: AsyncClient, mock_db: AsyncMock):
        public_project = _make_fake_project(
            user_id=str(uuid.uuid4()),
            title="Public Project",
        )
        public_project.visibility = "public"
        mock_db.execute.return_value = _scalar_one_or_none(public_project)

        resp = await client.get(f"/api/projects/{public_project.id}")

        assert resp.status_code == 200
        assert resp.json()["current_user_role"] == "viewer"


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

    @pytest.mark.asyncio
    async def test_editor_can_update_project(self, client: AsyncClient, mock_db: AsyncMock):
        project = _make_fake_project(user_id=str(uuid.uuid4()), title="Shared Project")
        project.members = [_fake_member(role="editor")]
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.put(f"/api/projects/{project.id}", json={"title": "Edited"})

        assert resp.status_code == 200
        assert project.title == "Edited"

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_project(self, client: AsyncClient, mock_db: AsyncMock):
        project = _make_fake_project(user_id=str(uuid.uuid4()), title="Shared Project")
        project.members = [_fake_member(role="viewer")]
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.put(f"/api/projects/{project.id}", json={"title": "Edited"})

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/projects/:id
# ---------------------------------------------------------------------------


class TestDeleteProject:

    @pytest.mark.asyncio
    async def test_delete_project(self, client: AsyncClient, mock_db: AsyncMock, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
        project = _make_fake_project()
        workspace = tmp_path / "projects" / project.id / "workspace"
        server_repo = tmp_path / "git-server" / "projects" / f"{project.id}.git"
        workspace.mkdir(parents=True)
        server_repo.mkdir(parents=True)
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.delete(f"/api/projects/{project.id}")

        assert resp.status_code == 204
        mock_db.delete.assert_awaited_once_with(project)
        assert not workspace.exists()
        assert not server_repo.exists()

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


class TestProjectAcl:

    @pytest.mark.asyncio
    async def test_owner_can_add_editor_member(self, client: AsyncClient, mock_db: AsyncMock):
        project = _make_fake_project()
        target_user = SimpleNamespace(id=str(uuid.uuid4()), email="editor@example.com")
        mock_db.execute.side_effect = [
            _scalar_one_or_none(project),
            _scalar_one_or_none(target_user),
            _scalar_one_or_none(None),
        ]

        def _track_add(obj):
            if obj.__class__.__name__ == "ProjectMember":
                obj.id = str(uuid.uuid4())
                obj.created_at = datetime.now(timezone.utc)
                obj.updated_at = datetime.now(timezone.utc)

        mock_db.add.side_effect = _track_add

        resp = await client.post(
            f"/api/projects/{project.id}/members",
            json={"email": "editor@example.com", "role": "editor"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["user_id"] == target_user.id
        assert body["email"] == "editor@example.com"
        assert body["role"] == "editor"

    @pytest.mark.asyncio
    async def test_public_project_viewer_cannot_create_chapter(self, client: AsyncClient, mock_db: AsyncMock):
        project = _make_fake_project(user_id=str(uuid.uuid4()), title="Public Project")
        project.visibility = "public"
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            f"/api/projects/{project.id}/chapters",
            json={"title": "Read-only edit", "content": "Should be blocked"},
        )

        assert resp.status_code == 403
