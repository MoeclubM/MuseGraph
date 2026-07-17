import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai import call_llm, require_structured_json_model
from app.services.llm_json import StrictJsonSchemaModel, extract_json_object


class OntologyEntityType(StrictJsonSchemaModel):
    name: str
    description: str
    examples: list[str]


class OntologyEdgeType(StrictJsonSchemaModel):
    name: str
    source_type: str
    target_type: str
    description: str


class OntologyMemoryDimension(StrictJsonSchemaModel):
    name: str
    description: str


class OntologyResponse(StrictJsonSchemaModel):
    text_type: str
    text_type_confidence: float
    text_type_reason: str
    memory_dimensions: list[OntologyMemoryDimension]
    entity_types: list[OntologyEntityType]
    edge_types: list[OntologyEdgeType]
    analysis_summary: str


_ONTOLOGY_PROMPT_MAX_CHARS = 50000
_ONTOLOGY_MIN_TIMEOUT_SECONDS = 300
_ONTOLOGY_MAX_TOKENS = 4096
_ONTOLOGY_MAX_ENTITY_TYPES = 24
_ONTOLOGY_MAX_EDGE_TYPES = 40
_ONTOLOGY_MAX_MEMORY_DIMENSIONS = 12
_TEXT_TYPE_VALUES = (
    "fiction",
    "screenplay",
    "game_lore",
    "nonfiction",
    "academic",
    "business",
    "business_report",
    "marketing",
    "product_doc",
    "resume",
    "technical",
    "poetry",
    "other",
)


def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip().upper())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:64]


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


def _normalize_text_type(value: Any) -> str:
    cleaned = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:64]


def _normalize_confidence(value: Any) -> float | None:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= confidence <= 1:
        return confidence
    return None


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


def _normalize_dimension_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = _normalize_text_type(item.get("name"))
    if not name:
        return None
    return {
        "name": name,
        "description": str(item.get("description") or "").strip(),
    }


def _normalize_ontology_payload(data: dict[str, Any]) -> dict[str, Any]:
    dimensions_raw = _pick_first_list(data, ["memory_dimensions"])
    entities_raw = _pick_first_list(data, ["entity_types"])
    edges_raw = _pick_first_list(data, ["edge_types"])

    dimensions = [normalized for normalized in (_normalize_dimension_item(item) for item in dimensions_raw) if normalized]
    entities = [normalized for normalized in (_normalize_entity_item(item) for item in entities_raw) if normalized]
    edges = [normalized for normalized in (_normalize_edge_item(item) for item in edges_raw) if normalized]

    analysis_summary = str(data.get("analysis_summary") or "").strip()

    return {
        "text_type": _normalize_text_type(data.get("text_type")),
        "text_type_confidence": _normalize_confidence(data.get("text_type_confidence")),
        "text_type_reason": str(data.get("text_type_reason") or "").strip(),
        "memory_dimensions": dimensions,
        "entity_types": entities,
        "edge_types": edges,
        "analysis_summary": analysis_summary,
    }


def _sanitize_ontology(data: dict[str, Any]) -> dict[str, Any]:
    dimensions_raw = data.get("memory_dimensions") if isinstance(data.get("memory_dimensions"), list) else []
    entities_raw = data.get("entity_types") if isinstance(data.get("entity_types"), list) else []
    edges_raw = data.get("edge_types") if isinstance(data.get("edge_types"), list) else []

    memory_dimensions: list[dict[str, Any]] = []
    seen_dimensions: set[str] = set()
    for item in dimensions_raw:
        normalized = _normalize_dimension_item(item)
        if not normalized:
            continue
        name = normalized["name"]
        if name in seen_dimensions:
            continue
        seen_dimensions.add(name)
        memory_dimensions.append(normalized)
        if len(memory_dimensions) >= _ONTOLOGY_MAX_MEMORY_DIMENSIONS:
            break

    entity_types: list[dict[str, Any]] = []
    seen_entities: set[str] = set()
    for item in entities_raw:
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("name") or "").strip()
        if not raw_name:
            continue
        name = _normalize_name(raw_name)
        if not name:
            continue
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
        if len(entity_types) >= _ONTOLOGY_MAX_ENTITY_TYPES:
            break

    edge_types: list[dict[str, Any]] = []
    valid_entity_names = {item["name"] for item in entity_types}
    seen_edges: set[tuple[str, str, str]] = set()
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
        if not name or not source_type or not target_type:
            continue
        if source_type not in valid_entity_names or target_type not in valid_entity_names:
            continue
        edge_key = (name, source_type, target_type)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        edge_types.append(
            {
                "name": name,
                "source_type": source_type,
                "target_type": target_type,
                "description": str(item.get("description") or "").strip(),
            }
        )
        if len(edge_types) >= _ONTOLOGY_MAX_EDGE_TYPES:
            break

    return {
        "text_type": _normalize_text_type(data.get("text_type")),
        "text_type_confidence": _normalize_confidence(data.get("text_type_confidence")),
        "text_type_reason": str(data.get("text_type_reason") or "").strip(),
        "memory_dimensions": memory_dimensions,
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


# Narrative / story-driven text types where a CONCEPT/RELATED_TO-only
# ontology is almost certainly too generic and should be retried.  For
# non-narrative types (technical docs, product specs, resumes, etc.) a
# minimal ontology may be appropriate and should not force a retry.
_NARRATIVE_TEXT_TYPES = frozenset({"fiction", "screenplay", "game_lore", "poetry"})


def _is_text_type_narrative(text_type: str) -> bool:
    """Return True when *text_type* is a narrative/story-driven category."""
    normalized = _normalize_text_type(text_type)
    return normalized in _NARRATIVE_TEXT_TYPES


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
    text_types = ", ".join(_TEXT_TYPE_VALUES)
    return (
        "You are an ontology architect. Read the input text and propose an ontology.\n"
        "Use the provided response schema.\n"
        f"First classify text_type as one of: {text_types}. Use lowercase snake_case.\n"
        "Set text_type_confidence from 0 to 1 and explain the decision in text_type_reason.\n"
        "Return 4-12 memory_dimensions: project-specific lanes that future writing must retrieve and update. "
        "Examples: character_state, timeline_event, relationship_change, open_thread, claim_evidence, brand_voice, audience_pain, rule_constraint, feature_spec, skill_inventory, metric_definition, system_dependency.\n"
        "Rules: 8-24 entity types, 12-40 edge types, concise names in uppercase snake case.\n"
        "Every edge source_type and target_type must refer to one of the returned entity type names.\n"
        "Derive entity types and edge types from the actual content of the text. "
        "Do not default to fiction-specific types (Person, Place, Organization) unless the text is actually narrative. "
        "Adapt the schema and memory_dimensions to the detected text_type: "
        "fiction needs characters/events/foreshadows/conflicts; "
        "nonfiction needs claims/evidence/citations/concepts; "
        "business or marketing needs products/audiences/messages/metrics; "
        "game lore needs factions/locations/items/quests/rules; "
        "product docs need features/specs/requirements/dependencies; "
        "resumes need experience/skills/education/achievements; "
        "business reports need findings/metrics/recommendations/risks; "
        "technical docs need systems/APIs/configurations/procedures.\n"
        "Prefer concrete domain relations over generic RELATED_TO, including family, location, possession, transformation, conflict, obligation, event participation, supports/refutes, cites, unlocks, depends_on, implements, configures, and reports_to when present.\n"
        "Do not add commentary.\n\n"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Text:\n{sampled_text}"
    )


def _build_retry_prompt(text: str, requirement: str | None) -> str:
    sampled_text = _build_ontology_source_excerpt(text, max_chars=_ONTOLOGY_PROMPT_MAX_CHARS)
    text_types = ", ".join(_TEXT_TYPE_VALUES)
    return (
        "Build a rich ontology for the text.\n"
        "Use the provided response schema.\n"
        "Hard constraints:\n"
        f"0) Detect text_type as one of: {text_types}; include text_type_confidence between 0 and 1 and text_type_reason.\n"
        "1) Include 4-12 memory_dimensions as project-specific retrieval/writeback lanes.\n"
        "2) At least 8 entity_types and at least 12 edge_types when the text supports them.\n"
        "3) Derive entity and edge types from the actual content; do not default to fiction-specific types for non-narrative text. "
        "A CONCEPT/RELATED_TO-only ontology is acceptable only for non-narrative text types.\n"
        "4) Use concrete relation names and valid source_type/target_type.\n"
        "5) Preserve type-specific completeness: narrative state for fiction, claim/evidence structure for nonfiction, "
        "scenario mechanics for game lore, product/audience/message structure for marketing, "
        "feature/spec structure for product docs, experience/skills structure for resumes, "
        "findings/metrics structure for business reports, system/API structure for technical docs.\n"
        "6) Return only the structured result.\n\n"
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
    selected_model = (model or "").strip()
    if not payload_text:
        raise ValueError("No source text provided for ontology generation")
    try:
        selected_model = require_structured_json_model(selected_model, "Ontology generation")
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc

    provider_name = ""
    input_tokens = 0
    output_tokens = 0
    api_called = False
    try:
        llm_result = await call_llm(
            selected_model,
            _build_ontology_prompt(payload_text, requirement),
            db,
            max_tokens=_ONTOLOGY_MAX_TOKENS,
            prefer_stream_override=True,
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
        sanitized_text_type = str(sanitized.get("text_type") or "").strip()
        # For non-narrative text types, a CONCEPT/RELATED_TO-only ontology
        # may be appropriate, so only flag it as "too generic" when the text
        # is narrative (fiction, screenplay, game_lore, poetry).
        minimal_for_narrative = (
            _is_minimal_ontology(sanitized)
            and _is_text_type_narrative(sanitized_text_type)
        )
        needs_retry = (
            minimal_for_narrative
            or not sanitized.get("memory_dimensions")
            or not sanitized.get("entity_types")
            or not sanitized.get("edge_types")
            or not sanitized_text_type
            or sanitized.get("text_type_confidence") is None
            or not str(sanitized.get("text_type_reason") or "").strip()
        )
        if needs_retry:
            retry_result = await call_llm(
                selected_model,
                _build_retry_prompt(payload_text, requirement),
                db,
                max_tokens=_ONTOLOGY_MAX_TOKENS,
                prefer_stream_override=True,
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
            if not retry_sanitized.get("memory_dimensions"):
                raise ValueError("retry_output_missing_memory_dimensions")
            if not retry_sanitized.get("entity_types") or not retry_sanitized.get("edge_types"):
                raise ValueError("retry_output_missing_valid_entity_or_edge_types")
            if _is_minimal_ontology(retry_sanitized) and _is_text_type_narrative(str(retry_sanitized.get("text_type") or "")):
                raise ValueError("retry_output_too_generic_concept_related_to")
            if not str(retry_sanitized.get("text_type") or "").strip():
                raise ValueError("retry_output_missing_text_type")
            if retry_sanitized.get("text_type_confidence") is None:
                raise ValueError("retry_output_invalid_text_type_confidence")
            if not str(retry_sanitized.get("text_type_reason") or "").strip():
                raise ValueError("retry_output_missing_text_type_reason")
            sanitized = retry_sanitized

        if not sanitized.get("memory_dimensions"):
            raise ValueError("llm_output_missing_memory_dimensions")
        if not sanitized["entity_types"] or not sanitized["edge_types"]:
            raise ValueError("llm_output_missing_valid_entity_or_edge_types")
        if _is_minimal_ontology(sanitized) and _is_text_type_narrative(str(sanitized.get("text_type") or "")):
            raise ValueError("llm_output_too_generic_concept_related_to")
        if not str(sanitized.get("text_type") or "").strip():
            raise ValueError("llm_output_missing_text_type")
        if sanitized.get("text_type_confidence") is None:
            raise ValueError("llm_output_invalid_text_type_confidence")
        if not str(sanitized.get("text_type_reason") or "").strip():
            raise ValueError("llm_output_missing_text_type_reason")

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


def build_memory_input_with_ontology(text: str, ontology: dict[str, Any] | None) -> str:
    if not ontology:
        return text
    dimensions = ontology.get("memory_dimensions") or []
    entities = ontology.get("entity_types") or []
    edges = ontology.get("edge_types") or []
    ontology_header = {
        "text_type": ontology.get("text_type"),
        "memory_dimensions": [
            {"name": d.get("name"), "description": d.get("description")}
            for d in dimensions
            if isinstance(d, dict)
        ],
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
        "[MEMORY_EXTRACTION_RULES]\n"
        "1) Use canonical names for entities. Treat aliases, abbreviations, and alternate names as references to the same entity instead of creating separate entities.\n"
        "2) Model significant occurrences (events, milestones, decisions, changes, transitions) as distinct nodes rather than attributes of other entities.\n"
        "3) Distinguish between different entity categories appropriate to the text domain; do not conflate locations with actors, concepts with instances, or containers with contents.\n"
        "4) Preserve concrete domain facts: relationships, dependencies, ownership, membership, participation, transformations, state changes, cause-effect chains, and temporal sequences.\n"
        "5) Keep important objects, places, organizations, systems, concepts, and time points as separate nodes when they affect the content.\n"
        "6) Classify extracted facts into the ontology memory_dimensions so retrieval can target the right lane.\n"
        "7) Adapt extraction depth to the text type: narrative texts benefit from character/event/relationship detail; "
        "analytical texts benefit from claim/evidence/methodology structure; "
        "technical texts benefit from system/configuration/procedure granularity; "
        "business texts benefit from stakeholder/product/metric/constraint clarity.\n"
        "[/MEMORY_EXTRACTION_RULES]\n\n"
    )
    return (
        "[ONTOLOGY_CONTEXT]\n"
        + json.dumps(ontology_header, ensure_ascii=False)
        + "\n[/ONTOLOGY_CONTEXT]\n\n"
        + extraction_rules
        + text
    )
