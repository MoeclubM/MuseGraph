from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from dulwich import porcelain
from httpx import AsyncClient

from app.config import settings
from app.services.project_git import (
    add_project_git_remote,
    commit_project_git,
    create_project_record_point,
    create_project_git_branch,
    fetch_project_git_remote,
    get_project_git_snapshot,
    initialize_project_git_repo,
    list_project_record_points,
    pull_project_git_branch,
    push_project_git_branch,
    stage_project_git_paths,
    switch_project_git_branch,
    unstage_project_git_paths,
)
from app.services import project_workspace as project_workspace_service
from app.services.project_versions import restore_project_record_point


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _project(user_id: str):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id="project-git-1",
        user_id=user_id,
        visibility="private",
        members=[],
        title="Git Project",
        description="Stored as workspace files",
        component_models={"operation_create": "model-a"},
        operation_prompts={"CREATE": "draft"},
        ontology_schema=None,
        creative_state={"phase": "draft"},
        memory_id=None,
        chapters=[
            SimpleNamespace(
                id="chapter-git-1",
                project_id="project-git-1",
                title="Main Draft",
                content="initial workspace text",
                status="draft",
                blueprint=None,
                plan=None,
                summary=None,
                continuity_notes=None,
                order_index=0,
                created_at=now,
                updated_at=now,
            )
        ],
        facts=[],
        created_at=now,
        updated_at=now,
    )


def _init_bare_repo(path):
    repo = porcelain.init(str(path), bare=True)
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")
    repo.close()


def _commit_file(workdir, path: str, content: str, message: bytes):
    target = workdir / path
    target.write_text(content, encoding="utf-8")
    porcelain.add(str(workdir), [path])
    porcelain.commit(str(workdir), message=message, author=b"Remote Writer <remote@example.com>", committer=b"Remote Writer <remote@example.com>")


def test_project_git_diff_reads_real_workspace_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    workspace = tmp_path / "projects" / "project-git-1" / "workspace"
    workspace.mkdir(parents=True)
    initialize_project_git_repo(
        "project-git-1",
        author_name="MuseGraph Test",
        author_email="test@example.com",
    )
    draft = workspace / "draft.md"
    draft.write_text("line one\n", encoding="utf-8")
    stage_project_git_paths("project-git-1", ["draft.md"])
    commit_project_git("project-git-1", "initial")

    draft.write_text("line one\nline two\n", encoding="utf-8")
    payload = get_project_git_snapshot("project-git-1")

    assert payload["branch"]
    assert payload["files"] == [{"xy": " M", "path": "draft.md", "old_path": None}]
    assert "+line two" in payload["unstaged_diff"]
    assert payload["commits"][0]["subject"] == "initial"


def test_project_git_stage_unstage_and_commit_real_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    workspace = tmp_path / "projects" / "project-git-1" / "workspace"
    initialize_project_git_repo(
        "project-git-1",
        author_name="MuseGraph Test",
        author_email="test@example.com",
    )

    draft = workspace / "draft.md"
    draft.write_text("first draft\n", encoding="utf-8")
    snapshot = get_project_git_snapshot("project-git-1")
    assert snapshot["files"] == [{"xy": "??", "path": "draft.md", "old_path": None}]
    assert "+first draft" in snapshot["untracked_diff"]

    staged = stage_project_git_paths("project-git-1")
    assert staged["files"] == [{"xy": "A ", "path": "draft.md", "old_path": None}]
    assert "+first draft" in staged["staged_diff"]

    unstaged = unstage_project_git_paths("project-git-1")
    assert unstaged["files"] == [{"xy": "??", "path": "draft.md", "old_path": None}]

    stage_project_git_paths("project-git-1", ["draft.md"])
    committed = commit_project_git("project-git-1", "Add draft")
    assert committed["files"] == []
    assert committed["commits"][0]["subject"] == "Add draft"


def test_project_git_create_and_switch_branch_real_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    workspace = tmp_path / "projects" / "project-git-1" / "workspace"
    initialize_project_git_repo(
        "project-git-1",
        author_name="MuseGraph Test",
        author_email="test@example.com",
    )
    (workspace / "draft.md").write_text("branch base\n", encoding="utf-8")
    stage_project_git_paths("project-git-1")
    commit_project_git("project-git-1", "Base")

    created = create_project_git_branch("project-git-1", "draft/scene-a")
    assert created["branch"] == "draft/scene-a"
    assert "draft/scene-a" in created["branches"]

    switched = switch_project_git_branch("project-git-1", "main")
    assert switched["branch"] == "main"
    assert "draft/scene-a" in switched["branches"]


def test_project_git_remote_fetch_pull_push_real_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    workspace = tmp_path / "projects" / "project-git-1" / "workspace"
    remote = tmp_path / "remote.git"
    other = tmp_path / "other"
    _init_bare_repo(remote)
    initialize_project_git_repo(
        "project-git-1",
        author_name="MuseGraph Test",
        author_email="test@example.com",
    )
    (workspace / "draft.md").write_text("remote base\n", encoding="utf-8")
    stage_project_git_paths("project-git-1")
    commit_project_git("project-git-1", "Base")

    added = add_project_git_remote("project-git-1", "backup", str(remote))
    assert any(remote_info["name"] == "backup" for remote_info in added["remotes"])
    pushed = push_project_git_branch("project-git-1", "backup", "main")
    assert any(remote_info["name"] == "backup" for remote_info in pushed["remotes"])

    porcelain.clone(str(remote), str(other), checkout=True, branch=b"main")
    _commit_file(other, "remote.md", "remote change\n", b"Remote change")
    porcelain.push(
        str(other),
        str(remote),
        refspecs=b"refs/heads/main:refs/heads/main",
    )

    fetch_project_git_remote("project-git-1", "backup")
    pulled = pull_project_git_branch("project-git-1", "backup", "main")
    assert pulled["files"] == []
    assert (workspace / "remote.md").read_text(encoding="utf-8") == "remote change\n"


@pytest.mark.asyncio
async def test_project_versions_api_lists_record_points(client: AsyncClient, mock_db, fake_user, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    project = _project(fake_user.id)
    initialize_project_git_repo(
        project.id,
        author_name="MuseGraph Test",
        author_email="test@example.com",
    )
    project_workspace_service.write_project_workspace_snapshot(
        project,
        project.chapters,
        project.facts,
    )
    create_project_record_point(project.id, "Initial draft")
    mock_db.execute.return_value = _scalar_one_or_none(project)

    resp = await client.get(f"/api/projects/{project.id}/versions")

    assert resp.status_code == 200
    body = resp.json()
    assert body["record_points"][0]["label"] == "Initial draft"


@pytest.mark.asyncio
async def test_project_versions_api_creates_named_record_point_without_content_edits(
    client: AsyncClient,
    mock_db,
    fake_user,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    project = _project(fake_user.id)
    initialize_project_git_repo(
        project.id,
        author_name="MuseGraph Test",
        author_email="test@example.com",
    )
    project_workspace_service.write_project_workspace_snapshot(
        project,
        project.chapters,
        project.facts,
    )
    create_project_record_point(project.id, "Initial draft")
    mock_db.execute.return_value = _scalar_one_or_none(project)

    resp = await client.post(f"/api/projects/{project.id}/versions/record-points", json={"message": "Named checkpoint"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["record_points"][0]["label"] == "Named checkpoint"


@pytest.mark.asyncio
async def test_project_versions_api_restores_record_point(client: AsyncClient, mock_db, fake_user, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    project = _project(fake_user.id)
    initialize_project_git_repo(
        project.id,
        author_name="MuseGraph Test",
        author_email="test@example.com",
    )
    project_workspace_service.write_project_workspace_snapshot(
        project,
        project.chapters,
        project.facts,
    )
    initial_id = create_project_record_point(project.id, "Initial draft")["current_record_point"]
    project.title = "Changed Project"
    project.chapters[0].content = "changed workspace text"
    project_workspace_service.write_project_workspace_snapshot(
        project,
        project.chapters,
        project.facts,
    )
    create_project_record_point(project.id, "Changed draft")
    mock_db.execute.return_value = _scalar_one_or_none(project)

    resp = await client.post(f"/api/projects/{project.id}/versions/restore", json={"record_point_id": initial_id})

    assert resp.status_code == 200
    assert project.title == "Git Project"
    assert project.chapters[0].content == "initial workspace text"
    assert resp.json()["record_points"][0]["label"] == f"Restore record point {initial_id[:7]}"


@pytest.mark.asyncio
async def test_project_record_point_restore_rewrites_project_content(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "FILE_STORAGE_ROOT", str(tmp_path))
    project = _project("user-1")
    initialize_project_git_repo(
        project.id,
        author_name="MuseGraph Test",
        author_email="test@example.com",
    )
    project_workspace_service.write_project_workspace_snapshot(
        project,
        project.chapters,
        project.facts,
    )
    initial = create_project_record_point(project.id, "Initial draft")
    initial_id = initial["current_record_point"]

    project.title = "Changed Project"
    project.chapters[0].content = "changed workspace text"
    project_workspace_service.write_project_workspace_snapshot(
        project,
        project.chapters,
        project.facts,
    )
    create_project_record_point(project.id, "Changed draft")

    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    await restore_project_record_point(project, db, initial_id)

    history = list_project_record_points(project.id)
    assert project.title == "Git Project"
    assert project.chapters[0].content == "initial workspace text"
    assert history["record_points"][0]["label"] == f"Restore record point {initial_id[:7]}"
