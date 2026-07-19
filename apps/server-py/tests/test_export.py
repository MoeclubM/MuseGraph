from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

from dulwich import porcelain
from dulwich.repo import Repo

from app.services import export


def test_repository_export_contains_history_without_internal_remote(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    repo = porcelain.init(workspace)
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")
    repo.close()
    (workspace / "docs").mkdir(parents=True)
    (workspace / "README.md").write_text("# Delivery\n", encoding="utf-8")
    (workspace / "docs" / "guide.md").write_text("Guide\n", encoding="utf-8")
    porcelain.add(workspace, paths=["README.md", "docs/guide.md"])
    commit_id = porcelain.commit(
        workspace,
        message=b"Create delivery",
        author=b"MuseGraph <noreply@musegraph.local>",
        committer=b"MuseGraph <noreply@musegraph.local>",
    )
    porcelain.remote_add(workspace, "origin", "/srv/musegraph/internal.git")
    (workspace / ".git" / "objects" / "pack.lock").write_bytes(b"lock")
    (workspace / ".git" / "logs").mkdir(exist_ok=True)
    (workspace / ".git" / "logs" / "HEAD").write_text("internal log\n", encoding="utf-8")
    monkeypatch.setattr(export, "project_workspace_root", lambda _project_id: workspace)

    content, filename = export._export_project_repository(
        SimpleNamespace(id="project-id", title="交付文档")
    )

    assert filename == "交付文档-repository.zip"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        assert "交付文档/README.md" in names
        assert "交付文档/docs/guide.md" in names
        assert "交付文档/.git/HEAD" in names
        assert "交付文档/.git/config" in names
        assert "交付文档/.git/objects/pack.lock" not in names
        assert "交付文档/.git/logs/HEAD" not in names
        config = archive.read("交付文档/.git/config").decode("utf-8")
        assert "[core]" in config
        assert "remote" not in config
        assert "/srv/musegraph" not in config
        archive.extractall(tmp_path / "extracted")

    delivered = tmp_path / "extracted" / "交付文档"
    delivered_repo = Repo(delivered)
    try:
        assert delivered_repo.head() == commit_id
    finally:
        delivered_repo.close()
    assert porcelain.status(delivered).unstaged == []
