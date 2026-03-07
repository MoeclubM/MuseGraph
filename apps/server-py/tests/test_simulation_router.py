"""Tests for simulation router endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

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


def _get_endpoint_globals(app, endpoint_name: str) -> dict:
    for route in app.routes:
        if hasattr(route, "endpoint") and getattr(route, "name", "") == endpoint_name:
            return route.endpoint.__globals__
        if hasattr(route, "routes"):
            for sub in route.routes:
                if hasattr(sub, "endpoint") and getattr(sub, "name", "") == endpoint_name:
                    return sub.endpoint.__globals__
    raise RuntimeError(f"Endpoint {endpoint_name!r} not found")


def _prepared_package(g: dict, provenance: dict, *, profile_name: str = "Agent1") -> dict:
    return g["_inject_provenance"](
        {
            "profiles": [
                {
                    "name": profile_name,
                    "role": "participant",
                    "persona": "Tracks narrative shifts",
                    "stance": "neutral",
                    "likely_actions": ["Post updates"],
                }
            ],
            "simulation_config": {
                "active_platforms": ["twitter"],
                "time_config": {
                    "total_hours": 24,
                    "minutes_per_round": 60,
                    "peak_hours": [19, 20],
                    "off_peak_hours": [1, 2],
                },
                "events": [{"title": "Kickoff", "trigger_hour": 1, "description": "Start"}],
                "agent_activity": [
                    {
                        "name": profile_name,
                        "activity_level": 0.6,
                        "posts_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            },
        },
        provenance,
    )


class TestSimulationCreate:
    """Test simulation creation endpoints."""

    @pytest.mark.asyncio
    async def test_create_simulation_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test successful simulation creation."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            cognee_dataset_id="dataset-1",
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Some content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
        )

        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/simulation/create",
            json={"project_id": "proj-1"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "simulation_id" in body["data"]

    @pytest.mark.asyncio
    async def test_create_simulation_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test creation with non-existent project returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.post(
            "/api/simulation/create",
            json={"project_id": "nonexistent"},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_simulation_no_graph(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test creation without graph returns 400."""
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            cognee_dataset_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/simulation/create",
            json={"project_id": "proj-1"},
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_simulation_unauthorized(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test creation on another user's project returns 403."""
        project = SimpleNamespace(
            id="proj-1",
            user_id="different-user-id",
            cognee_dataset_id="dataset-1",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            "/api/simulation/create",
            json={"project_id": "proj-1"},
        )

        assert resp.status_code == 403


class TestSimulationPrepare:
    """Test simulation prepare endpoints."""

    @pytest.mark.asyncio
    async def test_prepare_simulation_starts_task(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test prepare starts background task."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            status="created",
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/simulation/prepare",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        assert "task_id" in resp.json()["data"]

    @pytest.mark.asyncio
    async def test_prepare_simulation_already_ready(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test prepare returns early when already ready."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            status="ready",
            profiles=[{"name": "Agent1"}],
            simulation_config={
                "time_config": {"total_hours": 24},
                "content_hash": "hash-1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            run_state={},
            metadata_={},
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/simulation/prepare",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["already_prepared"] is True

    @pytest.mark.asyncio
    async def test_prepare_simulation_with_selected_chapters_starts_task(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test prepare with chapter_ids still starts work when runtime is not ready."""
        now = datetime.now(timezone.utc)
        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            status="created",
            profiles=[],
            simulation_config={},
            run_state={},
            metadata_={},
        )
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Some content",
                    order_index=0,
                    created_at=now,
                    updated_at=now,
                )
            ],
        )
        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
            _scalars_all(project.chapters),
        ]

        resp = await client.post(
            "/api/simulation/prepare",
            json={"simulation_id": "sim-1", "chapter_ids": ["ch-1"]},
        )

        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body.get("already_prepared") is not True
        assert "task_id" in body
        assert sim.status == "preparing"

    @pytest.mark.asyncio
    async def test_prepare_status_by_task(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting prepare status by task_id."""
        from app.services.task_state import task_manager

        task_manager.cleanup_old_tasks(max_age_hours=0)
        task = task_manager.create_task("simulation_prepare", metadata={"simulation_id": "sim-1"})
        task_manager.complete_task(task.task_id, result={}, message="Done")

        resp = await client.post(
            "/api/simulation/prepare/status",
            json={"task_id": task.task_id},
        )

        assert resp.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_prepare_status_by_simulation(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting prepare status by simulation_id."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            status="ready",
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/simulation/prepare/status",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "ready"


class TestSimulationStart:
    """Test simulation start endpoint."""

    @pytest.mark.asyncio
    async def test_start_simulation_success(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test starting simulation successfully."""
        from tests.conftest import app

        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            status="ready",
            profiles=[{"name": "Agent1"}],
            simulation_config={},
            run_state={},
            posts=[],
            comments=[],
            actions=[],
        )
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test",
            simulation_requirement="Test requirement",
            oasis_analysis={},
            ontology_schema={},
            component_models=None,
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Some content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
        ]
        g = _get_endpoint_globals(app, "start_simulation")
        expected_provenance = g["_build_provenance"](source_chapter_ids=[], text="Some content")
        package = _prepared_package(g, expected_provenance)
        mock_refresh = AsyncMock(
            return_value={"latest_package": package}
        )
        mock_build = AsyncMock(
            return_value=(
                {"metrics": {"total_rounds": 10}},
                [{"id": "post1"}],
                [],
                [{"action_id": "a1"}],
            )
        )
        orig_refresh = g["_refresh_project_analysis_with_provenance"]
        orig_build = g["_build_run_artifacts_with_llm"]
        g["_refresh_project_analysis_with_provenance"] = mock_refresh
        g["_build_run_artifacts_with_llm"] = mock_build
        try:
            resp = await client.post(
                "/api/simulation/start",
                json={"simulation_id": "sim-1"},
            )
        finally:
            g["_refresh_project_analysis_with_provenance"] = orig_refresh
            g["_build_run_artifacts_with_llm"] = orig_build

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_build_run_artifacts_salvages_invalid_top_level_json(self, mock_db: AsyncMock):
        from tests.conftest import app

        g = _get_endpoint_globals(app, "start_simulation")
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id="user-1",
            profiles=[
                {
                    "name": "Agent1",
                    "role": "participant",
                    "persona": "Tracks narrative shifts",
                    "stance": "neutral",
                }
            ],
            simulation_config={
                "active_platforms": ["twitter"],
                "time_config": {"total_hours": 24, "minutes_per_round": 60},
                "events": [],
                "agent_activity": [
                    {
                        "name": "Agent1",
                        "activity_level": 0.6,
                        "posts_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            },
        )
        project = SimpleNamespace(
            id="proj-1",
            simulation_requirement="Test requirement",
            oasis_analysis={
                "scenario_summary": "Scenario summary",
                "continuation_guidance": {
                    "must_follow": ["rule1"],
                    "next_steps": ["step1"],
                    "avoid": [],
                },
            },
            component_models=None,
        )
        run_result = {"metrics": {"total_rounds": 2}}
        malformed = (
            '{'
            '"rounds":['
            '{"round":1,"posts":[{"agent":"Agent1","platform":"twitter","content":"Post 1"}],"comments":[{"agent":"Agent1","platform":"twitter","content":"Comment 1"}],"actions":[{"agent":"Agent1","action_type":"share","summary":"Shared"}]},'
            '{"round":2,"posts":[{"agent":"Agent1","platform":"twitter","content":"Post 2"}],"comments":[],"actions":[{"agent":"Agent1","action_type":"react","summary":"Reacted"}]}'
            '],'
            '"highlights":["Highlight 1"]'
            '}'
        )

        orig_call = g["call_llm"]
        orig_extract = g["extract_json_object"]
        mock_call = AsyncMock(return_value={"content": malformed})
        g["call_llm"] = mock_call
        g["extract_json_object"] = MagicMock(return_value={"posts": [], "comments": [], "actions": []})
        try:
            updated_run, posts, comments, actions = await g["_build_run_artifacts_with_llm"](
                sim=sim,
                project=project,
                run_result=run_result,
                max_rounds=2,
                db=mock_db,
            )
            assert len(posts) == 2
            assert len(comments) == 1
            assert any(action["action_type"] == "share" for action in actions)
            assert "highlights" not in updated_run
            assert mock_call.await_args.kwargs["max_tokens"] > 1024
        finally:
            g["call_llm"] = orig_call
            g["extract_json_object"] = orig_extract

    @pytest.mark.asyncio
    async def test_start_simulation_created_syncs_runtime_from_package(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test start can hydrate a created simulation from the latest prepared package."""
        from tests.conftest import app

        now = datetime.now(timezone.utc)
        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            status="created",
            profiles=[],
            simulation_config={},
            run_state={},
            posts=[],
            comments=[],
            actions=[],
            env_status={},
            metadata_={},
        )
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test",
            simulation_requirement="Test requirement",
            oasis_analysis={},
            ontology_schema={},
            component_models=None,
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Some content",
                    order_index=0,
                    created_at=now,
                    updated_at=now,
                )
            ],
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
        ]
        g = _get_endpoint_globals(app, "start_simulation")
        expected_provenance = g["_build_provenance"](source_chapter_ids=[], text="Some content")
        package = _prepared_package(g, expected_provenance)
        analysis = {"latest_package": package}
        mock_refresh = AsyncMock(return_value=analysis)
        mock_build = AsyncMock(
            return_value=(
                {"metrics": {"total_rounds": 6}},
                [{"id": "post1"}],
                [],
                [{"action_id": "a1"}],
            )
        )
        orig_refresh = g["_refresh_project_analysis_with_provenance"]
        orig_build = g["_build_run_artifacts_with_llm"]
        g["_refresh_project_analysis_with_provenance"] = mock_refresh
        g["_build_run_artifacts_with_llm"] = mock_build
        try:
            resp = await client.post(
                "/api/simulation/start",
                json={"simulation_id": "sim-1"},
            )
        finally:
            g["_refresh_project_analysis_with_provenance"] = orig_refresh
            g["_build_run_artifacts_with_llm"] = orig_build

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"
        assert sim.profiles[0]["name"] == "Agent1"
        assert sim.simulation_config["content_hash"] == expected_provenance["content_hash"]
        assert project.oasis_analysis["latest_run"]["content_hash"] == expected_provenance["content_hash"]

    @pytest.mark.asyncio
    async def test_start_simulation_created_auto_prepares_runtime(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test starting from created auto-prepares runtime before generating artifacts."""
        from tests.conftest import app

        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            status="created",
            profiles=[],
            simulation_config={},
            run_state={},
            posts=[],
            comments=[],
            actions=[],
            metadata_={},
        )
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test",
            simulation_requirement="Test requirement",
            oasis_analysis={},
            ontology_schema={},
            component_models=None,
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Some content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
        ]
        g = _get_endpoint_globals(app, "start_simulation")
        expected_provenance = g["_build_provenance"](source_chapter_ids=[], text="Some content")
        package = _prepared_package(g, expected_provenance)
        mock_refresh = AsyncMock(return_value={"latest_package": package})
        mock_build = AsyncMock(
            return_value=(
                {"metrics": {"total_rounds": 10}},
                [{"id": "post1"}],
                [],
                [{"action_id": "a1"}],
            )
        )
        orig_refresh = g["_refresh_project_analysis_with_provenance"]
        orig_build = g["_build_run_artifacts_with_llm"]
        g["_refresh_project_analysis_with_provenance"] = mock_refresh
        g["_build_run_artifacts_with_llm"] = mock_build
        try:
            resp = await client.post(
                "/api/simulation/start",
                json={"simulation_id": "sim-1"},
            )
        finally:
            g["_refresh_project_analysis_with_provenance"] = orig_refresh
            g["_build_run_artifacts_with_llm"] = orig_build

        assert resp.status_code == 200
        assert sim.profiles
        assert sim.simulation_config["content_hash"] == expected_provenance["content_hash"]
        assert resp.json()["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_start_simulation_preparing_with_prepared_runtime_succeeds(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test preparing status can recover when runtime artifacts are already prepared."""
        from tests.conftest import app

        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test",
            simulation_requirement="Test requirement",
            oasis_analysis={},
            ontology_schema={},
            component_models=None,
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Some content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
        )

        g = _get_endpoint_globals(app, "start_simulation")
        expected_provenance = g["_build_provenance"](source_chapter_ids=[], text="Some content")
        package = _prepared_package(g, expected_provenance)
        profiles, config = g["_resolve_prepared_runtime"](package, project)
        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            status="preparing",
            profiles=profiles,
            simulation_config=g["_inject_provenance"](dict(config), expected_provenance),
            run_state={"status": "ready", "content_hash": expected_provenance["content_hash"]},
            posts=[],
            comments=[],
            actions=[],
            metadata_={
                "source_chapter_ids": [],
                "content_hash": expected_provenance["content_hash"],
                "generated_at": expected_provenance["generated_at"],
            },
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
        ]
        mock_refresh = AsyncMock(return_value={"latest_package": package})
        mock_build = AsyncMock(
            return_value=(
                {"metrics": {"total_rounds": 10}},
                [{"id": "post1"}],
                [],
                [{"action_id": "a1"}],
            )
        )
        orig_refresh = g["_refresh_project_analysis_with_provenance"]
        orig_build = g["_build_run_artifacts_with_llm"]
        g["_refresh_project_analysis_with_provenance"] = mock_refresh
        g["_build_run_artifacts_with_llm"] = mock_build
        try:
            resp = await client.post(
                "/api/simulation/start",
                json={"simulation_id": "sim-1"},
            )
        finally:
            g["_refresh_project_analysis_with_provenance"] = orig_refresh
            g["_build_run_artifacts_with_llm"] = orig_build

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_start_simulation_llm_failure_returns_422(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test start fails fast when LLM generation returns invalid artifacts."""
        from tests.conftest import app

        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            status="ready",
            profiles=[{"name": "Agent1"}],
            simulation_config={},
            run_state={},
            posts=[],
            comments=[],
            actions=[],
        )
        project = SimpleNamespace(
            id="proj-1",
            user_id=fake_user.id,
            title="Test",
            simulation_requirement="Req",
            oasis_analysis={},
            ontology_schema={},
            component_models=None,
            chapters=[
                SimpleNamespace(
                    id="ch-1",
                    project_id="proj-1",
                    title="Main Draft",
                    content="Some content",
                    order_index=0,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            ],
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
        ]
        g = _get_endpoint_globals(app, "start_simulation")
        expected_provenance = g["_build_provenance"](source_chapter_ids=[], text="Some content")
        package = _prepared_package(g, expected_provenance)
        mock_refresh = AsyncMock(
            return_value={"latest_package": package}
        )
        mock_build = AsyncMock(
            side_effect=ValueError("simulation_run_llm_response_not_json_or_invalid_schema")
        )
        orig_refresh = g["_refresh_project_analysis_with_provenance"]
        orig_build = g["_build_run_artifacts_with_llm"]
        g["_refresh_project_analysis_with_provenance"] = mock_refresh
        g["_build_run_artifacts_with_llm"] = mock_build
        try:
            resp = await client.post(
                "/api/simulation/start",
                json={"simulation_id": "sim-1"},
            )
        finally:
            g["_refresh_project_analysis_with_provenance"] = orig_refresh
            g["_build_run_artifacts_with_llm"] = orig_build

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_start_simulation_not_runnable(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test start when simulation not in runnable state."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            status="preparing",
            profiles=[],
            simulation_config={},
            run_state={},
            metadata_={},
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/simulation/start",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 400
        assert "still preparing" in resp.json()["detail"]


class TestSimulationStop:
    """Test simulation stop endpoint."""

    @pytest.mark.asyncio
    async def test_stop_simulation(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test stopping simulation."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            status="running",
            run_state={"is_running": True},
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/simulation/stop",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "stopped"


class TestSimulationList:
    """Test simulation listing endpoints."""

    @pytest.mark.asyncio
    async def test_list_simulations(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test listing simulations."""
        sims = [
            SimpleNamespace(
                simulation_id="sim-1",
                project_id="proj-1",
                user_id=fake_user.id,
                status="completed",
                simulation_config={},
                profiles=[],
                run_state={},
                env_status={},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]
        mock_db.execute.return_value = _scalars_all(sims)

        resp = await client.get("/api/simulation/list")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    @pytest.mark.asyncio
    async def test_list_simulations_by_project(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test listing simulations filtered by project."""
        mock_db.execute.return_value = _scalars_all([])

        resp = await client.get("/api/simulation/list?project_id=proj-1")

        assert resp.status_code == 200


class TestSimulationGet:
    """Test simulation retrieval endpoints."""

    @pytest.mark.asyncio
    async def test_get_simulation(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting simulation by ID."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            status="completed",
            simulation_config={},
            profiles=[],
            run_state={},
            env_status={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1")

        assert resp.status_code == 200
        assert resp.json()["data"]["simulation_id"] == "sim-1"

    @pytest.mark.asyncio
    async def test_get_simulation_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        """Test getting non-existent simulation returns 404."""
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await client.get("/api/simulation/nonexistent")

        assert resp.status_code == 404


class TestSimulationRunStatus:
    """Test run status endpoints."""

    @pytest.mark.skip(reason="Complex nested mock structure - endpoint tested via integration")
    @pytest.mark.asyncio
    async def test_get_run_status(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting run status."""
        pass

    @pytest.mark.skip(reason="Complex nested mock structure - endpoint tested via integration")
    @pytest.mark.asyncio
    async def test_get_run_status_detail(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting detailed run status."""
        pass


class TestSimulationActions:
    """Test actions endpoint."""

    @pytest.mark.asyncio
    async def test_get_actions(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting simulation actions."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            actions=[
                {"action_id": "a1", "agent": "Agent1"},
                {"action_id": "a2", "agent": "Agent2"},
            ],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/actions")

        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    @pytest.mark.asyncio
    async def test_get_actions_pagination(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test actions pagination."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            actions=[{"action_id": f"a{i}"} for i in range(100)],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/actions?limit=10&offset=20")

        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 10


class TestSimulationTimeline:
    """Test timeline endpoint."""

    @pytest.mark.asyncio
    async def test_get_timeline(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting simulation timeline."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            posts=[
                {"round_num": 1, "content": "Post 1"},
                {"round_num": 2, "content": "Post 2"},
            ],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/timeline")

        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    @pytest.mark.asyncio
    async def test_get_timeline_with_range(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test timeline with round range."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            posts=[
                {"round_num": 1},
                {"round_num": 2},
                {"round_num": 3},
                {"round_num": 4},
            ],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/timeline?start_round=2&end_round=3")

        assert resp.status_code == 200


class TestSimulationPosts:
    """Test posts endpoint."""

    @pytest.mark.asyncio
    async def test_get_posts(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting simulation posts."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            posts=[
                {"id": "p1", "platform": "twitter"},
                {"id": "p2", "platform": "reddit"},
            ],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/posts")

        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    @pytest.mark.asyncio
    async def test_get_posts_by_platform(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test filtering posts by platform."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            posts=[
                {"id": "p1", "platform": "twitter"},
                {"id": "p2", "platform": "reddit"},
            ],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/posts?platform=twitter")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 1


class TestSimulationComments:
    """Test comments endpoint."""

    @pytest.mark.asyncio
    async def test_get_comments(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting simulation comments."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            comments=[{"id": "c1"}, {"id": "c2"}],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/comments")

        assert resp.status_code == 200
        assert resp.json()["count"] == 2


class TestSimulationProfiles:
    """Test profiles endpoint."""

    @pytest.mark.asyncio
    async def test_get_profiles(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting simulation profiles."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            profiles=[{"name": "Agent1"}, {"name": "Agent2"}],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/profiles")

        assert resp.status_code == 200
        assert resp.json()["data"]["total_expected"] == 2


class TestSimulationConfig:
    """Test config endpoint."""

    @pytest.mark.asyncio
    async def test_get_config(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting simulation config."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            simulation_config={"active_platforms": ["twitter"]},
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/config")

        assert resp.status_code == 200
        assert "active_platforms" in resp.json()["data"]


class TestAgentStats:
    """Test agent stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_agent_stats(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting agent statistics."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            profiles=[{"name": "Agent1"}, {"name": "Agent2"}],
            posts=[{"agent": "Agent1"}, {"agent": "Agent1"}, {"agent": "Agent2"}],
            comments=[{"agent": "Agent2"}],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.get("/api/simulation/sim-1/agent-stats")

        assert resp.status_code == 200
        stats = {s["agent"]: s for s in resp.json()["data"]}
        assert stats["Agent1"]["posts"] == 2
        assert stats["Agent2"]["comments"] == 1


class TestInterview:
    """Test interview endpoints."""

    @pytest.mark.asyncio
    async def test_interview_single(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test single agent interview."""
        from tests.conftest import app

        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            profiles=[{"name": "Agent1", "role": "User"}],
            interview_history=[],
        )
        project = SimpleNamespace(
            id="proj-1",
            simulation_requirement="Test requirement",
            component_models=None,
        )

        mock_db.execute.return_value = _scalar_one_or_none(sim)
        g = _get_endpoint_globals(app, "interview_one")
        mock_interview = AsyncMock(
            return_value={
                "simulation_id": "sim-1",
                "agent": "Agent1",
                "agent_role": "User",
                "prompt": "What do you think?",
                "response": "Agent response",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        orig_interview = g["_interview_single"]
        g["_interview_single"] = mock_interview
        try:
            resp = await client.post(
                "/api/simulation/interview",
                json={"simulation_id": "sim-1", "prompt": "What do you think?"},
            )
        finally:
            g["_interview_single"] = orig_interview

        assert resp.status_code == 200
        assert "response" in resp.json()["data"]

    @pytest.mark.asyncio
    async def test_interview_batch(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test batch interview."""
        from tests.conftest import app

        sim = SimpleNamespace(
            simulation_id="sim-1",
            project_id="proj-1",
            user_id=fake_user.id,
            profiles=[{"name": "Agent1"}, {"name": "Agent2"}],
            interview_history=[],
        )
        project = SimpleNamespace(
            id="proj-1",
            simulation_requirement="Test",
            component_models=None,
        )

        mock_db.execute.return_value = _scalar_one_or_none(sim)
        g = _get_endpoint_globals(app, "interview_batch")
        mock_interview = AsyncMock(
            side_effect=[
                {
                    "simulation_id": "sim-1",
                    "agent": "Agent1",
                    "agent_role": "User",
                    "prompt": "Question 1",
                    "response": "Response",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "simulation_id": "sim-1",
                    "agent": "Agent2",
                    "agent_role": "User",
                    "prompt": "Question 2",
                    "response": "Response",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            ]
        )
        orig_interview = g["_interview_single"]
        g["_interview_single"] = mock_interview
        try:
            resp = await client.post(
                "/api/simulation/interview/batch",
                json={
                    "simulation_id": "sim-1",
                    "interviews": [
                        {"prompt": "Question 1"},
                        {"prompt": "Question 2"},
                    ],
                },
            )
        finally:
            g["_interview_single"] = orig_interview

        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    @pytest.mark.asyncio
    async def test_interview_history(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting interview history."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            interview_history=[
                {"prompt": "Q1", "response": "A1"},
                {"prompt": "Q2", "response": "A2"},
            ],
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/simulation/interview/history",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        assert resp.json()["count"] == 2


class TestEnvStatus:
    """Test environment status endpoints."""

    @pytest.mark.asyncio
    async def test_get_env_status(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test getting environment status."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            env_status={"alive": True, "status": "running"},
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/simulation/env-status",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["env_alive"] is True

    @pytest.mark.asyncio
    async def test_close_env(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        """Test closing simulation environment."""
        sim = SimpleNamespace(
            simulation_id="sim-1",
            user_id=fake_user.id,
            status="running",
            env_status={"alive": True},
        )
        mock_db.execute.return_value = _scalar_one_or_none(sim)

        resp = await client.post(
            "/api/simulation/close-env",
            json={"simulation_id": "sim-1"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["closed"] is True


class TestHelperFunctions:
    """Test simulation helper functions."""

    def test_ensure_list(self):
        """Test _ensure_list helper."""
        from app.routers.simulation import _ensure_list

        assert _ensure_list([1, 2]) == [1, 2]
        assert _ensure_list("not a list") == []
        assert _ensure_list(None) == []

    def test_ensure_dict(self):
        """Test _ensure_dict helper."""
        from app.routers.simulation import _ensure_dict

        assert _ensure_dict({"a": 1}) == {"a": 1}
        assert _ensure_dict("not a dict") == {}
        assert _ensure_dict(None) == {}

    def test_split_timeline(self):
        """Test _split_timeline helper."""
        from app.routers.simulation import _split_timeline

        posts = [
            {"round_num": 1, "content": "A"},
            {"round_num": 2, "content": "B"},
            {"round_num": 1, "content": "C"},
        ]
        result = _split_timeline(posts)

        assert len(result) == 2
        assert len(result[0]["posts"]) == 2
