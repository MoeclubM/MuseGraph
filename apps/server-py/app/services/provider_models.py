from __future__ import annotations

from typing import Literal
from typing import Any

from app.models.config import AIProviderConfig


def _normalize_string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        values.append(text)
        seen.add(text)
    return values


def parse_provider_models(raw: Any) -> dict[str, list[str]]:
    if isinstance(raw, list):
        return {"models": _normalize_string_list(raw), "embedding_models": [], "reranker_models": []}

    if isinstance(raw, dict):
        chat_models = _normalize_string_list(raw.get("models"))
        embedding_models = _normalize_string_list(raw.get("embedding_models"))
        if not embedding_models:
            embedding_models = _normalize_string_list(raw.get("embeddings"))
        reranker_models = _normalize_string_list(raw.get("reranker_models"))
        if not reranker_models:
            reranker_models = _normalize_string_list(raw.get("rerankers"))
        return {
            "models": chat_models,
            "embedding_models": embedding_models,
            "reranker_models": reranker_models,
        }

    return {"models": [], "embedding_models": [], "reranker_models": []}


def dump_provider_models(
    *,
    models: list[str] | None = None,
    embedding_models: list[str] | None = None,
    reranker_models: list[str] | None = None,
) -> list[str] | dict[str, list[str]]:
    chat_models = _normalize_string_list(models)
    embed_models = _normalize_string_list(embedding_models)
    rerank_models = _normalize_string_list(reranker_models)

    if embed_models or rerank_models:
        return {
            "models": chat_models,
            "embedding_models": embed_models,
            "reranker_models": rerank_models,
        }
    return chat_models


def get_chat_models(raw: Any) -> list[str]:
    return parse_provider_models(raw).get("models", [])


def get_embedding_models(raw: Any) -> list[str]:
    return parse_provider_models(raw).get("embedding_models", [])


def get_models(raw: Any, kind: Literal["chat", "embedding"]) -> list[str]:
    parsed = parse_provider_models(raw)
    if kind == "embedding":
        return parsed.get("embedding_models", [])
    return parsed.get("models", [])


def get_reranker_models(raw: Any) -> list[str]:
    return parse_provider_models(raw).get("reranker_models", [])


def get_provider_reranker_models(provider: AIProviderConfig) -> list[str]:
    return get_reranker_models(provider.models)


def get_provider_chat_models(provider: AIProviderConfig) -> list[str]:
    return get_chat_models(provider.models)


def get_provider_embedding_models(provider: AIProviderConfig) -> list[str]:
    return get_embedding_models(provider.models)


def get_provider_models(provider: AIProviderConfig, kind: Literal["chat", "embedding", "reranker"]) -> list[str]:
    if kind == "reranker":
        return get_reranker_models(provider.models)
    return get_models(provider.models, kind)


def set_provider_chat_models(provider: AIProviderConfig, models: list[str]) -> None:
    current = parse_provider_models(provider.models)
    provider.models = dump_provider_models(
        models=models,
        embedding_models=current.get("embedding_models", []),
        reranker_models=current.get("reranker_models", []),
    )


def set_provider_embedding_models(provider: AIProviderConfig, embedding_models: list[str]) -> None:
    current = parse_provider_models(provider.models)
    provider.models = dump_provider_models(
        models=current.get("models", []),
        embedding_models=embedding_models,
        reranker_models=current.get("reranker_models", []),
    )


def set_provider_reranker_models(provider: AIProviderConfig, reranker_models: list[str]) -> None:
    current = parse_provider_models(provider.models)
    provider.models = dump_provider_models(
        models=current.get("models", []),
        embedding_models=current.get("embedding_models", []),
        reranker_models=reranker_models,
    )


def set_provider_models(provider: AIProviderConfig, kind: Literal["chat", "embedding", "reranker"], models: list[str]) -> None:
    current = parse_provider_models(provider.models)
    if kind == "embedding":
        provider.models = dump_provider_models(
            models=current.get("models", []),
            embedding_models=models,
            reranker_models=current.get("reranker_models", []),
        )
        return
    if kind == "reranker":
        provider.models = dump_provider_models(
            models=current.get("models", []),
            embedding_models=current.get("embedding_models", []),
            reranker_models=models,
        )
        return
    provider.models = dump_provider_models(
        models=models,
        embedding_models=current.get("embedding_models", []),
        reranker_models=current.get("reranker_models", []),
    )
