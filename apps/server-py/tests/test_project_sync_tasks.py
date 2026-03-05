from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


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
        cognee_dataset_id=None,
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
async def test_create_mutations_are_recorded_as_project_sync_tasks(
    client: AsyncClient,
    mock_db: AsyncMock,
    fake_user,
):
    project_id = f"proj-sync-{uuid.uuid4().hex}"
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
        json={"name": "主角", "role": "lead", "profile": "profile", "notes": "notes"},
    )
    assert character_resp.status_code == 201

    glossary_resp = await client.post(
        f"/api/projects/{project_id}/glossary-terms",
        json={"term": "术语A", "definition": "定义A", "aliases": ["A"]},
    )
    assert glossary_resp.status_code == 201

    worldbook_resp = await client.post(
        f"/api/projects/{project_id}/worldbook-entries",
        json={"title": "设定A", "content": "内容A", "tags": ["tag-a"]},
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
async def test_update_delete_mutations_are_recorded_as_project_sync_tasks(
    client: AsyncClient,
    mock_db: AsyncMock,
    fake_user,
):
    project_id = f"proj-sync-{uuid.uuid4().hex}"
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
        content="Another content",
        order_index=1,
        created_at=now,
        updated_at=now,
    )
    character = SimpleNamespace(
        id=f"char-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        name="配角",
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
        term="术语B",
        definition="旧定义",
        aliases=["B"],
        notes=None,
        order_index=0,
        created_at=now,
        updated_at=now,
    )
    worldbook_entry = SimpleNamespace(
        id=f"wb-{uuid.uuid4().hex[:8]}",
        project_id=project_id,
        title="世界观B",
        category=None,
        content="旧内容",
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
        cognee_dataset_id=None,
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
        json={"definition": "新定义"},
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
