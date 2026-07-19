from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import ProjectMember, TextProject
from app.models.user import User

PROJECT_VISIBILITY_PRIVATE = "private"
PROJECT_VISIBILITY_PUBLIC = "public"
PROJECT_VISIBILITIES = {PROJECT_VISIBILITY_PRIVATE, PROJECT_VISIBILITY_PUBLIC}

PROJECT_ROLE_ADMIN = "admin"
PROJECT_ROLE_OWNER = "owner"
PROJECT_ROLE_EDITOR = "editor"
PROJECT_ROLE_VIEWER = "viewer"
PROJECT_MEMBER_ROLES = {PROJECT_ROLE_OWNER, PROJECT_ROLE_EDITOR, PROJECT_ROLE_VIEWER}
PROJECT_COLLABORATOR_ROLES = {PROJECT_ROLE_EDITOR, PROJECT_ROLE_VIEWER}

PROJECT_PERMISSION_VIEW = "view"
PROJECT_PERMISSION_EDIT = "edit"
PROJECT_PERMISSION_RUN_AI = "run_ai"
PROJECT_PERMISSION_BUILD_MEMORY = "build_memory"
PROJECT_PERMISSION_MANAGE = "manage"
PROJECT_PERMISSION_DELETE = "delete"
PROJECT_PERMISSIONS = {
    PROJECT_PERMISSION_VIEW,
    PROJECT_PERMISSION_EDIT,
    PROJECT_PERMISSION_RUN_AI,
    PROJECT_PERMISSION_BUILD_MEMORY,
    PROJECT_PERMISSION_MANAGE,
    PROJECT_PERMISSION_DELETE,
}

PROJECT_ROLE_PERMISSIONS = {
    PROJECT_ROLE_ADMIN: PROJECT_PERMISSIONS,
    PROJECT_ROLE_OWNER: PROJECT_PERMISSIONS,
    PROJECT_ROLE_EDITOR: {
        PROJECT_PERMISSION_VIEW,
        PROJECT_PERMISSION_EDIT,
        PROJECT_PERMISSION_RUN_AI,
        PROJECT_PERMISSION_BUILD_MEMORY,
    },
    PROJECT_ROLE_VIEWER: {PROJECT_PERMISSION_VIEW},
}


def project_permissions_for_role(role: str | None) -> list[str]:
    return sorted(PROJECT_ROLE_PERMISSIONS.get(role or "", set()))


def accessible_project_ids_query(user: User):
    return permitted_project_ids_query(user, PROJECT_PERMISSION_VIEW)


def permitted_project_ids_query(user: User, permission: str):
    if permission not in PROJECT_PERMISSIONS:
        raise ValueError(f"Unknown project permission: {permission}")
    if user.is_admin:
        return select(TextProject.id)

    roles = {
        role
        for role, permissions in PROJECT_ROLE_PERMISSIONS.items()
        if role != PROJECT_ROLE_ADMIN and permission in permissions
    }
    conditions = []
    if PROJECT_ROLE_OWNER in roles:
        conditions.append(TextProject.user_id == user.id)
    member_roles = roles & PROJECT_MEMBER_ROLES
    if member_roles:
        conditions.append(ProjectMember.role.in_(member_roles))
    if permission == PROJECT_PERMISSION_VIEW:
        conditions.append(TextProject.visibility == PROJECT_VISIBILITY_PUBLIC)

    return (
        select(TextProject.id)
        .outerjoin(
            ProjectMember,
            and_(ProjectMember.project_id == TextProject.id, ProjectMember.user_id == user.id),
        )
        .where(or_(*conditions))
        .distinct()
    )


def accessible_projects_query(user: User):
    if user.is_admin:
        return select(TextProject)
    return select(TextProject).where(
        or_(
            TextProject.user_id == user.id,
            select(ProjectMember.id)
            .where(
                ProjectMember.project_id == TextProject.id,
                ProjectMember.user_id == user.id,
            )
            .exists(),
        )
    )


def _attach_access(project: TextProject, role: str) -> None:
    project.current_user_role = role
    project.current_user_permissions = project_permissions_for_role(role)


async def get_project_role(project: TextProject, user: User) -> str | None:
    if user.is_admin:
        return PROJECT_ROLE_ADMIN
    if project.user_id == user.id:
        return PROJECT_ROLE_OWNER

    for member in project.__dict__.get("members") or []:
        if member.user_id == user.id:
            return member.role
    if project.visibility == PROJECT_VISIBILITY_PUBLIC:
        return PROJECT_ROLE_VIEWER
    return None


async def require_project_permission(
    project_id: str,
    user: User,
    db: AsyncSession,
    permission: str = PROJECT_PERMISSION_VIEW,
    *,
    load_options: Iterable = (),
) -> TextProject:
    if permission not in PROJECT_PERMISSIONS:
        raise ValueError(f"Unknown project permission: {permission}")

    query = select(TextProject).where(TextProject.id == project_id).options(selectinload(TextProject.members))
    for option in load_options:
        query = query.options(option)
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    role = await get_project_role(project, user)
    if not role or permission not in PROJECT_ROLE_PERMISSIONS[role]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    _attach_access(project, role)
    return project


def validate_project_visibility(visibility: str) -> str:
    normalized = str(visibility or "").strip().lower()
    if normalized not in PROJECT_VISIBILITIES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid project visibility")
    return normalized


def validate_project_member_role(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized not in PROJECT_COLLABORATOR_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid project member role")
    return normalized
