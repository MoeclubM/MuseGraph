"""Tests for cognee graph router endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from app.services.task_state import TaskRecord, TaskStatus


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


def _close_and_stub_task(coro):
    coro.close()
    return MagicMock()


class TestCogneeGraphStatus:
    """Test graph status endpoints."""

    @pytest.mark.asyncio
    async def test_get_graph_status_no_graph(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting status when no graph exists."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            cognee_dataset_id=None,
            ontology_schema=None,
            oasis_analysis=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/graphs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "empty"

    @pytest.mark.asyncio
    async def test_get_graph_status_with_graph(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting status when graph exists."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            cognee_dataset_id="dataset-1",
            ontology_schema={"entity_types": []},
            oasis_analysis={"test": "data"},
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/graphs")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["dataset_id"] == "dataset-1"

    @pytest.mark.asyncio
    async def test_get_graph_status_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting status of another user's project."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/graphs")

        assert resp.status_code == 403


class TestCogneeGraphAdd:
    """Test adding content to graph."""

    @pytest.mark.asyncio
    async def test_add_text_to_graph_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test adding text to another user's project."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/graphs",
            json={"text": "Test content"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_add_text_to_graph_no_ontology(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test adding text without ontology returns 400."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            ontology_schema=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/graphs",
            json={"text": "Test content"},
        )

        assert resp.status_code == 400


class TestCogneeGraphSearch:
    """Test graph search endpoints."""

    @pytest.mark.asyncio
    async def test_search_graph_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test searching another user's graph."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/graphs/search",
            json={"query": "test query"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_search_graph_no_dataset(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test searching graph without dataset returns 400."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            cognee_dataset_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/graphs/search",
            json={"query": "test query"},
        )

        assert resp.status_code == 400


class TestCogneeGraphVisualization:
    """Test graph visualization endpoint."""

    @pytest.mark.asyncio
    async def test_get_visualization_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting visualization of another user's graph."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/graphs/visualization")

        assert resp.status_code == 403

    @pytest.mark.skip(reason="Requires async cognee mock which is not available")
    @pytest.mark.asyncio
    async def test_get_visualization_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting visualization successfully."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            cognee_dataset_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        async def mock_viz_func(project_id, **_kwargs):
            return {"nodes": [], "edges": []}

        with patch("app.routers.cognee_graph.get_graph_visualization", side_effect=mock_viz_func):
            resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/graphs/visualization")

            assert resp.status_code == 200
            data = resp.json()
            assert "nodes" in data
            assert "edges" in data


class TestCogneeGraphDelete:
    """Test graph deletion endpoint."""

    @pytest.mark.asyncio
    async def test_delete_graph_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test deleting another user's graph."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.delete("/api/projects/11111111-1111-4111-8111-111111111111/graphs")

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_graph_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test deleting graph successfully."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            cognee_dataset_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch("app.routers.cognee_graph.delete_dataset") as mock_delete:
            mock_delete.return_value = None

            resp = await client.delete("/api/projects/11111111-1111-4111-8111-111111111111/graphs")

            assert resp.status_code == 204


class TestOntologyGenerate:
    """Test ontology generation endpoint."""

    @pytest.mark.asyncio
    async def test_generate_ontology_unauthorized(self, client: AsyncClient, mock_db: AsyncMock):
        """Test generating ontology for another user's project."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id="different-user-id",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/graphs/ontology/generate",
            json={"text": "Test content"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_generate_ontology_no_text(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test generating ontology without text returns 400."""
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            chapters=[],
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/graphs/ontology/generate",
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
def _get_endpoint_globals(app, endpoint_name: str) -> dict:
    for route in app.routes:
        if hasattr(route, "endpoint") and getattr(route, "name", "") == endpoint_name:
            return route.endpoint.__globals__
        if hasattr(route, "routes"):
            for sub in route.routes:
                if hasattr(sub, "endpoint") and getattr(sub, "name", "") == endpoint_name:
                    return sub.endpoint.__globals__
    raise RuntimeError(f"Endpoint {endpoint_name!r} not found")


from tests.conftest import app as _test_app


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


_cg_mod = _GlobalsProxy(_get_endpoint_globals(_test_app, "get_graph_status"))


class TestOasisAnalyze:
    """Test POST /api/projects/{id}/graphs/oasis/analyze."""

    @pytest.mark.asyncio
    async def test_analyze_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis=None,
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_analysis = {"agents": [], "scenarios": []}
        mock_context = {"insights": ["insight1"], "relationships": []}

        with patch.object(_cg_mod, "analyze_and_enrich_oasis", new_callable=AsyncMock) as mock_fn, \
             patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"):
            mock_fn.return_value = (mock_analysis, mock_context)
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/analyze",
                json={"text": "Analyze this text"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["analysis"]["agents"] == mock_analysis["agents"]
            assert data["analysis"]["scenarios"] == mock_analysis["scenarios"]
            assert data["analysis"].get("content_hash")
            assert data["context"]["insights"] == mock_context["insights"]
            assert data["context"]["relationships"] == mock_context["relationships"]
            assert data["context"].get("content_hash")

    @pytest.mark.asyncio
    async def test_analyze_exception(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis=None,
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch.object(_cg_mod, "analyze_and_enrich_oasis", new_callable=AsyncMock) as mock_fn, \
             patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"):
            mock_fn.side_effect = RuntimeError("LLM call failed")
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/analyze",
                json={"text": "Analyze this text"},
            )
            assert resp.status_code == 500
            assert "LLM call failed" in resp.json()["detail"]


class TestOasisPrepare:
    """Test POST /api/projects/{id}/graphs/oasis/prepare."""

    @pytest.mark.asyncio
    async def test_prepare_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1",
            oasis_analysis={"agents": [], "scenarios": []},
            simulation_requirement="test req", component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_package = {"config": {}, "agents": []}

        with patch.object(_cg_mod, "build_oasis_package", return_value=mock_package), \
             patch.object(_cg_mod, "_ensure_analysis_for_provenance", new_callable=AsyncMock, return_value={"agents": [], "scenarios": []}), \
             patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/prepare",
                json={"text": "prepare text"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["package"] == mock_package

    @pytest.mark.asyncio
    async def test_prepare_exception(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis={"agents": []},
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.side_effect = [
            _scalar_one_or_none(project),
            _scalars_all(project.chapters),
            _scalar_one_or_none(None),
        ]

        with patch.object(_cg_mod, "build_oasis_package", side_effect=RuntimeError("Package build failed")), \
             patch.object(_cg_mod, "_ensure_analysis_for_provenance", new_callable=AsyncMock, return_value={"agents": [], "scenarios": []}), \
             patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/prepare", json={},
            )
            assert resp.status_code == 500
            assert "Package build failed" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_prepare_with_requirement_provided(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis={"agents": []},
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch.object(_cg_mod, "build_oasis_package", return_value={"config": {}}), \
             patch.object(_cg_mod, "_ensure_analysis_for_provenance", new_callable=AsyncMock, return_value={"agents": [], "scenarios": []}), \
             patch.object(
                 _cg_mod,
                 "_resolve_text",
                 new_callable=AsyncMock,
                 return_value=(
                     "Some content",
                     {
                         "source_chapter_ids": ["ch-1"],
                         "content_hash": "h",
                         "generated_at": "2026-01-01T00:00:00+00:00",
                     },
                 ),
             ), \
             patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/prepare",
                json={"requirement": "custom requirement", "chapter_ids": ["ch-1"]},
            )
            assert resp.status_code == 200
            assert project.simulation_requirement == "custom requirement"


class TestOasisPrepareTask:
    """Test POST /api/projects/{id}/graphs/oasis/prepare/task."""

    @pytest.mark.asyncio
    async def test_prepare_task_starts(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis=None,
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        nonce = datetime.now(timezone.utc).isoformat()

        with patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"), \
             patch.object(_cg_mod.asyncio, "create_task", side_effect=_close_and_stub_task) as mock_ct:
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/prepare/task",
                json={"text": f"prepare text {nonce}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["task"]["task_type"] == "oasis_prepare"
            assert data["task"]["status"] == "pending"
            mock_ct.assert_called_once()


class TestOasisRun:
    """Test POST /api/projects/{id}/graphs/oasis/run."""

    @pytest.mark.asyncio
    async def test_run_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1",
            oasis_analysis={"agents": [], "latest_package": {"config": {}}},
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.side_effect = [
            _scalar_one_or_none(project),
            _scalars_all(project.chapters),
            _scalar_one_or_none(None),
        ]
        mock_run_result = {"steps": [], "summary": "done"}
        valid_analysis = {
            "scenario_summary": "Ready",
            "continuation_guidance": {"must_follow": ["rule1"], "next_steps": ["step1"], "avoid": []},
            "agent_profiles": [
                {
                    "name": "Agent1",
                    "role": "Analyst",
                    "persona": "Tracks narrative trends",
                    "stance": "neutral",
                    "likely_actions": ["Summarize events"],
                }
            ],
            "simulation_config": {
                "time_config": {
                    "total_hours": 48,
                    "minutes_per_round": 60,
                    "peak_hours": [19, 20],
                    "off_peak_hours": [1, 2],
                },
                "events": [{"title": "Kickoff", "trigger_hour": 1, "description": "Start"}],
                "agent_activity": [
                    {
                        "name": "Agent1",
                        "activity_level": 0.6,
                        "actions_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            },
            "latest_package": {"simulation_id": "sim-1", "content_hash": "h"},
        }

        with patch.object(_cg_mod, "build_oasis_run_result", return_value=mock_run_result), \
             patch.object(_cg_mod, "_ensure_analysis_for_provenance", new_callable=AsyncMock, return_value=valid_analysis):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/run", json={},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["run_result"]["steps"] == mock_run_result["steps"]
            assert data["run_result"]["summary"] == mock_run_result["summary"]
            assert data["run_result"].get("content_hash")

    @pytest.mark.asyncio
    async def test_run_no_package_auto_builds(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis=None,
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        valid_analysis = {
            "scenario_summary": "Ready",
            "continuation_guidance": {"must_follow": ["rule1"], "next_steps": ["step1"], "avoid": []},
            "agent_profiles": [
                {
                    "name": "Agent1",
                    "role": "Analyst",
                    "persona": "Tracks narrative trends",
                    "stance": "neutral",
                    "likely_actions": ["Summarize events"],
                }
            ],
            "simulation_config": {
                "time_config": {
                    "total_hours": 48,
                    "minutes_per_round": 60,
                    "peak_hours": [19, 20],
                    "off_peak_hours": [1, 2],
                },
                "events": [{"title": "Kickoff", "trigger_hour": 1, "description": "Start"}],
                "agent_activity": [
                    {
                        "name": "Agent1",
                        "activity_level": 0.6,
                        "actions_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            },
            "latest_package": {"simulation_id": "sim-1", "content_hash": "h"},
        }

        with patch.object(
            _cg_mod,
            "_resolve_text",
            new_callable=AsyncMock,
            return_value=(
                "Some content",
                {
                    "source_chapter_ids": ["ch-1"],
                    "content_hash": "h",
                    "generated_at": "2026-01-01T00:00:00+00:00",
                },
            ),
        ), \
             patch.object(_cg_mod, "_ensure_analysis_for_provenance", new_callable=AsyncMock, return_value=valid_analysis):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/run", json={},
            )
        assert resp.status_code == 200
        assert resp.json()["run_result"].get("content_hash")


class TestOasisRunTask:
    """Test POST /api/projects/{id}/graphs/oasis/run/task."""

    @pytest.mark.asyncio
    async def test_run_task_starts(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis=None,
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        nonce = datetime.now(timezone.utc).isoformat()

        with patch.object(_cg_mod.asyncio, "create_task", side_effect=_close_and_stub_task) as mock_ct:
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/run/task",
                json={"package": {"nonce": nonce}},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["task"]["task_type"] == "oasis_run"
            assert data["task"]["status"] == "pending"
            mock_ct.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_task_reuses_inflight_idempotent_task(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis=None,
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        existing_task = TaskRecord(
            task_id="task-existing-1",
            task_type="oasis_run",
            status=TaskStatus.PROCESSING,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            progress=35,
            message="Running simulation estimation...",
            metadata={"project_id": "11111111-1111-4111-8111-111111111111", "idempotency_key": "oasis_run:existing"},
        )

        with patch.object(_cg_mod, "task_manager") as mock_tm, \
             patch.object(_cg_mod.asyncio, "create_task") as mock_ct:
            mock_tm.find_inflight_task_by_idempotency.return_value = existing_task
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/run/task", json={},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["task"]["task_id"] == "task-existing-1"
            mock_tm.create_task.assert_not_called()
            mock_ct.assert_not_called()


class TestOasisReport:
    """Test POST /api/projects/{id}/graphs/oasis/report."""

    @pytest.mark.asyncio
    async def test_report_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1",
            oasis_analysis={
                "agents": [],
                "latest_package": {"config": {}, "agents": []},
                "latest_run": {"steps": [], "summary": "done"},
            },
            simulation_requirement="test req", component_models=None,
        )
        mock_db.execute.side_effect = [
            _scalar_one_or_none(project),
            _scalars_all(project.chapters),
            _scalar_one_or_none(None),
        ]
        mock_report = {"sections": [], "summary": "Report complete"}
        valid_analysis = {
            "scenario_summary": "Ready",
            "continuation_guidance": {"must_follow": ["rule1"], "next_steps": ["step1"], "avoid": []},
            "agent_profiles": [
                {
                    "name": "Agent1",
                    "role": "Analyst",
                    "persona": "Tracks narrative trends",
                    "stance": "neutral",
                    "likely_actions": ["Summarize events"],
                }
            ],
            "simulation_config": {
                "time_config": {
                    "total_hours": 48,
                    "minutes_per_round": 60,
                    "peak_hours": [19, 20],
                    "off_peak_hours": [1, 2],
                },
                "events": [{"title": "Kickoff", "trigger_hour": 1, "description": "Start"}],
                "agent_activity": [
                    {
                        "name": "Agent1",
                        "activity_level": 0.6,
                        "actions_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            },
            "latest_package": {"simulation_id": "sim-1", "content_hash": "h"},
            "latest_run": {"steps": [], "summary": "done", "content_hash": "h"},
        }

        with patch.object(_cg_mod, "generate_oasis_report", new_callable=AsyncMock) as mock_fn, \
             patch.object(_cg_mod, "_ensure_analysis_for_provenance", new_callable=AsyncMock, return_value=valid_analysis), \
             patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"):
            mock_fn.return_value = mock_report
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/report", json={},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["report"]["sections"] == mock_report["sections"]
            assert data["report"]["summary"] == mock_report["summary"]
            assert data["report"].get("content_hash")

    @pytest.mark.asyncio
    async def test_report_no_package(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis={},
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        valid_analysis = {
            "scenario_summary": "Ready",
            "continuation_guidance": {"must_follow": ["rule1"], "next_steps": ["step1"], "avoid": []},
            "agent_profiles": [
                {
                    "name": "Agent1",
                    "role": "Analyst",
                    "persona": "Tracks narrative trends",
                    "stance": "neutral",
                    "likely_actions": ["Summarize events"],
                }
            ],
            "simulation_config": {
                "time_config": {
                    "total_hours": 48,
                    "minutes_per_round": 60,
                    "peak_hours": [19, 20],
                    "off_peak_hours": [1, 2],
                },
                "events": [{"title": "Kickoff", "trigger_hour": 1, "description": "Start"}],
                "agent_activity": [
                    {
                        "name": "Agent1",
                        "activity_level": 0.6,
                        "actions_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            },
            "latest_package": {"simulation_id": "sim-1", "content_hash": "h"},
        }

        mock_report = {"sections": [], "summary": "generated"}
        with patch.object(
            _cg_mod,
            "_resolve_text",
            new_callable=AsyncMock,
            return_value=(
                "Some content",
                {
                    "source_chapter_ids": ["ch-1"],
                    "content_hash": "h",
                    "generated_at": "2026-01-01T00:00:00+00:00",
                },
            ),
        ), \
             patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"), \
             patch.object(_cg_mod, "_ensure_analysis_for_provenance", new_callable=AsyncMock, return_value=valid_analysis), \
             patch.object(_cg_mod, "generate_oasis_report", new_callable=AsyncMock, return_value=mock_report):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/report", json={},
            )
            assert resp.status_code == 200
            assert resp.json()["report"]["summary"] == "generated"

    @pytest.mark.asyncio
    async def test_report_no_run_result_auto_generates(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test report auto-generates run_result when missing."""
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1",
            oasis_analysis={
                "agents": [],
                "latest_package": {"config": {}, "agents": []},
            },
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.side_effect = [
            _scalar_one_or_none(project),
            _scalars_all(project.chapters),
            _scalar_one_or_none(None),
        ]
        mock_run = {"steps": [], "summary": "auto"}
        mock_report = {"sections": []}
        valid_analysis = {
            "scenario_summary": "Ready",
            "continuation_guidance": {"must_follow": ["rule1"], "next_steps": ["step1"], "avoid": []},
            "agent_profiles": [
                {
                    "name": "Agent1",
                    "role": "Analyst",
                    "persona": "Tracks narrative trends",
                    "stance": "neutral",
                    "likely_actions": ["Summarize events"],
                }
            ],
            "simulation_config": {
                "time_config": {
                    "total_hours": 48,
                    "minutes_per_round": 60,
                    "peak_hours": [19, 20],
                    "off_peak_hours": [1, 2],
                },
                "events": [{"title": "Kickoff", "trigger_hour": 1, "description": "Start"}],
                "agent_activity": [
                    {
                        "name": "Agent1",
                        "activity_level": 0.6,
                        "actions_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            },
            "latest_package": {"simulation_id": "sim-1", "content_hash": "h"},
        }

        with patch.object(_cg_mod, "build_oasis_run_result", return_value=mock_run), \
             patch.object(_cg_mod, "_ensure_analysis_for_provenance", new_callable=AsyncMock, return_value=valid_analysis), \
             patch.object(_cg_mod, "generate_oasis_report", new_callable=AsyncMock, return_value=mock_report), \
             patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/report", json={},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["report"]["sections"] == mock_report["sections"]
            assert data["report"].get("content_hash")


class TestOasisReportTask:
    """Test POST /api/projects/{id}/graphs/oasis/report/task."""

    @pytest.mark.asyncio
    async def test_report_task_starts(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
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
            ], ontology_schema={"entity_types": ["Person"]},
            cognee_dataset_id="dataset-1", oasis_analysis=None,
            simulation_requirement=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        nonce = datetime.now(timezone.utc).isoformat()

        with patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"), \
             patch.object(_cg_mod.asyncio, "create_task", side_effect=_close_and_stub_task) as mock_ct:
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/report/task", json={"report_model": f"gpt-4-{nonce}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["task"]["task_type"] == "oasis_report"
            assert data["task"]["status"] == "pending"
            mock_ct.assert_called_once()


class TestOasisTaskStatus:
    """Test GET /api/projects/{id}/graphs/oasis/tasks/{task_id}."""

    @pytest.mark.asyncio
    async def test_task_not_found(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id)
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch.object(_cg_mod, "task_manager") as mock_tm:
            mock_tm.get_task.return_value = None
            resp = await client.get(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/tasks/nonexistent-id",
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
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/tasks/some-task-id",
            )
            assert resp.status_code == 404
            assert "Task not found" in resp.json()["detail"]


class TestOasisTaskList:
    """Test GET /api/projects/{id}/graphs/oasis/tasks."""

    @pytest.mark.asyncio
    async def test_list_tasks(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id)
        mock_db.execute.return_value = _scalar_one_or_none(project)

        now = datetime.now(timezone.utc)
        fake_task = MagicMock()
        fake_task.to_dict.return_value = {
            "task_id": "task-1",
            "task_type": "oasis_prepare",
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
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/oasis/tasks",
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert len(data["tasks"]) == 1
            assert data["tasks"][0]["task_id"] == "task-1"


class TestGraphSearchExtended:
    """Test POST /api/projects/{id}/graphs/search - extended."""

    @pytest.mark.asyncio
    async def test_search_no_dataset_returns_400(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id,
            cognee_dataset_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/projects/11111111-1111-4111-8111-111111111111/graphs/search",
            json={"query": "find something"},
        )
        assert resp.status_code == 400
        assert "No graph data" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_search_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id,
            cognee_dataset_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_results = [{"content": "result1"}]

        with patch.object(_cg_mod, "search_graph", new_callable=AsyncMock, return_value=mock_results):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/search",
                json={"query": "find something"},
            )
            assert resp.status_code == 200
            assert resp.json()["results"] == mock_results


class TestGraphVisualizationSuccess:
    """Test GET /api/projects/{id}/graphs/visualization."""

    @pytest.mark.asyncio
    async def test_visualization_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id,
            cognee_dataset_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        mock_viz = {
            "nodes": [{"id": "n1", "label": "Person", "type": "ENTITY"}],
            "edges": [{"source": "n1", "target": "n2", "label": "KNOWS"}],
        }

        with patch.object(_cg_mod, "get_graph_visualization", new_callable=AsyncMock, return_value=mock_viz):
            resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/graphs/visualization")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["nodes"]) == 1
            assert len(data["edges"]) == 1
            assert data["nodes"][0]["label"] == "Person"

    @pytest.mark.asyncio
    async def test_visualization_runtime_error_returns_502(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111", user_id=fake_user.id,
            cognee_dataset_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        with patch.object(
            _cg_mod,
            "get_graph_visualization",
            new_callable=AsyncMock,
            side_effect=RuntimeError("graph backend unavailable"),
        ):
            resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/graphs/visualization")
            assert resp.status_code == 502
            assert "graph backend unavailable" in resp.json()["detail"]


class TestAddToGraphOntologyFromBody:
    """Test POST /api/projects/{id}/graphs with ontology in body."""

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
            cognee_dataset_id=None, component_models=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)
        body_ontology = {"entity_types": ["Character"]}

        with patch.object(_cg_mod, "build_graph_input_with_ontology", return_value="graph input"), \
             patch.object(_cg_mod, "resolve_component_model", return_value="gpt-4"), \
             patch.object(_cg_mod, "add_and_cognify", new_callable=AsyncMock, return_value="dataset-new"):
            resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs",
                json={"text": "Test content", "ontology": body_ontology},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["status"] == "ok"
            assert data["dataset_id"] == "dataset-new"
            assert project.ontology_schema == body_ontology


