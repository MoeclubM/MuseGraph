from typing import Literal

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import AIProviderConfig
from app.services.provider_models import (
    build_provider_model_ref,
    get_provider_models,
    parse_provider_model_ref,
)


ModelKind = Literal["chat", "embedding", "reranker"]
PROJECT_COMPONENT_MODEL_KINDS: dict[str, ModelKind] = {
    "operation_agent_task": "chat",
    "operation_analyze": "chat",
    "operation_agent_suggest": "chat",
    "memory_llm": "chat",
    "memory_embedding": "embedding",
    "memory_reranker": "reranker",
}


def accessible_providers_query(owner_user_id: str):
    return (
        select(AIProviderConfig)
        .where(
            AIProviderConfig.is_active.is_(True),
            or_(
                AIProviderConfig.user_id == owner_user_id,
                AIProviderConfig.user_id.is_(None),
            ),
        )
        .order_by(
            case((AIProviderConfig.user_id == owner_user_id, 0), else_=1),
            AIProviderConfig.priority.desc(),
            AIProviderConfig.name,
        )
    )


async def list_available_provider_models(
    db: AsyncSession,
    *,
    owner_user_id: str,
    kind: ModelKind,
) -> list[dict[str, str]]:
    providers = (await db.execute(accessible_providers_query(owner_user_id))).scalars()
    return [
        {
            "id": build_provider_model_ref(provider.id, model),
            "name": model,
            "provider": provider.name,
            "provider_id": provider.id,
            "scope": "account" if provider.user_id else "platform",
        }
        for provider in providers
        for model in get_provider_models(provider, kind)
    ]


async def resolve_provider_model(
    db: AsyncSession,
    reference: str,
    *,
    owner_user_id: str,
    kind: ModelKind,
) -> tuple[AIProviderConfig, str]:
    provider_id, model = parse_provider_model_ref(reference)
    provider = (
        await db.execute(
            accessible_providers_query(owner_user_id).where(
                AIProviderConfig.id == provider_id
            )
        )
    ).scalar_one_or_none()
    if provider is None:
        raise ValueError("Selected model provider is inactive or unavailable to this account")
    if model not in get_provider_models(provider, kind):
        raise ValueError(f'Provider "{provider.name}" has not registered {kind} model "{model}"')
    return provider, model


async def validate_project_component_models(
    db: AsyncSession,
    *,
    owner_user_id: str,
    component_models: dict[str, str],
) -> None:
    unknown = set(component_models) - {
        *PROJECT_COMPONENT_MODEL_KINDS,
        "memory_embedding_dimensions",
    }
    if unknown:
        raise ValueError(f"Unknown project model components: {sorted(unknown)}")
    dimensions = component_models.get("memory_embedding_dimensions")
    if dimensions is not None and (
        not str(dimensions).isdigit() or int(dimensions) <= 0
    ):
        raise ValueError("memory_embedding_dimensions must be a positive integer")
    for component, kind in PROJECT_COMPONENT_MODEL_KINDS.items():
        reference = str(component_models.get(component) or "").strip()
        if reference:
            await resolve_provider_model(
                db,
                reference,
                owner_user_id=owner_user_id,
                kind=kind,
            )
