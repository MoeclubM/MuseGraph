from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runtime import ProjectSkill
from app.schemas.runtime import ResolvedSkillSnapshot
from app.services.agent.pack_core import load_pack
from app.services.agent.skill_catalog import (
    ALL_AGENT_TOOLS,
    BUILTIN_SKILL_MAP,
    BUILTIN_SKILLS,
)


ROLE_NAMES = {
    "architect",
    "planner",
    "composer",
    "writer",
    "auditor",
    "reviser",
    "evaluator",
    "updater",
    "memory_builder",
    "graph_extractor",
}
SCOPE_NAMES = {"write", "analyze", "suggest"}
MODEL_COMPONENTS = {
    "operation_agent_task",
    "operation_analyze",
    "operation_continue",
    "operation_rewrite",
    "operation_agent_suggest",
}


def _builtin_snapshot(slug: str) -> ResolvedSkillSnapshot:
    skill = BUILTIN_SKILL_MAP[slug]
    return ResolvedSkillSnapshot(
        slug=skill.slug,
        name=skill.name,
        description=skill.description,
        instructions=skill.instructions,
        scopes=sorted(skill.scopes),
        roles=sorted(skill.roles),
        allowed_tools=sorted(skill.allowed_tools),
        default_model_component=skill.default_model_component,
        version=skill.version,
        source="builtin",
    )


def builtin_skill_snapshots() -> list[ResolvedSkillSnapshot]:
    return [_builtin_snapshot(skill.slug) for skill in BUILTIN_SKILLS]


def validate_skill_definition(
    *,
    slug: str,
    scopes: list[str],
    roles: list[str],
    allowed_tools: list[str],
    default_model_component: str | None,
    params_schema: dict[str, Any],
) -> None:
    normalized_slug = slug.strip().lower()
    if normalized_slug in BUILTIN_SKILL_MAP:
        raise ValueError(f"Custom skill cannot override built-in slug: {normalized_slug}")
    invalid_scopes = sorted(set(scopes) - SCOPE_NAMES)
    if invalid_scopes:
        raise ValueError(f"Unknown skill scopes: {', '.join(invalid_scopes)}")
    invalid_roles = sorted(set(roles) - ROLE_NAMES)
    if invalid_roles:
        raise ValueError(f"Unknown agent roles: {', '.join(invalid_roles)}")
    invalid_tools = sorted(set(allowed_tools) - ALL_AGENT_TOOLS)
    if invalid_tools:
        raise ValueError(f"Unknown or disallowed tools: {', '.join(invalid_tools)}")
    if default_model_component and default_model_component not in MODEL_COMPONENTS:
        raise ValueError(f"Unknown model component: {default_model_component}")
    if params_schema and params_schema.get("type") != "object":
        raise ValueError("params_schema must be a JSON Schema object")
    if params_schema:
        Draft202012Validator.check_schema(params_schema)


async def resolve_project_skill(
    db: AsyncSession,
    *,
    project_id: str,
    pack_slug: str,
    operation: str,
    role: str,
    requested_slug: str | None = None,
) -> ResolvedSkillSnapshot:
    if operation not in SCOPE_NAMES:
        raise ValueError(f"Unknown operation: {operation}")
    if role not in ROLE_NAMES:
        raise ValueError(f"Unknown agent role: {role}")

    slug = (requested_slug or "").strip().lower()
    if not slug:
        pack = load_pack(pack_slug)
        pack_key = "suggest" if operation == "suggest" else role
        slug = str(pack.default_skills.get(pack_key) or "general").strip().lower()

    if slug in BUILTIN_SKILL_MAP:
        snapshot = _builtin_snapshot(slug)
    else:
        result = await db.execute(
            select(ProjectSkill).where(
                ProjectSkill.project_id == project_id,
                ProjectSkill.slug == slug,
                ProjectSkill.enabled.is_(True),
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise LookupError(f"Enabled project skill not found: {slug}")
        validate_skill_definition(
            slug=record.slug,
            scopes=list(record.scopes),
            roles=list(record.roles),
            allowed_tools=list(record.allowed_tools),
            default_model_component=record.default_model_component,
            params_schema=dict(record.params_schema),
        )
        snapshot = ResolvedSkillSnapshot(
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

    if operation not in snapshot.scopes:
        raise ValueError(f"Skill {snapshot.slug} does not support {operation}")
    if role not in snapshot.roles:
        raise ValueError(f"Skill {snapshot.slug} does not support role {role}")
    return snapshot


def validate_pack_skill_references() -> None:
    from app.services.agent.pack_core import list_packs

    for descriptor in list_packs():
        pack = load_pack(descriptor["text_type"])
        for role, slug in pack.default_skills.items():
            if role not in ROLE_NAMES | {"suggest"}:
                raise ValueError(f"Pack {pack.text_type} has unknown default skill role: {role}")
            if slug not in BUILTIN_SKILL_MAP:
                raise ValueError(
                    f"Pack {pack.text_type} references unknown built-in skill: {slug}"
                )
