from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path
from typing import Any

from app.services.project_files import project_workspace_root
from app.services.project_workspace import write_project_workspace_snapshot


def _safe_archive_title(project: Any) -> str:
    title = project.title or "untitled"
    safe = "".join(c for c in title if c.isalnum() or c in " -_").strip()[:50]
    return safe or "untitled"


def _zip_workspace_directory(workspace: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(workspace.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(workspace)
            if ".git" in relative.parts:
                continue
            archive.write(path, arcname=relative.as_posix())
    return buffer.getvalue()


def export_project_bundle_sync(
    project: Any,
    chapters: list[Any],
    facts: list[Any],
) -> tuple[bytes, str, str]:
    """Build a ZIP of the project workspace snapshot (documents, metadata, uploads)."""
    write_project_workspace_snapshot(
        project,
        chapters,
        facts,
    )
    workspace = project_workspace_root(project.id)
    content = _zip_workspace_directory(workspace)
    filename = f"{_safe_archive_title(project)}.zip"
    return content, "application/zip", filename


async def export_project_bundle(
    project: Any,
    chapters: list[Any],
    facts: list[Any],
) -> tuple[bytes, str, str]:
    return await asyncio.to_thread(
        export_project_bundle_sync,
        project,
        chapters,
        facts,
    )
