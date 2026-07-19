from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import TextProject
from app.models.runtime import ProjectAgent, PromptTemplate
from app.schemas.agent_configuration import (
    PROMPT_PHASES,
    ProjectAgentSnapshot,
    PromptTemplateSnapshot,
)


async def validate_prompt_template_bindings(
    db: AsyncSession,
    *,
    user_id: str,
    prompt_template_ids: dict[str, str],
) -> None:
    if set(prompt_template_ids) - PROMPT_PHASES:
        raise ValueError("Unknown prompt template phase")
    if not prompt_template_ids:
        return
    try:
        for template_id in prompt_template_ids.values():
            uuid.UUID(template_id)
    except ValueError as exc:
        raise ValueError("Prompt template IDs must be UUIDs") from exc
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id.in_(prompt_template_ids.values()),
            PromptTemplate.user_id == user_id,
        )
    )
    templates = {item.id: item for item in result.scalars()}
    if set(templates) != set(prompt_template_ids.values()):
        raise ValueError("Prompt templates must belong to the current account")
    for phase, template_id in prompt_template_ids.items():
        if templates[template_id].phase != phase:
            raise ValueError(
                f"Prompt template {template_id} belongs to phase "
                f"{templates[template_id].phase}, not {phase}"
            )


async def resolve_project_agent(
    db: AsyncSession,
    *,
    project: TextProject,
    mode: str,
    requested_agent_id: str | None,
    require_model: bool = True,
) -> tuple[ProjectAgent, ProjectAgentSnapshot]:
    agent_id = requested_agent_id or project.active_agent_id
    if not agent_id:
        raise LookupError("Project has no active Agent")
    result = await db.execute(
        select(ProjectAgent).where(
            ProjectAgent.id == agent_id,
            ProjectAgent.project_id == project.id,
            ProjectAgent.enabled.is_(True),
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise LookupError("Enabled project Agent not found")

    ids = dict(agent.prompt_template_ids)
    templates: dict[str, PromptTemplate] = {}
    if ids:
        template_result = await db.execute(
            select(PromptTemplate).where(PromptTemplate.id.in_(ids.values()))
        )
        templates = {item.id: item for item in template_result.scalars()}
        if set(templates) != set(ids.values()):
            raise LookupError("Project Agent references a missing prompt template")
        for phase, template_id in ids.items():
            if templates[template_id].phase != phase:
                raise ValueError(
                    f"Project Agent prompt phase mismatch: {phase}/{templates[template_id].phase}"
                )

    component = {
        "write": "operation_agent_task",
        "analyze": "operation_analyze",
        "suggest": "operation_agent_suggest",
    }[mode]
    model = agent.model or str((project.component_models or {}).get(component) or "").strip()
    if require_model and not model:
        raise ValueError(
            f"Project Agent has no model and project component is not configured: {component}"
        )
    snapshot = ProjectAgentSnapshot(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        model=model,
        model_source=(
            "agent"
            if agent.model
            else ("project_component" if model else None)
        ),
        effort=agent.effort,
        version=agent.version,
        prompt_templates={
            phase: PromptTemplateSnapshot(
                id=template.id,
                name=template.name,
                phase=template.phase,
                content=template.content,
                version=template.version,
            )
            for phase, template_id in ids.items()
            for template in [templates[template_id]]
        },
    )
    return agent, snapshot


def phase_prompt(
    agent_snapshot: dict[str, Any],
    phase: str,
    *,
    instruction: str,
    project: TextProject,
) -> str:
    template = (agent_snapshot.get("prompt_templates") or {}).get(phase)
    if not template:
        return ""
    content = str(template["content"])
    values = {
        "instruction": instruction,
        "project_title": project.title,
        "project_description": project.description or "",
        "pack_slug": project.pack_slug,
        "agent_name": str(agent_snapshot["name"]),
    }
    for name, value in values.items():
        content = content.replace("{{" + name + "}}", value)
    return f"\n\n项目 Agent 自定义 {phase} 提示词：\n{content}"
