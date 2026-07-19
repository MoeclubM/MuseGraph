from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.runtime import AgentRun, ProjectAgent
from app.models.user import User
from app.schemas.agent_configuration import (
    ProjectAgentCreate,
    ProjectAgentResponse,
    ProjectAgentUpdate,
)
from app.services.agent.configuration import validate_prompt_template_bindings
from app.services.project_access import (
    PROJECT_PERMISSION_MANAGE,
    PROJECT_PERMISSION_VIEW,
    require_project_permission,
)

router = APIRouter()


@router.get("", response_model=list[ProjectAgentResponse])
async def list_project_agents(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_VIEW)
    result = await db.execute(
        select(ProjectAgent)
        .where(ProjectAgent.project_id == project_id)
        .order_by(ProjectAgent.created_at)
    )
    return [ProjectAgentResponse.model_validate(item) for item in result.scalars()]


@router.post("", response_model=ProjectAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_project_agent(
    project_id: str,
    body: ProjectAgentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await require_project_permission(project_id, user, db, PROJECT_PERMISSION_MANAGE)
    try:
        await validate_prompt_template_bindings(
            db,
            user_id=user.id,
            prompt_template_ids=dict(body.prompt_template_ids),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    agent = ProjectAgent(
        project_id=project_id,
        created_by_user_id=user.id,
        **body.model_dump(),
    )
    db.add(agent)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project Agent name already exists",
        ) from exc
    return ProjectAgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=ProjectAgentResponse)
async def update_project_agent(
    project_id: str,
    agent_id: str,
    body: ProjectAgentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(
        project_id, user, db, PROJECT_PERMISSION_MANAGE
    )
    result = await db.execute(
        select(ProjectAgent).where(
            ProjectAgent.id == agent_id,
            ProjectAgent.project_id == project_id,
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project Agent not found")
    updates = body.model_dump(exclude_unset=True)
    if updates.get("enabled") is False and project.active_agent_id == agent.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active project Agent cannot be disabled",
        )
    if "prompt_template_ids" in updates:
        try:
            await validate_prompt_template_bindings(
                db,
                user_id=user.id,
                prompt_template_ids=updates["prompt_template_ids"],
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    for key, value in updates.items():
        setattr(agent, key, value)
    agent.version += 1
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project Agent name already exists",
        ) from exc
    return ProjectAgentResponse.model_validate(agent)


@router.post("/{agent_id}/activate", response_model=ProjectAgentResponse)
async def activate_project_agent(
    project_id: str,
    agent_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(
        project_id, user, db, PROJECT_PERMISSION_MANAGE
    )
    result = await db.execute(
        select(ProjectAgent).where(
            ProjectAgent.id == agent_id,
            ProjectAgent.project_id == project_id,
            ProjectAgent.enabled.is_(True),
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enabled project Agent not found",
        )
    project.active_agent_id = agent.id
    await db.flush()
    return ProjectAgentResponse.model_validate(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_agent(
    project_id: str,
    agent_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await require_project_permission(
        project_id, user, db, PROJECT_PERMISSION_MANAGE
    )
    result = await db.execute(
        select(ProjectAgent).where(
            ProjectAgent.id == agent_id,
            ProjectAgent.project_id == project_id,
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project Agent not found")
    if project.active_agent_id == agent.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Active project Agent cannot be deleted",
        )
    used = await db.execute(select(AgentRun.id).where(AgentRun.agent_id == agent.id).limit(1))
    if used.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project Agent with run history cannot be deleted; disable it instead",
        )
    await db.delete(agent)
    return None
