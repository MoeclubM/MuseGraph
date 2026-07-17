"""Text-type pack loader.

A *text-type pack* is a YAML file in ``app/services/agent/packs/`` that
bundles per-text-type defaults: default skill flavors, auditor
dimensions, unit naming, and control-doc templates. Packs are read-only
data; they drive runtime behaviour but are
not stored in the database.

Usage::

    from app.services.agent.packs import load_pack, list_packs
    pack = load_pack("novel")
    pack.auditor_dimensions  # ["continuity", "evidence_grounding", ...]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from typing import Any

import yaml


@dataclass(frozen=True)
class TextTypePack:
    text_type: str
    display_name: str
    default_skills: dict[str, str] = field(default_factory=dict)
    auditor_dimensions: list[str] = field(default_factory=list)
    knowledge_types: list[str] = field(default_factory=list)
    unit: dict[str, Any] = field(default_factory=dict)
    control_docs: dict[str, str] = field(default_factory=dict)


_PACK_CACHE: dict[str, TextTypePack] = {}


def _packs_dir() -> resources.Traversable:
    return resources.files("app.services.agent").joinpath("packs")


def list_packs() -> list[dict[str, Any]]:
    """Return a small descriptor for every pack found on disk."""

    out: list[dict[str, Any]] = []
    for entry in _packs_dir().iterdir():
        name = entry.name
        if not name.endswith(".yaml"):
            continue
        slug = name[:-5]
        pack = load_pack(slug)
        out.append({
            "text_type": pack.text_type,
            "display_name": pack.display_name,
            "auditor_dimensions": pack.auditor_dimensions,
            "knowledge_types": pack.knowledge_types,
            "unit": pack.unit,
        })
    out.sort(key=lambda item: item["text_type"])
    return out


def load_pack(text_type: str | None) -> TextTypePack:
    """Load and cache a pack by slug."""

    slug = (text_type or "generic").strip().lower() or "generic"
    cached = _PACK_CACHE.get(slug)
    if cached is not None:
        return cached

    resource = _packs_dir().joinpath(f"{slug}.yaml")
    if not resource.is_file():
        raise FileNotFoundError(f"Unknown text-type pack: {slug}")

    raw = resource.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Pack {slug}.yaml is malformed: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Pack {slug}.yaml must be a mapping at the top level")

    required = {"text_type", "display_name", "auditor_dimensions"}
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Pack {slug}.yaml missing required keys: {missing}")
    if str(data["text_type"]) != slug:
        raise ValueError(f"Pack filename {slug}.yaml does not match text_type")
    default_skills = {
        str(k): str(v) for k, v in (data.get("default_skills") or {}).items()
    }
    auditor_dimensions = [str(d) for d in data.get("auditor_dimensions") or []]
    knowledge_types = [str(item) for item in data.get("knowledge_types") or []]
    unit = dict(data.get("unit") or {})
    control_docs = {
        str(k): str(v) for k, v in (data.get("control_docs") or {}).items()
    }
    if not default_skills:
        raise ValueError(f"Pack {slug}.yaml must define default_skills")
    if not auditor_dimensions:
        raise ValueError(f"Pack {slug}.yaml must define auditor_dimensions")
    if not knowledge_types:
        raise ValueError(f"Pack {slug}.yaml must define knowledge_types")
    if not str(unit.get("name") or "").strip():
        raise ValueError(f"Pack {slug}.yaml must define unit.name")
    if set(control_docs) != {"intent", "focus", "rules", "bible"}:
        raise ValueError(f"Pack {slug}.yaml must define all four control documents")
    for relative in control_docs.values():
        if not _packs_dir().joinpath(relative).is_file():
            raise FileNotFoundError(f"Pack {slug}.yaml references missing template: {relative}")

    pack = TextTypePack(
        text_type=str(data["text_type"]),
        display_name=str(data["display_name"]),
        default_skills=default_skills,
        auditor_dimensions=auditor_dimensions,
        knowledge_types=knowledge_types,
        unit=unit,
        control_docs=control_docs,
    )
    _PACK_CACHE[slug] = pack
    return pack


def clear_cache() -> None:
    """Drop the in-memory pack cache. Tests use this between cases."""

    _PACK_CACHE.clear()


def get_project_pack(project: Any) -> "TextTypePack":
    """Return the project's active ``TextTypePack``."""

    slug = str(project.pack_slug or "").strip().lower() or "generic"
    return load_pack(slug)


def set_project_pack(project: Any, slug: str) -> None:
    """Persist ``slug`` as the project's active pack (in-memory only; caller commits)."""

    normalized = slug.strip().lower()
    load_pack(normalized)
    project.pack_slug = normalized
