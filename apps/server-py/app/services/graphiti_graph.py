from __future__ import annotations

import asyncio
import gc
import html
import json
import logging
import os
import re
import shutil
import uuid
from contextlib import suppress
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field, create_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.config import AIProviderConfig
from app.models.project import TextProject
from app.services.ai import (
    _build_json_schema_example,
    _consume_openai_stream_response,
    _extract_openai_response_content,
    _is_deepseek_model,
    _load_llm_runtime_config,
    resolve_component_model,
)
from app.services.llm_json import extract_json_object
from app.services.llm_runtime import (
    DEFAULT_GRAPHITI_CHUNK_OVERLAP,
    DEFAULT_GRAPHITI_CHUNK_SIZE,
    DEFAULT_GRAPHITI_LLM_MAX_TOKENS,
    DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY,
    DEFAULT_LLM_REASONING_EFFORT,
    DEFAULT_LLM_OPENAI_API_STYLE,
    coerce_limiter_limit,
    model_supports_reasoning_effort,
    normalize_graphiti_chunk_config,
    normalize_graphiti_llm_max_tokens,
    normalize_model_concurrency_overrides,
    normalize_openai_api_style,
    normalize_reasoning_effort,
)
from app.services.provider_models import (
    get_provider_chat_models,
    get_provider_embedding_models,
    get_provider_reranker_models,
)

logger = logging.getLogger(__name__)

_GRAPHITI_MAX_VIS_NODES = 320
_GRAPHITI_MAX_VIS_EDGES = 900
_GRAPHITI_EPISODE_HEARTBEAT_SECONDS = 10.0
_GRAPHITI_SETUP_LOCK = asyncio.Lock()
_GRAPHITI_SETUP_COMPLETE: set[str] = set()


@dataclass
class _GraphitiRuntimeSelection:
    llm_provider_type: str
    llm_model: str
    llm_api_key: str
    llm_base_url: str
    embedding_model: str
    embedding_api_key: str
    embedding_base_url: str
    reranker_model: str
    reranker_api_key: str
    reranker_base_url: str
    timeout_seconds: int
    retry_count: int
    max_coroutines: int
    reasoning_effort: str | None
    chunk_size: int
    chunk_overlap: int
    llm_max_tokens: int
    openai_api_style: str = DEFAULT_LLM_OPENAI_API_STYLE


@dataclass
class GraphBuildPartialFailure(RuntimeError):
    graph_id: str
    total_chunks: int
    selected_chunk_indices: list[int]
    completed_chunk_indices: list[int]
    failed_chunk_indices: list[int]
    failed_errors: dict[str, str]

    def __post_init__(self) -> None:
        failed_count = len(self.failed_chunk_indices)
        selected_count = len(self.selected_chunk_indices)
        RuntimeError.__init__(
            self,
            f"Graph build partially failed. {failed_count}/{max(1, selected_count)} selected chunks failed.",
        )


def _is_graphiti_store_io_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return (
        ("io exception" in message and "cannot read from file" in message)
        or ("load table failed" in message and "exist in catalog" in message)
        or ("table" in message and "exist in catalog" in message)
    )


def _graphiti_store_unreadable_message(project_id: str) -> str:
    return (
        "Graphiti local graph store is unreadable for this project. "
        "Rebuild the knowledge graph to recreate the local Kuzu store. "
        f"project_id={project_id}"
    )


def _clear_graphiti_store(project_id: str) -> None:
    db_path = Path(_graphiti_store_path(project_id))
    store_dir = db_path.parent
    _GRAPHITI_SETUP_COMPLETE.discard(str(db_path))
    if store_dir.exists():
        shutil.rmtree(store_dir, ignore_errors=True)


def _open_kuzu_driver(
    KuzuDriver: Any,
    *,
    db_path: str,
    project_id: str | None = None,
    max_concurrent_queries: int | None = None,
) -> Any:
    kwargs: dict[str, Any] = {"db": db_path}
    if max_concurrent_queries is not None:
        kwargs["max_concurrent_queries"] = max_concurrent_queries
    try:
        driver = KuzuDriver(**kwargs)
    except Exception as exc:
        if project_id and _is_graphiti_store_io_error(exc):
            logger.warning(
                "Graphiti store is unreadable; clearing local store and retrying once. "
                "project_id=%s db_path=%s",
                project_id,
                db_path,
                exc_info=True,
            )
            _clear_graphiti_store(project_id)
            driver = KuzuDriver(**kwargs)
        else:
            raise
    return _patch_graphiti_driver_compatibility(driver)


def _parse_graphiti_response_content(
    response_model: type[BaseModel] | None,
    raw_content: str,
) -> Any:
    if response_model is None:
        return str(raw_content or "").strip()

    text = str(raw_content or "").strip()
    if not text:
        raise ValueError("Empty response content from Graphiti LLM provider")

    parsed_payload = extract_json_object(text)
    if parsed_payload is None:
        raise ValueError("Unable to parse Graphiti LLM response as JSON")

    return parsed_payload


def _validate_graphiti_response_payload(
    response_model: type[BaseModel] | None,
    payload: Any,
) -> Any:
    if response_model is None:
        return payload
    validated = response_model.model_validate(payload)
    return validated.model_dump(mode="python")


def _graphiti_telemetry_enabled() -> str:
    return "true" if not bool(getattr(settings, "TELEMETRY_DISABLED", True)) else "false"


def _graphiti_effective_max_tokens(value: int | None) -> int:
    try:
        requested = int(value or DEFAULT_GRAPHITI_LLM_MAX_TOKENS)
    except Exception:
        requested = DEFAULT_GRAPHITI_LLM_MAX_TOKENS
    return max(256, min(DEFAULT_GRAPHITI_LLM_MAX_TOKENS, requested))


def _graphiti_exception_status_code(exc: Exception) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(exc, "response", None)
    for attr in ("status_code", "status"):
        value = getattr(response, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _looks_like_graphiti_html_error(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    if "<!doctype html" in text or "<html" in text or "<body" in text or "text/html" in text:
        return True
    return bool(re.search(r"<[^>]+>", text))


def _sanitize_graphiti_error_message(exc: Exception) -> str:
    status_code = _graphiti_exception_status_code(exc)
    raw = str(exc or "").strip()
    if not raw:
        if status_code is not None:
            return f"Provider request failed with HTTP {status_code}"
        return f"{type(exc).__name__}: provider request failed"
    if not _looks_like_graphiti_html_error(raw):
        return raw
    cleaned = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if status_code is not None:
        if cleaned:
            return f"Provider returned HTTP {status_code}: {cleaned[:240]}"
        return f"Provider returned HTTP {status_code} with an HTML error page"
    if cleaned:
        return f"Provider returned an HTML error page: {cleaned[:240]}"
    return "Provider returned an HTML error page"


def _is_retryable_graphiti_llm_error(exc: Exception) -> bool:
    import openai

    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError, asyncio.TimeoutError, TimeoutError)):
        return True
    status_code = _graphiti_exception_status_code(exc)
    if isinstance(status_code, int) and status_code != 200:
        return True
    if _looks_like_graphiti_html_error(exc):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    retryable_markers = (
        "504",
        "gateway time-out",
        "gateway timeout",
        "timed out",
        "timeout",
        "connection error",
        "temporary",
        "temporarily unavailable",
        "bad gateway",
        "service unavailable",
        "write transaction",
        "only one write transaction",
        "cannot start a new write transaction",
    )
    return any(marker in text for marker in retryable_markers)


def _graphiti_retry_delay_seconds(attempt_number: int) -> float:
    return min(8.0, max(0.5, float(attempt_number) * 1.5))


def _graphiti_request_timeout_seconds(timeout_seconds: int | None) -> int:
    try:
        requested = int(timeout_seconds or 180)
    except Exception:
        requested = 180
    requested = max(60, min(1800, requested))
    return max(120, min(1800, requested + max(120, requested // 2)))


def _graphiti_episode_timeout_seconds(timeout_seconds: int | None) -> int:
    request_timeout_seconds = _graphiti_request_timeout_seconds(timeout_seconds)
    return max(180, min(1800, request_timeout_seconds + max(120, request_timeout_seconds // 2)))


def _graphiti_episode_worker_count(selected_count: int, max_coroutines: int) -> int:
    _ = (selected_count, max_coroutines)
    # Kuzu local permits one write transaction; serial episode writes prevent catalog corruption.
    return 1


def _resolve_graphiti_model_concurrency(model: str, runtime_cfg: dict[str, Any]) -> int:
    fallback = coerce_limiter_limit(
        runtime_cfg.get("llm_model_default_concurrency", DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY),
        DEFAULT_LLM_MODEL_DEFAULT_CONCURRENCY,
    )
    overrides = normalize_model_concurrency_overrides(runtime_cfg.get("llm_model_concurrency_overrides"))
    return overrides.get(str(model or "").strip().lower(), fallback)


def _build_graph_id() -> str:
    return f"graphiti_{uuid.uuid4().hex[:16]}"


def _project_graph_id(project: Any) -> str:
    return str(
        getattr(project, "graph_id", "") or ""
    ).strip()


def _split_text(text: str, *, chunk_size: int = DEFAULT_GRAPHITI_CHUNK_SIZE, overlap: int = DEFAULT_GRAPHITI_CHUNK_OVERLAP) -> list[str]:
    source = str(text or "").strip()
    if not source:
        return []
    safe_chunk_size, safe_overlap = normalize_graphiti_chunk_config(
        {"graphiti_chunk_size": chunk_size, "graphiti_chunk_overlap": overlap}
    )
    if len(source) <= safe_chunk_size:
        return [source]

    chunks: list[str] = []
    cursor = 0
    total_length = len(source)
    while cursor < total_length:
        end = min(cursor + safe_chunk_size, total_length)
        if end < total_length:
            search_start = cursor + max(1, int(safe_chunk_size * 0.55))
            boundary = -1
            boundary_len = 0
            for marker in ("\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", "，", ",", "、", " "):
                marker_boundary = source.rfind(marker, search_start, end)
                if marker_boundary > boundary and marker_boundary > cursor:
                    boundary = marker_boundary
                    boundary_len = 0 if marker.isspace() else len(marker)
            if boundary > cursor:
                end = boundary + boundary_len
        piece = source[cursor:end].strip()
        if piece:
            chunks.append(piece)
        if end >= total_length:
            break
        next_cursor = max(end - safe_overlap, cursor + 1)
        if next_cursor <= cursor:
            next_cursor = end
        cursor = next_cursor
    return chunks or [source]


async def _load_project(project_id: str, db: AsyncSession | None) -> TextProject | None:
    if db is None:
        return None
    result = await db.execute(select(TextProject).where(TextProject.id == project_id))
    return result.scalar_one_or_none()


def _normalize_type_name(value: str, *, default: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    segments = [segment for segment in re.split(r"[^A-Za-z0-9]+", raw) if segment]
    tokens: list[str] = []
    for segment in segments:
        parts = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", segment)
        tokens.extend(parts or [segment])
    if not tokens:
        compact = re.sub(r"[^A-Za-z0-9]+", "", raw)
        return compact[:1].upper() + compact[1:] if compact else default
    return "".join(token[:1].upper() + token[1:].lower() for token in tokens if token) or default


def _unique_type_name(value: str, *, default: str, existing: set[str]) -> str:
    candidate = _normalize_type_name(value, default=default)
    if candidate not in existing:
        return candidate
    suffix = 2
    while f"{candidate}{suffix}" in existing:
        suffix += 1
    return f"{candidate}{suffix}"


def _safe_attr_name(raw_name: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", str(raw_name or "").strip()).strip("_")
    if not candidate:
        return "attribute"
    if candidate[0].isdigit():
        candidate = f"field_{candidate}"
    if candidate in {"model_config", "model_fields", "model_extra"}:
        return f"entity_{candidate}"
    return candidate


def _build_model_class(name: str, description: str, attributes: list[dict[str, Any]]) -> type[BaseModel]:
    field_defs: dict[str, tuple[Any, Any]] = {}
    for attribute in attributes or []:
        attr_name = _safe_attr_name(str(attribute.get("name") or "attribute"))
        attr_desc = str(attribute.get("description") or attr_name).strip()
        if attr_name in field_defs:
            continue
        field_defs[attr_name] = (str | None, Field(default=None, description=attr_desc))
    model = create_model(name, __base__=BaseModel, **field_defs)
    model.__doc__ = description
    return model


def _prepare_graphiti_ontology(
    ontology: dict[str, Any] | None,
) -> tuple[dict[str, type[BaseModel]] | None, dict[str, type[BaseModel]] | None, dict[tuple[str, str], list[str]] | None]:
    if not isinstance(ontology, dict):
        return None, None, None

    raw_entities = [item for item in (ontology.get("entity_types") or []) if isinstance(item, dict)]
    raw_edges = [item for item in (ontology.get("edge_types") or []) if isinstance(item, dict)]

    entity_types: dict[str, type[BaseModel]] = {}
    entity_name_map: dict[str, str] = {}
    for entity_def in raw_entities:
        raw_name = str(entity_def.get("name") or "").strip()
        if not raw_name:
            continue
        normalized_name = _unique_type_name(raw_name, default="EntityType", existing=set(entity_types))
        entity_name_map[raw_name] = normalized_name
        description = str(entity_def.get("description") or f"A {raw_name} entity.").strip()
        entity_types[normalized_name] = _build_model_class(
            normalized_name,
            description,
            [item for item in (entity_def.get("attributes") or []) if isinstance(item, dict)],
        )

    edge_types: dict[str, type[BaseModel]] = {}
    edge_type_map: dict[tuple[str, str], list[str]] = {}
    for edge_def in raw_edges:
        raw_name = str(edge_def.get("name") or "").strip()
        if not raw_name:
            continue
        normalized_edge_name = _unique_type_name(raw_name, default="Relation", existing=set(edge_types))
        description = str(edge_def.get("description") or f"A {raw_name} relationship.").strip()
        edge_types[normalized_edge_name] = _build_model_class(
            normalized_edge_name,
            description,
            [item for item in (edge_def.get("attributes") or []) if isinstance(item, dict)],
        )
        raw_pairs = [item for item in (edge_def.get("source_targets") or []) if isinstance(item, dict)]
        if not raw_pairs:
            raw_source_type = str(edge_def.get("source_type") or "").strip()
            raw_target_type = str(edge_def.get("target_type") or "").strip()
            if raw_source_type and raw_target_type:
                raw_pairs = [{"source": raw_source_type, "target": raw_target_type}]
        for pair in raw_pairs:
            if not isinstance(pair, dict):
                continue
            raw_source = str(pair.get("source") or "").strip()
            raw_target = str(pair.get("target") or "").strip()
            source = entity_name_map.get(raw_source, _normalize_type_name(raw_source, default="Entity"))
            target = entity_name_map.get(raw_target, _normalize_type_name(raw_target, default="Entity"))
            edge_type_map.setdefault((source, target), []).append(normalized_edge_name)

    if not entity_types:
        return None, None, None
    return entity_types, (edge_types or None), (edge_type_map or None)


def _normalized_model_id(model: Any) -> str:
    text = str(model or "").strip()
    if "/" in text:
        _, text = text.split("/", 1)
    return text.lower()


def _model_id_matches(left: Any, right: Any) -> bool:
    left_id = _normalized_model_id(left)
    right_id = _normalized_model_id(right)
    return bool(left_id and right_id and left_id == right_id)


def _first_valid_model(models: list[str]) -> str | None:
    for item in models:
        value = str(item or "").strip()
        if value:
            return value
    return None


def _select_provider_for_model(
    configs: list[AIProviderConfig],
    *,
    model: str,
    kind: str,
) -> tuple[AIProviderConfig | None, str | None]:
    if kind == "embedding":
        getter = get_provider_embedding_models
    elif kind == "reranker":
        getter = get_provider_reranker_models
    else:
        getter = get_provider_chat_models
    for provider in configs:
        provider_models = getter(provider)
        for candidate in provider_models:
            if _model_id_matches(candidate, model):
                return provider, str(candidate).strip() or str(model).strip()
    return None, None


def _require_provider_api_key(provider: AIProviderConfig, *, purpose: str) -> str:
    value = str(getattr(provider, "api_key", "") or "").strip()
    if value:
        return value
    provider_name = str(getattr(provider, "name", "") or getattr(provider, "id", "") or provider.provider)
    raise RuntimeError(
        f"Provider '{provider_name}' is missing API key for {purpose}. Please set provider key in Admin."
    )


def _require_openai_compatible_provider(provider: AIProviderConfig, *, purpose: str) -> None:
    provider_type = str(getattr(provider, "provider", "") or "").strip().lower()
    if provider_type == "openai_compatible":
        return
    provider_name = str(getattr(provider, "name", "") or provider_type or "provider")
    raise RuntimeError(
        f"Graphiti local backend currently requires an OpenAI-compatible {purpose} provider. "
        f"Provider '{provider_name}' uses '{provider_type}'."
    )


def _require_graphiti_llm_provider(provider: AIProviderConfig) -> str:
    provider_type = str(getattr(provider, "provider", "") or "").strip().lower()
    if provider_type in {"openai_compatible", "anthropic_compatible"}:
        return provider_type
    provider_name = str(getattr(provider, "name", "") or provider_type or "provider")
    raise RuntimeError(
        "Graphiti local backend currently requires an OpenAI-compatible or Anthropic-compatible LLM provider. "
        f"Provider '{provider_name}' uses '{provider_type}'."
    )


async def _resolve_graphiti_runtime(
    *,
    project_id: str,
    db: AsyncSession | None,
    model: str | None = None,
    embedding_model: str | None = None,
    reranker_model: str | None = None,
) -> _GraphitiRuntimeSelection:
    if db is None:
        raise RuntimeError("Database session is required for Graphiti runtime configuration.")

    project = await _load_project(project_id, db)
    runtime_cfg = await _load_llm_runtime_config(db)
    result = await db.execute(
        select(AIProviderConfig)
        .where(AIProviderConfig.is_active == True)
        .order_by(AIProviderConfig.priority.desc())
    )
    configs = result.scalars().all()
    if not configs:
        raise RuntimeError("No active AI providers configured for Graphiti.")

    ontology_model = resolve_component_model(project, "ontology_generation") if project else ""
    requested_model = str(
        model or resolve_component_model(project, "graph_build", fallback_model=ontology_model)
    ).strip()
    requested_embedding_model = str(
        embedding_model or resolve_component_model(project, "graph_embedding", fallback_model="")
    ).strip()

    requested_reranker_model = str(
        reranker_model or resolve_component_model(project, "graph_reranker", fallback_model="")
    ).strip()

    llm_provider, llm_model = _select_provider_for_model(configs, model=requested_model, kind="chat")
    if llm_provider is None:
        llm_provider = next((item for item in configs if _first_valid_model(get_provider_chat_models(item))), None)
        llm_model = _first_valid_model(get_provider_chat_models(llm_provider)) if llm_provider else None
    if llm_provider is None or not llm_model:
        raise RuntimeError("No chat model configured in active providers for Graphiti graph build.")

    embedding_provider, selected_embedding_model = (
        _select_provider_for_model(configs, model=requested_embedding_model, kind="embedding")
        if requested_embedding_model
        else (None, None)
    )
    if embedding_provider is None:
        preferred_embedding = _first_valid_model(get_provider_embedding_models(llm_provider))
        if preferred_embedding:
            embedding_provider = llm_provider
            selected_embedding_model = preferred_embedding
        else:
            for item in configs:
                fallback_embedding = _first_valid_model(get_provider_embedding_models(item))
                if fallback_embedding:
                    embedding_provider = item
                    selected_embedding_model = fallback_embedding
                    break
    if embedding_provider is None or not selected_embedding_model:
        raise RuntimeError("No embedding model configured in active providers for Graphiti.")

    reranker_provider, selected_reranker_model = (
        _select_provider_for_model(configs, model=requested_reranker_model, kind="reranker")
        if requested_reranker_model
        else (None, None)
    )
    if reranker_provider is None:
        preferred_reranker = _first_valid_model(get_provider_reranker_models(llm_provider))
        if preferred_reranker:
            reranker_provider = llm_provider
            selected_reranker_model = preferred_reranker
        else:
            for item in configs:
                fallback_reranker = _first_valid_model(get_provider_reranker_models(item))
                if fallback_reranker:
                    reranker_provider = item
                    selected_reranker_model = fallback_reranker
                    break
    if reranker_provider is None or not selected_reranker_model:
        raise RuntimeError("No reranker model configured in active providers for Graphiti.")

    llm_provider_type = _require_graphiti_llm_provider(llm_provider)
    _require_openai_compatible_provider(embedding_provider, purpose="embedding")
    _require_openai_compatible_provider(reranker_provider, purpose="reranker")

    llm_api_key = _require_provider_api_key(llm_provider, purpose="LLM")
    embedding_api_key = _require_provider_api_key(embedding_provider, purpose="embedding")
    reranker_api_key = _require_provider_api_key(reranker_provider, purpose="reranker")

    llm_base_url = str(getattr(llm_provider, "base_url", "") or "").strip()
    embedding_base_url = str(getattr(embedding_provider, "base_url", "") or "").strip()
    reranker_base_url = str(getattr(reranker_provider, "base_url", "") or "").strip()
    max_coroutines = _resolve_graphiti_model_concurrency(llm_model, runtime_cfg)
    reasoning_effort = normalize_reasoning_effort(runtime_cfg.get("llm_reasoning_effort"))
    chunk_size, chunk_overlap = normalize_graphiti_chunk_config(runtime_cfg)
    llm_max_tokens = normalize_graphiti_llm_max_tokens(runtime_cfg)
    openai_api_style = normalize_openai_api_style(runtime_cfg.get("llm_openai_api_style"))

    return _GraphitiRuntimeSelection(
        llm_provider_type=llm_provider_type,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        embedding_model=selected_embedding_model,
        embedding_api_key=embedding_api_key,
        embedding_base_url=embedding_base_url,
        reranker_model=selected_reranker_model,
        reranker_api_key=reranker_api_key,
        reranker_base_url=reranker_base_url,
        timeout_seconds=max(5, min(1800, int(runtime_cfg.get("llm_request_timeout_seconds", 180) or 180))),
        retry_count=max(0, min(10, int(runtime_cfg.get("llm_retry_count", 2) or 2))),
        max_coroutines=max_coroutines,
        reasoning_effort=None if reasoning_effort == DEFAULT_LLM_REASONING_EFFORT else reasoning_effort,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        llm_max_tokens=llm_max_tokens,
        openai_api_style=openai_api_style,
    )


def _import_graphiti_runtime() -> tuple[Any, Any, Any, Any, Any, Any, Any, Any, Any]:
    try:
        from graphiti_core import Graphiti
        from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
        from graphiti_core.driver.kuzu_driver import KuzuDriver
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
        from graphiti_core.nodes import EpisodeType
        from graphiti_core.search.search_config_recipes import (
            COMBINED_HYBRID_SEARCH_RRF,
            EDGE_HYBRID_SEARCH_RRF,
            NODE_HYBRID_SEARCH_RRF,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Graphiti local backend dependency is missing. Install `graphiti-core[kuzu]` and rebuild the server."
        ) from exc
    return (
        Graphiti,
        KuzuDriver,
        OpenAIGenericClient,
        LLMConfig,
        OpenAIEmbedder,
        OpenAIEmbedderConfig,
        OpenAIRerankerClient,
        EpisodeType,
        {
            "combined_rrf": COMBINED_HYBRID_SEARCH_RRF,
            "edge_rrf": EDGE_HYBRID_SEARCH_RRF,
            "node_rrf": NODE_HYBRID_SEARCH_RRF,
        },
    )


def _graphiti_store_root() -> tuple[Path, str]:
    raw_path = str(getattr(settings, "GRAPHITI_DB_PATH", "") or "").strip()
    if not raw_path:
        raise RuntimeError("Graphiti local backend requires GRAPHITI_DB_PATH.")
    db_path = Path(raw_path).expanduser()
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    if db_path.suffix.lower() == ".kuzu":
        root = db_path.parent
        filename = db_path.name
    else:
        root = db_path
        filename = "graphiti.kuzu"
    root.mkdir(parents=True, exist_ok=True)
    return root, filename


def _graphiti_store_path(project_id: str | None = None) -> str:
    root, filename = _graphiti_store_root()
    if project_id:
        project_key = re.sub(r"[^A-Za-z0-9_-]+", "_", str(project_id).strip()).strip("_") or "default"
        project_dir = root / project_key
        project_dir.mkdir(parents=True, exist_ok=True)
        return str(project_dir / filename)
    return str(root / filename)


def _embedding_dimension() -> int:
    for candidate in (
        getattr(settings, "GRAPHITI_EMBEDDING_DIM", None),
        os.getenv("EMBEDDING_DIM"),
        os.getenv("EMBEDDING_DIMENSIONS"),
    ):
        try:
            if candidate is None:
                continue
            return max(1, int(candidate))
        except Exception:
            continue
    return 1024


def _patch_graphiti_driver_compatibility(driver: Any) -> Any:
    if not hasattr(driver, "_database"):
        driver._database = ""
    original_build_indices = getattr(driver, "build_indices_and_constraints", None)
    original_execute_query = getattr(driver, "execute_query", None)

    def _is_kuzu_existing_index_error(query: Any, exc: Exception) -> bool:
        message = str(exc).lower()
        query_text = str(query or "").lower()
        return (
            "create_fts_index" in query_text
            and ("already exists" in message or "equivalent" in message)
        )

    def _clone(*, database: str) -> Any:
        driver._database = str(database or "")
        return driver

    async def _execute_query(
        cypher_query_: str,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]] | list[list[dict[str, Any]]], None, None]:
        params = {k: v for k, v in kwargs.items() if v is not None}
        params.pop("database_", None)
        params.pop("routing_", None)

        client = getattr(driver, "client", None)
        client_execute = getattr(client, "execute", None)
        if not callable(client_execute):
            if not callable(original_execute_query):
                raise AttributeError("Graphiti driver is missing execute_query")
            return await original_execute_query(cypher_query_, **kwargs)

        try:
            results = await client_execute(cypher_query_, parameters=params)
        except Exception as exc:
            if _is_kuzu_existing_index_error(cypher_query_, exc):
                return [], None, None
            logger.error(
                "Error executing Kuzu query: %s\n%s\n%s",
                exc,
                cypher_query_,
                {k: (v[:5] if isinstance(v, list) else v) for k, v in params.items()},
            )
            raise

        if not results:
            return [], None, None

        if isinstance(results, list):
            dict_results = [list(result.rows_as_dict()) for result in results]
        else:
            dict_results = list(results.rows_as_dict())
        return dict_results, None, None  # type: ignore[return-value]

    async def _build_indices_and_constraints(delete_existing: bool = False) -> None:
        if not callable(getattr(driver, "execute_query", None)):
            if callable(original_build_indices):
                try:
                    await original_build_indices(delete_existing=delete_existing)
                except TypeError:
                    await original_build_indices()
            return

        del delete_existing
        try:
            from graphiti_core.driver.driver import GraphProvider
            from graphiti_core.graph_queries import get_fulltext_indices
        except ModuleNotFoundError:
            return

        for query in get_fulltext_indices(GraphProvider.KUZU):
            try:
                await driver.execute_query(query)
            except Exception as exc:
                message = str(exc).lower()
                if "already exists" in message or "equivalent" in message:
                    continue
                raise

    driver.clone = _clone
    driver.execute_query = _execute_query
    driver.build_indices_and_constraints = _build_indices_and_constraints
    return driver


def _patch_graphiti_llm_client(openai_generic_client_cls: type[Any]) -> type[Any]:
    class MuseGraphGraphitiClient(openai_generic_client_cls):
        async def _generate_response(
            self,
            messages: list[Any],
            response_model: type[BaseModel] | None = None,
            max_tokens: int = 16384,
            model_size: Any = None,
        ) -> dict[str, Any]:
            import openai

            from graphiti_core.llm_client.errors import RateLimitError

            openai_input = []
            instructions_parts: list[str] = []
            for message in messages:
                message.content = self._clean_input(message.content)
                if message.role == "system":
                    if message.content:
                        instructions_parts.append(message.content)
                    continue
                if message.role in {"user", "assistant", "developer"} and message.content:
                    openai_input.append(
                        {
                            "role": message.role,
                            "content": [{"type": "input_text", "text": message.content}],
                        }
                    )

            try:
                response_formats: list[dict[str, Any]] = [{"name": "json_object", "mode": "json_object"}]
                if response_model is not None:
                    response_formats = [
                        {"name": "json_schema", "mode": "parse"},
                        {"name": "json_object", "mode": "json_object"},
                    ]

                effective_max_tokens = _graphiti_effective_max_tokens(max_tokens or self.max_tokens)
                timeout_seconds = max(
                    5,
                    min(
                        1800,
                        int(getattr(getattr(self, "config", None), "timeout_seconds", 180) or 180),
                    ),
                )
                instructions = "\n\n".join(part for part in instructions_parts if part).strip() or None
                model_name = self.model or "gpt-4.1-mini"
                openai_api_style = normalize_openai_api_style(
                    getattr(getattr(self, "config", None), "openai_api_style", DEFAULT_LLM_OPENAI_API_STYLE)
                )

                if openai_api_style == "chat_completions" or _is_deepseek_model(model_name):
                    chat_messages: list[dict[str, str]] = []
                    if instructions:
                        chat_messages.append({"role": "system", "content": instructions})
                    for item in openai_input:
                        role = "system" if item.get("role") == "developer" else str(item.get("role") or "user")
                        text = "\n".join(
                            str(part.get("text") or "")
                            for part in item.get("content", [])
                            if isinstance(part, dict)
                        ).strip()
                        if text:
                            chat_messages.append({"role": role, "content": text})

                    example_payload = _build_json_schema_example(response_model.model_json_schema()) if response_model else {}
                    format_instruction = (
                        "Return valid json only. Do not include markdown or commentary. "
                        "The response must be a json object matching this example format.\n"
                        f"EXAMPLE JSON OUTPUT:\n{json.dumps(example_payload, ensure_ascii=False, indent=2)}"
                    )
                    if chat_messages:
                        chat_messages[-1]["content"] = f"{chat_messages[-1]['content']}\n\n{format_instruction}"
                    else:
                        chat_messages.append({"role": "user", "content": format_instruction})

                    request_kwargs: dict[str, Any] = {
                        "model": model_name,
                        "messages": chat_messages,
                        "max_tokens": effective_max_tokens,
                        "timeout": timeout_seconds,
                        "response_format": {"type": "json_object"},
                        "stream": True,
                    }
                    if _is_deepseek_model(model_name):
                        request_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                    reasoning_effort = str(
                        getattr(getattr(self, "config", None), "reasoning_effort", "") or ""
                    ).strip().lower()
                    if (
                        reasoning_effort
                        and model_supports_reasoning_effort(model_name)
                        and not (_is_deepseek_model(model_name) and reasoning_effort in {"none", "minimal"})
                    ):
                        request_kwargs["reasoning_effort"] = reasoning_effort

                    try:
                        response = await self.client.chat.completions.create(**request_kwargs)
                        if hasattr(response, "__aiter__"):
                            raw_content, _, _ = await _consume_openai_stream_response(response)
                        else:
                            raw_content = _extract_openai_response_content(response)
                        parsed_payload = _parse_graphiti_response_content(response_model, raw_content)
                        return _validate_graphiti_response_payload(response_model, parsed_payload)
                    except openai.RateLimitError as exc:
                        raise RateLimitError from exc
                    except Exception as exc:
                        logger.exception(
                            "Graphiti Chat Completions streaming request failed. model=%s response_model=%s base_url=%s "
                            "max_tokens=%s timeout=%s error_type=%s error=%r",
                            model_name,
                            getattr(response_model, "__name__", None),
                            getattr(getattr(self, "config", None), "base_url", ""),
                            effective_max_tokens,
                            timeout_seconds,
                            type(exc).__name__,
                            exc,
                        )
                        raise

                last_exc: Exception | None = None
                for attempt_index, response_format in enumerate(response_formats, start=1):
                    request_kwargs: dict[str, Any] = {
                        "model": self.model or "gpt-4.1-mini",
                        "input": openai_input or "",
                        "temperature": self.temperature,
                        "max_output_tokens": effective_max_tokens,
                        "timeout": timeout_seconds,
                    }
                    reasoning_effort = str(
                        getattr(getattr(self, "config", None), "reasoning_effort", "") or ""
                    ).strip().lower()
                    if reasoning_effort and model_supports_reasoning_effort(request_kwargs["model"]):
                        request_kwargs["reasoning"] = {"effort": reasoning_effort}
                    if instructions:
                        request_kwargs["instructions"] = instructions
                    try:
                        if response_format.get("mode") == "parse" and response_model is not None:
                            response = await self.client.responses.parse(
                                **request_kwargs,
                                text_format=response_model,
                            )
                            parsed_payload = response.output_parsed
                            if isinstance(parsed_payload, BaseModel):
                                parsed_payload = parsed_payload.model_dump(mode="python")
                            if parsed_payload is None:
                                raw_content = getattr(response, "output_text", "") or ""
                                parsed_payload = _parse_graphiti_response_content(response_model, raw_content)
                        else:
                            response = await self.client.responses.create(
                                **request_kwargs,
                                text={"format": {"type": "json_object"}},
                            )
                            raw_content = getattr(response, "output_text", "") or ""
                            parsed_payload = _parse_graphiti_response_content(response_model, raw_content)
                        return _validate_graphiti_response_payload(response_model, parsed_payload)
                    except openai.RateLimitError as exc:
                        raise RateLimitError from exc
                    except Exception as exc:
                        last_exc = exc
                        if _is_retryable_graphiti_llm_error(exc):
                            break
                    if attempt_index >= len(response_formats):
                        break
                    current_format_name = str(response_format.get("name") or "none")
                    next_format = response_formats[attempt_index]
                    next_format_name = str(next_format.get("name") or "none")
                    logger.warning(
                        "Graphiti structured-output request failed; retrying with fallback format. "
                        "model=%s response_model=%s base_url=%s format=%s next_format=%s "
                        "max_tokens=%s timeout=%s error_type=%s error=%r",
                        self.model or "gpt-4.1-mini",
                        getattr(response_model, "__name__", None),
                        getattr(getattr(self, "config", None), "base_url", ""),
                        current_format_name,
                        next_format_name,
                        effective_max_tokens,
                        timeout_seconds,
                        type(last_exc).__name__ if last_exc is not None else "UnknownError",
                        last_exc,
                    )
                    continue

                assert last_exc is not None
                logger.exception(
                    "Graphiti LLM request failed. model=%s response_model=%s base_url=%s "
                    "max_tokens=%s timeout=%s error_type=%s error=%r",
                    self.model or "gpt-4.1-mini",
                    getattr(response_model, "__name__", None),
                    getattr(getattr(self, "config", None), "base_url", ""),
                    effective_max_tokens,
                    timeout_seconds,
                    type(last_exc).__name__,
                    last_exc,
                )
                raise last_exc
            except openai.RateLimitError as exc:
                raise RateLimitError from exc

    return MuseGraphGraphitiClient


def _patch_graphiti_reranker_client(openai_reranker_client_cls: type[Any]) -> type[Any]:
    class MuseGraphOpenAIRerankerClient(openai_reranker_client_cls):
        async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
            import numpy as np
            import openai
            from graphiti_core.helpers import semaphore_gather
            from graphiti_core.llm_client import RateLimitError
            from graphiti_core.prompts import Message

            openai_messages_list: Any = [
                [
                    Message(
                        role="system",
                        content="You are an expert tasked with determining whether the passage is relevant to the query",
                    ),
                    Message(
                        role="user",
                        content=f"""
                           Respond with "True" if PASSAGE is relevant to QUERY and "False" otherwise.
                           <PASSAGE>
                           {passage}
                           </PASSAGE>
                           <QUERY>
                           {query}
                           </QUERY>
                           """,
                    ),
                ]
                for passage in passages
            ]
            reasoning_effort = str(getattr(getattr(self, "config", None), "reasoning_effort", "") or "").strip().lower()

            async def _request_rank(openai_messages: Any) -> Any:
                request_kwargs: dict[str, Any] = {
                    "model": self.config.model or "gpt-4.1-nano",
                    "messages": openai_messages,
                    "temperature": 0,
                    "max_tokens": 1,
                    "logit_bias": {"6432": 1, "7983": 1},
                    "logprobs": True,
                    "top_logprobs": 2,
                }
                if reasoning_effort and model_supports_reasoning_effort(request_kwargs["model"]):
                    request_kwargs["reasoning_effort"] = reasoning_effort
                return await self.client.chat.completions.create(**request_kwargs)

            try:
                responses = await semaphore_gather(*[_request_rank(openai_messages) for openai_messages in openai_messages_list])
                responses_top_logprobs = [
                    response.choices[0].logprobs.content[0].top_logprobs
                    if response.choices[0].logprobs is not None
                    and response.choices[0].logprobs.content is not None
                    else []
                    for response in responses
                ]
                scores: list[float] = []
                for top_logprobs in responses_top_logprobs:
                    if len(top_logprobs) == 0:
                        continue
                    norm_logprobs = np.exp(top_logprobs[0].logprob)
                    if top_logprobs[0].token.strip().split(" ")[0].lower() == "true":
                        scores.append(norm_logprobs)
                    else:
                        scores.append(1 - norm_logprobs)

                results = [(passage, score) for passage, score in zip(passages, scores, strict=True)]
                results.sort(reverse=True, key=lambda x: x[1])
                return results
            except openai.RateLimitError as exc:
                raise RateLimitError from exc
            except Exception as exc:
                logger.error("Error in generating reranker response: %s", exc)
                raise

    return MuseGraphOpenAIRerankerClient


async def _create_graphiti(*, runtime: _GraphitiRuntimeSelection, project_id: str | None = None) -> Any:
    (
        Graphiti,
        KuzuDriver,
        OpenAIGenericClient,
        LLMConfig,
        OpenAIEmbedder,
        OpenAIEmbedderConfig,
        OpenAIRerankerClient,
        _EpisodeType,
        _recipes,
    ) = _import_graphiti_runtime()

    db_path = _graphiti_store_path(project_id)
    os.environ["GRAPHITI_TELEMETRY_ENABLED"] = _graphiti_telemetry_enabled()
    os.environ["SEMAPHORE_LIMIT"] = str(runtime.max_coroutines)
    os.environ["EMBEDDING_DIM"] = str(_embedding_dimension())

    llm_max_tokens = _graphiti_effective_max_tokens(runtime.llm_max_tokens)
    llm_config = LLMConfig(
        api_key=runtime.llm_api_key,
        model=runtime.llm_model,
        base_url=runtime.llm_base_url or None,
        temperature=0,
        max_tokens=llm_max_tokens,
        small_model=runtime.reranker_model,
    )
    llm_config.timeout_seconds = _graphiti_request_timeout_seconds(runtime.timeout_seconds)
    llm_config.reasoning_effort = runtime.reasoning_effort
    llm_config.openai_api_style = runtime.openai_api_style
    reranker_config = LLMConfig(
        api_key=runtime.reranker_api_key,
        model=runtime.reranker_model,
        base_url=runtime.reranker_base_url or None,
        temperature=0,
        max_tokens=llm_max_tokens,
    )
    reranker_config.timeout_seconds = _graphiti_request_timeout_seconds(runtime.timeout_seconds)
    reranker_config.reasoning_effort = runtime.reasoning_effort
    embedder_config = OpenAIEmbedderConfig(
        api_key=runtime.embedding_api_key,
        base_url=runtime.embedding_base_url or None,
        embedding_model=runtime.embedding_model,
        embedding_dim=_embedding_dimension(),
    )
    graphiti_llm_client_cls = _patch_graphiti_llm_client(OpenAIGenericClient)
    graphiti_reranker_client_cls = _patch_graphiti_reranker_client(OpenAIRerankerClient)
    driver = _open_kuzu_driver(
        KuzuDriver,
        db_path=db_path,
        project_id=project_id,
        max_concurrent_queries=1,
    )
    if runtime.llm_provider_type == "anthropic_compatible":
        import anthropic
        from graphiti_core.llm_client.anthropic_client import AnthropicClient

        anthropic_client = anthropic.AsyncAnthropic(
            api_key=runtime.llm_api_key,
            base_url=runtime.llm_base_url or None,
            max_retries=1,
        )
        llm_client = AnthropicClient(
            config=llm_config,
            client=anthropic_client,
            max_tokens=llm_max_tokens,
        )
    else:
        llm_client = graphiti_llm_client_cls(config=llm_config, max_tokens=llm_max_tokens)
        llm_client.MAX_RETRIES = 0
    return Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=OpenAIEmbedder(config=embedder_config),
        cross_encoder=graphiti_reranker_client_cls(config=reranker_config),
        max_coroutines=runtime.max_coroutines,
    )


async def _run_graphiti_episode(
    *,
    graphiti: Any,
    runtime: _GraphitiRuntimeSelection,
    index: int,
    total_chunks: int,
    emit: Any,
    episode_kwargs: dict[str, Any],
) -> Any:
    episode_timeout_seconds = _graphiti_episode_timeout_seconds(runtime.timeout_seconds)
    max_episode_attempts = max(1, int(runtime.retry_count or 0) + 1)
    progress_before_episode = 30 + int((max(0, index - 1) / max(1, total_chunks)) * 70)

    for attempt in range(1, max_episode_attempts + 1):
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        task = asyncio.create_task(graphiti.add_episode(**episode_kwargs))
        emit(progress_before_episode, f"Graphiti ingesting episode {index}/{total_chunks}...")
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=_GRAPHITI_EPISODE_HEARTBEAT_SECONDS)
                if task in done:
                    return await task

                elapsed_seconds = int(loop.time() - started_at)
                if elapsed_seconds >= episode_timeout_seconds:
                    task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await task
                    raise asyncio.TimeoutError(
                        f"Graphiti episode {index}/{total_chunks} timed out after {elapsed_seconds}s"
                    )

                emit(
                    progress_before_episode,
                    f"Graphiti ingesting episode {index}/{total_chunks}... {elapsed_seconds}s elapsed",
                )
        except Exception as exc:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

            if _is_retryable_graphiti_llm_error(exc) and attempt < max_episode_attempts:
                delay_seconds = _graphiti_retry_delay_seconds(attempt)
                logger.warning(
                    "Graphiti episode failed; retrying. index=%s total=%s attempt=%s/%s timeout=%ss error_type=%s error=%r",
                    index,
                    total_chunks,
                    attempt + 1,
                    max_episode_attempts,
                    episode_timeout_seconds,
                    type(exc).__name__,
                    exc,
                )
                emit(
                    progress_before_episode,
                    f"Graphiti episode {index}/{total_chunks} retrying in {delay_seconds:.1f}s...",
                )
                await asyncio.sleep(delay_seconds)
                continue
            raise

    raise RuntimeError(f"Graphiti episode {index}/{total_chunks} failed without a terminal exception.")


async def setup_graphiti(project_id: str | None = None) -> None:
    global _GRAPHITI_SETUP_COMPLETE
    db_path = _graphiti_store_path(project_id)
    if db_path in _GRAPHITI_SETUP_COMPLETE:
        return
    async with _GRAPHITI_SETUP_LOCK:
        if db_path in _GRAPHITI_SETUP_COMPLETE:
            return
        (
            _Graphiti,
            KuzuDriver,
            _OpenAIGenericClient,
            _LLMConfig,
            _OpenAIEmbedder,
            _OpenAIEmbedderConfig,
            _OpenAIRerankerClient,
            _EpisodeType,
            _recipes,
        ) = _import_graphiti_runtime()
        os.environ["GRAPHITI_TELEMETRY_ENABLED"] = _graphiti_telemetry_enabled()
        async def _initialize_store() -> None:
            driver = KuzuDriver(db=db_path)
            try:
                await driver.build_indices_and_constraints()
            finally:
                try:
                    await driver.close()
                finally:
                    del driver
                    gc.collect()

        try:
            await _initialize_store()
        except Exception as exc:
            if project_id and _is_graphiti_store_io_error(exc):
                logger.warning(
                    "Graphiti store is unreadable during setup; clearing local store and retrying once. "
                    "project_id=%s db_path=%s",
                    project_id,
                    db_path,
                    exc_info=True,
                )
                _clear_graphiti_store(project_id)
                await _initialize_store()
            else:
                raise
        _GRAPHITI_SETUP_COMPLETE.add(db_path)


async def build_graph(
    project_id: str,
    text: str,
    *,
    ontology: dict[str, Any] | None = None,
    db: AsyncSession | None = None,
    progress_callback: Any | None = None,
    model: str | None = None,
    embedding_model: str | None = None,
    graph_id_override: str | None = None,
    chunk_indices: list[int] | None = None,
    continue_on_error: bool = False,
) -> str:
    await setup_graphiti(project_id)
    project = await _load_project(project_id, db)
    graph_id = str(graph_id_override or "").strip() or _project_graph_id(project) or _build_graph_id()
    runtime = await _resolve_graphiti_runtime(
        project_id=project_id,
        db=db,
        model=model,
        embedding_model=embedding_model,
    )
    chunks = _split_text(text, chunk_size=runtime.chunk_size, overlap=runtime.chunk_overlap)
    if not chunks:
        raise ValueError("No graph input text provided")
    entity_types, edge_types, edge_type_map = _prepare_graphiti_ontology(ontology)
    graphiti = await _create_graphiti(runtime=runtime, project_id=project_id)
    (
        _Graphiti,
        _GraphDriver,
        _OpenAIGenericClient,
        _LLMConfig,
        _OpenAIEmbedder,
        _OpenAIEmbedderConfig,
        _OpenAIRerankerClient,
        EpisodeType,
        _recipes,
    ) = _import_graphiti_runtime()

    def emit(progress: int, message: str) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(progress, message)
        except Exception:
            pass

    try:
        emit(25, "Preparing Graphiti local runtime...")
        await graphiti.build_indices_and_constraints()
        total_chunks = len(chunks)
        emit(
            28,
            f"Graphiti split source into {total_chunks} episodes "
            f"(chunk size {runtime.chunk_size}, overlap {runtime.chunk_overlap})...",
        )
        normalized_chunk_indices = [
            index
            for index in (chunk_indices or list(range(1, total_chunks + 1)))
            if 1 <= int(index) <= total_chunks
        ]
        seen_chunk_indices: set[int] = set()
        selected_chunk_indices: list[int] = []
        for raw_index in normalized_chunk_indices:
            index = int(raw_index)
            if index in seen_chunk_indices:
                continue
            selected_chunk_indices.append(index)
            seen_chunk_indices.add(index)
        if not selected_chunk_indices:
            raise ValueError("No graph chunks selected for build")
        completed_chunk_indices: list[int] = []
        failed_chunk_indices: list[int] = []
        failed_errors: dict[str, str] = {}
        base_reference_time = datetime.now(timezone.utc)
        selected_chunk_count = len(selected_chunk_indices)
        episode_worker_count = _graphiti_episode_worker_count(selected_chunk_count, runtime.max_coroutines)
        queue: asyncio.Queue[int] = asyncio.Queue()
        for index in selected_chunk_indices:
            queue.put_nowait(index)
        state_lock = asyncio.Lock()
        first_error: Exception | None = None

        if episode_worker_count > 1:
            emit(30, f"Graphiti parallel ingest enabled ({episode_worker_count} workers)...")

        async def _worker() -> None:
            nonlocal first_error
            while True:
                if first_error is not None and not continue_on_error:
                    return
                try:
                    index = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return

                chunk = chunks[index - 1]
                try:
                    await _run_graphiti_episode(
                        graphiti=graphiti,
                        runtime=runtime,
                        index=index,
                        total_chunks=total_chunks,
                        emit=emit,
                        episode_kwargs={
                            "name": f"{str(getattr(project, 'title', '') or 'MuseGraph Graph')} {index}/{total_chunks}",
                            "episode_body": chunk,
                            "source": EpisodeType.text,
                            "source_description": "MuseGraph graph build chunk",
                            "reference_time": base_reference_time + timedelta(seconds=index - 1),
                            "group_id": graph_id,
                            "entity_types": entity_types,
                            "edge_types": edge_types,
                            "edge_type_map": edge_type_map,
                            "saga": f"graph_build_{graph_id}",
                        },
                    )
                    async with state_lock:
                        completed_chunk_indices.append(index)
                        completed_count = len(completed_chunk_indices)
                    progress = 30 + int((completed_count / max(1, selected_chunk_count)) * 70)
                    emit(progress, f"Graphiti ingested {completed_count}/{selected_chunk_count} selected chunks...")
                except Exception as exc:
                    if not continue_on_error:
                        async with state_lock:
                            if first_error is None:
                                first_error = exc
                        return
                    async with state_lock:
                        failed_chunk_indices.append(index)
                        failed_errors[str(index)] = _sanitize_graphiti_error_message(exc)
                        completed_count = len(completed_chunk_indices)
                    emit(
                        30 + int((completed_count / max(1, selected_chunk_count)) * 70),
                        f"Chunk {index}/{total_chunks} failed. Continuing with remaining chunks...",
                    )
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(_worker()) for _ in range(episode_worker_count)]
        try:
            await asyncio.gather(*workers)
        finally:
            for worker_task in workers:
                if not worker_task.done():
                    worker_task.cancel()
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)

        completed_chunk_indices.sort()
        failed_chunk_indices.sort()
        if first_error is not None:
            raise first_error
        if failed_chunk_indices:
            raise GraphBuildPartialFailure(
                graph_id=graph_id,
                total_chunks=total_chunks,
                selected_chunk_indices=selected_chunk_indices,
                completed_chunk_indices=completed_chunk_indices,
                failed_chunk_indices=failed_chunk_indices,
                failed_errors=failed_errors,
            )
        emit(100, "Graph build complete")
        return graph_id
    finally:
        try:
            await graphiti.close()
        finally:
            del graphiti
            gc.collect()


async def search_graph(
    project_id: str,
    query: str,
    *,
    top_k: int = 10,
    search_type: str = "INSIGHTS",
    db: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    project = await _load_project(project_id, db)
    graph_id = _project_graph_id(project)
    if not graph_id:
        raise RuntimeError(f"Project {project_id} does not have a graph id.")

    await setup_graphiti(project_id)
    runtime = await _resolve_graphiti_runtime(project_id=project_id, db=db)
    graphiti = await _create_graphiti(runtime=runtime, project_id=project_id)
    try:
        normalized_type = str(search_type or "").strip().upper() or "INSIGHTS"
        *_, recipes = _import_graphiti_runtime()
        limit = max(1, min(50, int(top_k or 10)))
        if normalized_type in {"SUMMARIES", "CHUNKS"}:
            config = recipes["node_rrf"].model_copy(deep=True)
            config.limit = limit
            result = await graphiti.search_(query=query, config=config, group_ids=[graph_id])
            items: list[dict[str, Any]] = []
            for node in result.nodes or []:
                labels = list(getattr(node, "labels", None) or [])
                node_type = next((str(label) for label in labels if str(label) not in {"Entity", "Node"}), "Entity")
                content = str(getattr(node, "summary", "") or getattr(node, "name", "") or "").strip()
                if not content:
                    continue
                items.append(
                    {
                        "id": str(getattr(node, "uuid", "") or ""),
                        "content": content,
                        "type": node_type,
                        "score": 1.0,
                    }
                )
            return items

        if normalized_type in {"GRAPH_COMPLETION", "RAG_COMPLETION", "GRAPH_SUMMARY_COMPLETION"}:
            config = recipes["combined_rrf"].model_copy(deep=True)
            config.limit = limit
            result = await graphiti.search_(query=query, config=config, group_ids=[graph_id])
            items: list[dict[str, Any]] = []
            for edge in result.edges or []:
                fact = str(getattr(edge, "fact", "") or "").strip()
                if not fact:
                    continue
                items.append(
                    {
                        "id": str(getattr(edge, "uuid", "") or ""),
                        "content": fact,
                        "type": str(getattr(edge, "name", "") or "Relation"),
                        "score": 1.0,
                    }
                )
            for node in result.nodes or []:
                summary = str(getattr(node, "summary", "") or getattr(node, "name", "") or "").strip()
                if not summary:
                    continue
                labels = list(getattr(node, "labels", None) or [])
                node_type = next((str(label) for label in labels if str(label) not in {"Entity", "Node"}), "Entity")
                items.append(
                    {
                        "id": str(getattr(node, "uuid", "") or ""),
                        "content": summary,
                        "type": node_type,
                        "score": 0.9,
                    }
                )
            return items[:limit]

        results = await graphiti.search(query=query, group_ids=[graph_id], num_results=limit)
        items = []
        for edge in results or []:
            fact = str(getattr(edge, "fact", "") or "").strip()
            if not fact:
                continue
            items.append(
                {
                    "id": str(getattr(edge, "uuid", "") or ""),
                    "content": fact,
                    "type": str(getattr(edge, "name", "") or "Relation"),
                    "score": 1.0,
                }
            )
        return items
    except Exception as exc:
        if _is_graphiti_store_io_error(exc):
            logger.warning("Graphiti search store is unreadable for project %s", project_id, exc_info=True)
            raise RuntimeError(_graphiti_store_unreadable_message(project_id)) from exc
        raise
    finally:
        try:
            await graphiti.close()
        finally:
            del graphiti
            gc.collect()


def _strip_visualization_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    ignored = {
        "uuid",
        "name",
        "group_id",
        "created_at",
        "name_embedding",
        "summary",
        "fact_embedding",
        "episodes",
        "expired_at",
        "valid_at",
        "invalid_at",
    }
    return {key: value for key, value in (attributes or {}).items() if key not in ignored}


def _coerce_attributes(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _record_to_dict(record: Any) -> dict[str, Any]:
    if isinstance(record, dict):
        return record
    data = getattr(record, "data", None)
    if callable(data):
        try:
            return data()
        except Exception:
            pass
    keys = getattr(record, "keys", None)
    if callable(keys):
        try:
            return {key: record[key] for key in keys()}
        except Exception:
            pass
    return {}


async def get_graph_visualization(project_id: str, *, db: AsyncSession | None = None) -> dict[str, Any]:
    project = await _load_project(project_id, db)
    graph_id = _project_graph_id(project)
    if not graph_id:
        return {"nodes": [], "edges": []}

    return await get_graph_visualization_for_group(project_id, graph_id=graph_id, db=db)


async def get_graph_visualization_for_group(
    project_id: str,
    *,
    graph_id: str,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    graph_id = str(graph_id or "").strip()
    if not graph_id:
        return {"nodes": [], "edges": []}

    await setup_graphiti(project_id)
    runtime = await _resolve_graphiti_runtime(project_id=project_id, db=db)
    graphiti = await _create_graphiti(runtime=runtime, project_id=project_id)
    try:
        node_query = """
        MATCH (n:Entity)
        WHERE coalesce(n.group_id, '') = $group_id
        RETURN n.uuid AS uuid,
               n.name AS name,
               coalesce(n.labels, []) AS labels,
               coalesce(n.summary, '') AS summary,
               coalesce(n.attributes, '{}') AS attributes
        ORDER BY coalesce(n.name, '')
        LIMIT $limit
        """
        edge_query = """
        MATCH (source:Entity)-[:RELATES_TO]->(e:RelatesToNode_)-[:RELATES_TO]->(target:Entity)
        WHERE coalesce(e.group_id, '') = $group_id
          AND coalesce(source.group_id, '') = $group_id
          AND coalesce(target.group_id, '') = $group_id
        RETURN e.uuid AS uuid,
               source.uuid AS source,
               target.uuid AS target,
               coalesce(e.name, 'RELATED_TO') AS label,
               coalesce(e.fact, '') AS fact,
               coalesce(e.attributes, '{}') AS attributes
        LIMIT $limit
        """
        node_records, _, _ = await graphiti.driver.execute_query(
            node_query,
            group_id=graph_id,
            limit=_GRAPHITI_MAX_VIS_NODES,
        )
        edge_records, _, _ = await graphiti.driver.execute_query(
            edge_query,
            group_id=graph_id,
            limit=_GRAPHITI_MAX_VIS_EDGES,
        )

        nodes: list[dict[str, Any]] = []
        node_map: dict[str, str] = {}
        for record in node_records or []:
            payload = _record_to_dict(record)
            node_id = str(payload.get("uuid") or "").strip()
            if not node_id:
                continue
            labels = [str(label) for label in (payload.get("labels") or [])]
            node_type = next((label for label in labels if label not in {"Entity", "Node"}), "Entity")
            label = str(payload.get("name") or node_id)
            node_map[node_id] = label
            nodes.append(
                {
                    "id": node_id,
                    "label": label,
                    "type": node_type,
                    "summary": str(payload.get("summary") or ""),
                    "attributes": _strip_visualization_attributes(_coerce_attributes(payload.get("attributes"))),
                }
            )

        edges: list[dict[str, Any]] = []
        for record in edge_records or []:
            payload = _record_to_dict(record)
            source = str(payload.get("source") or "").strip()
            target = str(payload.get("target") or "").strip()
            if not source or not target:
                continue
            label = str(payload.get("label") or "RELATED_TO")
            edges.append(
                {
                    "id": str(payload.get("uuid") or f"{source}:{target}:{label}"),
                    "source": source,
                    "target": target,
                    "label": label,
                    "type": label,
                    "fact": str(payload.get("fact") or ""),
                    "source_label": node_map.get(source, source),
                    "target_label": node_map.get(target, target),
                    "attributes": _strip_visualization_attributes(_coerce_attributes(payload.get("attributes"))),
                }
            )

        return {"nodes": nodes, "edges": edges}
    except Exception as exc:
        if _is_graphiti_store_io_error(exc):
            logger.warning("Graphiti visualization store is unreadable for project %s", project_id, exc_info=True)
            raise RuntimeError(_graphiti_store_unreadable_message(project_id)) from exc
        raise
    finally:
        try:
            await graphiti.close()
        finally:
            del graphiti
            gc.collect()


async def has_graph_data(project_id: str, *, db: AsyncSession | None = None) -> bool:
    project = await _load_project(project_id, db)
    graph_id = _project_graph_id(project)
    if not graph_id:
        return False

    db_path = Path(_graphiti_store_path(project_id))
    if not db_path.exists():
        return False

    (
        _Graphiti,
        KuzuDriver,
        _OpenAIGenericClient,
        _LLMConfig,
        _OpenAIEmbedder,
        _OpenAIEmbedderConfig,
        _OpenAIRerankerClient,
        _EpisodeType,
        _recipes,
    ) = _import_graphiti_runtime()
    try:
        await setup_graphiti(project_id)
        driver = _open_kuzu_driver(KuzuDriver, db_path=str(db_path), project_id=project_id)
    except Exception:
        logger.warning("Failed to initialize Graphiti store health check for project %s", project_id, exc_info=True)
        return False
    try:
        node_records, _, _ = await driver.execute_query(
            """
            MATCH (n:Entity)
            WHERE coalesce(n.group_id, '') = $group_id
            RETURN count(n) AS node_count
            """,
            group_id=graph_id,
        )
        for record in node_records or []:
            payload = _record_to_dict(record)
            try:
                return int(payload.get("node_count") or 0) > 0
            except Exception:
                continue
        return False
    except Exception:
        logger.warning("Failed to check Graphiti store health for project %s", project_id, exc_info=True)
        return False
    finally:
        try:
            await driver.close()
        finally:
            del driver
            gc.collect()


async def delete_graph(
    project_id: str,
    *,
    model: str | None = None,
    embedding_model: str | None = None,
    db: AsyncSession | None = None,
) -> None:
    # Keep a compatible signature with the previous graph backend dispatch.
    _ = (model, embedding_model)
    project = await _load_project(project_id, db)
    graph_id = _project_graph_id(project)
    if not graph_id:
        return

    _clear_graphiti_store(project_id)

