from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path
from typing import Any

from app.services.project_files import project_workspace_root


def _safe_archive_title(project: Any) -> str:
    safe = "".join(
        character
        for character in str(project.title or "untitled")
        if character.isalnum() or character in " -_"
    ).strip()[:50]
    return safe or "untitled"


def _export_project_bundle(project: Any) -> tuple[bytes, str]:
    workspace = project_workspace_root(project.id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(workspace.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(workspace)
            if ".git" in relative.parts or path.is_symlink():
                continue
            archive.write(path, arcname=relative.as_posix())
    return buffer.getvalue(), f"{_safe_archive_title(project)}.zip"


def _export_project_repository(project: Any) -> tuple[bytes, str]:
    workspace = project_workspace_root(project.id)
    archive_root = _safe_archive_title(project)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(workspace.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(workspace)
            if relative.as_posix() == ".git/config":
                archive.writestr(
                    f"{archive_root}/.git/config",
                    (
                        "[core]\n"
                        "\trepositoryformatversion = 0\n"
                        "\tfilemode = false\n"
                        "\tbare = false\n"
                        "\tlogallrefupdates = true\n"
                    ),
                )
                continue
            if ".git" in relative.parts and (
                relative.name.endswith(".lock") or "logs" in relative.parts
            ):
                continue
            archive.write(path, arcname=f"{archive_root}/{relative.as_posix()}")
    return buffer.getvalue(), f"{archive_root}-repository.zip"


async def export_project_bundle(project: Any) -> tuple[bytes, str]:
    return await asyncio.to_thread(_export_project_bundle, project)


async def export_project_repository(project: Any) -> tuple[bytes, str]:
    return await asyncio.to_thread(_export_project_repository, project)
