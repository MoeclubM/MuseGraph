from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services.project_git import create_project_record_point, initialize_project_git_repo
from app.services.project_workspace import write_project_workspace_snapshot


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _project(user_id: str):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id="project-facts-1",
        user_id=user_id,
        title="Facts Project",
        description=None,
        visibility="private",
        component_models={},
        operation_prompts=None,
        ontology_schema=None,
        creative_state=None,
        memory_id=None,
        members=[],
        chapters=[],
        facts=[],
        created_at=now,
        updated_at=now,
    )


def _fact(project_id: str):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id="fact-1",
        project_id=project_id,
        created_by_user_id="user-1",
        created_by_agent_session_id=None,
        source_kind="manual",
        source_ref=None,
        title="Old Signal",
        content="The old lighthouse sends the signal.",
        metadata_=None,
        ontology_snapshot=None,
        entities=[],
        relationships=[],
        content_hash="hash-1",
        memory_status="ready",
        memory_task_id="task-1",
        memory_error=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_create_project_fact_writes_git_workspace_files(client: AsyncClient, mock_db, fake_user, tmp_path, monkeypatch):
    from app.routers import facts as facts_router

    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(facts_router, "schedule_fact_memory_sync", lambda **_: "fact-sync-task-1")
    initialize_project_git_repo("project-facts-1", author_name="MuseGraph Test", author_email="test@example.com")

    project = _project(fake_user.id)
    captured: dict[str, object] = {}

    def _add(obj):
        captured["fact"] = obj
        obj.created_at = datetime.now(timezone.utc)
        obj.updated_at = obj.created_at

    def _execute(_query):
        return _scalar_one_or_none(captured["fact"] if "fact" in captured else project)

    mock_db.add = MagicMock(side_effect=_add)
    mock_db.execute = AsyncMock(side_effect=_execute)

    resp = await client.post(
        "/api/projects/project-facts-1/facts",
        json={"title": "旧灯塔信号", "content": "旧灯塔在午夜发送信号。"},
    )

    assert resp.status_code == 201
    fact_id = resp.json()["id"]
    workspace = tmp_path / "projects" / project.id / "workspace"
    manifest = json.loads((workspace / ".musegraph" / "project.json").read_text(encoding="utf-8"))
    fact_file = json.loads((workspace / "facts" / f"{fact_id}.json").read_text(encoding="utf-8"))

    assert manifest["facts"][0]["id"] == fact_id
    assert manifest["facts"][0]["path"] == f"facts/{fact_id}.json"
    assert fact_file["title"] == "旧灯塔信号"
    assert fact_file["memory_status"] == "syncing"


@pytest.mark.asyncio
async def test_delete_project_fact_removes_git_workspace_files(client: AsyncClient, mock_db, fake_user, tmp_path, monkeypatch):
    from app.routers import facts as facts_router

    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(facts_router, "schedule_fact_memory_sync", lambda **_: "fact-sync-task-2")
    initialize_project_git_repo("project-facts-1", author_name="MuseGraph Test", author_email="test@example.com")

    project = _project(fake_user.id)
    fact = _fact(project.id)
    project.facts = [fact]
    write_project_workspace_snapshot(project, [], [fact])
    create_project_record_point(project.id, "Initial fact")

    calls = {"count": 0}

    def _execute(_query):
        if calls["count"] == 0:
            calls["count"] += 1
            return _scalar_one_or_none(project)
        return _scalar_one_or_none(fact)

    mock_db.execute = AsyncMock(side_effect=_execute)

    resp = await client.delete("/api/projects/project-facts-1/facts/fact-1")

    assert resp.status_code == 200
    workspace = tmp_path / "projects" / project.id / "workspace"
    manifest = json.loads((workspace / ".musegraph" / "project.json").read_text(encoding="utf-8"))

    assert not (workspace / "facts" / "fact-1.json").exists()
    assert manifest["facts"] == []
