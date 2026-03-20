"""Tests for graph construction and OASIS analysis endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.routers import cognee_graph
from app.services.task_state import task_manager
from tests.conftest import TEST_USER_ID, app as app_instance


def _make_project(
    *,
    project_id: str | None = None,
    user_id: str = TEST_USER_ID,
    chapter_content: str | None = "Base text",
    ontology_schema: dict | None = None,
    oasis_analysis: dict | None = None,
    cognee_dataset_id: str | None = None,
):
    return SimpleNamespace(
        id=project_id or str(uuid.uuid4()),
        user_id=user_id,
        title="Graph Project",
        description="desc",
        chapters=[
            SimpleNamespace(
                id=str(uuid.uuid4()),
                project_id=project_id or "proj-1",
                title="Main Draft",
                content=chapter_content or "",
                order_index=0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ],
        simulation_requirement=None,
        component_models={
            "ontology_generation": "gpt-4o-mini",
            "oasis_analysis": "gpt-4o-mini",
            "oasis_simulation_config": "gpt-4o-mini",
            "oasis_report": "gpt-4o-mini",
        },
        ontology_schema=ontology_schema,
        oasis_analysis=oasis_analysis,
        cognee_dataset_id=cognee_dataset_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _endpoint(path: str, method: str):
    method_upper = method.upper()
    for route in app_instance.routes:
        route_path = getattr(route, "path", None)
        route_methods = set(getattr(route, "methods", set()))
        if route_path == path and method_upper in route_methods:
            return route.endpoint
    raise AssertionError(f"Route not found: {method_upper} {path}")


@pytest.fixture(autouse=True)
def _reset_task_manager():
    try:
        task_manager._memory._tasks.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        sqlite_store = getattr(task_manager, "_sqlite", None)
        if sqlite_store is not None:
            with sqlite_store._lock:  # type: ignore[attr-defined]
                sqlite_store._conn.execute("DELETE FROM task_records")  # type: ignore[attr-defined]
                sqlite_store._conn.commit()  # type: ignore[attr-defined]
    except Exception:
        pass
    yield
    try:
        task_manager._memory._tasks.clear()  # type: ignore[attr-defined]
    except Exception:
        pass


class TestCogneeGraphFlow:
    def test_latest_running_graph_task_ignores_stale_processing_task(self):
        task = task_manager.create_task(
            "graph_build",
            metadata={"project_id": "project-1", "user_id": TEST_USER_ID},
        )
        task.status = cognee_graph.TaskStatus.PROCESSING
        task.progress = 32
        task.message = "Graphiti ingesting episodes 4/112..."
        task.updated_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=300)
        task_manager._memory.update_task(task)  # type: ignore[attr-defined]

        running = cognee_graph._latest_running_graph_task("project-1")

        assert running is None
        refreshed = task_manager.get_task(task.task_id)
        assert refreshed is not None
        assert refreshed.status == cognee_graph.TaskStatus.FAILED
        assert refreshed.message == "Graph build task timed out"

    @pytest.mark.asyncio
    async def test_list_tasks_invalid_project_id_returns_422(self, client: AsyncClient):
        resp = await client.get("/api/projects/undefined/graphs/tasks")

        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid project id"

    @pytest.mark.asyncio
    async def test_get_graph_status_marks_empty_store_as_stale(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = _make_project(
            project_id="11111111-1111-4111-8111-111111111111",
            ontology_schema={"entity_types": [{"name": "Character"}]},
            cognee_dataset_id="graph-1",
            oasis_analysis={
                "_graph_build_state": {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "chapter_hashes": {"chapter-1": "hash-1"},
                }
            },
        )
        chapter_row = (str(project.chapters[0].id), datetime.now(timezone.utc))
        chapter_result = MagicMock()
        chapter_result.all.return_value = [chapter_row]
        mock_db.execute.side_effect = [_scalar_one_or_none(project), chapter_result]
        monkeypatch.setattr(cognee_graph, "has_graph_data", AsyncMock(return_value=False))

        resp = await client.get(f"/api/projects/{project.id}/graphs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["graph_freshness"] == "stale"
        assert body["graph_reason"] == "graph_store_empty_or_unreadable"

    @pytest.mark.asyncio
    async def test_generate_ontology_success(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = _make_project(chapter_content="Project content")
        mock_db.execute.return_value = _scalar_one_or_none(project)
        generate_endpoint = _endpoint("/api/projects/{project_id}/graphs/ontology/generate", "POST")
        monkeypatch.setitem(
            generate_endpoint.__globals__,
            "resolve_component_model",
            lambda *_args, **_kwargs: "gpt-4o-mini",
        )
        monkeypatch.setitem(
            generate_endpoint.__globals__,
            "generate_ontology",
            AsyncMock(return_value={"entity_types": [{"name": "Character"}], "edge_types": [{"name": "REL"}]}),
        )
        resp = await client.post(
            f"/api/projects/{project.id}/graphs/ontology/generate",
            json={"text": "source text", "requirement": "simulate risk", "model": "model-ontology"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "entity_types" in body["ontology"]
        assert "edge_types" in body["ontology"]
        assert isinstance(project.ontology_schema, dict)
        assert project.ontology_schema.get("entity_types") is not None
        assert project.simulation_requirement == "simulate risk"

    @pytest.mark.asyncio
    async def test_generate_ontology_uses_body_text_when_selected_chapter_empty(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = _make_project(chapter_content="")
        chapter_query_result = MagicMock()
        chapter_query_scalars = MagicMock()
        chapter_query_scalars.all.return_value = project.chapters
        chapter_query_result.scalars.return_value = chapter_query_scalars
        mock_db.execute.side_effect = [
            _scalar_one_or_none(project),
            chapter_query_result,
        ]
        generate_endpoint = _endpoint("/api/projects/{project_id}/graphs/ontology/generate", "POST")
        monkeypatch.setitem(
            generate_endpoint.__globals__,
            "resolve_component_model",
            lambda *_args, **_kwargs: "gpt-4o-mini",
        )
        monkeypatch.setitem(
            generate_endpoint.__globals__,
            "generate_ontology",
            AsyncMock(return_value={"entity_types": [{"name": "Character"}], "edge_types": [{"name": "REL"}]}),
        )

        resp = await client.post(
            f"/api/projects/{project.id}/graphs/ontology/generate",
            json={
                "text": "unsaved editor content",
                "chapter_ids": [project.chapters[0].id],
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["ontology"].get("entity_types") is not None

    @pytest.mark.asyncio
    async def test_add_graph_requires_ontology(self, client: AsyncClient, mock_db: AsyncMock):
        project = _make_project(ontology_schema=None)
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            f"/api/projects/{project.id}/graphs",
            json={"text": "graph source"},
        )

        assert resp.status_code == 400
        assert "Ontology not generated" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_add_graph_success(self, client: AsyncClient, mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch):
        project = _make_project(ontology_schema={"entity_types": [{"name": "Actor"}], "edge_types": []})
        mock_db.execute.return_value = _scalar_one_or_none(project)
        cognify_mock = AsyncMock(return_value="dataset-001")
        add_graph_endpoint = _endpoint("/api/projects/{project_id}/graphs", "POST")
        monkeypatch.setitem(add_graph_endpoint.__globals__, "build_graph_input_with_ontology", lambda _text, _ontology: "graph input")
        monkeypatch.setitem(add_graph_endpoint.__globals__, "add_and_cognify", cognify_mock)

        resp = await client.post(
            f"/api/projects/{project.id}/graphs",
            json={"text": "graph source"},
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["dataset_id"] == "dataset-001"
        assert project.cognee_dataset_id == "dataset-001"
        cognify_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_oasis_analyze_requires_graph(self, client: AsyncClient, mock_db: AsyncMock):
        project = _make_project(
            ontology_schema={"entity_types": [{"name": "Actor"}], "edge_types": []},
            cognee_dataset_id=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            f"/api/projects/{project.id}/graphs/oasis/analyze",
            json={"text": "source"},
        )

        assert resp.status_code == 400
        assert "Graph not built" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_oasis_sync_pipeline_success(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = _make_project(
            ontology_schema={"entity_types": [{"name": "Actor"}], "edge_types": [{"name": "links"}]},
            cognee_dataset_id="dataset-001",
            chapter_content="Base content",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        analysis = {
            "scenario_summary": "Scenario summary",
            "key_drivers": ["driver-a"],
            "continuation_guidance": {"next_steps": ["step-a"]},
            "simulation_config": {"time_config": {"total_hours": 24, "minutes_per_round": 60}},
        }
        context = {"node_count": 12, "edge_count": 20}
        package = {"simulation_id": "sim-001", "profiles": [{"name": "Agent"}], "simulation_config": {}}
        run_result = {"run_id": "run-001", "metrics": {"total_rounds": 24}}
        report = {"report_id": "report-001", "title": "OASIS Report", "executive_summary": "summary"}

        async def _fake_generate_and_store(**kwargs):
            kwargs["project"].oasis_analysis = analysis
            return analysis, context

        analyze_mock = AsyncMock(side_effect=_fake_generate_and_store)
        report_mock = AsyncMock(return_value=report)
        package_mock = MagicMock(return_value=package)
        run_mock = MagicMock(return_value=run_result)
        analyze_endpoint = _endpoint("/api/projects/{project_id}/graphs/oasis/analyze", "POST")
        prepare_endpoint = _endpoint("/api/projects/{project_id}/graphs/oasis/prepare", "POST")
        run_endpoint = _endpoint("/api/projects/{project_id}/graphs/oasis/run", "POST")
        report_endpoint = _endpoint("/api/projects/{project_id}/graphs/oasis/report", "POST")
        monkeypatch.setitem(analyze_endpoint.__globals__, "_generate_and_store_oasis_analysis", analyze_mock)
        monkeypatch.setitem(prepare_endpoint.__globals__, "build_oasis_package", package_mock)
        monkeypatch.setitem(run_endpoint.__globals__, "build_oasis_run_result", run_mock)
        monkeypatch.setitem(report_endpoint.__globals__, "generate_oasis_report", report_mock)
        monkeypatch.setitem(report_endpoint.__globals__, "build_oasis_run_result", run_mock)
        monkeypatch.setitem(
            run_endpoint.__globals__,
            "_resolve_chapters_for_project",
            AsyncMock(return_value=project.chapters),
        )

        analyze_resp = await client.post(
            f"/api/projects/{project.id}/graphs/oasis/analyze",
            json={"text": "source", "requirement": "focus risk", "analysis_model": "m-analyze", "simulation_model": "m-sim"},
        )
        prepare_resp = await client.post(
            f"/api/projects/{project.id}/graphs/oasis/prepare",
            json={"text": "source"},
        )
        run_resp = await client.post(
            f"/api/projects/{project.id}/graphs/oasis/run",
            json={"chapter_ids": [project.chapters[0].id]},
        )
        report_resp = await client.post(
            f"/api/projects/{project.id}/graphs/oasis/report",
            json={"report_model": "m-report", "chapter_ids": [project.chapters[0].id]},
        )

        assert analyze_resp.status_code == 200, analyze_resp.text
        assert analyze_resp.json()["analysis"]["scenario_summary"] == "Scenario summary"
        assert analyze_resp.json()["context"]["node_count"] == 12
        assert project.oasis_analysis["scenario_summary"] == "Scenario summary"
        assert project.simulation_requirement == "focus risk"

        assert prepare_resp.status_code == 200, prepare_resp.text
        assert prepare_resp.json()["package"]["simulation_id"] == "sim-001"
        assert project.oasis_analysis["latest_package"]["simulation_id"] == "sim-001"

        assert run_resp.status_code == 200, run_resp.text
        assert run_resp.json()["run_result"]["run_id"] == "run-001"
        assert project.oasis_analysis["latest_run"]["run_id"] == "run-001"

        assert report_resp.status_code == 200, report_resp.text
        assert report_resp.json()["report"]["report_id"] == "report-001"
        assert project.oasis_analysis["latest_report"]["report_id"] == "report-001"

        assert run_resp.json()["run_result"].get("source_chapter_ids") == [project.chapters[0].id]
        assert report_resp.json()["report"].get("source_chapter_ids") == [project.chapters[0].id]

        assert analyze_mock.await_count >= 1
        assert package_mock.call_count >= 1
        assert run_mock.call_count >= 1
        assert report_mock.await_count >= 1

    @pytest.mark.asyncio
    async def test_oasis_task_prepare_and_query(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = _make_project(
            ontology_schema={"entity_types": [{"name": "Actor"}], "edge_types": []},
            cognee_dataset_id="dataset-001",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        def _fake_create_task(coro):
            coro.close()
            return MagicMock()

        task_prepare_endpoint = _endpoint("/api/projects/{project_id}/graphs/oasis/prepare/task", "POST")
        monkeypatch.setitem(task_prepare_endpoint.__globals__, "asyncio", SimpleNamespace(create_task=_fake_create_task))
        start_resp = await client.post(
            f"/api/projects/{project.id}/graphs/oasis/prepare/task",
            json={"text": "source"},
        )

        assert start_resp.status_code == 200
        start_body = start_resp.json()
        assert start_body["status"] == "accepted"
        assert start_body["task"]["task_type"] == "oasis_prepare"

        task_id = start_body["task"]["task_id"]
        status_resp = await client.get(f"/api/projects/{project.id}/graphs/oasis/tasks/{task_id}")
        list_resp = await client.get(f"/api/projects/{project.id}/graphs/oasis/tasks")

        assert status_resp.status_code == 200
        assert status_resp.json()["task"]["task_id"] == task_id
        assert list_resp.status_code == 200
        assert any(item["task_id"] == task_id for item in list_resp.json()["tasks"])

@pytest.mark.asyncio
async def test_resolve_chapters_queries_db_without_touching_lazy_relationship():
    from app.routers import cognee_graph as cognee_graph_router

    chapter = SimpleNamespace(
        id="chapter-1",
        project_id="proj-1",
        title="Main Draft",
        content="body",
        order_index=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    class _LazyProject(SimpleNamespace):
        @property
        def chapters(self):
            raise AssertionError("lazy relationship should not be touched")

    project = _LazyProject(id="proj-1")
    query_result = MagicMock()
    query_scalars = MagicMock()
    query_scalars.all.return_value = [chapter]
    query_result.scalars.return_value = query_scalars
    db = AsyncMock()
    db.execute.return_value = query_result

    chapters = await cognee_graph_router._resolve_chapters_for_project(project, None, db)

    assert [item.id for item in chapters] == ["chapter-1"]
    db.execute.assert_awaited_once()


class TestCogneeGraphTaskErrors:
    def test_describe_task_exception_keeps_message(self):
        from app.routers import cognee_graph as cognee_graph_router

        assert cognee_graph_router._describe_task_exception(RuntimeError("build failed")) == "build failed"

    def test_describe_task_exception_falls_back_to_type_and_repr(self):
        from app.routers import cognee_graph as cognee_graph_router

        error = RuntimeError()
        described = cognee_graph_router._describe_task_exception(error)

        assert described.startswith("RuntimeError:")
        assert "RuntimeError()" in described
