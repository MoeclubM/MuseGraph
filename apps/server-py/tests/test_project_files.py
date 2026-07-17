from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services.project_files import (
    create_project_file,
    delete_project_file,
    list_project_files,
    read_project_file,
    rename_project_file,
    save_project_file,
)
from app.services.project_git import initialize_project_git_repo


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _project(user_id: str):
    return SimpleNamespace(
        id="project-files-1",
        user_id=user_id,
        visibility="private",
        members=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_project_file_service_uses_real_workspace_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    initialize_project_git_repo("project-1", author_name="MuseGraph Test", author_email="test@example.com")

    saved = save_project_file(
        "project-1",
        "设定.md",
        "角色：林默\n目标：找到水源".encode("utf-8"),
        "text/markdown",
    )
    listed = list_project_files("project-1")
    content = read_project_file("project-1", saved["path"])

    assert saved["path"].startswith("uploads/")
    assert listed["files"][0]["path"] == saved["path"]
    assert content["content"] == "角色：林默\n目标：找到水源"


def test_project_file_service_blocks_workspace_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))

    with pytest.raises(ValueError):
        read_project_file("project-1", "../secret.md")


def test_project_file_service_hides_internal_version_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    initialize_project_git_repo("project-1", author_name="MuseGraph Test", author_email="test@example.com")
    workspace = tmp_path / "projects" / "project-1" / "workspace"
    (workspace / ".musegraph").mkdir()
    (workspace / ".musegraph" / "project.json").write_text("{}", encoding="utf-8")

    listed = list_project_files("project-1")

    assert all(not item["path"].startswith(".git/") for item in listed["files"])
    assert all(not item["path"].startswith(".musegraph/") for item in listed["files"])
    with pytest.raises(ValueError, match="Project version metadata is internal"):
        read_project_file("project-1", ".git/config")
    with pytest.raises(ValueError, match="Project version metadata is internal"):
        read_project_file("project-1", ".musegraph/project.json")


def test_project_file_service_manual_create_rename_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    initialize_project_git_repo("project-1", author_name="MuseGraph Test", author_email="test@example.com")

    created = create_project_file("project-1", "notes/灵感.md", "第一条灵感")
    renamed = rename_project_file("project-1", created["path"], "notes/灵感-改名.md")
    content = read_project_file("project-1", renamed["path"])
    delete_project_file("project-1", renamed["path"])

    listed = list_project_files("project-1")
    assert created["path"] == "notes/灵感.md"
    assert renamed["path"] == "notes/灵感-改名.md"
    assert content["content"] == "第一条灵感"
    assert listed["files"] == []


@pytest.mark.asyncio
async def test_project_file_upload_api(client: AsyncClient, mock_db, fake_user, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    initialize_project_git_repo("project-files-1", author_name="MuseGraph Test", author_email="test@example.com")
    mock_db.execute.return_value = _scalar_one_or_none(_project(fake_user.id))

    resp = await client.post(
        "/api/projects/project-files-1/files",
        files={"file": ("资料.json", b'{"name":"MuseGraph"}', "application/json")},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["path"].startswith("uploads/")
    assert body["text_extractable"] is True

    read_resp = await client.get(
        "/api/projects/project-files-1/files/content",
        params={"path": body["path"]},
    )
    assert read_resp.status_code == 200
    assert read_resp.json()["content"] == '{"name":"MuseGraph"}'


@pytest.mark.asyncio
async def test_project_file_manual_api(client: AsyncClient, mock_db, fake_user, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    initialize_project_git_repo("project-files-1", author_name="MuseGraph Test", author_email="test@example.com")
    mock_db.execute.return_value = _scalar_one_or_none(_project(fake_user.id))

    create_resp = await client.post(
        "/api/projects/project-files-1/files/manual",
        json={"path": "manual/提纲.md", "content": "开场：雨夜"},
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["path"] == "manual/提纲.md"

    rename_resp = await client.patch(
        "/api/projects/project-files-1/files/rename",
        json={"path": "manual/提纲.md", "new_path": "manual/新版提纲.md"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["path"] == "manual/新版提纲.md"

    read_resp = await client.get(
        "/api/projects/project-files-1/files/content",
        params={"path": "manual/新版提纲.md"},
    )
    assert read_resp.status_code == 200
    assert read_resp.json()["content"] == "开场：雨夜"

    delete_resp = await client.delete(
        "/api/projects/project-files-1/files",
        params={"path": "manual/新版提纲.md"},
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json() == {"ok": True, "path": "manual/新版提纲.md"}
