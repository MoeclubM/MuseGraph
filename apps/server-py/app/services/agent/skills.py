"""Skill runtime helpers.

These helpers load skill records from the ``prompt_skills`` table and
turn them into prompt prefixes / tool whitelists that the agent loop and
suggest endpoint can plug in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import PromptSkill
from app.models.project import TextProject
from app.services.agent.skill_catalog import builtin_skill_records


@dataclass(frozen=True)
class ResolvedSkill:
    slug: str
    name: str
    system_prompt: str
    allowed_tools: frozenset[str] | None
    default_model_component: str | None
    scope: list[str]


def _to_resolved(record: PromptSkill) -> ResolvedSkill:
    tools = record.allowed_tools if isinstance(record.allowed_tools, list) else None
    return ResolvedSkill(
        slug=record.slug,
        name=record.name,
        system_prompt=record.system_prompt or "",
        allowed_tools=frozenset(str(t) for t in tools) if tools else None,
        default_model_component=record.default_model_component or None,
        scope=list(record.scope) if isinstance(record.scope, list) else [],
    )


async def load_active_skill(slug: str | None, db: AsyncSession) -> ResolvedSkill | None:
    """Look up a skill by slug. Returns None for blank/inactive slugs.

    Resolution order: project-scoped custom (if multiple projects share
    the same slug) is currently ambiguous when called without project_id,
    so this helper looks up the *global* record first; project lookup is
    handled by ``list_project_visible_skills``.
    """

    cleaned = (slug or "").strip()
    if not cleaned:
        return None
    result = await db.execute(
        select(PromptSkill).where(
            PromptSkill.slug == cleaned, PromptSkill.is_active.is_(True)
        )
    )
    record = result.scalars().first()
    if record is None:
        return None
    return _to_resolved(record)


async def list_skills(scope: str | None, db: AsyncSession) -> list[dict[str, Any]]:
    """List active skills, optionally filtered by scope tag (global only)."""

    stmt = (
        select(PromptSkill)
        .where(PromptSkill.is_active.is_(True))
        .order_by(PromptSkill.sort_order, PromptSkill.name)
    )
    result = await db.execute(stmt)
    out: list[dict[str, Any]] = []
    for record in result.scalars().all():
        record_scope = record.scope if isinstance(record.scope, list) else []
        if scope and record_scope and scope not in record_scope:
            continue
        out.append({
            "id": record.id,
            "slug": record.slug,
            "name": record.name,
            "icon": record.icon,
            "description": record.description,
            "scope": record_scope,
            "tags": record.tags or [],
            "is_builtin": record.is_builtin,
            "default_model_component": record.default_model_component,
        })
    return out


async def _get_disabled_slugs(project_id: str, db: AsyncSession) -> list[str]:
    project = await db.get(TextProject, project_id)
    if project is None:
        return []
    state = project.creative_state if isinstance(project.creative_state, dict) else {}
    skills_state = state.get("skills") if isinstance(state.get("skills"), dict) else {}
    disabled = skills_state.get("disabled_slugs")
    return [str(s) for s in disabled] if isinstance(disabled, list) else []


async def list_project_visible_skills(
    project_id: str, scope: str | None, *, db: AsyncSession,
) -> list[dict[str, Any]]:
    """Union of global built-ins (minus project-disabled) and the project's own customs."""

    disabled = set(await _get_disabled_slugs(project_id, db))
    stmt = (
        select(PromptSkill)
        .where(
            PromptSkill.is_active.is_(True),
            or_(
                PromptSkill.owner_project_id.is_(None),
                PromptSkill.owner_project_id == project_id,
            ),
        )
        .order_by(PromptSkill.sort_order, PromptSkill.name)
    )
    rows = (await db.execute(stmt)).scalars().all()
    out: list[dict[str, Any]] = []
    for record in rows:
        if record.is_builtin and record.slug in disabled:
            continue
        record_scope = record.scope if isinstance(record.scope, list) else []
        if scope and record_scope and scope not in record_scope:
            continue
        out.append({
            "id": record.id,
            "slug": record.slug,
            "name": record.name,
            "icon": record.icon,
            "description": record.description,
            "scope": record_scope,
            "tags": record.tags or [],
            "is_builtin": record.is_builtin,
            "owner_project_id": record.owner_project_id,
            "default_model_component": record.default_model_component,
        })
    return out


async def find_project_skills(
    project_id: str,
    query: str,
    *,
    scope: str | None,
    limit: int,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Cheap ranked search over visible skills. Returns at most ``limit`` rows."""

    visible = await list_project_visible_skills(project_id, scope, db=db)
    q = (query or "").strip().lower()
    if not q:
        return visible[: max(0, limit)]

    def score(item: dict[str, Any]) -> int:
        s = 0
        name = (item.get("name") or "").lower()
        slug = (item.get("slug") or "").lower()
        desc = (item.get("description") or "").lower()
        tags = " ".join(str(t).lower() for t in item.get("tags") or [])
        if slug == q or name == q:
            s += 100
        if slug.startswith(q) or name.startswith(q):
            s += 50
        if q in slug or q in name:
            s += 20
        if q in desc:
            s += 10
        if q in tags:
            s += 8
        return s

    ranked = [(score(i), i) for i in visible]
    ranked = [pair for pair in ranked if pair[0] > 0]
    ranked.sort(key=lambda p: -p[0])
    return [item for _, item in ranked[: max(0, limit)]]


async def set_project_skill_disabled(
    project_id: str, slug: str, disabled: bool, *, db: AsyncSession,
) -> None:
    """Toggle a built-in slug into / out of ``creative_state.skills.disabled_slugs``.

    No-op for blank slugs. Custom skills (non-builtin owned by this
    project) ignore this list — their visibility is controlled by
    creating / deleting the row itself, so callers should not flip
    their state here.
    """

    s = (slug or "").strip()
    if not s:
        return
    project = await db.get(TextProject, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")
    state = dict(project.creative_state or {})
    skills_state = dict(state.get("skills") or {})
    current = list(skills_state.get("disabled_slugs") or [])
    if disabled and s not in current:
        current.append(s)
    elif not disabled:
        current = [x for x in current if x != s]
    skills_state["disabled_slugs"] = current
    state["skills"] = skills_state
    project.creative_state = state
    await db.flush()


async def seed_builtin_skills(db: AsyncSession) -> int:
    """Idempotent upsert of every record returned by ``builtin_skill_records()``.

    Returns the number of *new* rows inserted on this call.
    """

    inserted = 0
    for record in builtin_skill_records():
        existing = (
            await db.execute(
                select(PromptSkill).where(
                    PromptSkill.slug == record["slug"],
                    PromptSkill.owner_project_id.is_(None),
                )
            )
        ).scalars().first()
        if existing is None:
            db.add(PromptSkill(**record))
            inserted += 1
        else:
            for key, value in record.items():
                setattr(existing, key, value)
    await db.commit()
    return inserted

