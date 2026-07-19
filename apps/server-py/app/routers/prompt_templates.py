from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.runtime import ProjectAgent, PromptTemplate
from app.models.user import User
from app.schemas.agent_configuration import (
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
)

router = APIRouter()


@router.get("", response_model=list[PromptTemplateResponse])
async def list_prompt_templates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PromptTemplate)
        .where(PromptTemplate.user_id == user.id)
        .order_by(PromptTemplate.phase, PromptTemplate.name)
    )
    return [PromptTemplateResponse.model_validate(item) for item in result.scalars()]


@router.post("", response_model=PromptTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt_template(
    body: PromptTemplateCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    template = PromptTemplate(user_id=user.id, **body.model_dump())
    db.add(template)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Prompt template name already exists",
        ) from exc
    await db.refresh(template)
    return PromptTemplateResponse.model_validate(template)


@router.patch("/{template_id}", response_model=PromptTemplateResponse)
async def update_prompt_template(
    template_id: str,
    body: PromptTemplateUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.user_id == user.id,
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found")
    updates = body.model_dump(exclude_unset=True)
    if "phase" in updates and updates["phase"] != template.phase:
        agents = list((await db.execute(select(ProjectAgent))).scalars())
        if any(template.id in agent.prompt_template_ids.values() for agent in agents):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bound prompt template phase cannot be changed",
            )
    for key, value in updates.items():
        setattr(template, key, value)
    template.version += 1
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Prompt template name already exists",
        ) from exc
    await db.refresh(template)
    return PromptTemplateResponse.model_validate(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt_template(
    template_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.user_id == user.id,
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found")
    agents = list((await db.execute(select(ProjectAgent))).scalars())
    if any(template.id in agent.prompt_template_ids.values() for agent in agents):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Prompt template is bound to a project Agent",
        )
    await db.delete(template)
    return None
