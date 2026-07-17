from __future__ import annotations

import io
import mimetypes
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings

ALLOWED_PROJECT_FILE_EXTENSIONS = {
    ".txt", ".md", ".json", ".yaml", ".yml", ".docx", ".pdf",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
}
INTERNAL_WORKSPACE_DIRS = {".git", ".musegraph"}


def _storage_root() -> Path:
    return Path(settings.FILE_STORAGE_ROOT).expanduser().resolve()


def project_workspace_root(project_id: str) -> Path:
    root = _storage_root()
    workspace = (root / "projects" / str(project_id) / "workspace").resolve()
    workspace.relative_to(root)
    return workspace


def _project_file_path(project_id: str, relative_path: str) -> Path:
    workspace = project_workspace_root(project_id)
    normalized = str(relative_path or "").strip().replace("\\", "/").lstrip("/")
    if not normalized:
        raise ValueError("Project file path cannot be empty")
    target = (workspace / normalized).resolve()
    relative = target.relative_to(workspace)
    if any(part in INTERNAL_WORKSPACE_DIRS for part in relative.parts):
        raise ValueError("Project version metadata is internal")
    current = workspace
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic links are not allowed in project paths")
    if target.is_symlink():
        raise ValueError("Symbolic links are not allowed in project paths")
    return target


def _metadata(project_id: str, path: Path) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    stat = path.stat()
    rel_path = path.relative_to(workspace).as_posix()
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return {
        "path": rel_path,
        "name": path.name,
        "size": stat.st_size,
        "content_type": content_type,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "text_extractable": path.suffix.lower() in ALLOWED_PROJECT_FILE_EXTENSIONS,
    }


def extract_text_from_file(filename: str, content: bytes) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in {".txt", ".md", ".json", ".yaml", ".yml"}:
        return content.decode("utf-8")
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return f"[Image file: {filename}]"
    if ext == ".docx":
        from docx import Document

        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(f"Unsupported file type: {ext}")


def validate_project_upload(filename: str, path: Path) -> None:
    ext = Path(filename or "").suffix.lower()
    with path.open("rb") as source:
        header = source.read(16)
    if ext == ".pdf" and not header.startswith(b"%PDF-"):
        raise ValueError("PDF signature does not match the filename")
    if ext == ".docx":
        if not header.startswith(b"PK"):
            raise ValueError("DOCX signature does not match the filename")
        with zipfile.ZipFile(path) as archive:
            total_size = 0
            for item in archive.infolist():
                member = Path(item.filename)
                if member.is_absolute() or ".." in member.parts:
                    raise ValueError("DOCX contains an unsafe archive path")
                if item.is_dir():
                    continue
                total_size += item.file_size
                if item.compress_size and item.file_size / item.compress_size > 100:
                    raise ValueError("DOCX contains an unsafe compression ratio")
            if total_size > 200 * 1024 * 1024:
                raise ValueError("DOCX expanded content exceeds 200 MiB")
    signatures = {
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".gif": (b"GIF87a", b"GIF89a"),
    }
    if ext in signatures and not any(header.startswith(value) for value in signatures[ext]):
        raise ValueError(f"{ext} signature does not match the filename")
    if ext == ".webp" and not (
        header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    ):
        raise ValueError("WEBP signature does not match the filename")
    if ext == ".svg":
        raise ValueError("SVG upload is not allowed; create trusted SVG text in the editor")


def save_project_file_from_path(
    project_id: str,
    filename: str,
    source_path: Path,
    content_type: str | None = None,
) -> dict[str, Any]:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_PROJECT_FILE_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")
    validate_project_upload(filename, source_path)
    expected_content_type = (
        mimetypes.guess_type(filename)[0] or "application/octet-stream"
    )
    if (
        content_type
        and content_type.split(";", 1)[0].strip().lower()
        != expected_content_type.lower()
    ):
        raise ValueError("Declared MIME type does not match the uploaded file")
    workspace = project_workspace_root(project_id)
    uploads_dir = workspace / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    original_name = Path(filename or f"upload{ext}").name
    stored_path = (uploads_dir / f"{uuid4().hex}-{original_name}").resolve()
    stored_path.relative_to(workspace)
    shutil.copy2(source_path, stored_path)
    rel_path = stored_path.relative_to(workspace).as_posix()
    _commit_workspace_change(project_id, [rel_path], f"Upload project file {original_name}")
    return _metadata(project_id, stored_path)


def _commit_workspace_change(project_id: str, paths: list[str], message: str) -> None:
    from app.services.project_git import commit_project_git, push_project_git_branch, stage_project_git_paths

    snapshot = stage_project_git_paths(project_id, paths)
    commit_snapshot = commit_project_git(project_id, message)
    push_project_git_branch(project_id, "origin", commit_snapshot.get("branch") or snapshot["branch"])


def create_project_file(project_id: str, relative_path: str, content: str = "") -> dict[str, Any]:
    ext = Path(relative_path or "").suffix.lower()
    if ext not in ALLOWED_PROJECT_FILE_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    target = _project_file_path(project_id, relative_path)
    if target.exists():
        raise FileExistsError(f"Project file already exists: {relative_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    rel_path = target.relative_to(project_workspace_root(project_id)).as_posix()
    _commit_workspace_change(project_id, [rel_path], f"Create project file {rel_path}")
    return _metadata(project_id, target)


def update_project_file(project_id: str, relative_path: str, content: str) -> dict[str, Any]:
    target = _project_file_path(project_id, relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"Project file not found: {relative_path}")
    if target.suffix.lower() not in {".txt", ".md", ".json", ".yaml", ".yml", ".svg"}:
        raise ValueError(f"Project file is not editable text: {relative_path}")
    target.write_text(content, encoding="utf-8")
    rel_path = target.relative_to(project_workspace_root(project_id)).as_posix()
    _commit_workspace_change(project_id, [rel_path], f"Update project file {rel_path}")
    return _metadata(project_id, target)


def delete_project_file(project_id: str, relative_path: str) -> None:
    target = _project_file_path(project_id, relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"Project file not found: {relative_path}")
    rel_path = target.relative_to(project_workspace_root(project_id)).as_posix()
    target.unlink()
    _commit_workspace_change(project_id, [rel_path], f"Delete project file {rel_path}")


def rename_project_file(project_id: str, relative_path: str, new_relative_path: str) -> dict[str, Any]:
    target = _project_file_path(project_id, relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"Project file not found: {relative_path}")
    new_target = _project_file_path(project_id, new_relative_path)
    if new_target.exists():
        raise FileExistsError(f"Project file already exists: {new_relative_path}")
    ext = new_target.suffix.lower()
    if ext not in ALLOWED_PROJECT_FILE_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    old_rel = target.relative_to(project_workspace_root(project_id)).as_posix()
    new_target.parent.mkdir(parents=True, exist_ok=True)
    target.rename(new_target)
    new_rel = new_target.relative_to(project_workspace_root(project_id)).as_posix()
    _commit_workspace_change(project_id, [old_rel, new_rel], f"Rename project file {old_rel} to {new_rel}")
    return _metadata(project_id, new_target)


def list_project_files(project_id: str) -> dict[str, Any]:
    workspace = project_workspace_root(project_id)
    workspace.mkdir(parents=True, exist_ok=True)
    files = [
        _metadata(project_id, path)
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
        and not any(part in INTERNAL_WORKSPACE_DIRS for part in path.relative_to(workspace).parts)
    ]
    return {"files": files}


def read_project_file(project_id: str, relative_path: str) -> dict[str, Any]:
    target = _project_file_path(project_id, relative_path)
    if not target.is_file():
        raise FileNotFoundError(f"Project file not found: {relative_path}")
    data = target.read_bytes()
    item = _metadata(project_id, target)
    item["content"] = extract_text_from_file(target.name, data)
    return item
