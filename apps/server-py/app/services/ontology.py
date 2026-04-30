import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import AIProviderConfig
from app.services.ai import DEFAULT_MODEL
from app.services.ai import call_llm
from app.services.llm_json import StrictJsonSchemaModel, extract_json_object
from app.services.provider_models import get_provider_chat_models


class OntologyEntityType(StrictJsonSchemaModel):
    name: str
    description: str
    examples: list[str]


class OntologyEdgeType(StrictJsonSchemaModel):
    name: str
    source_type: str
    target_type: str
    description: str


class OntologyResponse(StrictJsonSchemaModel):
    entity_types: list[OntologyEntityType]
    edge_types: list[OntologyEdgeType]
    analysis_summary: str


_ONTOLOGY_PROMPT_MAX_CHARS = 8000
_ONTOLOGY_MIN_TIMEOUT_SECONDS = 300
_ONTOLOGY_MAX_TOKENS = 4096


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
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or "").strip()
    return {
        "name": name,
        "description": str(item.get("description") or "").strip(),
        "examples": _to_example_list(item.get("examples")),
    }


def _normalize_edge_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None

    return {
        "name": str(item.get("name") or "").strip(),
        "source_type": str(item.get("source_type") or "").strip(),
        "target_type": str(item.get("target_type") or "").strip(),
        "description": str(item.get("description") or "").strip(),
    }


def _normalize_ontology_payload(data: dict[str, Any]) -> dict[str, Any]:
    entities_raw = _pick_first_list(data, ["entity_types"])
    edges_raw = _pick_first_list(data, ["edge_types"])

    entities = [normalized for normalized in (_normalize_entity_item(item) for item in entities_raw) if normalized]
    edges = [normalized for normalized in (_normalize_edge_item(item) for item in edges_raw) if normalized]

    analysis_summary = str(data.get("analysis_summary") or "").strip()

    return {
        "entity_types": entities,
        "edge_types": edges,
        "analysis_summary": analysis_summary,
    }


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
        if len(entity_types) >= 24:
            break

    edge_types: list[dict[str, Any]] = []
    for item in edges_raw:
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("name") or "").strip()
        raw_source_type = str(item.get("source_type") or "").strip()
        raw_target_type = str(item.get("target_type") or "").strip()
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
        if len(edge_types) >= 40:
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
    sampled_text = _build_ontology_source_excerpt(text, max_chars=_ONTOLOGY_PROMPT_MAX_CHARS)
    return (
        "You are an ontology architect. Read the input text and propose an ontology.\n"
        "Use the provided response schema.\n"
        "Rules: 8-24 entity types, 12-40 edge types, concise names in uppercase snake case.\n"
        "Cover narrative roles, factions, places, objects, events, abilities, conflicts, motives, time points, and supernatural concepts when present.\n"
        "Prefer concrete domain relations over generic RELATED_TO, including family, location, possession, transformation, conflict, obligation, and event participation.\n"
        "Do not add commentary.\n\n"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Text:\n{sampled_text}"
    )


def _build_retry_prompt(text: str, requirement: str | None) -> str:
    sampled_text = _build_ontology_source_excerpt(text, max_chars=_ONTOLOGY_PROMPT_MAX_CHARS)
    return (
        "Build a rich ontology for the text.\n"
        "Use the provided response schema.\n"
        "Hard constraints:\n"
        "1) At least 8 entity_types and at least 12 edge_types when the text supports them.\n"
        "2) Do not use generic placeholders like only CONCEPT/RELATED_TO.\n"
        "3) Use concrete relation names and valid source_type/target_type.\n"
        "4) Preserve narrative completeness: people, places, groups, objects, events, abilities, conflicts, motives, and temporal relations.\n"
        "5) Return only the structured result.\n\n"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Text:\n{sampled_text}"
    )


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
            max_tokens=_ONTOLOGY_MAX_TOKENS,
            prefer_stream_override=True,
            stream_fallback_nonstream_override=False,
            minimum_timeout_seconds=_ONTOLOGY_MIN_TIMEOUT_SECONDS,
            response_schema=OntologyResponse,
        )
        api_called = True
        provider_name = str(llm_result.get("provider") or "")
        input_tokens = int(llm_result.get("input_tokens") or 0)
        output_tokens = int(llm_result.get("output_tokens") or 0)
        raw_content = str(llm_result.get("content") or "")
        parsed: dict[str, Any] | None = None
        parse_error: Exception | None = None
        try:
            parsed = extract_json_object(raw_content)
        except Exception as repair_exc:
            parse_error = repair_exc

        if not parsed:
            error_code = "llm_response_not_json_or_invalid_schema"
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
                max_tokens=_ONTOLOGY_MAX_TOKENS,
                prefer_stream_override=True,
                stream_fallback_nonstream_override=False,
                minimum_timeout_seconds=_ONTOLOGY_MIN_TIMEOUT_SECONDS,
                response_schema=OntologyResponse,
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
                retry_parsed = extract_json_object(retry_content)
            except Exception as retry_exc:
                retry_parse_error = retry_exc

            if not retry_parsed:
                error_code = "retry_llm_response_not_json_or_invalid_schema"
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
            "4) Preserve concrete narrative facts: kinship, meetings, travel, residence, ownership, role changes, conflicts, promises, transformations, and cause-effect events.\n"
            "5) Keep important objects, places, factions, supernatural beings, and time points as separate nodes when they affect the story.\n"
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
