import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import AIProviderConfig
from app.services.ai import DEFAULT_MODEL
from app.services.ai import call_llm
from app.services.llm_json import extract_json_object
from app.services.provider_models import get_provider_chat_models


def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip().upper())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:64] or "CONCEPT"


def _pick_first_list(data: dict[str, Any], keys: list[str]) -> list[Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _to_example_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()][:8]
    if isinstance(value, str):
        parts = re.split(r"[,\n;，；、]+", value)
        return [p.strip() for p in parts if p.strip()][:8]
    return []


def _normalize_entity_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        return {"name": item, "description": "", "examples": []}
    if not isinstance(item, dict):
        return None
    name = str(
        item.get("name")
        or item.get("type")
        or item.get("entity")
        or item.get("label")
        or item.get("entity_type")
        or ""
    ).strip()
    return {
        "name": name,
        "description": str(item.get("description") or item.get("desc") or item.get("definition") or "").strip(),
        "examples": _to_example_list(
            item.get("examples")
            or item.get("sample")
            or item.get("samples")
            or item.get("instances")
        ),
    }


def _normalize_edge_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        return {
            "name": item,
            "source_type": "",
            "target_type": "",
            "description": "",
        }
    if not isinstance(item, dict):
        return None

    def _stringify_type(value: Any) -> str:
        if isinstance(value, dict):
            return str(
                value.get("type")
                or value.get("name")
                or value.get("entity_type")
                or value.get("label")
                or value.get("id")
                or ""
            ).strip()
        return str(value or "").strip()

    source_candidates = [
        item.get("source_type"),
        item.get("sourceType"),
        item.get("source"),
        item.get("from"),
        item.get("head"),
        item.get("subject"),
        item.get("subject_type"),
        item.get("source_entity"),
        item.get("source_entity_type"),
    ]
    target_candidates = [
        item.get("target_type"),
        item.get("targetType"),
        item.get("target"),
        item.get("to"),
        item.get("tail"),
        item.get("object"),
        item.get("object_type"),
        item.get("target_entity"),
        item.get("target_entity_type"),
    ]
    source_type = next((text for text in (_stringify_type(value) for value in source_candidates) if text), "")
    target_type = next((text for text in (_stringify_type(value) for value in target_candidates) if text), "")

    return {
        "name": str(item.get("name") or item.get("relation") or item.get("type") or item.get("predicate") or "").strip(),
        "source_type": source_type,
        "target_type": target_type,
        "description": str(item.get("description") or item.get("desc") or "").strip(),
    }


def _normalize_ontology_payload(data: dict[str, Any]) -> dict[str, Any]:
    nested = data.get("ontology")
    if isinstance(nested, dict):
        merged = dict(nested)
        merged.update(data)
        data = merged

    entities_raw = _pick_first_list(
        data,
        [
            "entity_types",
            "entityTypes",
            "entities",
            "entity_type_list",
            "entityTypeList",
            "entity_types_list",
            "nodes",
            "node_types",
            "concepts",
            "classes",
        ],
    )
    edges_raw = _pick_first_list(
        data,
        [
            "edge_types",
            "edgeTypes",
            "relations",
            "relationship_types",
            "relationships",
            "edges",
            "links",
            "triples",
            "predicates",
        ],
    )

    entities = [normalized for normalized in (_normalize_entity_item(item) for item in entities_raw) if normalized]
    edges = [normalized for normalized in (_normalize_edge_item(item) for item in edges_raw) if normalized]

    analysis_summary = str(
        data.get("analysis_summary")
        or data.get("summary")
        or data.get("analysis")
        or data.get("explanation")
        or ""
    ).strip()

    return {
        "entity_types": entities,
        "edge_types": edges,
        "analysis_summary": analysis_summary,
    }


async def _repair_ontology_json(raw_output: str, model: str, db: AsyncSession) -> str | None:
    content = (raw_output or "").strip()
    if not content:
        return None
    repair_prompt = (
        "You are a JSON normalizer. Convert the following ontology draft into strict JSON only.\n"
        "Required schema:\n"
        "{\n"
        '  "entity_types": [{"name":"...", "description":"...", "examples":["..."]}],\n'
        '  "edge_types": [{"name":"...", "source_type":"...", "target_type":"...", "description":"..."}],\n'
        '  "analysis_summary": "..."\n'
        "}\n"
        "Rules:\n"
        "1) Output JSON object only, no markdown.\n"
        "2) Keep entity/edge names concise; use uppercase snake case when possible.\n"
        "3) Keep relation source_type/target_type explicit and non-empty.\n\n"
        f"Draft:\n{content[:12000]}"
    )
    repaired = await call_llm(
        model,
        repair_prompt,
        db,
        prefer_stream_override=False,
        stream_fallback_nonstream_override=False,
    )
    return str(repaired.get("content") or "").strip() or None


def _sanitize_ontology(data: dict[str, Any]) -> dict[str, Any]:
    entities_raw = data.get("entity_types") if isinstance(data.get("entity_types"), list) else []
    edges_raw = data.get("edge_types") if isinstance(data.get("edge_types"), list) else []

    entity_types: list[dict[str, Any]] = []
    seen_entities: set[str] = set()
    for item in entities_raw:
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("name") or "").strip()
        if not raw_name:
            continue
        name = _normalize_name(raw_name)
        if name in seen_entities:
            continue
        seen_entities.add(name)
        entity_types.append(
            {
                "name": name,
                "description": str(item.get("description") or "").strip(),
                "examples": [str(x).strip() for x in (item.get("examples") or []) if str(x).strip()][:8],
            }
        )
        if len(entity_types) >= 16:
            break

    edge_types: list[dict[str, Any]] = []
    entity_names = [entity["name"] for entity in entity_types if isinstance(entity, dict) and entity.get("name")]
    default_source = entity_names[0] if entity_names else ""
    default_target = entity_names[1] if len(entity_names) > 1 else default_source
    for item in edges_raw:
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("name") or "").strip()
        raw_source_type = str(item.get("source_type") or "").strip()
        raw_target_type = str(item.get("target_type") or "").strip()
        if not raw_source_type:
            raw_source_type = default_source
        if not raw_target_type:
            raw_target_type = default_target
        if not raw_name or not raw_source_type or not raw_target_type:
            continue
        name = _normalize_name(raw_name)
        source_type = _normalize_name(raw_source_type)
        target_type = _normalize_name(raw_target_type)
        edge_types.append(
            {
                "name": name,
                "source_type": source_type,
                "target_type": target_type,
                "description": str(item.get("description") or "").strip(),
            }
        )
        if len(edge_types) >= 24:
            break

    return {
        "entity_types": entity_types,
        "edge_types": edge_types,
        "analysis_summary": str(data.get("analysis_summary") or "").strip(),
    }


def _is_minimal_ontology(ontology: dict[str, Any]) -> bool:
    entities = ontology.get("entity_types") if isinstance(ontology.get("entity_types"), list) else []
    edges = ontology.get("edge_types") if isinstance(ontology.get("edge_types"), list) else []
    if len(entities) != 1 or len(edges) != 1:
        return False
    entity_name = str((entities[0] or {}).get("name") or "").strip().upper() if isinstance(entities[0], dict) else ""
    edge_name = str((edges[0] or {}).get("name") or "").strip().upper() if isinstance(edges[0], dict) else ""
    return entity_name == "CONCEPT" and edge_name == "RELATED_TO"


def _build_ontology_source_excerpt(text: str, *, max_chars: int = 12000) -> str:
    source = (text or "").strip()
    if not source:
        return ""
    if len(source) <= max_chars:
        return source

    # Evenly sample the full text span so ontology generation is not biased
    # toward only the beginning of long content.
    segment_count = min(10, max(4, len(source) // 50000 + 4))
    separator = "\n\n[...]\n\n"
    separator_total = len(separator) * (segment_count - 1)
    budget = max_chars - separator_total
    while segment_count > 2 and budget // segment_count < 300:
        segment_count -= 1
        separator_total = len(separator) * (segment_count - 1)
        budget = max_chars - separator_total

    segment_len = max(240, budget // segment_count)
    last_start = max(0, len(source) - segment_len)
    parts: list[str] = []
    seen: set[str] = set()

    for idx in range(segment_count):
        start = int((last_start * idx) / max(1, segment_count - 1))
        end = min(len(source), start + segment_len)

        # Prefer paragraph boundaries inside the window.
        start_boundary = source.rfind("\n\n", max(0, start - 120), min(len(source), start + 120))
        if start_boundary != -1:
            start = max(0, start_boundary + 2)
            end = min(len(source), start + segment_len)
        end_boundary = source.rfind("\n\n", start + max(1, int(segment_len * 0.55)), end)
        if end_boundary != -1 and end_boundary > start:
            end = end_boundary

        piece = source[start:end].strip()
        if not piece:
            continue
        if piece in seen:
            continue
        seen.add(piece)
        parts.append(piece)

    if not parts:
        return source[:max_chars].strip()

    excerpt = separator.join(parts).strip()
    if len(excerpt) <= max_chars:
        return excerpt
    return excerpt[:max_chars].strip()


def _build_ontology_prompt(text: str, requirement: str | None) -> str:
    sampled_text = _build_ontology_source_excerpt(text, max_chars=12000)
    return (
        "You are an ontology architect. Read the input text and propose an ontology in JSON only.\n"
        "Output schema:\n"
        "{\n"
        '  "entity_types": [{"name":"...", "description":"...", "examples":["..."]}],\n'
        '  "edge_types": [{"name":"...", "source_type":"...", "target_type":"...", "description":"..."}],\n'
        '  "analysis_summary": "..."\n'
        "}\n"
        "Rules: 6-16 entity types, 8-24 edge types, concise names in uppercase snake case.\n"
        "Do not include markdown.\n\n"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Text:\n{sampled_text}"
    )


def _build_retry_prompt(text: str, requirement: str | None) -> str:
    sampled_text = _build_ontology_source_excerpt(text, max_chars=12000)
    return (
        "Return strict JSON only. Build a rich ontology for the text.\n"
        "Schema:\n"
        "{\n"
        '  "entity_types": [{"name":"...", "description":"...", "examples":["..."]}],\n'
        '  "edge_types": [{"name":"...", "source_type":"...", "target_type":"...", "description":"..."}],\n'
        '  "analysis_summary": "..."\n'
        "}\n"
        "Hard constraints:\n"
        "1) At least 6 entity_types and at least 8 edge_types.\n"
        "2) Do not use generic placeholders like only CONCEPT/RELATED_TO.\n"
        "3) Use concrete relation names and valid source_type/target_type.\n"
        "4) Output JSON object only.\n\n"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Text:\n{sampled_text}"
    )


async def _parse_ontology_from_content(
    *,
    raw_content: str,
    model: str,
    db: AsyncSession,
) -> dict[str, Any] | None:
    parsed = extract_json_object(raw_content)
    if parsed:
        return parsed
    repaired_content = await _repair_ontology_json(raw_content, model, db)
    if not repaired_content:
        return None
    return extract_json_object(repaired_content)


def _attach_meta(
    ontology: dict[str, Any],
    *,
    model: str | None,
    api_called: bool,
    provider: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> dict[str, Any]:
    payload = dict(ontology or {})
    payload["_meta"] = {
        "model": (model or "").strip() or None,
        "provider": (provider or "").strip() or None,
        "api_called": bool(api_called),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
    }
    return payload


async def generate_ontology(
    text: str,
    db: AsyncSession,
    requirement: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    payload_text = (text or "").strip()
    selected_model = (model or "").strip() or DEFAULT_MODEL
    if not payload_text:
        raise ValueError("No source text provided for ontology generation")

    provider_name = ""
    input_tokens = 0
    output_tokens = 0
    api_called = False
    try:
        # Pick a model from active providers first.
        result = await db.execute(
            select(AIProviderConfig).where(AIProviderConfig.is_active == True).order_by(AIProviderConfig.priority.desc())
        )
        providers = result.scalars().all()
        selected_model = (model or "").strip() or None
        for provider in providers:
            if selected_model:
                break
            provider_models = get_provider_chat_models(provider)
            if provider_models:
                selected_model = provider_models[0]
                break
        if not selected_model:
            selected_model = DEFAULT_MODEL

        llm_result = await call_llm(
            selected_model,
            _build_ontology_prompt(payload_text, requirement),
            db,
            max_tokens=2200,
            prefer_stream_override=False,
            stream_fallback_nonstream_override=False,
        )
        api_called = True
        provider_name = str(llm_result.get("provider") or "")
        input_tokens = int(llm_result.get("input_tokens") or 0)
        output_tokens = int(llm_result.get("output_tokens") or 0)
        raw_content = str(llm_result.get("content") or "")
        parsed: dict[str, Any] | None = None
        parse_error: Exception | None = None
        try:
            parsed = await _parse_ontology_from_content(
                raw_content=raw_content,
                model=selected_model,
                db=db,
            )
        except Exception as repair_exc:
            parse_error = repair_exc

        if not parsed:
            error_code = "llm_response_not_json_or_invalid_schema_after_repair"
            if parse_error:
                error_code = f"{error_code}:{type(parse_error).__name__}:{str(parse_error)[:120]}"
            raise ValueError(error_code)

        sanitized = _sanitize_ontology(_normalize_ontology_payload(parsed))
        needs_retry = (
            _is_minimal_ontology(sanitized)
            or not sanitized.get("entity_types")
            or not sanitized.get("edge_types")
        )
        if needs_retry:
            retry_result = await call_llm(
                selected_model,
                _build_retry_prompt(payload_text, requirement),
                db,
                max_tokens=2200,
                prefer_stream_override=False,
                stream_fallback_nonstream_override=False,
            )
            input_tokens += int(retry_result.get("input_tokens") or 0)
            output_tokens += int(retry_result.get("output_tokens") or 0)
            retry_provider = str(retry_result.get("provider") or "").strip()
            if retry_provider:
                provider_name = retry_provider
            retry_content = str(retry_result.get("content") or "")
            retry_parsed: dict[str, Any] | None = None
            retry_parse_error: Exception | None = None
            try:
                retry_parsed = await _parse_ontology_from_content(
                    raw_content=retry_content,
                    model=selected_model,
                    db=db,
                )
            except Exception as retry_exc:
                retry_parse_error = retry_exc

            if not retry_parsed:
                error_code = "retry_llm_response_not_json_or_invalid_schema_after_repair"
                if retry_parse_error:
                    error_code = f"{error_code}:{type(retry_parse_error).__name__}:{str(retry_parse_error)[:120]}"
                raise ValueError(error_code)

            retry_sanitized = _sanitize_ontology(_normalize_ontology_payload(retry_parsed))
            if not retry_sanitized.get("entity_types") or not retry_sanitized.get("edge_types"):
                raise ValueError("retry_output_missing_valid_entity_or_edge_types")
            if _is_minimal_ontology(retry_sanitized):
                raise ValueError("retry_output_too_generic_concept_related_to")
            sanitized = retry_sanitized

        if not sanitized["entity_types"] or not sanitized["edge_types"]:
            raise ValueError("llm_output_missing_valid_entity_or_edge_types")
        if _is_minimal_ontology(sanitized):
            raise ValueError("llm_output_too_generic_concept_related_to")

        summary = (sanitized.get("analysis_summary") or "").strip()
        if not summary:
            sanitized["analysis_summary"] = "Ontology generated by LLM API."
        return _attach_meta(
            sanitized,
            model=selected_model,
            provider=provider_name,
            api_called=api_called,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"ontology_pipeline_failed:{type(exc).__name__}:{str(exc)[:120]}") from exc


def build_graph_input_with_ontology(text: str, ontology: dict[str, Any] | None) -> str:
    if not ontology:
        return text
    try:
        entities = ontology.get("entity_types") or []
        edges = ontology.get("edge_types") or []
        ontology_header = {
            "entity_types": [
                {"name": e.get("name"), "description": e.get("description")}
                for e in entities
                if isinstance(e, dict)
            ],
            "edge_types": [
                {
                    "name": r.get("name"),
                    "source_type": r.get("source_type"),
                    "target_type": r.get("target_type"),
                }
                for r in edges
                if isinstance(r, dict)
            ],
        }
        extraction_rules = (
            "[GRAPH_EXTRACTION_RULES]\n"
            "1) People, organizations, and other entities must use canonical names. Treat aliases as aliases of the same entity instead of creating new entities.\n"
            "2) Event phrases such as deaths, funerals, or ceremonies must be modeled as event nodes instead of person entities.\n"
            "3) Scene or location phrases must not be used as person aliases.\n"
            "[/GRAPH_EXTRACTION_RULES]\n\n"
        )
        return (
            "[ONTOLOGY_CONTEXT]\n"
            + json.dumps(ontology_header, ensure_ascii=False)
            + "\n[/ONTOLOGY_CONTEXT]\n\n"
            + extraction_rules
            + text
        )
    except Exception:
        return text
