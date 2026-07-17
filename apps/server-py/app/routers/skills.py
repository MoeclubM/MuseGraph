"""Project-scoped agent skills router.

Skills are reusable agent prompt presets. Built-ins are global (
``owner_project_id IS NULL``); per-project customs (``owner_project_id``
= this project) are managed here. Built-ins cannot be deleted; they can
only be toggled on/off via ``creative_state.skills.disabled_slugs``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.config import PromptSkill
from app.models.user import User
from app.services.agent.skills import (
    list_project_visible_skills,
    set_project_skill_disabled,
)
from app.services.project_access import (
    PROJECT_PERMISSION_EDIT,
    PROJECT_PERMISSION_VIEW,
    require_project_permission,
)


router = APIRouter()


class SkillCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    system_prompt: str
    icon: str | None = None
    scope: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None
    default_model_component: str | None = None


class SkillToggle(BaseModel):
    enabled: bool


def _serialize(record: PromptSkill) -> dict[str, Any]:
    return {
        "id": record.id,
        "slug": record.slug,
        "name": record.name,
        "icon": record.icon,
        "description": record.description,
        "scope": record.scope or [],
        "tags": record.tags or [],
        "system_prompt": record.system_prompt,
        "allowed_tools": record.allowed_tools,
        "default_model_component": record.default_model_component,
        "is_builtin": record.is_builtin,
        "is_active": record.is_active,
        "owner_project_id": record.owner_project_id,
    }


@router.get("", response_model=list[dict[str, Any]])
async def list_skills(
    project_id: str,
    scope: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return enabled-for-this-project skills (built-ins minus disabled + project customs)."""

    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    return await list_project_visible_skills(project_id, scope, db=db)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_custom_skill(
    project_id: str,
    body: SkillCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a project-scoped custom skill."""

    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    existing = (
        await db.execute(
            select(PromptSkill).where(
                PromptSkill.slug == body.slug,
                PromptSkill.owner_project_id == project_id,
            )
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A custom skill with this slug already exists in this project.",
        )
    record = PromptSkill(
        slug=body.slug,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        icon=body.icon,
        scope=body.scope,
        tags=body.tags,
        allowed_tools=body.allowed_tools,
        default_model_component=body.default_model_component,
        is_builtin=False,
        is_active=True,
        sort_order=999,
        owner_project_id=project_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _serialize(record)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_skill(
    project_id: str,
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a project-scoped custom skill. Built-ins cannot be deleted."""

    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    record = (
        await db.execute(
            select(PromptSkill).where(
                PromptSkill.slug == slug,
                PromptSkill.owner_project_id == project_id,
            )
        )
    ).scalars().first()
    if record is None:
        global_record = (
            await db.execute(
                select(PromptSkill).where(
                    PromptSkill.slug == slug,
                    PromptSkill.owner_project_id.is_(None),
                )
            )
        ).scalars().first()
        if global_record is not None and global_record.is_builtin:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="Built-in skills cannot be deleted; use POST /toggle to disable.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found"
        )
    await db.delete(record)
    await db.commit()


@router.post("/{slug}/toggle")
async def toggle_skill(
    project_id: str,
    slug: str,
    body: SkillToggle,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enable / disable a skill for this project. For built-ins it flips
    membership in ``creative_state.skills.disabled_slugs``. For project
    customs the toggle simply marks ``is_active`` (and the disabled list
    is also updated for consistency)."""

    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_EDIT)
    record = (
        await db.execute(
            select(PromptSkill).where(
                PromptSkill.slug == slug,
                PromptSkill.owner_project_id.is_(None),
            )
        )
    ).scalars().first()
    if record is None:
        record = (
            await db.execute(
                select(PromptSkill).where(
                    PromptSkill.slug == slug,
                    PromptSkill.owner_project_id == project_id,
                )
            )
        ).scalars().first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found"
        )

    if not record.is_builtin:
        record.is_active = body.enabled

    await set_project_skill_disabled(project_id, slug, not body.enabled, db=db)
    await db.commit()
    return {"ok": True, "slug": slug, "enabled": body.enabled, "is_builtin": record.is_builtin}
