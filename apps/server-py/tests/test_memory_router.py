"""Tests for memory construction endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.routers import memory
from app.services.creative_workflow import chapter_memory_hash, chapter_memory_text
from app.services.task_state import task_manager
from tests.conftest import TEST_USER_ID, get_app_endpoint, iter_app_routes


def _make_project(
    *,
    project_id: str | None = None,
    user_id: str = TEST_USER_ID,
    chapter_content: str | None = "Base text",
    ontology_schema: dict | None = None,
    memory_id: str | None = None,
):
    return SimpleNamespace(
        id=project_id or str(uuid.uuid4()),
        user_id=user_id,
        visibility="private",
        members=[],
        title="Memory Project",
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
        component_models={
            "ontology_generation": "gpt-4o-mini",
            "memory_build": "gpt-4o-mini",
        },
        ontology_schema=ontology_schema,
        memory_id=memory_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


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


def _endpoint(path: str, method: str):
    return get_app_endpoint(path, method)


@pytest.fixture(autouse=True)
def _reset_task_manager():
    try:
        task_manager._memory._tasks.clear()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        task_manager._runners.clear()  # type: ignore[attr-defined]
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
    try:
        task_manager._runners.clear()  # type: ignore[attr-defined]
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _stub_workspace_snapshot(monkeypatch: pytest.MonkeyPatch):
    snapshot = AsyncMock()
    monkeypatch.setattr(memory, "write_project_workspace_version_snapshot_from_db", snapshot)
    for route in iter_app_routes():
        endpoint = getattr(route, "endpoint", None)
        globals_ = getattr(endpoint, "__globals__", None)
        if isinstance(globals_, dict) and "write_project_workspace_version_snapshot_from_db" in globals_:
            monkeypatch.setitem(globals_, "write_project_workspace_version_snapshot_from_db", snapshot)


class TestMemoryMemoryFlow:
    def test_latest_running_memory_task_ignores_stale_processing_task(self):
        task = task_manager.create_task(
            "memory_build",
            metadata={"project_id": "project-1", "user_id": TEST_USER_ID},
        )
        task.status = memory.TaskStatus.PROCESSING
        task.progress = 32
        task.message = "Cognee ingesting chunks 4/112..."
        task.updated_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=300)
        task_manager._memory.update_task(task)  # type: ignore[attr-defined]

        running = memory._latest_running_memory_task("project-1")

        assert running is None
        refreshed = task_manager.get_task(task.task_id)
        assert refreshed is not None
        assert refreshed.status == memory.TaskStatus.FAILED
        assert refreshed.message == "Memory build task timed out"

    def test_latest_running_memory_task_keeps_stale_task_with_active_runner(self):
        task = task_manager.create_task(
            "memory_build",
            metadata={"project_id": "project-1", "user_id": TEST_USER_ID},
        )
        task.status = memory.TaskStatus.PROCESSING
        task.progress = 32
        task.message = "Cognee ingesting chunks 4/112..."
        task.updated_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=300)
        task_manager._memory.update_task(task)  # type: ignore[attr-defined]
        runner = MagicMock()
        runner.done.return_value = False
        task_manager.register_runner(task.task_id, runner)

        running = memory._latest_running_memory_task("project-1")

        assert running is not None
        assert running.task_id == task.task_id
        refreshed = task_manager.get_task(task.task_id)
        assert refreshed is not None
        assert refreshed.status == memory.TaskStatus.PROCESSING
        assert refreshed.message == "Cognee ingesting chunks 4/112..."

    def test_start_project_task_cancels_older_auto_memory_sync_task(self, monkeypatch: pytest.MonkeyPatch):
        old_task = task_manager.create_task(
            "memory_build",
            metadata={
                "project_id": "project-1",
                "user_id": TEST_USER_ID,
                "idempotency_key": "memory_build:old",
                "auto_created": True,
                "trigger_source_kind": "chapter",
            },
        )
        task_manager.update_task(old_task.task_id, status=memory.TaskStatus.PROCESSING, message="Building old memory")
        old_task = task_manager.get_task(old_task.task_id)
        assert old_task is not None
        old_task.created_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        task_manager._memory.update_task(old_task)  # type: ignore[attr-defined]

        def _fake_create_task(coro):
            coro.close()
            runner = MagicMock()
            runner.done.return_value = False
            return runner

        async def _worker(_task_id: str) -> None:
            return None

        monkeypatch.setattr(memory.asyncio, "create_task", _fake_create_task)

        response = memory._start_project_task(
            task_type="memory_build",
            project_id="project-1",
            user_id=TEST_USER_ID,
            metadata={
                "idempotency_key": "memory_build:new",
                "auto_created": True,
                "trigger_source_kind": "chapter",
                "trigger_action": "update",
            },
            worker=_worker,
        )

        refreshed_old = task_manager.get_task(old_task.task_id)
        assert response.status == "accepted"
        assert refreshed_old is not None
        assert refreshed_old.status == memory.TaskStatus.CANCELLED
        assert refreshed_old.message == "Cancelled because a newer automatic memory sync task was scheduled"

    def test_start_project_task_keeps_manual_memory_build_task(self, monkeypatch: pytest.MonkeyPatch):
        old_task = task_manager.create_task(
            "memory_build",
            metadata={
                "project_id": "project-1",
                "user_id": TEST_USER_ID,
                "idempotency_key": "memory_build:manual",
            },
        )
        task_manager.update_task(old_task.task_id, status=memory.TaskStatus.PROCESSING, message="Manual build")

        def _fake_create_task(coro):
            coro.close()
            runner = MagicMock()
            runner.done.return_value = False
            return runner

        async def _worker(_task_id: str) -> None:
            return None

        monkeypatch.setattr(memory.asyncio, "create_task", _fake_create_task)

        response = memory._start_project_task(
            task_type="memory_build",
            project_id="project-1",
            user_id=TEST_USER_ID,
            metadata={
                "idempotency_key": "memory_build:auto",
                "auto_created": True,
                "trigger_source_kind": "chapter",
                "trigger_action": "update",
            },
            worker=_worker,
        )

        refreshed_old = task_manager.get_task(old_task.task_id)
        assert response.status == "accepted"
        assert refreshed_old is not None
        assert refreshed_old.status == memory.TaskStatus.PROCESSING
        assert refreshed_old.message == "Manual build"

    @pytest.mark.asyncio
    async def test_list_tasks_invalid_project_id_returns_422(self, client: AsyncClient):
        resp = await client.get("/api/projects/undefined/memory/tasks")

        assert resp.status_code == 422
        assert resp.json()["detail"] == "Invalid project id"

    @pytest.mark.asyncio
    async def test_get_memory_status_marks_empty_store_as_stale(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = _make_project(
            project_id="11111111-1111-4111-8111-111111111111",
            ontology_schema={"entity_types": [{"name": "Character"}]},
            memory_id="memory-1",
        )
        project.creative_state = {
            "memory_build_state": {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "chapter_hashes": {"chapter-1": "hash-1"},
            }
        }
        chapter_row = (str(project.chapters[0].id), datetime.now(timezone.utc))
        chapter_result = MagicMock()
        chapter_result.all.return_value = [chapter_row]
        mock_db.execute.side_effect = [_scalar_one_or_none(project), chapter_result]
        monkeypatch.setitem(_endpoint("/api/projects/{project_id}/memory", "GET").__globals__, "has_memory_data", AsyncMock(return_value=False))

        resp = await client.get(f"/api/projects/{project.id}/memory")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["memory_freshness"] == "stale"
        assert body["memory_reason"] == "memory_store_empty_or_unreadable"


    @pytest.mark.asyncio
    async def test_memory_preview_exposes_typed_strategy_without_memory(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ):
        project = _make_project(
            project_id="11111111-1111-4111-8111-111111111111",
            ontology_schema={
                "text_type": "game_lore",
                "text_type_confidence": 0.91,
                "text_type_reason": "World rules and factions dominate the source.",
                "entity_types": [{"name": "Faction"}],
                "edge_types": [{"name": "CONTROLS", "source_type": "Faction", "target_type": "Location"}],
            },
            memory_id=None,
            chapter_content="",
        )
        mock_db.execute.return_value = _scalar_one_or_none(project)

        resp = await client.post(
            f"/api/projects/{project.id}/memory/preview",
            json={
                "op_type": "CONTINUE",
                "input": "公会准备进入北境矿坑。",
                "reference_cards": {
                    "worldbook_entries": [
                        {
                            "id": "w1",
                            "title": "北境矿坑",
                            "category": "地点",
                            "content": "寒铁公会控制的地下区域",
                            "tags": ["矿坑", "寒铁公会"],
                        }
                    ],
                    "explicit_worldbook_entry_ids": ["w1"],
                },
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["memory"]["text_type"] == "game_lore"
        assert "factions, locations, items" in body["memory"]["retrieval_strategy"]["type_focus"]
        assert body["memory"]["dynamic_memory"]["enabled"] is False
        assert "北境矿坑" in body["rendered_context"]

    @pytest.mark.asyncio
    async def test_generate_ontology_success(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = _make_project(chapter_content="Project content")
        mock_db.execute.return_value = _scalar_one_or_none(project)
        generate_endpoint = _endpoint("/api/projects/{project_id}/memory/ontology/generate", "POST")
        monkeypatch.setitem(
            generate_endpoint.__globals__,
            "resolve_explicit_component_model",
            lambda *_args, **_kwargs: "gpt-4o-mini",
        )
        monkeypatch.setitem(
            generate_endpoint.__globals__,
            "generate_ontology",
            AsyncMock(return_value={"entity_types": [{"name": "Character"}], "edge_types": [{"name": "REL"}]}),
        )
        resp = await client.post(
            f"/api/projects/{project.id}/memory/ontology/generate",
            json={"text": "source text", "requirement": "keep source facts", "model": "model-ontology"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "entity_types" in body["ontology"]
        assert "edge_types" in body["ontology"]
        assert isinstance(project.ontology_schema, dict)
        assert project.ontology_schema.get("entity_types") is not None

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
        generate_endpoint = _endpoint("/api/projects/{project_id}/memory/ontology/generate", "POST")
        monkeypatch.setitem(
            generate_endpoint.__globals__,
            "resolve_explicit_component_model",
            lambda *_args, **_kwargs: "gpt-4o-mini",
        )
        monkeypatch.setitem(
            generate_endpoint.__globals__,
            "generate_ontology",
            AsyncMock(return_value={"entity_types": [{"name": "Character"}], "edge_types": [{"name": "REL"}]}),
        )

        resp = await client.post(
            f"/api/projects/{project.id}/memory/ontology/generate",
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
    async def test_add_memory_accepts_text_without_ontology(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        project = _make_project(ontology_schema=None)
        mock_db.execute.return_value = _scalar_one_or_none(project)
        build_mock = AsyncMock(return_value="dataset-no-ontology")
        add_memory_endpoint = _endpoint("/api/projects/{project_id}/memory", "POST")
        monkeypatch.setitem(add_memory_endpoint.__globals__, "build_memory", build_mock)

        resp = await client.post(
            f"/api/projects/{project.id}/memory",
            json={"text": "memory source"},
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["memory_id"] == "dataset-no-ontology"
        assert project.memory_id == "dataset-no-ontology"
        assert build_mock.await_args.kwargs["ontology"] is None

    @pytest.mark.asyncio
    async def test_add_memory_success(self, client: AsyncClient, mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch):
        project = _make_project(ontology_schema={"entity_types": [{"name": "Actor"}], "edge_types": []})
        mock_db.execute.return_value = _scalar_one_or_none(project)
        build_mock = AsyncMock(return_value="dataset-001")
        add_memory_endpoint = _endpoint("/api/projects/{project_id}/memory", "POST")
        monkeypatch.setitem(add_memory_endpoint.__globals__, "build_memory_input_with_ontology", lambda _text, _ontology: "memory input")
        monkeypatch.setitem(add_memory_endpoint.__globals__, "build_memory", build_mock)

        resp = await client.post(
            f"/api/projects/{project.id}/memory",
            json={"text": "memory source"},
        )

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "ok"
        assert body["memory_id"] == "dataset-001"
        assert project.memory_id == "dataset-001"
        build_mock.assert_awaited_once()



    @pytest.mark.asyncio
    async def test_execute_memory_build_reports_preview_memory_id(
        self,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from app.routers import memory as memory_router

        project = _make_project(
            project_id="11111111-1111-4111-8111-111111111111",
            ontology_schema={"entity_types": [{"name": "Actor"}], "edge_types": []},
            chapter_content="Base text",
        )
        preview_memory_ids: list[str] = []
        build_mock = AsyncMock(return_value="memory-preview-1")
        mock_db.execute.return_value = _scalars_all(project.chapters)
        monkeypatch.setattr(memory_router, "build_memory_input_with_ontology", lambda _text, _ontology: "memory input")
        monkeypatch.setattr(memory_router, "build_memory", build_mock)

        result = await memory_router._execute_memory_build(
            project_id=project.id,
            project=project,
            body_text=None,
            chapter_ids=None,
            ontology=None,
            mode="rebuild",
            db=mock_db,
            preview_memory_id_callback=preview_memory_ids.append,
        )

        assert result["status"] == "ok"
        assert preview_memory_ids == ["memory-preview-1"] or preview_memory_ids[0].startswith("memory_")
        assert build_mock.await_args.kwargs["memory_id_override"] == preview_memory_ids[0]
        assert build_mock.await_args.kwargs["reset"] is True
        assert result["graph_nodes"] == 0
        assert result["graph_edges"] == 0

    @pytest.mark.asyncio
    async def test_execute_memory_build_incremental_appends_without_reset(
        self,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from app.routers import memory as memory_router

        project = _make_project(
            project_id="11111111-1111-4111-8111-111111111111",
            ontology_schema={"entity_types": [{"name": "Actor"}], "edge_types": []},
            chapter_content="Base text",
            memory_id="memory-existing",
        )
        project.chapters[0].id = "chapter-existing"
        project.chapters.append(
            SimpleNamespace(
                id="chapter-new",
                project_id=project.id,
                title="New Draft",
                content="New chapter text",
                order_index=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        project.creative_state = {
            "memory_build_state": {
                "mode": "rebuild",
                "chapter_hashes": {
                    "chapter-existing": chapter_memory_hash(project.chapters[0]),
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        build_mock = AsyncMock(return_value="memory-existing")
        mock_db.execute.return_value = _scalars_all(project.chapters)
        ontology_input_mock = MagicMock(side_effect=AssertionError("incremental memory build must not duplicate ontology"))
        monkeypatch.setattr(memory_router, "build_memory_input_with_ontology", ontology_input_mock)
        monkeypatch.setattr(memory_router, "build_memory", build_mock)

        result = await memory_router._execute_memory_build(
            project_id=project.id,
            project=project,
            body_text=None,
            chapter_ids=None,
            ontology=None,
            mode="incremental",
            db=mock_db,
        )

        assert result["status"] == "ok"
        assert result["mode"] == "incremental"
        assert result["changed_chapter_ids"] == ["chapter-new"]
        assert build_mock.await_args.args[1] == chapter_memory_text(project.chapters[1])
        assert build_mock.await_args.kwargs["ontology"] is None
        assert build_mock.await_args.kwargs["memory_id_override"] == "memory-existing"
        assert build_mock.await_args.kwargs["reset"] is False
        ontology_input_mock.assert_not_called()
        assert result["graph_nodes"] == 0
        assert result["graph_edges"] == 0

    @pytest.mark.asyncio
    async def test_execute_memory_build_incremental_requires_existing_memory(
        self,
        mock_db: AsyncMock,
    ):
        from app.routers import memory as memory_router

        project = _make_project(
            project_id="11111111-1111-4111-8111-111111111111",
            ontology_schema={"entity_types": [{"name": "Actor"}], "edge_types": []},
            chapter_content="Base text",
            memory_id=None,
        )
        mock_db.execute.return_value = _scalars_all(project.chapters)

        with pytest.raises(ValueError, match="requires existing cognee project memory"):
            await memory_router._execute_memory_build(
                project_id=project.id,
                project=project,
                body_text=None,
                chapter_ids=None,
                ontology=None,
                mode="incremental",
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_execute_memory_build_incremental_rejects_edited_chapters(
        self,
        mock_db: AsyncMock,
    ):
        from app.routers import memory as memory_router

        project = _make_project(
            project_id="11111111-1111-4111-8111-111111111111",
            ontology_schema={"entity_types": [{"name": "Actor"}], "edge_types": []},
            chapter_content="Edited text",
            memory_id="memory-existing",
        )
        project.chapters[0].id = "chapter-existing"
        project.creative_state = {
            "memory_build_state": {
                "mode": "rebuild",
                "chapter_hashes": {
                    "chapter-existing": memory_router._hash_text("Original text"),
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        mock_db.execute.return_value = _scalars_all(project.chapters)

        with pytest.raises(ValueError, match="only supports newly added chapters"):
            await memory_router._execute_memory_build(
                project_id=project.id,
                project=project,
                body_text=None,
                chapter_ids=None,
                ontology=None,
                mode="incremental",
                db=mock_db,
            )


@pytest.mark.asyncio
async def test_text_ingest_task_create(
    client: AsyncClient,
    mock_db: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    project = _make_project(ontology_schema=None, memory_id=None)
    mock_db.execute.return_value = _scalar_one_or_none(project)

    def _fake_create_task(coro):
        coro.close()
        return MagicMock()

    ingest_endpoint = _endpoint("/api/projects/{project_id}/memory/ingest/text/task", "POST")
    monkeypatch.setitem(ingest_endpoint.__globals__, "asyncio", SimpleNamespace(create_task=_fake_create_task))

    start_resp = await client.post(
        f"/api/projects/{project.id}/memory/ingest/text/task",
        json={
            "text": "林烬救下沈鸢，但沈鸢隐瞒了玄鸦司身份。",
            "source_title": "Imported Chapter",
            "requirement": "续写时保持人物秘密与阵营冲突。",
        },
    )

    assert start_resp.status_code == 200
    body = start_resp.json()
    assert body["status"] == "accepted"
    assert body["task"]["task_type"] == "text_ingest"
    assert body["task"]["metadata"]["source_title"] == "Imported Chapter"


@pytest.mark.asyncio
async def test_public_viewer_cannot_run_memory_search_or_rag(
    client: AsyncClient,
    mock_db: AsyncMock,
):
    project = _make_project(user_id="owner-user-id", memory_id="memory-public")
    project.visibility = "public"
    mock_db.execute.return_value = _scalar_one_or_none(project)

    search_resp = await client.post(
        f"/api/projects/{project.id}/memory/search",
        json={"query": "关系", "search_type": "INSIGHTS", "top_k": 3},
    )
    rag_resp = await client.post(
        f"/api/projects/{project.id}/memory/rag",
        json={"query": "关系", "search_type": "INSIGHTS", "top_k": 3},
    )

    assert search_resp.status_code == 403
    assert rag_resp.status_code == 403


@pytest.mark.asyncio
async def test_public_viewer_cannot_build_or_ingest_memory(
    client: AsyncClient,
    mock_db: AsyncMock,
):
    project = _make_project(user_id="owner-user-id", memory_id="memory-public")
    project.visibility = "public"
    mock_db.execute.return_value = _scalar_one_or_none(project)

    build_resp = await client.post(
        f"/api/projects/{project.id}/memory/build/task",
        json={"text": "source", "build_mode": "rebuild"},
    )
    ontology_resp = await client.post(
        f"/api/projects/{project.id}/memory/ontology/generate/task",
        json={"text": "source"},
    )
    ingest_resp = await client.post(
        f"/api/projects/{project.id}/memory/ingest/text/task",
        json={"text": "source", "source_title": "source"},
    )
    assert build_resp.status_code == 403
    assert ontology_resp.status_code == 403
    assert ingest_resp.status_code == 403


@pytest.mark.asyncio
async def test_run_text_ingest_task_completes_full_pipeline(
    mock_db: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.routers import memory as memory_router

    project = _make_project(
        project_id="11111111-1111-4111-8111-111111111111",
        chapter_content="Existing chapter",
        ontology_schema=None,
        memory_id=None,
    )
    mock_db.execute.side_effect = [
        _scalar_one_or_none(project),
        _scalars_all(project.chapters),
    ]

    added_objects = []
    mock_db.add.side_effect = lambda obj: added_objects.append(obj)

    async def _flush():
        for obj in added_objects:
            if isinstance(obj, memory_router.ProjectChapter) and not obj.id:
                obj.id = "22222222-2222-4222-8222-222222222222"

    mock_db.flush.side_effect = _flush

    class _SessionContext:
        async def __aenter__(self_inner):
            return mock_db

        async def __aexit__(self_inner, exc_type, exc, tb):
            return False

    ontology = {
        "text_type": "fiction",
        "text_type_confidence": 0.91,
        "text_type_reason": "Named characters and conflict.",
        "entity_types": [{"name": "Person"}],
        "edge_types": [{"name": "KNOWS", "source_type": "Person", "target_type": "Person"}],
        "analysis_summary": "Imported text ontology",
    }
    memory_result = {
        "status": "built",
        "requested_mode": "rebuild",
        "mode": "rebuild",
        "memory_id": "memory-imported",
        "changed_chapter_ids": ["22222222-2222-4222-8222-222222222222"],
        "added_chapter_ids": ["22222222-2222-4222-8222-222222222222"],
        "modified_chapter_ids": [],
        "removed_chapter_ids": [],
    }
    generate_ontology_mock = AsyncMock(return_value=ontology)
    execute_memory_mock = AsyncMock(return_value=memory_result)
    monkeypatch.setattr(memory_router, "async_session", lambda: _SessionContext())
    monkeypatch.setattr(memory_router, "generate_ontology", generate_ontology_mock)
    monkeypatch.setattr(memory_router, "_execute_memory_build", execute_memory_mock)

    task = task_manager.create_task(
        "text_ingest",
        metadata={"project_id": project.id, "user_id": TEST_USER_ID},
    )

    await memory_router._run_text_ingest_task(
        task.task_id,
        project_id=project.id,
        user_id=TEST_USER_ID,
        text="林烬救下沈鸢，但沈鸢隐瞒了玄鸦司身份。",
        source_title="Imported Chapter",
        requirement="续写时保持人物秘密与阵营冲突。",
        ontology_model="gpt-4o-mini",
        build_mode="rebuild",
    )

    stored = task_manager.get_task(task.task_id)
    assert stored is not None
    assert stored.status == memory.TaskStatus.COMPLETED
    assert project.ontology_schema == ontology
    assert stored.result["chapter_id"] == "22222222-2222-4222-8222-222222222222"
    assert stored.result["text_profile"]["text_type"] == "fiction"
    assert stored.result["memory"] == memory_result
    execute_memory_mock.assert_awaited_once()
    assert execute_memory_mock.await_args.kwargs["chapter_ids"] == ["22222222-2222-4222-8222-222222222222"]


@pytest.mark.asyncio
async def test_resolve_chapters_queries_db_without_touching_lazy_relationship():
    from app.routers import memory as memory_router

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

    chapters = await memory_router._resolve_chapters_for_project(project, None, db)

    assert [item.id for item in chapters] == ["chapter-1"]
    db.execute.assert_awaited_once()


class TestMemoryMemoryTaskErrors:
    def test_describe_task_exception_keeps_message(self):
        from app.routers import memory as memory_router

        assert memory_router._describe_task_exception(RuntimeError("build failed")) == "build failed"

    def test_describe_task_exception_falls_back_to_type_and_repr(self):
        from app.routers import memory as memory_router

        error = RuntimeError()
        described = memory_router._describe_task_exception(error)

        assert described.startswith("RuntimeError:")
        assert "RuntimeError()" in described
