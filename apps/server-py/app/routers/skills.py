from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.runtime import ProjectSkill
from app.models.user import User
from app.schemas.runtime import AgentRole, ResolvedSkillSnapshot, SkillScope
from app.services.agent.skills import (
    builtin_skill_snapshots,
    resolve_project_skill,
    validate_skill_definition,
)
from app.services.project_access import (
    PROJECT_PERMISSION_MANAGE,
    PROJECT_PERMISSION_VIEW,
    require_project_permission,
)

router = APIRouter()


class SkillWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(min_length=1, max_length=50_000)
    scopes: list[SkillScope] = Field(min_length=1)
    roles: list[AgentRole] = Field(min_length=1)
    allowed_tools: list[str] = Field(min_length=1)
    params_schema: dict[str, Any] = Field(default_factory=dict)
    default_model_component: str | None = Field(default=None, max_length=80)
    enabled: bool = True


class SkillUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(min_length=1, max_length=50_000)
    scopes: list[SkillScope] = Field(min_length=1)
    roles: list[AgentRole] = Field(min_length=1)
    allowed_tools: list[str] = Field(min_length=1)
    params_schema: dict[str, Any] = Field(default_factory=dict)
    default_model_component: str | None = Field(default=None, max_length=80)
    enabled: bool = True


def _snapshot(record: ProjectSkill) -> ResolvedSkillSnapshot:
    return ResolvedSkillSnapshot(
        slug=record.slug,
        name=record.name,
        description=record.description,
        instructions=record.instructions,
        scopes=record.scopes,
        roles=record.roles,
        allowed_tools=record.allowed_tools,
        params_schema=record.params_schema,
        default_model_component=record.default_model_component,
        version=record.version,
        source="project",
    )


@router.get("", response_model=list[ResolvedSkillSnapshot])
async def list_skills(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    result = await db.execute(
        select(ProjectSkill)
        .where(ProjectSkill.project_id == project_id)
        .order_by(ProjectSkill.slug)
    )
    return builtin_skill_snapshots() + [_snapshot(record) for record in result.scalars()]


@router.post("", response_model=ResolvedSkillSnapshot, status_code=status.HTTP_201_CREATED)
async def create_skill(
    project_id: str,
    body: SkillWrite,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    try:
        validate_skill_definition(
            slug=body.slug,
            scopes=body.scopes,
            roles=body.roles,
            allowed_tools=body.allowed_tools,
            default_model_component=body.default_model_component,
            params_schema=body.params_schema,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    exists = await db.execute(
        select(ProjectSkill.id).where(
            ProjectSkill.project_id == project_id,
            ProjectSkill.slug == body.slug,
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Skill slug already exists")
    record = ProjectSkill(project_id=project_id, **body.model_dump())
    db.add(record)
    await db.flush()
    return _snapshot(record)


@router.put("/{slug}", response_model=ResolvedSkillSnapshot)
async def update_skill(
    project_id: str,
    slug: str,
    body: SkillUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    result = await db.execute(
        select(ProjectSkill).where(
            ProjectSkill.project_id == project_id,
            ProjectSkill.slug == slug,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project skill not found")
    try:
        validate_skill_definition(
            slug=record.slug,
            scopes=body.scopes,
            roles=body.roles,
            allowed_tools=body.allowed_tools,
            default_model_component=body.default_model_component,
            params_schema=body.params_schema,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    for key, value in body.model_dump().items():
        setattr(record, key, value)
    record.version += 1
    await db.flush()
    return _snapshot(record)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    project_id: str,
    slug: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    result = await db.execute(
        select(ProjectSkill).where(
            ProjectSkill.project_id == project_id,
            ProjectSkill.slug == slug,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project skill not found")
    await db.delete(record)
    return None


@router.get("/resolve/preview", response_model=ResolvedSkillSnapshot)
async def preview_skill_resolution(
    project_id: str,
    operation: Literal["write", "analyze", "suggest"] = Query(...),
    role: AgentRole = Query(...),
    slug: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    try:
        return await resolve_project_skill(
            db,
            project_id=project_id,
            pack_slug=project.pack_slug,
            operation=operation,
            role=role,
            requested_slug=slug,
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
