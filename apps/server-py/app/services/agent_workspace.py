from __future__ import annotations

import difflib
import hashlib
import shutil
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas.runtime import FileChange, KnowledgeOperation
from app.services.project_files import project_workspace_root
from app.services.project_git import (
    commit_project_git,
    get_project_git_snapshot,
    push_project_git_branch,
    stage_project_git_paths,
)

AGENT_WRITABLE_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml"}
INTERNAL_PARTS = {".git", ".musegraph"}


def _runs_root() -> Path:
    root = (Path(settings.FILE_STORAGE_ROOT).expanduser().resolve() / "runs").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_workspace_root(run_id: str) -> Path:
    root = _runs_root()
    workspace = (root / run_id / "workspace").resolve()
    workspace.relative_to(root)
    return workspace


def _safe_path(workspace: Path, relative_path: str, *, writable: bool = False) -> Path:
    normalized = str(relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not normalized:
        raise ValueError("File path is required")
    target = (workspace / normalized).resolve()
    relative = target.relative_to(workspace)
    if any(part in INTERNAL_PARTS for part in relative.parts):
        raise ValueError("Internal project metadata cannot be accessed")
    if writable and target.suffix.lower() not in AGENT_WRITABLE_EXTENSIONS:
        raise ValueError(f"Agent cannot write file type: {target.suffix.lower()}")
    current = workspace
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic links are not allowed in agent workspaces")
    return target


def create_run_workspace(project_id: str, run_id: str) -> Path:
    source = project_workspace_root(project_id)
    if not source.is_dir():
        raise FileNotFoundError(f"Project workspace not found: {project_id}")
    target = run_workspace_root(run_id)
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".git", ".musegraph"),
    )
    return target


def delete_run_workspace(run_id: str) -> None:
    root = _runs_root()
    run_root = run_workspace_root(run_id).parent.resolve()
    run_root.relative_to(root)
    if run_root.exists():
        shutil.rmtree(run_root)


def list_run_files(run_id: str) -> list[dict[str, Any]]:
    workspace = run_workspace_root(run_id)
    return [
        {
            "path": path.relative_to(workspace).as_posix(),
            "size": path.stat().st_size,
        }
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and not any(part in INTERNAL_PARTS for part in path.relative_to(workspace).parts)
    ]


def read_run_file(run_id: str, relative_path: str) -> str:
    workspace = run_workspace_root(run_id)
    target = _safe_path(workspace, relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"Run file not found: {relative_path}")
    return target.read_text(encoding="utf-8")


def write_run_file(run_id: str, relative_path: str, content: str) -> dict[str, Any]:
    workspace = run_workspace_root(run_id)
    target = _safe_path(workspace, relative_path, writable=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {
        "path": target.relative_to(workspace).as_posix(),
        "size": target.stat().st_size,
    }


def delete_run_file(run_id: str, relative_path: str) -> None:
    workspace = run_workspace_root(run_id)
    target = _safe_path(workspace, relative_path, writable=True)
    if not target.is_file():
        raise FileNotFoundError(f"Run file not found: {relative_path}")
    target.unlink()


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_map(root: Path) -> dict[str, Path]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not any(part in INTERNAL_PARTS for part in path.relative_to(root).parts)
    }


def collect_file_changes(project_id: str, run_id: str) -> list[FileChange]:
    canonical_root = project_workspace_root(project_id)
    candidate_root = run_workspace_root(run_id)
    before = _file_map(canonical_root)
    after = _file_map(candidate_root)
    changes: list[FileChange] = []
    for path in sorted(set(before) | set(after)):
        before_bytes = before[path].read_bytes() if path in before else None
        after_bytes = after[path].read_bytes() if path in after else None
        if before_bytes == after_bytes:
            continue
        if before_bytes is None:
            change_type = "added"
        elif after_bytes is None:
            change_type = "deleted"
        else:
            change_type = "modified"
        try:
            before_text = before_bytes.decode("utf-8") if before_bytes is not None else ""
            after_text = after_bytes.decode("utf-8") if after_bytes is not None else ""
            diff = "".join(
                difflib.unified_diff(
                    before_text.splitlines(keepends=True),
                    after_text.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
        except UnicodeDecodeError:
            diff = f"Binary files a/{path} and b/{path} differ\n"
        changes.append(
            FileChange(
                path=path,
                change_type=change_type,
                before_hash=_content_hash(before_bytes) if before_bytes is not None else None,
                after_hash=_content_hash(after_bytes) if after_bytes is not None else None,
                diff=diff,
            )
        )
    return changes


def current_project_commit(project_id: str) -> str:
    snapshot = get_project_git_snapshot(project_id)
    commits = snapshot.get("commits") or []
    return str(commits[0]["hash"]) if commits else ""


def publish_file_changes(
    project_id: str,
    run_id: str,
    changes: list[FileChange],
    message: str,
) -> str:
    if not changes:
        return current_project_commit(project_id)
    canonical_root = project_workspace_root(project_id)
    candidate_root = run_workspace_root(run_id)
    backup_root = run_workspace_root(run_id).parent / "publish-backup"
    if backup_root.exists():
        shutil.rmtree(backup_root)
    backup_root.mkdir(parents=True)
    existing_paths: set[str] = set()
    try:
        for change in changes:
            canonical = _safe_path(canonical_root, change.path)
            candidate = _safe_path(candidate_root, change.path)
            backup = backup_root / change.path
            if canonical.is_file():
                existing_paths.add(change.path)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(canonical, backup)
            if change.change_type == "deleted":
                canonical.unlink()
            else:
                canonical.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, canonical)
        paths = [change.path for change in changes]
        stage_project_git_paths(project_id, paths)
        snapshot = commit_project_git(project_id, message)
        push_project_git_branch(project_id, "origin", snapshot["branch"])
        return str(snapshot["commits"][0]["hash"])
    except Exception:
        for change in changes:
            canonical = _safe_path(canonical_root, change.path)
            backup = backup_root / change.path
            if change.path in existing_paths:
                canonical.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, canonical)
            elif canonical.exists():
                canonical.unlink()
        raise
    finally:
        if backup_root.exists():
            shutil.rmtree(backup_root)


def apply_knowledge_operations(
    records: list[dict[str, Any]],
    operations: list[KnowledgeOperation],
    revision_id: str,
) -> list[dict[str, Any]]:
    current = {str(record["id"]): dict(record) for record in records}
    for operation in operations:
        if operation.operation == "delete":
            if operation.record_id not in current:
                raise ValueError(f"Knowledge record not found: {operation.record_id}")
            del current[operation.record_id]
            continue
        record = operation.record.model_dump(mode="json")
        record["revision"] = revision_id
        current[record["id"]] = record
    for record in current.values():
        if record["kind"] == "relation":
            if record["source_id"] not in current:
                raise ValueError(f"Relation source does not exist: {record['source_id']}")
            if record["target_id"] not in current:
                raise ValueError(f"Relation target does not exist: {record['target_id']}")
    return [current[key] for key in sorted(current)]
