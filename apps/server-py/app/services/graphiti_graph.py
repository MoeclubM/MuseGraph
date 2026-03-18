from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, get_origin

from pydantic import BaseModel, Field, create_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.config import AIProviderConfig
from app.models.project import TextProject
from app.services.ai import _load_llm_runtime_config, resolve_component_model
from app.services.llm_json import extract_json_object, normalize_json_content
from app.services.provider_models import get_provider_chat_models, get_provider_embedding_models

logger = logging.getLogger(__name__)

_GRAPHITI_CHUNK_SIZE = 5000
_GRAPHITI_CHUNK_OVERLAP = 400
_GRAPHITI_MAX_VIS_NODES = 320
_GRAPHITI_MAX_VIS_EDGES = 900
_GRAPHITI_SETUP_LOCK = asyncio.Lock()
_GRAPHITI_SETUP_COMPLETE: set[str] = set()


@dataclass
class _GraphitiRuntimeSelection:
    llm_model: str
    llm_api_key: str
    llm_base_url: str
    embedding_model: str
    embedding_api_key: str
    embedding_base_url: str
    reranker_model: str
    timeout_seconds: int
    retry_count: int
    max_coroutines: int


def _normalize_graphiti_structured_payload(
    response_model: type[BaseModel] | None,
    payload: Any,
) -> Any:
    if response_model is None:
        return payload

    model_fields = getattr(response_model, "model_fields", {})
    field_names = list(model_fields.keys())
    model_name = getattr(response_model, "__name__", "")

    def _normalize_entity_items(items: list[Any]) -> list[Any]:
        normalized_entities = []
        for item in items:
            if isinstance(item, dict) and "name" not in item:
                for alias in ("entity_name", "node_name", "entity"):
                    alias_value = str(item.get(alias) or "").strip()
                    if alias_value:
                        copied = dict(item)
                        copied.pop(alias, None)
                        copied["name"] = alias_value
                        item = copied
                        break
            normalized_entities.append(item)
        return normalized_entities

    def _normalize_edge_items(items: list[Any]) -> list[Any]:
        normalized_edges = []
        for item in items:
            if isinstance(item, dict):
                aliased = dict(item)
                if "source_entity_name" not in aliased:
                    for alias in ("source_name", "source_entity", "source"):
                        alias_value = str(aliased.get(alias) or "").strip()
                        if alias_value:
                            aliased.pop(alias, None)
                            aliased["source_entity_name"] = alias_value
                            break
                if "target_entity_name" not in aliased:
                    for alias in ("target_name", "target_entity", "target"):
                        alias_value = str(aliased.get(alias) or "").strip()
                        if alias_value:
                            aliased.pop(alias, None)
                            aliased["target_entity_name"] = alias_value
                            break
                if "relation_type" not in aliased:
                    for alias in ("edge_type", "relation", "relation_name", "name"):
                        alias_value = str(aliased.get(alias) or "").strip()
                        if alias_value:
                            aliased.pop(alias, None)
                            aliased["relation_type"] = alias_value
                            break
                if "fact" not in aliased:
                    for alias in ("relationship_fact", "relation_fact", "description", "summary", "statement"):
                        alias_value = str(aliased.get(alias) or "").strip()
                        if alias_value:
                            aliased.pop(alias, None)
                            aliased["fact"] = alias_value
                            break
                if "fact" not in aliased:
                    source_name = str(aliased.get("source_entity_name") or "").strip()
                    relation_type = str(aliased.get("relation_type") or "").strip()
                    target_name = str(aliased.get("target_entity_name") or "").strip()
                    if source_name and relation_type and target_name:
                        aliased["fact"] = (
                            f"{source_name} {relation_type.replace('_', ' ').lower()} {target_name}"
                        )
                item = aliased
            normalized_edges.append(item)
        return normalized_edges

    def _normalize_node_resolution_items(items: list[Any]) -> list[Any]:
        normalized = []
        for item in items:
            if isinstance(item, dict) and "name" not in item:
                alias = "entity_name" if str(item.get("entity_name") or "").strip() else "node_name"
                alias_value = str(item.get(alias) or "").strip()
                if alias_value:
                    copied = dict(item)
                    copied.pop(alias, None)
                    copied["name"] = alias_value
                    item = copied
            normalized.append(item)
        return normalized

    def _normalize_summary_items(items: list[Any]) -> list[Any]:
        normalized = []
        for item in items:
            if isinstance(item, dict):
                if "name" in item and "summary" in item:
                    normalized.append(item)
                    continue
                if len(item) == 1:
                    only_key, only_value = next(iter(item.items()))
                    if isinstance(only_value, str):
                        normalized.append({"name": str(only_key), "summary": only_value})
                        continue
                alias_name = str(item.get("entity_name") or item.get("node_name") or "").strip()
                alias_summary = str(item.get("text") or item.get("description") or "").strip()
                if alias_name and alias_summary:
                    normalized.append({"name": alias_name, "summary": alias_summary})
                    continue
            normalized.append(item)
        return normalized

    def _normalize_summary_text_payload(value: Any) -> list[dict[str, str]]:
        text = str(value or "").strip()
        if not text:
            return []
        normalized: list[dict[str, str]] = []
        for raw_line in re.split(r"[\r\n]+", text):
            line = str(raw_line or "").strip()
            if not line:
                continue
            line = re.sub(r"^[\-\*\u2022\d\.\)\s]+", "", line).strip()
            match = re.match(
                r'^(?:\*\*(?P<bold>[^*]+)\*\*|(?P<plain>[^:：\-]{2,80}))\s*[:：\-]\s*(?P<summary>.+)$',
                line,
            )
            if not match:
                continue
            name = str(match.group("bold") or match.group("plain") or "").strip().strip("*").strip('"').strip("'")
            summary = str(match.group("summary") or "").strip().strip('"').strip("'")
            if name and summary:
                normalized.append({"name": name, "summary": summary})
        return normalized

    def _normalize_int_list(value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        normalized: list[int] = []
        for item in value:
            if isinstance(item, bool):
                continue
            if isinstance(item, int):
                normalized.append(item)
                continue
            if isinstance(item, float) and item.is_integer():
                normalized.append(int(item))
                continue
            if isinstance(item, str):
                stripped = item.strip()
                if stripped.lstrip("-").isdigit():
                    normalized.append(int(stripped))
        return normalized

    def _normalize_edge_duplicate_payload(value: Any) -> dict[str, list[int]]:
        candidate = value
        if isinstance(candidate, list):
            candidate = next(
                (item for item in candidate if isinstance(item, dict)),
                None,
            )
        if not isinstance(candidate, dict):
            return {"duplicate_facts": [], "contradicted_facts": []}

        duplicate_facts = candidate.get("duplicate_facts")
        if duplicate_facts is None:
            for alias in ("duplicates", "duplicate_idxs", "duplicate_indices", "duplicate_ids"):
                if alias in candidate:
                    duplicate_facts = candidate.get(alias)
                    break

        contradicted_facts = candidate.get("contradicted_facts")
        if contradicted_facts is None:
            for alias in (
                "contradictions",
                "contradicted_idxs",
                "contradicted_indices",
                "invalidated_facts",
            ):
                if alias in candidate:
                    contradicted_facts = candidate.get(alias)
                    break

        return {
            "duplicate_facts": _normalize_int_list(duplicate_facts),
            "contradicted_facts": _normalize_int_list(contradicted_facts),
        }

    if model_name == "EdgeDuplicate":
        return _normalize_edge_duplicate_payload(payload)

    if isinstance(payload, list) and len(field_names) == 1:
        if model_name == "ExtractedEntities":
            return {"extracted_entities": _normalize_entity_items(payload)}
        if model_name == "ExtractedEdges":
            return {"edges": _normalize_edge_items(payload)}
        if model_name == "NodeResolutions":
            return {"entity_resolutions": _normalize_node_resolution_items(payload)}
        if model_name == "SummarizedEntities":
            return {"summaries": _normalize_summary_items(payload)}
        return {field_names[0]: payload}

    if isinstance(payload, str) and len(field_names) == 1 and payload.strip():
        return {field_names[0]: payload.strip()}

    if not isinstance(payload, dict):
        return payload

    if model_name == "ExtractedEntities" and isinstance(payload.get("extracted_entities"), list):
        return {"extracted_entities": _normalize_entity_items(payload["extracted_entities"])}

    if model_name == "ExtractedEntities" and "extracted_entities" not in payload:
        candidate = payload.get("nodes")
        if not isinstance(candidate, list):
            candidate = payload.get("entities")
        if isinstance(candidate, list):
            return {"extracted_entities": _normalize_entity_items(candidate)}

    if model_name == "ExtractedEdges" and isinstance(payload.get("edges"), list):
        return {"edges": _normalize_edge_items(payload["edges"])}

    if model_name == "ExtractedEdges" and "edges" not in payload:
        for key in ("relationships", "relations"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return {"edges": _normalize_edge_items(candidate)}

    if model_name == "NodeResolutions" and isinstance(payload.get("entity_resolutions"), list):
        return {"entity_resolutions": _normalize_node_resolution_items(payload["entity_resolutions"])}

    if model_name == "SummarizedEntities" and isinstance(payload.get("summaries"), list):
        return {"summaries": _normalize_summary_items(payload["summaries"])}

    if model_name == "SummarizedEntities" and isinstance(payload.get("summaries"), str):
        return {"summaries": _normalize_summary_text_payload(payload.get("summaries"))}

    if model_name == "SummarizedEntities" and "summaries" not in payload:
        if payload and all(isinstance(value, str) for value in payload.values()):
            return {
                "summaries": [
                    {"name": str(name), "summary": str(summary)}
                    for name, summary in payload.items()
                ]
            }

    if len(field_names) == 1 and field_names[0] not in payload and len(payload) == 1:
        only_value = next(iter(payload.values()))
        if isinstance(only_value, (list, dict, str)):
            return {field_names[0]: only_value}

    if len(field_names) == 1 and field_names[0] not in payload:
        field_annotation = getattr(model_fields[field_names[0]], "annotation", None)
        if get_origin(field_annotation) is list:
            if model_name == "SummarizedEntities":
                return {field_names[0]: _normalize_summary_text_payload(payload)}
            if model_name == "NodeResolutions":
                return {field_names[0]: _normalize_node_resolution_items([payload])}
            return {field_names[0]: [payload]}

    return payload


def _parse_graphiti_response_content(
    response_model: type[BaseModel] | None,
    raw_content: str,
) -> Any:
    text = str(raw_content or "").strip()
    if not text:
        raise ValueError("Empty response content from Graphiti LLM provider")

    parsed_payload = None
    for candidate in (normalize_json_content(text), text):
        if not candidate:
            continue
        try:
            parsed_payload = json.loads(candidate)
            break
        except Exception:
            continue

    if parsed_payload is None:
        parsed_payload = extract_json_object(text)

    if parsed_payload is None:
        # Some providers still return plain text for single-field structured prompts.
        if response_model is not None:
            field_names = list(getattr(response_model, "model_fields", {}).keys())
            if len(field_names) == 1:
                return {field_names[0]: text}
        raise ValueError("Unable to parse Graphiti LLM response as JSON")

    return _normalize_graphiti_structured_payload(response_model, parsed_payload)


def _graphiti_telemetry_enabled() -> str:
    return "true" if not bool(getattr(settings, "TELEMETRY_DISABLED", True)) else "false"


def _build_graph_id() -> str:
    return f"graphiti_{uuid.uuid4().hex[:16]}"


def _split_text(text: str, *, chunk_size: int = _GRAPHITI_CHUNK_SIZE, overlap: int = _GRAPHITI_CHUNK_OVERLAP) -> list[str]:
    source = str(text or "").strip()
    if not source:
        return []
    if len(source) <= chunk_size:
        return [source]

    chunks: list[str] = []
    cursor = 0
    total_length = len(source)
    while cursor < total_length:
        end = min(cursor + chunk_size, total_length)
        if end < total_length:
            boundary = source.rfind("\n\n", cursor + max(1, int(chunk_size * 0.6)), end)
            if boundary > cursor:
                end = boundary
        piece = source[cursor:end].strip()
        if piece:
            chunks.append(piece)
        if end >= total_length:
            break
        next_cursor = max(end - overlap, cursor + 1)
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
        for pair in (edge_def.get("source_targets") or []):
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
    embedding: bool,
) -> tuple[AIProviderConfig | None, str | None]:
    getter = get_provider_embedding_models if embedding else get_provider_chat_models
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


async def _resolve_graphiti_runtime(
    *,
    project_id: str,
    db: AsyncSession | None,
    model: str | None = None,
    embedding_model: str | None = None,
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

    llm_provider, llm_model = _select_provider_for_model(configs, model=requested_model, embedding=False)
    if llm_provider is None:
        llm_provider = next((item for item in configs if _first_valid_model(get_provider_chat_models(item))), None)
        llm_model = _first_valid_model(get_provider_chat_models(llm_provider)) if llm_provider else None
    if llm_provider is None or not llm_model:
        raise RuntimeError("No chat model configured in active providers for Graphiti graph build.")

    embedding_provider, selected_embedding_model = (
        _select_provider_for_model(configs, model=requested_embedding_model, embedding=True)
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

    _require_openai_compatible_provider(llm_provider, purpose="LLM")
    _require_openai_compatible_provider(embedding_provider, purpose="embedding")

    llm_api_key = _require_provider_api_key(llm_provider, purpose="LLM")
    embedding_api_key = _require_provider_api_key(embedding_provider, purpose="embedding")

    llm_base_url = str(getattr(llm_provider, "base_url", "") or "").strip()
    embedding_base_url = str(getattr(embedding_provider, "base_url", "") or "").strip()
    max_coroutines = max(1, min(20, int(runtime_cfg.get("llm_task_concurrency", 4) or 4)))

    return _GraphitiRuntimeSelection(
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        embedding_model=selected_embedding_model,
        embedding_api_key=embedding_api_key,
        embedding_base_url=embedding_base_url,
        reranker_model=llm_model,
        timeout_seconds=max(5, min(1800, int(runtime_cfg.get("llm_request_timeout_seconds", 180) or 180))),
        retry_count=max(0, min(10, int(runtime_cfg.get("llm_retry_count", 2) or 2))),
        max_coroutines=max_coroutines,
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

    def _clone(*, database: str) -> Any:
        driver._database = str(database or "")
        return driver

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

            openai_messages = []
            for message in messages:
                message.content = self._clean_input(message.content)
                if message.role == "user":
                    openai_messages.append({"role": "user", "content": message.content})
                elif message.role == "system":
                    openai_messages.append({"role": "system", "content": message.content})

            try:
                response_format: dict[str, Any] = {"type": "json_object"}
                if response_model is not None:
                    schema_name = getattr(response_model, "__name__", "structured_response")
                    response_format = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "schema": response_model.model_json_schema(),
                        },
                    }

                response = await self.client.chat.completions.create(
                    model=self.model or "gpt-4.1-mini",
                    messages=openai_messages,
                    temperature=self.temperature,
                    max_tokens=max_tokens or self.max_tokens,
                    response_format=response_format,  # type: ignore[arg-type]
                )
                raw_content = response.choices[0].message.content or ""
                return _parse_graphiti_response_content(response_model, raw_content)
            except openai.RateLimitError as exc:
                raise RateLimitError from exc
            except Exception as exc:
                logger.error(f"Error in generating Graphiti LLM response: {exc}")
                raise

    return MuseGraphGraphitiClient


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

    llm_config = LLMConfig(
        api_key=runtime.llm_api_key,
        model=runtime.llm_model,
        base_url=runtime.llm_base_url or None,
        temperature=0,
        max_tokens=16384,
        small_model=runtime.reranker_model,
    )
    embedder_config = OpenAIEmbedderConfig(
        api_key=runtime.embedding_api_key,
        base_url=runtime.embedding_base_url or None,
        embedding_model=runtime.embedding_model,
        embedding_dim=_embedding_dimension(),
    )
    graphiti_llm_client_cls = _patch_graphiti_llm_client(OpenAIGenericClient)
    driver = _patch_graphiti_driver_compatibility(
        KuzuDriver(db=db_path, max_concurrent_queries=runtime.max_coroutines)
    )
    return Graphiti(
        graph_driver=driver,
        llm_client=graphiti_llm_client_cls(config=llm_config, max_tokens=16384),
        embedder=OpenAIEmbedder(config=embedder_config),
        cross_encoder=OpenAIRerankerClient(config=llm_config),
        max_coroutines=runtime.max_coroutines,
    )


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
        driver = _patch_graphiti_driver_compatibility(KuzuDriver(db=db_path))
        try:
            await driver.build_indices_and_constraints()
        finally:
            await driver.close()
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
) -> str:
    chunks = _split_text(text)
    if not chunks:
        raise ValueError("No graph input text provided")

    await setup_graphiti(project_id)
    project = await _load_project(project_id, db)
    graph_id = str(getattr(project, "cognee_dataset_id", "") or "").strip() or _build_graph_id()
    runtime = await _resolve_graphiti_runtime(
        project_id=project_id,
        db=db,
        model=model,
        embedding_model=embedding_model,
    )
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
        previous_episode_uuid: str | None = None
        for index, chunk in enumerate(chunks, start=1):
            result = await graphiti.add_episode(
                name=f"{str(getattr(project, 'title', '') or 'MuseGraph Graph')} {index}/{total_chunks}",
                episode_body=chunk,
                source=EpisodeType.text,
                source_description="MuseGraph graph build chunk",
                reference_time=datetime.now(timezone.utc),
                group_id=graph_id,
                entity_types=entity_types,
                edge_types=edge_types,
                edge_type_map=edge_type_map,
                previous_episode_uuids=[previous_episode_uuid] if previous_episode_uuid else None,
                saga=f"graph_build_{graph_id}",
                saga_previous_episode_uuid=previous_episode_uuid,
            )
            previous_episode_uuid = str(getattr(getattr(result, "episode", None), "uuid", "") or "").strip() or previous_episode_uuid
            progress = 30 + int((index / total_chunks) * 70)
            emit(progress, f"Graphiti ingesting episodes {index}/{total_chunks}...")
        emit(100, "Graph build complete")
        return graph_id
    finally:
        await graphiti.close()


async def search_graph(
    project_id: str,
    query: str,
    *,
    top_k: int = 10,
    search_type: str = "INSIGHTS",
    db: AsyncSession | None = None,
) -> list[dict[str, Any]]:
    project = await _load_project(project_id, db)
    graph_id = str(getattr(project, "cognee_dataset_id", "") or "").strip()
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
    finally:
        await graphiti.close()


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
    graph_id = str(getattr(project, "cognee_dataset_id", "") or "").strip()
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
    finally:
        await graphiti.close()


async def delete_graph(project_id: str, *, db: AsyncSession | None = None) -> None:
    project = await _load_project(project_id, db)
    graph_id = str(getattr(project, "cognee_dataset_id", "") or "").strip()
    if not graph_id:
        return

    db_path = Path(_graphiti_store_path(project_id))
    store_dir = db_path.parent
    _GRAPHITI_SETUP_COMPLETE.discard(str(db_path))
    if store_dir.exists():
        shutil.rmtree(store_dir, ignore_errors=True)
