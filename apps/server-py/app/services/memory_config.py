from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.config import AIProviderConfig
from app.models.project import TextProject
from app.services.memory_client import start_project_memory_instance
from app.services.provider_models import parse_provider_model_ref
from app.services.provider_resolution import resolve_provider_model
from app.services.provider_type import is_anthropic_provider
from app.services.secret_crypto import decrypt_secret


async def _provider_for_model(
    db: AsyncSession,
    model_reference: str,
    *,
    owner_user_id: str,
    embedding: bool,
) -> AIProviderConfig:
    provider, _model = await resolve_provider_model(
        db,
        model_reference,
        owner_user_id=owner_user_id,
        kind="embedding" if embedding else "chat",
    )
    if embedding and provider.provider != "openai_compatible":
        raise RuntimeError("Project Cognee embedding provider must be OpenAI-compatible")
    return provider


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
    llm_provider = await _provider_for_model(
        db,
        llm_model,
        owner_user_id=project.user_id,
        embedding=False,
    )
    embedding_provider = await _provider_for_model(
        db,
        embedding_model,
        owner_user_id=project.user_id,
        embedding=True,
    )
    _llm_provider_id, llm_model_name = parse_provider_model_ref(llm_model)
    _embedding_provider_id, embedding_model_name = parse_provider_model_ref(embedding_model)
    dimensions_raw = str(component_models.get("memory_embedding_dimensions") or "").strip()
    if not dimensions_raw.isdigit() or int(dimensions_raw) <= 0:
        raise RuntimeError("memory_embedding_dimensions must be a positive integer")
    if is_anthropic_provider(llm_provider.provider):
        llm_endpoint = str(llm_provider.base_url or "").rstrip("/").removesuffix("/v1")
        llm = {
            "llm_provider": "custom",
            "llm_model": (
                llm_model_name
                if llm_model_name.startswith("anthropic/")
                else f"anthropic/{llm_model_name}"
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
                llm_model_name
                if llm_model_name.startswith("openai/")
                else f"openai/{llm_model_name}"
            ),
            "llm_endpoint": llm_provider.base_url or "",
            "llm_api_key": decrypt_secret(llm_provider.api_key),
            "llm_max_completion_tokens": settings.COGNEE_LLM_MAX_TOKENS,
            "llm_args": {
                "extra_body": {"thinking": {"type": "disabled"}},
            },
        }
    await start_project_memory_instance(
        project.id,
        llm=llm,
        embedding={
            "embedding_provider": "openai_compatible",
            "embedding_model": embedding_model_name,
            "embedding_endpoint": embedding_provider.base_url or "",
            "embedding_api_key": decrypt_secret(embedding_provider.api_key),
            "embedding_dimensions": int(dimensions_raw),
        },
    )
