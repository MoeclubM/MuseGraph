from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.config import AIProviderConfig
from app.models.user import User
from app.schemas.provider import (
    UserProviderCreate,
    UserProviderResponse,
    UserProviderUpdate,
)
from app.services.provider_models import (
    build_provider_model_ref,
    dump_provider_models,
    get_provider_chat_models,
    get_provider_embedding_models,
    get_provider_reranker_models,
)
from app.services.provider_security import validate_provider_base_url
from app.services.provider_type import normalize_provider_type, parse_supported_provider_types
from app.services.provider_usage import provider_model_references_in_use
from app.services.secret_crypto import encrypt_secret


router = APIRouter()
SUPPORTED_PROVIDER_TYPES = parse_supported_provider_types(settings.SUPPORTED_PROVIDER_TYPES)


def _serialize_provider(provider: AIProviderConfig) -> UserProviderResponse:
    return UserProviderResponse(
        id=provider.id,
        name=provider.name,
        provider=provider.provider,
        base_url=provider.base_url,
        models=get_provider_chat_models(provider),
        embedding_models=get_provider_embedding_models(provider),
        reranker_models=get_provider_reranker_models(provider),
        is_active=provider.is_active,
        priority=provider.priority,
        has_api_key=bool(provider.api_key),
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


async def _owned_provider(
    provider_id: str,
    user_id: str,
    db: AsyncSession,
) -> AIProviderConfig:
    provider = (
        await db.execute(
            select(AIProviderConfig).where(
                AIProviderConfig.id == provider_id,
                AIProviderConfig.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


def _provider_type(value: str) -> str:
    try:
        return normalize_provider_type(value, supported=SUPPORTED_PROVIDER_TYPES)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


async def _base_url(value: str | None) -> str | None:
    try:
        return await validate_provider_base_url(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


async def _flush_provider(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider name already exists in this account",
        ) from exc


@router.get("", response_model=list[UserProviderResponse])
async def list_user_providers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    providers = (
        await db.execute(
            select(AIProviderConfig)
            .where(AIProviderConfig.user_id == user.id)
            .order_by(AIProviderConfig.priority.desc(), AIProviderConfig.name)
        )
    ).scalars()
    return [_serialize_provider(provider) for provider in providers]


@router.post("", response_model=UserProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_user_provider(
    body: UserProviderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    provider = AIProviderConfig(
        user_id=user.id,
        name=body.name.strip(),
        provider=_provider_type(body.provider),
        api_key=encrypt_secret(body.api_key.get_secret_value()),
        base_url=await _base_url(body.base_url),
        models=dump_provider_models(
            models=body.models,
            embedding_models=body.embedding_models,
            reranker_models=body.reranker_models,
        ),
        is_active=body.is_active,
        priority=body.priority,
    )
    db.add(provider)
    await _flush_provider(db)
    await db.refresh(provider)
    return _serialize_provider(provider)


@router.patch("/{provider_id}", response_model=UserProviderResponse)
async def update_user_provider(
    provider_id: str,
    body: UserProviderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    provider = await _owned_provider(provider_id, user.id, db)
    updates = body.model_dump(exclude_unset=True)
    current_models = {
        "models": get_provider_chat_models(provider),
        "embedding_models": get_provider_embedding_models(provider),
        "reranker_models": get_provider_reranker_models(provider),
    }
    next_models = {
        key: updates.get(key, value)
        for key, value in current_models.items()
    }
    removed_references = {
        build_provider_model_ref(provider.id, model)
        for key, models in current_models.items()
        for model in set(models) - set(next_models[key])
    }
    used_references = await provider_model_references_in_use(db, provider.id)
    if removed_references & used_references:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider models are still selected by a project or Agent",
        )
    if any(key in updates for key in current_models):
        provider.models = dump_provider_models(**next_models)
    if "name" in updates:
        provider.name = updates["name"].strip()
    if "provider" in updates:
        provider.provider = _provider_type(updates["provider"])
    if "api_key" in updates:
        provider.api_key = encrypt_secret(updates["api_key"].get_secret_value())
    if "base_url" in updates:
        provider.base_url = await _base_url(updates["base_url"])
    if "is_active" in updates:
        provider.is_active = updates["is_active"]
    if "priority" in updates:
        provider.priority = updates["priority"]
    await _flush_provider(db)
    await db.refresh(provider)
    return _serialize_provider(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_provider(
    provider_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    provider = await _owned_provider(provider_id, user.id, db)
    if await provider_model_references_in_use(db, provider.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Provider is still selected by a project or Agent",
        )
    await db.delete(provider)
    return None
