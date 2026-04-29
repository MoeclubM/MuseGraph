from __future__ import annotations

import uuid
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _with_timestamps(obj: object) -> None:
    now = _now()
    if getattr(obj, "id", None) in (None, ""):
        setattr(obj, "id", f"obj-{uuid.uuid4().hex[:10]}")
    if getattr(obj, "created_at", None) is None:
        setattr(obj, "created_at", now)
    setattr(obj, "updated_at", now)


def _build_project(project_id: str, user_id: str) -> SimpleNamespace:
    now = _now()
    return SimpleNamespace(
        id=project_id,
        user_id=user_id,
        title="Sync Test Project",
        description=None,
        simulation_requirement=None,
        component_models={},
        ontology_schema=None,
        oasis_analysis=None,
        graph_id=None,
        chapters=[
            SimpleNamespace(
                id=f"ch-base-{uuid.uuid4().hex[:8]}",
                project_id=project_id,
                title="Main Draft",
                content="Base content",
                order_index=0,
                created_at=now,
                updated_at=now,
            )
        ],
        characters=[],
        glossary_terms=[],
        worldbook_entries=[],
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_schedule_chapter_graph_refresh_uses_full_workspace_text(fake_user, monkeypatch):
    from app.routers import graph as graph_router
    from app.routers import projects as projects_router

    project_id = str(uuid.uuid4())
    project = _build_project(project_id, fake_user.id)
    project.ontology_schema = {"entity_types": [{"name": "PERSON"}], "edge_types": [{"name": "KNOWS"}]}
    project.chapters.append(
        SimpleNamespace(
            id=f"ch-extra-{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            title="Chapter 2",
            content="Second content",
            order_index=1,
            created_at=_now(),
            updated_at=_now(),
        )
    )

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_scalar_one_or_none(project))

    class _SessionContext:
        async def __aenter__(self):
            return fake_db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    captured: dict[str, object] = {}

    def _fake_build_graph_task_idempotency_key(project_id_arg: str, body):
        captured["project_id"] = project_id_arg
        captured["body"] = body
        return "graph_build:test-key"

    def _fake_start_project_task(*, task_type, project_id, user_id, worker, metadata=None):
        captured["task_type"] = task_type
        captured["scheduled_project_id"] = project_id
        captured["scheduled_user_id"] = user_id
        captured["worker"] = worker
        captured["metadata"] = metadata or {}
        return SimpleNamespace(task=SimpleNamespace(task_id="graph-task-1"))

    monkeypatch.setattr(projects_router, "async_session", lambda: _SessionContext())
    monkeypatch.setattr(graph_router, "_build_graph_task_idempotency_key", _fake_build_graph_task_idempotency_key)
    monkeypatch.setattr(graph_router, "_start_project_task", _fake_start_project_task)

    await projects_router._schedule_chapter_graph_refresh(
        project_id,
        fake_user.id,
        "update",
        project.chapters[0].id,
    )

    body = captured["body"]
    assert body.text == "Base content\n\nSecond content"
    assert body.build_mode == "incremental"
    assert captured["task_type"] == "graph_build"
    assert captured["scheduled_project_id"] == project_id
    assert captured["scheduled_user_id"] == fake_user.id
    assert captured["metadata"] == {
        "build_mode": "incremental",
        "resume_failed": False,
        "idempotency_key": "graph_build:test-key",
        "trigger_source_kind": "chapter",
        "trigger_action": "update",
        "trigger_entity_id": project.chapters[0].id,
        "auto_created": True,
    }
    assert callable(captured["worker"])


@pytest.mark.asyncio
async def test_create_mutations_are_recorded_as_project_sync_tasks(
    client: AsyncClient,
    mock_db: AsyncMock,
    fake_user,
):
    project_id = str(uuid.uuid4())
    project = _build_project(project_id, fake_user.id)

    mock_db.add = MagicMock(side_effect=_with_timestamps)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_scalar_one_or_none(project))

    chapter_resp = await client.post(
        f"/api/projects/{project_id}/chapters",
        json={"title": "Chapter 2", "content": "New content"},
    )
    assert chapter_resp.status_code == 201

    character_resp = await client.post(
        f"/api/projects/{project_id}/characters",
        json={"name": "Lead", "role": "lead", "profile": "profile", "notes": "notes"},
    )
    assert character_resp.status_code == 201

    glossary_resp = await client.post(
        f"/api/projects/{project_id}/glossary-terms",
        json={"term": "Term A", "definition": "Definition A", "aliases": ["A"]},
    )
    assert glossary_resp.status_code == 201

    worldbook_resp = await client.post(
        f"/api/projects/{project_id}/worldbook-entries",
        json={"title": "Setting A", "content": "Content A", "tags": ["tag-a"]},
    )
    assert worldbook_resp.status_code == 201

    list_resp = await client.get(
        f"/api/projects/{project_id}/graphs/tasks",
        params={"task_type": "project_sync", "limit": 50},
    )
    assert list_resp.status_code == 200
    tasks = list_resp.json()["tasks"]
    project_tasks = [item for item in tasks if (item.get("metadata") or {}).get("project_id") == project_id]
    assert len(project_tasks) >= 4

    source_kinds = {(item.get("metadata") or {}).get("source_kind") for item in project_tasks}
    assert {"chapter", "character", "glossary_term", "worldbook_entry"}.issubset(source_kinds)

    for item in project_tasks:
        assert item["status"] == "completed"
        detail = item.get("progress_detail")
        assert isinstance(detail, dict)
        assert detail.get("stage") == "sync_event"
        assert detail.get("step")


@pytest.mark.asyncio
async def test_chapter_mutations_schedule_background_graph_refresh_when_ontology_exists(
    mock_db: AsyncMock,
    fake_user,
):
    from app.routers import projects as projects_router
    from app.schemas.project import ProjectChapterCreate, ProjectChapterUpdate, ProjectCharacterCreate

    project_id = str(uuid.uuid4())
    now = _now()
    chapter_1 = SimpleNamespace(
        id=f"ch-1-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        title="Chapter 1",
        content="Old content",
        order_index=0,
        created_at=now,
        updated_at=now,
    )
    chapter_2 = SimpleNamespace(
        id=f"ch-2-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        title="Chapter 2",
        content="More content",
        order_index=1,
        created_at=now,
        updated_at=now,
    )
    project = SimpleNamespace(
        id=project_id,
        user_id=fake_user.id,
        title="Sync Test Project",
        description=None,
        simulation_requirement=None,
        component_models={},
        ontology_schema={"entity_types": [{"name": "PERSON"}], "edge_types": [{"name": "KNOWS"}]},
        oasis_analysis=None,
        graph_id="graph-1",
        chapters=[chapter_1, chapter_2],
        characters=[],
        glossary_terms=[],
        worldbook_entries=[],
        created_at=now,
        updated_at=now,
    )

    scheduled: list[tuple[object, tuple[object, ...]]] = []

    def _fake_add_task(self, func, *args, **kwargs):
        scheduled.append((func, args))

    mock_db.add = MagicMock(side_effect=_with_timestamps)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_scalar_one_or_none(project))

    with patch.object(projects_router.BackgroundTasks, "add_task", autospec=True, side_effect=_fake_add_task):
        await projects_router.create_project_chapter(
            project_id,
            ProjectChapterCreate(title="Chapter 3", content="New content"),
            projects_router.BackgroundTasks(),
            fake_user,
            mock_db,
        )
        await projects_router.update_project_chapter(
            project_id,
            chapter_1.id,
            ProjectChapterUpdate(content="Updated content"),
            projects_router.BackgroundTasks(),
            fake_user,
            mock_db,
        )
        await projects_router.delete_project_chapter(
            project_id,
            chapter_2.id,
            projects_router.BackgroundTasks(),
            fake_user,
            mock_db,
        )
        await projects_router.create_project_character(
            project_id,
            ProjectCharacterCreate(name="Lead", role="lead", profile="profile", notes="notes"),
            fake_user,
            mock_db,
        )

    assert len(scheduled) == 3
    assert [item[1][2] for item in scheduled] == ["create", "update", "delete"]
    assert all(item[0] is projects_router._schedule_chapter_graph_refresh for item in scheduled)
    assert all(item[1][0] == project_id for item in scheduled)
    assert all(item[1][1] == fake_user.id for item in scheduled)
    assert all(item[1][3] for item in scheduled)


@pytest.mark.asyncio
async def test_chapter_mutations_skip_background_graph_refresh_when_auto_sync_disabled(
    mock_db: AsyncMock,
    fake_user,
):
    from app.routers import projects as projects_router
    from app.schemas.project import ProjectChapterCreate, ProjectChapterUpdate

    project_id = str(uuid.uuid4())
    now = _now()
    chapter = SimpleNamespace(
        id=f"ch-1-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        title="Chapter 1",
        content="Old content",
        order_index=0,
        created_at=now,
        updated_at=now,
    )
    project = SimpleNamespace(
        id=project_id,
        user_id=fake_user.id,
        title="Sync Test Project",
        description=None,
        simulation_requirement=None,
        component_models={projects_router.GRAPH_AUTO_SYNC_COMPONENT_KEY: projects_router.GRAPH_AUTO_SYNC_DISABLED},
        ontology_schema={"entity_types": [{"name": "PERSON"}], "edge_types": [{"name": "KNOWS"}]},
        oasis_analysis=None,
        graph_id="graph-1",
        chapters=[chapter],
        characters=[],
        glossary_terms=[],
        worldbook_entries=[],
        created_at=now,
        updated_at=now,
    )

    scheduled: list[tuple[object, tuple[object, ...]]] = []

    def _fake_add_task(self, func, *args, **kwargs):
        scheduled.append((func, args))

    mock_db.add = MagicMock(side_effect=_with_timestamps)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_scalar_one_or_none(project))

    with patch.object(projects_router.BackgroundTasks, "add_task", autospec=True, side_effect=_fake_add_task):
        await projects_router.create_project_chapter(
            project_id,
            ProjectChapterCreate(title="Chapter 2", content="New content"),
            projects_router.BackgroundTasks(),
            fake_user,
            mock_db,
        )
        await projects_router.update_project_chapter(
            project_id,
            chapter.id,
            ProjectChapterUpdate(content="Updated content"),
            projects_router.BackgroundTasks(),
            fake_user,
            mock_db,
        )

    assert scheduled == []


@pytest.mark.asyncio
async def test_background_chapter_refresh_reuses_same_inflight_graph_task_as_manual_incremental_trigger(
    mock_db: AsyncMock,
    fake_user,
    monkeypatch,
):
    from app.routers import graph as graph_router
    from app.routers import projects as projects_router

    project_id = str(uuid.uuid4())
    project = _build_project(project_id, fake_user.id)
    project.ontology_schema = {"entity_types": [{"name": "PERSON"}], "edge_types": [{"name": "KNOWS"}]}
    project.chapters.append(
        SimpleNamespace(
            id=f"ch-extra-{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            title="Chapter 2",
            content="Second content",
            order_index=1,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    full_text = "Base content\n\nSecond content"

    fake_background_db = AsyncMock()
    fake_background_db.execute = AsyncMock(return_value=_scalar_one_or_none(project))

    class _SessionContext:
        async def __aenter__(self):
            return fake_background_db

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(projects_router, "async_session", lambda: _SessionContext())
    mock_db.execute = AsyncMock(return_value=_scalar_one_or_none(project))

    expected_key = graph_router._build_graph_task_idempotency_key(
        project_id,
        graph_router.GraphBuildRequest(text=full_text, build_mode="incremental"),
    )
    existing_task = TaskRecord(
        task_id="graph-build-existing",
        task_type="graph_build",
        status=TaskStatus.PROCESSING,
        created_at=_now(),
        updated_at=_now(),
        progress=25,
        message="Graph build is running",
        metadata={
            "project_id": project_id,
            "user_id": fake_user.id,
            "idempotency_key": expected_key,
        },
    )

    with patch.object(graph_router, "task_manager") as mock_task_manager, patch.object(graph_router.asyncio, "create_task") as mock_create_task:
        mock_task_manager.find_inflight_task_by_idempotency.return_value = existing_task

        await projects_router._schedule_chapter_graph_refresh(
            project_id,
            fake_user.id,
            "update",
            project.chapters[0].id,
        )

        response = await graph_router.add_to_graph_task(
            project_id,
            graph_router.GraphBuildRequest(text=full_text, build_mode="incremental"),
            fake_user,
            mock_db,
        )

        assert response.status == "accepted"
        assert response.task.task_id == existing_task.task_id
        assert mock_task_manager.create_task.call_count == 0
        assert mock_create_task.call_count == 0

        idempotency_calls = mock_task_manager.find_inflight_task_by_idempotency.call_args_list
        assert len(idempotency_calls) == 2
        assert [call.kwargs["task_type"] for call in idempotency_calls] == ["graph_build", "graph_build"]
        assert [call.kwargs["project_id"] for call in idempotency_calls] == [project_id, project_id]
        assert [call.kwargs["idempotency_key"] for call in idempotency_calls] == [expected_key, expected_key]


@pytest.mark.asyncio
async def test_manual_auto_sync_route_ignores_auto_sync_disabled_setting(
    client: AsyncClient,
    mock_db: AsyncMock,
    fake_user,
):
    from app.routers import graph as graph_router
    from app.routers import projects as projects_router

    project_id = str(uuid.uuid4())
    project = _build_project(project_id, fake_user.id)
    project.component_models = {projects_router.GRAPH_AUTO_SYNC_COMPONENT_KEY: projects_router.GRAPH_AUTO_SYNC_DISABLED}
    project.ontology_schema = {"entity_types": [{"name": "PERSON"}], "edge_types": [{"name": "KNOWS"}]}
    mock_db.execute = AsyncMock(return_value=_scalar_one_or_none(project))

    response_payload = graph_router.GraphTaskStartResponse(
        status="accepted",
        task=graph_router.GraphTaskInfo(
            task_id="manual-auto-sync-task",
            task_type="graph_build",
            status="pending",
            created_at=_now(),
            updated_at=_now(),
            progress=0,
            message="Queued",
            result=None,
            error=None,
            progress_detail=None,
            metadata={"project_id": project_id},
        ),
    )

    with patch.object(projects_router, "_start_chapter_graph_refresh", AsyncMock(return_value=response_payload)) as mock_start:
        resp = await client.post(f"/api/projects/{project_id}/graphs/build/auto-sync/task")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["task"]["task_id"] == "manual-auto-sync-task"
    assert mock_start.await_count == 1
    assert mock_start.await_args.args == (project_id, fake_user.id, "manual")
    assert mock_start.await_args.kwargs == {
        "respect_auto_sync_setting": False,
        "require_ready": True,
    }


@pytest.mark.asyncio
async def test_update_delete_mutations_are_recorded_as_project_sync_tasks(
    client: AsyncClient,
    mock_db: AsyncMock,
    fake_user,
):
    project_id = str(uuid.uuid4())
    now = _now()
    chapter_1 = SimpleNamespace(
        id=f"ch-1-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        title="Chapter 1",
        content="Old content",
        order_index=0,
        created_at=now,
        updated_at=now,
    )
    chapter_2 = SimpleNamespace(
        id=f"ch-2-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        title="Chapter 2",
        content="Old content",
        order_index=1,
        created_at=now,
        updated_at=now,
    )
    character = SimpleNamespace(
        id=f"char-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        name="Supporting Role",
        role="support",
        profile="profile",
        notes="notes",
        order_index=0,
        created_at=now,
        updated_at=now,
    )
    glossary_term = SimpleNamespace(
        id=f"term-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        term="Term B",
        definition="Old definition",
        aliases=["B"],
        notes=None,
        order_index=0,
        created_at=now,
        updated_at=now,
    )
    worldbook_entry = SimpleNamespace(
        id=f"wb-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        title="Worldbook B",
        category=None,
        content="Old content",
        tags=["tag-b"],
        notes=None,
        order_index=0,
        created_at=now,
        updated_at=now,
    )
    project = SimpleNamespace(
        id=project_id,
        user_id=fake_user.id,
        title="Sync Test Project",
        description=None,
        simulation_requirement=None,
        component_models={},
        ontology_schema=None,
        oasis_analysis=None,
        graph_id=None,
        chapters=[chapter_1, chapter_2],
        characters=[character],
        glossary_terms=[glossary_term],
        worldbook_entries=[worldbook_entry],
        created_at=now,
        updated_at=now,
    )

    mock_db.add = MagicMock(side_effect=_with_timestamps)
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()
    mock_db.execute = AsyncMock(return_value=_scalar_one_or_none(project))

    update_chapter_resp = await client.put(
        f"/api/projects/{project_id}/chapters/{chapter_1.id}",
        json={"content": "Updated content"},
    )
    assert update_chapter_resp.status_code == 200

    delete_character_resp = await client.delete(
        f"/api/projects/{project_id}/characters/{character.id}",
    )
    assert delete_character_resp.status_code == 204

    update_term_resp = await client.put(
        f"/api/projects/{project_id}/glossary-terms/{glossary_term.id}",
        json={"definition": "New definition"},
    )
    assert update_term_resp.status_code == 200

    delete_worldbook_resp = await client.delete(
        f"/api/projects/{project_id}/worldbook-entries/{worldbook_entry.id}",
    )
    assert delete_worldbook_resp.status_code == 204

    list_resp = await client.get(
        f"/api/projects/{project_id}/graphs/tasks",
        params={"task_type": "project_sync", "limit": 50},
    )
    assert list_resp.status_code == 200
    tasks = list_resp.json()["tasks"]
    project_tasks = [item for item in tasks if (item.get("metadata") or {}).get("project_id") == project_id]

    assert any(
        (item.get("metadata") or {}).get("source_kind") == "chapter"
        and (item.get("metadata") or {}).get("action") == "update"
        for item in project_tasks
    )
    assert any(
        (item.get("metadata") or {}).get("source_kind") == "character"
        and (item.get("metadata") or {}).get("action") == "delete"
        for item in project_tasks
    )
    assert any(
        (item.get("metadata") or {}).get("source_kind") == "glossary_term"
        and (item.get("metadata") or {}).get("action") == "update"
        for item in project_tasks
    )
    assert any(
        (item.get("metadata") or {}).get("source_kind") == "worldbook_entry"
        and (item.get("metadata") or {}).get("action") == "delete"
        for item in project_tasks
    )


