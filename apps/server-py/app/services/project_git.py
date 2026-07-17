from __future__ import annotations

import difflib
import io
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dulwich import porcelain
from dulwich.index import IndexEntry, iter_tree_contents
from dulwich.repo import Repo

from app.config import settings
from app.services.project_files import project_workspace_root


def _storage_root() -> Path:
    return Path(settings.FILE_STORAGE_ROOT).expanduser().resolve()


def project_git_server_root() -> Path:
    return _storage_root() / "git-server"


def project_git_server_repo_root(project_id: str) -> Path:
    return project_git_server_root() / "projects" / f"{project_id}.git"


def _call_git(fn: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        raise RuntimeError(str(exc) or exc.__class__.__name__) from exc


def _decode(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _path_bytes(path: str | bytes) -> bytes:
    if isinstance(path, bytes):
        return path
    return path.replace("\\", "/").encode("utf-8")


def _normalize_paths(paths: list[str] | None) -> list[str]:
    return [path.strip().replace("\\", "/").lstrip("/") for path in paths or [] if path.strip()]


def _open_repo(workspace: Path) -> Repo:
    if not (workspace / ".git").is_dir():
        workspace.mkdir(parents=True, exist_ok=True)
        repo = _call_git(porcelain.init, str(workspace), bare=False)
        try:
            repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")
        finally:
            repo.close()
        _set_user_config(workspace, "MuseGraph", "noreply@musegraph.local")
        bare_path = _storage_root() / "git-server" / "projects" / f"{workspace.parent.name}.git"
        bare_path.parent.mkdir(parents=True, exist_ok=True)
        if not (bare_path / "objects").is_dir():
            bare_repo = _call_git(porcelain.init, str(bare_path), bare=True)
            try:
                bare_repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")
            finally:
                bare_repo.close()
        _set_remote_config(workspace, "origin", str(bare_path))
        return _call_git(Repo, str(workspace))
    return _call_git(Repo, str(workspace))


def _init_working_repo(workspace: Path) -> Repo:
    if (workspace / ".git").is_dir():
        return _open_repo(workspace)
    return _call_git(porcelain.init, str(workspace), bare=False)


def _init_bare_repo(path: Path) -> Repo:
    if (path / "objects").is_dir():
        return _call_git(Repo, str(path))
    return _call_git(porcelain.init, str(path), bare=True)


def _set_main_branch(repo: Repo) -> None:
    repo.refs.set_symbolic_ref(b"HEAD", b"refs/heads/main")


def _set_user_config(workspace: Path, author_name: str, author_email: str) -> None:
    repo = _open_repo(workspace)
    try:
        config = repo.get_config()
        config.set((b"user",), b"name", author_name)
        config.set((b"user",), b"email", author_email)
        config.write_to_path()
    finally:
        repo.close()


def _set_remote_config(workspace: Path, remote: str, url: str) -> None:
    repo = _open_repo(workspace)
    try:
        config = repo.get_config()
        section = (b"remote", remote.encode("utf-8"))
        config.set(section, b"url", url)
        config.set(section, b"fetch", f"+refs/heads/*:refs/remotes/{remote}/*")
        config.write_to_path()
    finally:
        repo.close()


def _remote_url(workspace: Path, remote: str) -> str:
    repo = _open_repo(workspace)
    try:
        return _decode(repo.get_config().get((b"remote", remote.encode("utf-8")), b"url"))
    finally:
        repo.close()


def _active_branch(workspace: Path) -> str:
    return _decode(_call_git(porcelain.active_branch, str(workspace)))


def _branch_ref(branch: str) -> bytes:
    return f"refs/heads/{branch}".encode("utf-8")


def _remote_ref(remote: str, branch: str) -> bytes:
    return f"refs/remotes/{remote}/{branch}".encode("utf-8")


def _head_id(repo: Repo) -> bytes | None:
    try:
        return repo.head()
    except KeyError:
        return None


def _ref_value(repo: Repo, ref: bytes) -> bytes | None:
    try:
        return repo.refs[ref]
    except KeyError:
        return None


def _has_commits(workspace: Path) -> bool:
    repo = _open_repo(workspace)
    try:
        return _head_id(repo) is not None
    finally:
        repo.close()


def _ancestor_ids(repo: Repo, start: bytes | None) -> set[bytes]:
    if start is None:
        return set()
    seen: set[bytes] = set()
    pending = [start]
    while pending:
        commit_id = pending.pop()
        if commit_id in seen:
            continue
        seen.add(commit_id)
        pending.extend(repo[commit_id].parents)
    return seen


def _branch_payload(workspace: Path) -> dict[str, Any]:
    branch = _active_branch(workspace)
    repo = _open_repo(workspace)
    try:
        local_id = _ref_value(repo, _branch_ref(branch))
        remote_id = _ref_value(repo, _remote_ref("origin", branch))
        if local_id and remote_id:
            local_ancestors = _ancestor_ids(repo, local_id)
            remote_ancestors = _ancestor_ids(repo, remote_id)
            ahead = len(local_ancestors - remote_ancestors)
            behind = len(remote_ancestors - local_ancestors)
            detail = []
            if ahead:
                detail.append(f"ahead {ahead}")
            if behind:
                detail.append(f"behind {behind}")
            suffix = f" [{', '.join(detail)}]" if detail else ""
            branch_status = f"{branch}...origin/{branch}{suffix}"
        else:
            ahead = 0
            behind = 0
            branch_status = branch
        return {
            "branch": branch,
            "branch_status": branch_status,
            "ahead": ahead,
            "behind": behind,
        }
    finally:
        repo.close()


def _status_files(workspace: Path) -> list[dict[str, str | None]]:
    status = _call_git(porcelain.status, str(workspace), untracked_files="all")
    files: dict[str, list[str]] = {}
    for key, code in (("add", "A"), ("modify", "M"), ("delete", "D")):
        for path in status.staged[key]:
            files.setdefault(_decode(path), [" ", " "])[0] = code
    for path in status.unstaged:
        text = _decode(path)
        files.setdefault(text, [" ", " "])[1] = "M" if (workspace / text).exists() else "D"
    for path in status.untracked:
        text = _decode(path)
        files[text] = ["?", "?"]
    return [
        {"xy": "".join(xy), "path": path, "old_path": None}
        for path, xy in sorted(files.items(), key=lambda item: item[0])
    ]


def _diff(workspace: Path, *, staged: bool) -> str:
    output = io.BytesIO()
    _call_git(porcelain.diff, str(workspace), staged=staged, outstream=output)
    return output.getvalue().decode("utf-8", errors="replace")


def _untracked_diff(workspace: Path, files: list[dict[str, str | None]]) -> str:
    chunks: list[str] = []
    for item in files:
        if item["xy"] != "??":
            continue
        path = str(item["path"] or "")
        target = workspace / path
        if not target.is_file():
            continue
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        body = difflib.unified_diff([], lines, fromfile="/dev/null", tofile=f"b/{path}")
        diff_lines = list(body)
        chunks.append(
            f"diff --git a/{path} b/{path}\n"
            "new file mode 100644\n"
            + "".join(diff_lines)
        )
    return "\n".join(chunk.rstrip() for chunk in chunks)


def _remote_payload(workspace: Path) -> list[dict[str, str]]:
    repo = _open_repo(workspace)
    try:
        config = repo.get_config()
        remotes: list[dict[str, str]] = []
        for section in config.sections():
            if len(section) != 2 or section[0] != b"remote":
                continue
            name = _decode(section[1])
            url = _decode(config.get(section, b"url"))
            remotes.append({"name": name, "url": url, "kind": "fetch"})
            remotes.append({"name": name, "url": url, "kind": "push"})
        return remotes
    finally:
        repo.close()


def _recent_commits(workspace: Path) -> list[dict[str, str]]:
    repo = _open_repo(workspace)
    try:
        head = _head_id(repo)
        if head is None:
            return []
        commits: list[dict[str, str]] = []
        for entry in repo.get_walker(include=[head], max_entries=30):
            commit = entry.commit
            subject = _decode(commit.message).splitlines()[0] if commit.message else ""
            authored_at = datetime.fromtimestamp(commit.commit_time, tz=timezone.utc).isoformat()
            commits.append({"hash": commit.id.decode("ascii"), "authored_at": authored_at, "subject": subject})
        return commits
    finally:
        repo.close()


def _resolve_commit_id(repo: Repo, record_point_id: str) -> bytes:
    candidate = record_point_id.strip()
    if not candidate:
        raise RuntimeError("Record point id is required")
    matches = [
        entry.commit.id
        for entry in repo.get_walker()
        if entry.commit.id.decode("ascii").startswith(candidate)
    ]
    if not matches:
        raise RuntimeError(f"Record point not found: {record_point_id}")
    if len(matches) > 1:
        raise RuntimeError(f"Record point id is ambiguous: {record_point_id}")
    return matches[0]


def _read_file_at_commit(workspace: Path, record_point_id: str, relative_path: str) -> str:
    repo = _open_repo(workspace)
    try:
        commit_id = _resolve_commit_id(repo, record_point_id)
        commit = repo[commit_id]
        raw_path = _path_bytes(relative_path)
        for entry in iter_tree_contents(repo.object_store, commit.tree):
            if entry.path == raw_path:
                return repo[entry.sha].as_raw_string().decode("utf-8")
    finally:
        repo.close()
    raise RuntimeError(f"Record point file not found: {relative_path}")


def _chapter_content_from_workspace_document(text: str) -> str:
    marker = "\n---\n\n"
    if not text.startswith("---\n") or marker not in text:
        raise RuntimeError("Versioned document is missing MuseGraph metadata header")
    return text.split(marker, 1)[1].removesuffix("\n")


def list_project_record_points(project_id: str) -> dict[str, Any]:
    snapshot = get_project_git_snapshot(project_id)
    return {
        "current_record_point": snapshot["commits"][0]["hash"] if snapshot["commits"] else None,
        "record_points": [
            {
                "id": commit["hash"],
                "label": commit["subject"],
                "created_at": commit["authored_at"],
            }
            for commit in snapshot["commits"]
        ],
        "pending_changes_count": len(snapshot.get("files") or []),
    }


def create_project_record_point(project_id: str, message: str) -> dict[str, Any]:
    stage_project_git_paths(project_id)
    snapshot = commit_project_git(project_id, message)
    push_project_git_branch(project_id, "origin", snapshot["branch"])
    return list_project_record_points(project_id)


def read_project_record_point_snapshot(project_id: str, record_point_id: str) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    manifest = json.loads(_read_file_at_commit(workspace, record_point_id, ".musegraph/project.json"))
    documents = {
        chapter["id"]: _chapter_content_from_workspace_document(
            _read_file_at_commit(workspace, record_point_id, chapter["path"])
        )
        for chapter in manifest["chapters"]
    }
    return {"manifest": manifest, "documents": documents}


def _branches_payload(workspace: Path, current_branch: str) -> list[str]:
    repo = _open_repo(workspace)
    try:
        branches = [
            _decode(ref.removeprefix(b"refs/heads/"))
            for ref in repo.refs.keys()
            if ref.startswith(b"refs/heads/")
        ]
        if current_branch and current_branch not in branches:
            branches.insert(0, current_branch)
        return sorted(branches)
    finally:
        repo.close()


def _head_tree_entries(repo: Repo) -> dict[bytes, Any]:
    head = _head_id(repo)
    if head is None:
        return {}
    commit = repo[head]
    return {entry.path: entry for entry in iter_tree_contents(repo.object_store, commit.tree)}


def _unstage_paths_from_head(workspace: Path, paths: list[str]) -> None:
    repo = _open_repo(workspace)
    try:
        index = repo.open_index()
        tree_entries = _head_tree_entries(repo)
        for path in paths:
            raw = _path_bytes(path)
            entry = tree_entries.get(raw)
            if entry is None:
                if raw in index:
                    del index[raw]
                continue
            blob = repo[entry.sha]
            index[raw] = IndexEntry(0, 0, 0, 0, entry.mode, 0, 0, blob.raw_length(), entry.sha, 0)
        index.write()
    finally:
        repo.close()


def _record_remote_refs(workspace: Path, remote: str, refs: dict[bytes, bytes]) -> None:
    repo = _open_repo(workspace)
    try:
        for ref, commit_id in refs.items():
            if not ref.startswith(b"refs/heads/"):
                continue
            branch = _decode(ref.removeprefix(b"refs/heads/"))
            repo.refs[_remote_ref(remote, branch)] = commit_id
    finally:
        repo.close()


def _record_pushed_branch(workspace: Path, remote: str, branch: str) -> None:
    repo = _open_repo(workspace)
    try:
        commit_id = repo.refs[_branch_ref(branch)]
        repo.refs[_remote_ref(remote, branch)] = commit_id
    finally:
        repo.close()


def _resolve_branch(branch: str | None) -> str:
    name = str(branch or "").strip()
    if not name:
        raise RuntimeError("Git branch is required")
    return name


def _resolve_remote(remote: str | None) -> str:
    name = str(remote or "").strip()
    if not name:
        raise RuntimeError("Git remote name is required")
    return name


def initialize_project_git_repo(project_id: str, *, author_name: str, author_email: str) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    server_repo = project_git_server_repo_root(project_id)
    workspace.mkdir(parents=True, exist_ok=True)
    server_repo.parent.mkdir(parents=True, exist_ok=True)

    repo = _init_working_repo(workspace)
    try:
        _set_main_branch(repo)
    finally:
        repo.close()

    bare_repo = _init_bare_repo(server_repo)
    try:
        _set_main_branch(bare_repo)
    finally:
        bare_repo.close()

    _set_user_config(workspace, author_name, author_email)
    _set_remote_config(workspace, "origin", str(server_repo))
    return get_project_git_snapshot(project_id)


def ensure_project_git_repo(project_id: str) -> None:
    """Initialize the project git workspace lazily for projects that predate it."""
    workspace = project_workspace_root(project_id)
    if not (workspace / ".git").is_dir():
        initialize_project_git_repo(
            project_id,
            author_name="MuseGraph",
            author_email="noreply@musegraph.local",
        )


def delete_project_git_storage(project_id: str) -> None:
    project_dir = project_workspace_root(project_id).parent.resolve()
    projects_root = (_storage_root() / "projects").resolve()
    server_repo = project_git_server_repo_root(project_id).resolve()
    server_projects_root = (project_git_server_root() / "projects").resolve()
    project_dir.relative_to(projects_root)
    server_repo.relative_to(server_projects_root)
    if project_dir.exists():
        shutil.rmtree(project_dir)
    if server_repo.exists():
        shutil.rmtree(server_repo)


def get_project_git_snapshot(project_id: str) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    branch_payload = _branch_payload(workspace)
    files = _status_files(workspace)
    return {
        **branch_payload,
        "files": files,
        "staged_diff": _diff(workspace, staged=True),
        "unstaged_diff": _diff(workspace, staged=False),
        "untracked_diff": _untracked_diff(workspace, files),
        "branches": _branches_payload(workspace, branch_payload["branch"]),
        "commits": _recent_commits(workspace),
        "remotes": _remote_payload(workspace),
    }


def get_project_git_diff(project_id: str) -> dict[str, Any]:
    return get_project_git_snapshot(project_id)


def stage_project_git_paths(project_id: str, paths: list[str] | None = None) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    normalized = _normalize_paths(paths)
    _call_git(porcelain.add, str(workspace), paths=normalized or None)
    return get_project_git_snapshot(project_id)


def unstage_project_git_paths(project_id: str, paths: list[str] | None = None) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    normalized = _normalize_paths(paths)
    if _has_commits(workspace):
        if normalized:
            _unstage_paths_from_head(workspace, normalized)
        else:
            _call_git(porcelain.reset, str(workspace), "mixed", "HEAD")
    else:
        if not normalized:
            status = _call_git(porcelain.status, str(workspace), untracked_files="all")
            normalized = [_decode(path) for paths_ in status.staged.values() for path in paths_]
        if normalized:
            _call_git(porcelain.rm, str(workspace), normalized, cached=True)
    return get_project_git_snapshot(project_id)


def commit_project_git(project_id: str, message: str) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    _call_git(porcelain.commit, str(workspace), message=message.encode("utf-8"))
    return get_project_git_snapshot(project_id)


def create_project_git_branch(project_id: str, branch: str) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    name = _resolve_branch(branch)
    _call_git(porcelain.switch, str(workspace), b"HEAD", create=name.encode("utf-8"))
    return get_project_git_snapshot(project_id)


def switch_project_git_branch(project_id: str, branch: str) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    name = _resolve_branch(branch)
    _call_git(porcelain.switch, str(workspace), name.encode("utf-8"))
    return get_project_git_snapshot(project_id)


def add_project_git_remote(project_id: str, name: str, url: str) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    remote = _resolve_remote(name)
    remote_url = url.strip()
    if not remote_url:
        raise RuntimeError("Git remote URL is required")
    _call_git(porcelain.remote_add, str(workspace), remote, remote_url)
    return get_project_git_snapshot(project_id)


def fetch_project_git_remote(project_id: str, remote: str) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    remote_name = _resolve_remote(remote)
    result = _call_git(
        porcelain.fetch,
        str(workspace),
        _remote_url(workspace, remote_name),
        outstream=io.StringIO(),
        errstream=io.BytesIO(),
        quiet=True,
    )
    _record_remote_refs(workspace, remote_name, result.refs)
    return get_project_git_snapshot(project_id)


def pull_project_git_branch(project_id: str, remote: str, branch: str | None = None) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    remote_name = _resolve_remote(remote)
    branch_name = _resolve_branch(branch or _active_branch(workspace))
    refspec = f"refs/heads/{branch_name}:refs/heads/{branch_name}".encode("utf-8")
    _call_git(
        porcelain.pull,
        str(workspace),
        _remote_url(workspace, remote_name),
        refspecs=refspec,
        ff_only=True,
        outstream=io.BytesIO(),
        errstream=io.BytesIO(),
    )
    _record_pushed_branch(workspace, remote_name, branch_name)
    return get_project_git_snapshot(project_id)


def push_project_git_branch(project_id: str, remote: str, branch: str | None = None) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    remote_name = _resolve_remote(remote)
    branch_name = _resolve_branch(branch or _active_branch(workspace))
    refspec = f"refs/heads/{branch_name}:refs/heads/{branch_name}".encode("utf-8")
    _call_git(
        porcelain.push,
        str(workspace),
        _remote_url(workspace, remote_name),
        refspecs=refspec,
        outstream=io.BytesIO(),
        errstream=io.BytesIO(),
    )
    _record_pushed_branch(workspace, remote_name, branch_name)
    return get_project_git_snapshot(project_id)
