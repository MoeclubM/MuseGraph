"""Control-doc seeding.

On project creation, the active text-type pack's templates are copied
into the project workspace as four long-lived editable files:
``intent.md`` / ``focus.md`` / ``rules.md`` / ``bible.md``.
"""

from __future__ import annotations

from importlib import resources
from typing import Any

from app.services.agent.packs import get_project_pack
from app.services.agent.packs import TextTypePack
from app.services.project_files import (
    create_project_file,
    list_project_files,
    project_workspace_root,
)

CONTROL_DOC_NAMES = ("intent", "focus", "rules", "bible")


def _template_text(pack: TextTypePack, name: str) -> str:
    """Read a control-document template from a pack."""

    relative = pack.control_docs[name]
    resource = resources.files("app.services.agent.packs").joinpath(relative)
    if not resource.is_file():
        raise FileNotFoundError(f"Missing control-doc template: {relative}")
    return resource.read_text(encoding="utf-8")


def missing_control_docs(project_id: str) -> list[str]:
    """Return the subset of CONTROL_DOC_NAMES absent from the workspace root."""

    files = list_project_files(project_id).get("files") or []
    existing = {
        str(item.get("path") or "").lstrip("/") for item in files if isinstance(item, dict)
    }
    return [name for name in CONTROL_DOC_NAMES if f"{name}.md" not in existing]


def seed_control_docs(project_id: str, project: Any) -> list[str]:
    """Create any missing control docs from the active pack.

    Returns the list of workspace-relative paths that were created.
    Existing files are never overwritten.
    """

    pack = get_project_pack(project)
    created: list[str] = []
    for name in missing_control_docs(project_id):
        relative = f"{name}.md"
        create_project_file(project_id, relative, _template_text(pack, name))
        created.append(relative)
    return created
