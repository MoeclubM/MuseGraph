from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.project import ProjectMember, TextProject
from app.models.runtime import ProjectAgent, ProjectRevision
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberUpdate,
    ProjectPublicResponse,
    ProjectResponse,
    ProjectSearchResult,
    ProjectUpdate,
    ProjectVisibilityUpdate,
)
from app.services.agent.control_docs import seed_control_docs
from app.services.agent.pack_core import load_pack
from app.services.memory_client import (
    delete_project_memory_instance,
    remember_knowledge_dataset,
    start_project_memory_instance,
)
from app.services.project_access import (
    PROJECT_PERMISSION_DELETE,
    PROJECT_PERMISSION_MANAGE,
    PROJECT_PERMISSION_VIEW,
    accessible_projects_query,
    project_permissions_for_role,
    require_project_permission,
)
from app.services.project_git import (
    delete_project_git_storage,
    initialize_project_git_repo,
)
from app.services.provider_resolution import validate_project_component_models
from app.services.agent_workspace import current_project_commit

router = APIRouter()


def _attach_access(project: TextProject, user: User) -> None:
    if user.is_admin:
        role = "admin"
    elif project.user_id == user.id:
        role = "owner"
    else:
        role = next(
            (
                member.role
                for member in project.__dict__.get("members") or []
                if member.user_id == user.id
            ),
            "viewer" if project.visibility == "public" else None,
        )
    project.current_user_role = role
    project.current_user_permissions = project_permissions_for_role(role) if role else []


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        accessible_projects_query(user).order_by(TextProject.updated_at.desc())
    )
    projects = list(result.scalars().unique())
    for project in projects:
        _attach_access(project, user)
    return [ProjectResponse.model_validate(project) for project in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    load_pack(body.pack_slug)
    try:
        await validate_project_component_models(
            db,
            owner_user_id=user.id,
            component_models=body.component_models,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    project_id = str(uuid.uuid4())
    project = TextProject(
        id=project_id,
        user_id=user.id,
        title=body.title,
        description=body.description,
        visibility=body.visibility,
        component_models=body.component_models,
        memory_instance_id=project_id,
        pack_slug=body.pack_slug,
    )
    db.add(project)
    await db.flush()
    agent = ProjectAgent(
        project_id=project.id,
        created_by_user_id=user.id,
        name="默认创作 Agent",
        description="继承项目对应运行模式的模型配置，使用内置阶段提示词。",
        prompt_template_ids={},
    )
    db.add(agent)
    await db.flush()
    project.active_agent_id = agent.id
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    memory_started = False
    try:
        initialize_project_git_repo(
            project.id,
            author_name=user.nickname or "MuseGraph User",
            author_email=user.email,
        )
        seed_control_docs(project.id, project)
        git_commit = current_project_commit(project.id)
        revision = ProjectRevision(
            project_id=project.id,
            parent_revision_id=None,
            git_commit=git_commit,
            knowledge_dataset=f"project:{project.id}:revision:root",
            status="active",
            message="Initialize project",
        )
        db.add(revision)
        await db.flush()
        project.active_revision_id = revision.id
        project.memory_instance_id = project.id
        await start_project_memory_instance(project.id, llm={}, embedding={})
        memory_started = True
        await remember_knowledge_dataset(project.id, revision.knowledge_dataset, [])
    except Exception:
        delete_project_git_storage(project.id)
        if memory_started:
            await delete_project_memory_instance(project.id)
        raise
    await db.commit()
    await db.refresh(project)
    _attach_access(project, user)
    return ProjectResponse.model_validate(project)


@router.get("/public", response_model=ProjectSearchResult)
async def public_projects(
    query: str = Query(default="", max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    condition = TextProject.visibility == "public"
    if query.strip():
        pattern = f"%{query.strip()}%"
        condition = condition & or_(
            TextProject.title.ilike(pattern),
            TextProject.description.ilike(pattern),
        )
    total = int(
        (
            await db.execute(select(func.count()).select_from(TextProject).where(condition))
        ).scalar_one()
    )
    result = await db.execute(
        select(TextProject)
        .where(condition)
        .order_by(TextProject.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return ProjectSearchResult(
        items=[ProjectPublicResponse.model_validate(item) for item in result.scalars()],
        total=total,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    _attach_access(project, user)
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    updates = body.model_dump(exclude_unset=True)
    if "pack_slug" in updates:
        load_pack(updates["pack_slug"])
    if "component_models" in updates:
        try:
            await validate_project_component_models(
                db,
                owner_user_id=project.user_id,
                component_models=updates["component_models"],
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    for key, value in updates.items():
        setattr(project, key, value)
    await db.flush()
    await db.refresh(project)
    _attach_access(project, user)
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}/visibility", response_model=ProjectResponse)
async def update_visibility(
    project_id: str,
    body: ProjectVisibilityUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    project.visibility = body.visibility
    await db.flush()
    await db.refresh(project)
    _attach_access(project, user)
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(project_id, user, db, PROJECT_PERMISSION_DELETE)
    await delete_project_memory_instance(project_id)
    await db.delete(project)
    delete_project_git_storage(project_id)
    return None


@router.get("/{project_id}/members", response_model=list[ProjectMemberResponse])
async def list_members(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at)
    )
    return [ProjectMemberResponse.model_validate(item) for item in result.scalars()]


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    project_id: str,
    body: ProjectMemberCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    target = await db.get(User, body.user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    exists = await db.execute(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == body.user_id,
        )
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project member already exists")
    member = ProjectMember(project_id=project_id, user_id=body.user_id, role=body.role)
    db.add(member)
    await db.flush()
    return ProjectMemberResponse.model_validate(member)


@router.patch("/{project_id}/members/{member_id}", response_model=ProjectMemberResponse)
async def update_member(
    project_id: str,
    member_id: str,
    body: ProjectMemberUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None or member.role == "owner":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Editable member not found")
    member.role = body.role
    await db.flush()
    return ProjectMemberResponse.model_validate(member)


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    project_id: str,
    member_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None or member.role == "owner":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Removable member not found")
    await db.delete(member)
    return None
