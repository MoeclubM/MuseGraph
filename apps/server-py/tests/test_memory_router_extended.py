"""Tests for memory router endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import get_endpoint_globals, iter_app_routes


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


class TestMemoryMemoryStatus:
    """Test memory status endpoints."""

    @pytest.mark.asyncio
    async def test_get_memory_status_no_memory(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting status when no memory exists."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            visibility="private",
            members=[],
            memory_id=None,
            ontology_schema=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        endpoint_globals = get_endpoint_globals("get_memory_status")
        with patch.dict(endpoint_globals, {"has_memory_data": AsyncMock(return_value=True)}):
            resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/memory")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "empty"

    @pytest.mark.asyncio
    async def test_get_memory_status_with_memory(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting status when memory exists."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            visibility="private",
            members=[],
            memory_id="dataset-1",
            ontology_schema=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/memory")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["memory_id"] == "dataset-1"

    @pytest.mark.asyncio
    async def test_get_memory_status_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting status of another user's project."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
            visibility="private",
            members=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/memory")

        assert resp.status_code == 403


class TestMemoryMemoryAdd:
    """Test adding content to memory."""

    @pytest.mark.asyncio
    async def test_add_text_to_memory_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test adding text to another user's project."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
            visibility="private",
            members=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/memory",
            json={"text": "Test content"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_add_text_to_memory_without_ontology(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test adding text without ontology builds plain text memory."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            visibility="private",
            members=[],
            chapters=[],
            component_models={"memory_build": "gpt-4o-mini"},
            creative_state=None,
            memory_id=None,
            ontology_schema=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch.object(_cg_mod, "build_memory", new_callable=AsyncMock, return_value="dataset-1") as build_memory:
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/memory",
                json={"text": "Test content"},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "ok"
        assert body["memory_id"] == "dataset-1"
        assert project.memory_id == "dataset-1"
        build_memory.assert_awaited_once()
        assert build_memory.await_args.kwargs["ontology"] is None


class TestMemoryMemorySearch:
    """Test memory search endpoints."""

    @pytest.mark.asyncio
    async def test_search_memory_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test searching another user's memory."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
            visibility="private",
            members=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/memory/search",
            json={"query": "test query"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_search_memory_without_memory(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test searching memory without memory data returns 400."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            visibility="private",
            members=[],
            memory_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/memory/search",
            json={"query": "test query"},
        )

        assert resp.status_code == 400


class TestMemoryMemoryVisualization:
    """Test memory visualization endpoint."""

    @pytest.mark.asyncio
    async def test_get_visualization_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting visualization of another user's memory."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
            visibility="private",
            members=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/memory/visualization")

        assert resp.status_code == 403

    @pytest.mark.skip(reason="Requires async memory mock which is not available")
    @pytest.mark.asyncio
    async def test_get_visualization_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting visualization successfully."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            visibility="private",
            members=[],
            memory_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        async def mock_viz_func(project_id, **_kwargs):
            return {"nodes": [], "edges": []}

        with patch("app.routers.memory.get_memory_visualization", side_effect=mock_viz_func):
            resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/memory/visualization")

            assert resp.status_code == 200
            data = resp.json()
            assert "nodes" in data
            assert "edges" in data


class TestMemoryMemoryDelete:
    """Test memory deletion endpoint."""

    @pytest.mark.asyncio
    async def test_delete_memory_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test deleting another user's memory."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
            visibility="private",
            members=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.delete("/api/projects/11111111-1111-4111-8111-111111111111/memory")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_memory_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test deleting memory successfully."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            visibility="private",
            members=[],
            memory_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        endpoint_globals = get_endpoint_globals("delete_memory")
        with patch.dict(endpoint_globals, {"delete_memory_data": AsyncMock(return_value=None)}):

            resp = await client.delete("/api/projects/11111111-1111-4111-8111-111111111111/memory")

            assert resp.status_code == 204


class TestOntologyGenerate:
    """Test ontology generation endpoint."""

    @pytest.mark.asyncio
    async def test_generate_ontology_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test generating ontology for another user's project."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
            visibility="private",
            members=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/memory/ontology/generate",
            json={"text": "Test content"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_generate_ontology_no_text(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test generating ontology without text returns 400."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            visibility="private",
            members=[],
            chapters=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/memory/ontology/generate",
            json={},
        )

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Additional test classes for missing coverage lines
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Resolve endpoint globals from the test app instance so patches affect the
# same module instance used by ASGITransport requests.
# ---------------------------------------------------------------------------
class _GlobalsProxy:
    def __init__(self, globals_dict: dict):
        object.__setattr__(self, "_g", globals_dict)

    def __getattr__(self, name: str):
        g = object.__getattribute__(self, "_g")
        if name in g:
            return g[name]
        raise AttributeError(name)

    def __setattr__(self, name: str, value):
        g = object.__getattribute__(self, "_g")
        g[name] = value

    def __delattr__(self, name: str):
        g = object.__getattribute__(self, "_g")
        if name in g:
            del g[name]
        else:
            raise AttributeError(name)


_cg_mod = _GlobalsProxy(get_endpoint_globals("get_memory_status"))


@pytest.fixture(autouse=True)
def _stub_workspace_snapshot(monkeypatch: pytest.MonkeyPatch):
    snapshot = AsyncMock()
    for route in iter_app_routes():
        endpoint = getattr(route, "endpoint", None)
        globals_ = getattr(endpoint, "__globals__", None)
        if isinstance(globals_, dict) and "write_project_workspace_version_snapshot_from_db" in globals_:
            monkeypatch.setitem(globals_, "write_project_workspace_version_snapshot_from_db", snapshot)


class TestMemoryTaskStatus:
    """Test GET /api/projects/{id}/memory/tasks/{task_id}."""

    @pytest.mark.asyncio
    async def test_task_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id)
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch.object(_cg_mod, "task_manager") as mock_tm:
            mock_tm.get_task.return_value = None
            resp = await client.get(
                "/api/projects/11111111-1111-4111-8111-111111111111/memory/tasks/nonexistent-id",
            )
            assert resp.status_code == 404
            assert "Task not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_task_wrong_project(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id)
        mock_db.execute.return_value = _scalar_one_or_none(project)

        fake_task = MagicMock()
        fake_task.metadata = {"project_id": "proj-OTHER"}

        with patch.object(_cg_mod, "task_manager") as mock_tm:
            mock_tm.get_task.return_value = fake_task
            resp = await client.get(
                "/api/projects/11111111-1111-4111-8111-111111111111/memory/tasks/some-task-id",
            )
            assert resp.status_code == 404
            assert "Task not found" in resp.json()["detail"]


class TestMemoryTaskList:
    """Test GET /api/projects/{id}/memory/tasks."""

    @pytest.mark.asyncio
    async def test_list_tasks(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id)
        mock_db.execute.return_value = _scalar_one_or_none(project)

        now = datetime.now(timezone.utc)
        fake_task = MagicMock()
        fake_task.to_dict.return_value = {
            "task_id": "task-1",
            "task_type": "memory_build",
            "status": "completed",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "progress": 100,
            "message": "Done",
            "result": {"package": {}},
            "error": None,
            "metadata": {"project_id": "11111111-1111-4111-8111-111111111111"},
        }

        with patch.object(_cg_mod, "task_manager") as mock_tm:
            mock_tm.list_tasks.return_value = [fake_task]
            resp = await client.get(
                "/api/projects/11111111-1111-4111-8111-111111111111/memory/tasks",
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert len(data["tasks"]) == 1
            assert data["tasks"][0]["task_id"] == "task-1"


class TestMemorySearchExtended:
    """Test POST /api/projects/{id}/memory/search - extended."""

    @pytest.mark.asyncio
    async def test_search_without_memory_returns_400(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id,
            memory_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/memory/search",
            json={"query": "find something"},
        )
        assert resp.status_code == 400
        assert "No memory data" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_search_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id,
            memory_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_results = [{"content": "result1"}]

        with patch.object(_cg_mod, "search_memory", new_callable=AsyncMock, return_value=mock_results):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/memory/search",
                json={"query": "find something"},
            )
            assert resp.status_code == 200
            assert resp.json()["results"] == mock_results


class TestMemoryVisualizationSuccess:
    """Test GET /api/projects/{id}/memory/visualization."""

    @pytest.mark.asyncio
    async def test_visualization_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id,
            memory_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_viz = {
            "nodes": [{"id": "n1", "label": "Person", "type": "ENTITY"}],
            "edges": [{"source": "n1", "target": "n2", "label": "KNOWS"}],
        }

        with patch.object(_cg_mod, "get_memory_visualization", new_callable=AsyncMock, return_value=mock_viz):
            resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/memory/visualization")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["nodes"]) == 1
            assert len(data["edges"]) == 1
            assert data["nodes"][0]["label"] == "Person"

    @pytest.mark.asyncio
    async def test_visualization_runtime_error_returns_502(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id,
            memory_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch.object(
            _cg_mod,
            "get_memory_visualization",
            new_callable=AsyncMock,
            side_effect=RuntimeError("memory backend unavailable"),
        ):
            resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/memory/visualization")
            assert resp.status_code == 502
            assert "memory backend unavailable" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_visualization_uses_preview_task_memory_id(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id,
            memory_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        task = _cg_mod.task_manager.create_task(
            "memory_build",
            metadata={"project_id": project.id, "user_id": fake_user.id},
        )
        _cg_mod.task_manager.update_task(task.task_id, progress_detail={"preview_memory_id": "memory-preview-1"})
        mock_viz = {"nodes": [], "edges": []}

        with patch.object(_cg_mod, "get_memory_visualization_for_group", new_callable=AsyncMock, return_value=mock_viz) as mock_preview:
            resp = await client.get(
                f"/api/projects/{project.id}/memory/visualization",
                params={"preview_task_id": task.task_id},
            )

        assert resp.status_code == 200
        mock_preview.assert_awaited_once()
        assert mock_preview.await_args.kwargs["memory_id"] == "memory-preview-1"


class TestAddToMemoryOntologyFromBody:
    """Test POST /api/projects/{id}/memory with ontology in body."""

    @pytest.mark.asyncio
    async def test_add_with_ontology_in_body(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id, title="Test",
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="11111111-1111-4111-8111-111111111111",
                    title="Main Draft",
                    content="Some content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ], ontology_schema=None,
            memory_id=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        body_ontology = {"entity_types": ["Character"]}

        with patch.object(_cg_mod, "build_memory_input_with_ontology", return_value="memory input"), \
             patch.object(_cg_mod, "resolve_explicit_component_model", return_value="gpt-4"), \
             patch.object(_cg_mod, "build_memory", new_callable=AsyncMock, return_value="dataset-new"):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/memory",
                json={"text": "Test content", "ontology": body_ontology},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["status"] == "ok"
            assert data["memory_id"] == "dataset-new"
            assert project.ontology_schema == body_ontology



