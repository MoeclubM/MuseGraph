from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.config import AIProviderConfig
from app.models.project import TextProject
from app.services.memory_client import start_project_memory_instance
from app.services.provider_models import (
    get_provider_chat_models,
    get_provider_embedding_models,
)
from app.services.provider_type import is_anthropic_provider
from app.services.secret_crypto import decrypt_secret


async def _provider_for_model(
    db: AsyncSession,
    model: str,
    *,
    embedding: bool,
) -> AIProviderConfig:
    result = await db.execute(
        select(AIProviderConfig)
        .where(AIProviderConfig.is_active.is_(True))
        .order_by(AIProviderConfig.priority.desc(), AIProviderConfig.created_at)
    )
    for provider in result.scalars():
        if embedding and provider.provider != "openai_compatible":
            continue
        models = (
            get_provider_embedding_models(provider)
            if embedding
            else get_provider_chat_models(provider)
        )
        if model in models:
            return provider
    kind = "embedding" if embedding else "LLM"
    raise RuntimeError(f"Project Cognee {kind} model has no active provider: {model}")


async def ensure_project_memory_instance(
    project: TextProject,
    db: AsyncSession,
    *,
    require_models: bool = False,
) -> None:
    component_models = project.component_models or {}
    llm_model = str(component_models.get("memory_llm") or "").strip()
    embedding_model = str(component_models.get("memory_embedding") or "").strip()
    if not llm_model and not embedding_model:
        if require_models:
            raise RuntimeError(
                "Configure memory_llm, memory_embedding, and memory_embedding_dimensions before storing knowledge"
            )
        await start_project_memory_instance(project.id, llm={}, embedding={})
        return
    if not llm_model or not embedding_model:
        raise RuntimeError(
            "Both memory_llm and memory_embedding must be configured for Cognee"
        )
    llm_provider = await _provider_for_model(db, llm_model, embedding=False)
    embedding_provider = await _provider_for_model(db, embedding_model, embedding=True)
    dimensions_raw = str(component_models.get("memory_embedding_dimensions") or "").strip()
    if not dimensions_raw.isdigit() or int(dimensions_raw) <= 0:
        raise RuntimeError("memory_embedding_dimensions must be a positive integer")
    if is_anthropic_provider(llm_provider.provider):
        llm_endpoint = str(llm_provider.base_url or "").rstrip("/").removesuffix("/v1")
        llm = {
            "llm_provider": "custom",
            "llm_model": (
                llm_model
                if llm_model.startswith("anthropic/")
                else f"anthropic/{llm_model}"
            ),
            "llm_endpoint": llm_endpoint,
            "llm_api_key": decrypt_secret(llm_provider.api_key),
            "llm_max_completion_tokens": settings.COGNEE_LLM_MAX_TOKENS,
            "llm_args": {
                "thinking": {"type": "disabled"},
                "allowed_openai_params": ["thinking"],
            },
        }
    else:
        llm = {
            "llm_provider": "openai",
            "llm_model": (
                llm_model if llm_model.startswith("openai/") else f"openai/{llm_model}"
            ),
            "llm_endpoint": llm_provider.base_url or "",
            "llm_api_key": decrypt_secret(llm_provider.api_key),
            "llm_max_completion_tokens": settings.COGNEE_LLM_MAX_TOKENS,
        }
    await start_project_memory_instance(
        project.id,
        llm=llm,
        embedding={
            "embedding_provider": "openai_compatible",
            "embedding_model": embedding_model,
            "embedding_endpoint": embedding_provider.base_url or "",
            "embedding_api_key": decrypt_secret(embedding_provider.api_key),
            "embedding_dimensions": int(dimensions_raw),
        },
    )
