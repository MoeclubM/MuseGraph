import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import AIProviderConfig
from app.services.ai import DEFAULT_MODEL
from app.services.ai import call_llm
from app.services.llm_json import extract_json_object


def _normalize_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", (name or "").strip().upper())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:64] or "CONCEPT"


def _sanitize_ontology(data: dict[str, Any]) -> dict[str, Any]:
    entities_raw = data.get("entity_types") if isinstance(data.get("entity_types"), list) else []
    edges_raw = data.get("edge_types") if isinstance(data.get("edge_types"), list) else []

    entity_types: list[dict[str, Any]] = []
    seen_entities: set[str] = set()
    for item in entities_raw:
        if not isinstance(item, dict):
            continue
        name = _normalize_name(str(item.get("name") or ""))
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
    for item in edges_raw:
        if not isinstance(item, dict):
            continue
        name = _normalize_name(str(item.get("name") or "RELATED_TO"))
        source_type = _normalize_name(str(item.get("source_type") or "CONCEPT"))
        target_type = _normalize_name(str(item.get("target_type") or "CONCEPT"))
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

    if not entity_types:
        entity_types = [{"name": "CONCEPT", "description": "General concept", "examples": []}]
    if not edge_types:
        edge_types = [
            {
                "name": "RELATED_TO",
                "source_type": "CONCEPT",
                "target_type": "CONCEPT",
                "description": "Generic relation between concepts",
            }
        ]

    return {
        "entity_types": entity_types,
        "edge_types": edge_types,
        "analysis_summary": str(data.get("analysis_summary") or "").strip(),
    }


def _fallback_ontology(text: str, requirement: str | None = None) -> dict[str, Any]:
    lowered = (text or "").lower()
    entities: list[dict[str, Any]] = [
        {"name": "CONCEPT", "description": "Core concepts and topics in text", "examples": []}
    ]
    edges: list[dict[str, Any]] = [
        {
            "name": "RELATED_TO",
            "source_type": "CONCEPT",
            "target_type": "CONCEPT",
            "description": "General semantic relation",
        }
    ]

    keyword_map = {
        "PERSON": (" he ", " she ", "mr.", "mrs.", "dr.", "professor", "user", "people"),
        "ORGANIZATION": ("inc", "ltd", "company", "organization", "team", "group"),
        "PLACE": ("city", "country", "region", "location", "street", "province"),
        "EVENT": ("meeting", "launch", "incident", "event", "conference", "release"),
        "DATE": ("202", "january", "february", "march", "april", "may", "june"),
    }

    for name, keys in keyword_map.items():
        if any(k in lowered for k in keys):
            entities.append(
                {
                    "name": name,
                    "description": f"{name.title()} entities detected from text patterns",
                    "examples": [],
                }
            )
            edges.append(
                {
                    "name": f"{name}_RELATED_TO_CONCEPT",
                    "source_type": name,
                    "target_type": "CONCEPT",
                    "description": f"Link {name.title()} entities to concepts",
                }
            )

    summary = "Ontology generated with fallback strategy."
    if requirement:
        summary += f" Requirement considered: {requirement[:120]}"
    return {"entity_types": entities, "edge_types": edges, "analysis_summary": summary}


async def generate_ontology(
    text: str,
    db: AsyncSession,
    requirement: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    payload_text = (text or "").strip()
    if not payload_text:
        return _fallback_ontology("", requirement)

    # Pick a model from active providers first.
    try:
        result = await db.execute(
            select(AIProviderConfig).where(AIProviderConfig.is_active == True).order_by(AIProviderConfig.priority.desc())
        )
        providers = result.scalars().all()
        selected_model = (model or "").strip() or None
        for provider in providers:
            if selected_model:
                break
            if provider.models and len(provider.models) > 0:
                selected_model = provider.models[0]
                break
        if not selected_model:
            selected_model = DEFAULT_MODEL

        prompt = (
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
            f"Text:\n{payload_text[:12000]}"
        )

        llm_result = await call_llm(selected_model, prompt, db)
        parsed = extract_json_object(str(llm_result.get("content") or ""))
        if parsed:
            sanitized = _sanitize_ontology(parsed)
            if sanitized["entity_types"] and sanitized["edge_types"]:
                return sanitized
    except Exception:
        pass

    return _fallback_ontology(payload_text, requirement)


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
        return (
            "[ONTOLOGY_CONTEXT]\n"
            + json.dumps(ontology_header, ensure_ascii=False)
            + "\n[/ONTOLOGY_CONTEXT]\n\n"
            + text
        )
    except Exception:
        return text
