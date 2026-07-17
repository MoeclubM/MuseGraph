from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.project_workspace import (
    delete_project_chapter_document,
    delete_project_fact_file,
    write_project_workspace_snapshot_from_db,
    write_project_workspace_snapshot,
)


def _chapter(chapter_id: str, title: str, content: str, order_index: int):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=chapter_id,
        project_id="project-workspace-1",
        title=title,
        content=content,
        status="draft",
        blueprint={"goal": "抵达"},
        plan="推进港口线索",
        summary="港口出现异常信号",
        continuity_notes={"weather": "fog"},
        order_index=order_index,
        created_at=now,
        updated_at=now,
    )


def _fact(fact_id: str, title: str):
    return SimpleNamespace(
        id=fact_id,
        project_id="project-workspace-1",
        created_by_user_id="user-1",
        created_by_agent_session_id=None,
        source_kind="manual",
        source_ref={"source": "note"},
        title=title,
        content="港口信号来自旧灯塔。",
        metadata_={"priority": "high"},
        ontology_snapshot={"entity_types": [{"name": "Place"}]},
        entities=[{"id": "old-lighthouse", "name": "旧灯塔"}],
        relationships=[],
        content_hash="fact-hash-1",
        memory_status="ready",
        memory_task_id="task-1",
        memory_error=None,
    )


def _project():
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id="project-workspace-1",
        title="异星档案",
        description="章节以真实文件落盘",
        visibility="private",
        component_models={"operation_create": "model-a"},
        operation_prompts={"CREATE": "写第一章"},
        ontology_schema={"entities": ["角色"]},
        creative_state={"phase": "drafting"},
        memory_id="memory-1",
        created_at=now,
        updated_at=now,
    )


def test_project_workspace_snapshot_writes_manifest_and_project_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    project = _project()
    chapters = [
        _chapter("chapter-b", "第二章", "林默抵达港口。", 1),
        _chapter("chapter-a", "第一章", "信号从海边亮起。", 0),
    ]
    facts = [_fact("fact-a", "旧灯塔信号")]

    payload = write_project_workspace_snapshot(project, chapters, facts)
    workspace = tmp_path / "projects" / project.id / "workspace"
    manifest = json.loads((workspace / ".musegraph" / "project.json").read_text(encoding="utf-8"))
    first_doc = (workspace / "documents" / "chapter-a.md").read_text(encoding="utf-8")
    fact_file = json.loads((workspace / "facts" / "fact-a.json").read_text(encoding="utf-8"))

    assert payload["chapters"][0]["id"] == "chapter-a"
    assert manifest["title"] == "异星档案"
    assert manifest["component_models"] == {"operation_create": "model-a"}
    assert [item["id"] for item in manifest["chapters"]] == ["chapter-a", "chapter-b"]
    assert manifest["facts"][0]["path"] == "facts/fact-a.json"
    assert '"title": "第一章"' in first_doc
    assert '"blueprint": {"goal": "抵达"}' in first_doc
    assert "信号从海边亮起。" in first_doc
    assert fact_file["memory_status"] == "ready"
    assert fact_file["content"] == "港口信号来自旧灯塔。"


def test_delete_project_chapter_document_surfaces_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))

    with pytest.raises(FileNotFoundError):
        delete_project_chapter_document("project-workspace-1", "missing-chapter")


def test_delete_project_fact_file_surfaces_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))

    with pytest.raises(FileNotFoundError):
        delete_project_fact_file("project-workspace-1", "missing-fact")


@pytest.mark.asyncio
async def test_project_workspace_db_snapshot_reuses_loaded_project_relations(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    project = _project()
    project.chapters = [_chapter("chapter-a", "第一章", "信号从海边亮起。", 0)]
    project.facts = [_fact("fact-a", "旧灯塔信号")]

    payload = await write_project_workspace_snapshot_from_db(project, object())
    workspace = tmp_path / "projects" / project.id / "workspace"
    manifest = json.loads((workspace / ".musegraph" / "project.json").read_text(encoding="utf-8"))

    assert payload["chapters"][0]["id"] == "chapter-a"
    assert manifest["facts"][0]["id"] == "fact-a"
    assert (workspace / "documents" / "chapter-a.md").exists()
