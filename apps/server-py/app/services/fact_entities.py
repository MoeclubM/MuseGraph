from __future__ import annotations

from typing import Any


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _entity_type_label(entity_type: str, ontology: dict[str, Any] | None) -> str:
    normalized = _normalize_text(entity_type) or "Entity"
    if not ontology:
        return normalized
    for item in ontology.get("entity_types") or []:
        if not isinstance(item, dict):
            continue
        name = _normalize_text(item.get("name"))
        if name and name.lower() == normalized.lower():
            return name
    return normalized


def _make_entity(
    *,
    entity_id: str,
    name: str,
    entity_type: str,
    summary: str = "",
    attributes: dict[str, Any] | None = None,
    source: str = "",
    fact_id: str | None = None,
    ontology: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_id = _normalize_text(entity_id) or _normalize_text(name)
    normalized_name = _normalize_text(name) or normalized_id
    normalized_type = _entity_type_label(entity_type, ontology)
    if not normalized_id:
        return {}
    return {
        "id": normalized_id,
        "name": normalized_name,
        "type": normalized_type,
        "summary": _normalize_text(summary),
        "attributes": dict(attributes or {}),
        "source": _normalize_text(source),
        "fact_id": fact_id,
    }


def _append_entity(bucket: dict[str, dict[str, Any]], entity: dict[str, Any]) -> None:
    if not entity:
        return
    entity_id = _normalize_text(entity.get("id"))
    if not entity_id:
        return
    existing = bucket.get(entity_id)
    if existing is None:
        bucket[entity_id] = entity
        return
    merged_attrs = dict(existing.get("attributes") or {})
    merged_attrs.update(entity.get("attributes") or {})
    existing["attributes"] = merged_attrs
    if entity.get("summary") and not existing.get("summary"):
        existing["summary"] = entity["summary"]
    if entity.get("source") and entity["source"] not in str(existing.get("source") or ""):
        existing["source"] = ", ".join(
            part for part in [str(existing.get("source") or "").strip(), str(entity.get("source") or "").strip()] if part
        )


def _entities_from_structured_value(
    key: str,
    value: Any,
    *,
    ontology: dict[str, Any] | None,
    source: str,
) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict):
                entity_type = _normalize_text(item.get("type") or item.get("kind") or key) or key
                entity = _make_entity(
                    entity_id=_normalize_text(item.get("id") or item.get("name") or f"{key}-{index}"),
                    name=_normalize_text(item.get("name") or item.get("title") or item.get("id") or f"{key}-{index}"),
                    entity_type=entity_type,
                    summary=_normalize_text(item.get("summary") or item.get("description") or item.get("content")),
                    attributes={k: v for k, v in item.items() if k not in {"id", "name", "title", "type", "kind", "summary", "description", "content"}},
                    source=source,
                    ontology=ontology,
                )
                if entity:
                    entities.append(entity)
            elif item not in (None, ""):
                entities.append(
                    _make_entity(
                        entity_id=f"{key}-{index}",
                        name=str(item),
                        entity_type=key,
                        source=source,
                        ontology=ontology,
                    )
                )
    elif isinstance(value, dict):
        if any(k in value for k in ("id", "name", "title", "type")):
            entity_type = _normalize_text(value.get("type") or value.get("kind") or key) or key
            entity = _make_entity(
                entity_id=_normalize_text(value.get("id") or value.get("name") or key),
                name=_normalize_text(value.get("name") or value.get("title") or value.get("id") or key),
                entity_type=entity_type,
                summary=_normalize_text(value.get("summary") or value.get("description")),
                attributes={k: v for k, v in value.items() if k not in {"id", "name", "title", "type", "kind", "summary", "description"}},
                source=source,
                ontology=ontology,
            )
            if entity:
                entities.append(entity)
        else:
            for nested_key, nested_value in value.items():
                entities.extend(
                    _entities_from_structured_value(
                        str(nested_key),
                        nested_value,
                        ontology=ontology,
                        source=source,
                    )
                )
    return entities


def collect_project_entities(
    *,
    facts: list[Any],
    ontology: dict[str, Any] | None = None,
    structured_memory: dict[str, Any] | None = None,
    fact_graph: dict[str, Any] | None = None,
    memory_schema: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    bucket: dict[str, dict[str, Any]] = {}

    for fact in facts:
        fact_id = _normalize_text(getattr(fact, "id", "")) or None
        fact_title = _normalize_text(getattr(fact, "title", ""))
        for entity in getattr(fact, "entities", None) or []:
            if not isinstance(entity, dict):
                continue
            record = _make_entity(
                entity_id=_normalize_text(entity.get("id") or entity.get("name")),
                name=_normalize_text(entity.get("name") or entity.get("id")),
                entity_type=_normalize_text(entity.get("type") or "Entity"),
                summary=_normalize_text(entity.get("summary")),
                attributes={k: v for k, v in entity.items() if k not in {"id", "name", "type", "summary"}},
                source=f"fact:{fact_title or fact_id or 'unknown'}",
                fact_id=fact_id,
                ontology=ontology,
            )
            _append_entity(bucket, record)

    for node in (fact_graph or {}).get("nodes") or []:
        if not isinstance(node, dict):
            continue
        record = _make_entity(
            entity_id=_normalize_text(node.get("id") or node.get("name")),
            name=_normalize_text(node.get("name") or node.get("label") or node.get("id")),
            entity_type=_normalize_text(node.get("type") or "Entity"),
            summary=_normalize_text(node.get("summary") or node.get("description")),
            attributes={k: v for k, v in node.items() if k not in {"id", "name", "label", "type", "summary", "description"}},
            source="fact_graph",
            ontology=ontology,
        )
        _append_entity(bucket, record)

    for key, value in (structured_memory or {}).items():
        for entity in _entities_from_structured_value(str(key), value, ontology=ontology, source="structured_memory"):
            _append_entity(bucket, entity)

    for key, value in (memory_schema or {}).items():
        if key in {"entity_types", "edge_types", "text_type", "analysis_summary"}:
            continue
        for entity in _entities_from_structured_value(str(key), value, ontology=ontology, source="memory_schema"):
            _append_entity(bucket, entity)

    return sorted(bucket.values(), key=lambda item: (str(item.get("type") or ""), str(item.get("name") or "")))


def group_entities_by_type(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        entity_type = _normalize_text(entity.get("type")) or "Entity"
        groups.setdefault(entity_type, []).append(entity)
    return [
        {
            "type": entity_type,
            "label": entity_type,
            "count": len(items),
            "entities": sorted(items, key=lambda item: str(item.get("name") or "")),
        }
        for entity_type, items in sorted(groups.items(), key=lambda pair: pair[0].lower())
    ]


def search_project_entities(
    entities: list[dict[str, Any]],
    *,
    query: str,
    entity_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    needle = _normalize_text(query).lower()
    if not needle:
        return []
    type_filter = _normalize_text(entity_type).lower() if entity_type else ""
    matches: list[tuple[int, dict[str, Any]]] = []
    for entity in entities:
        if type_filter and _normalize_text(entity.get("type")).lower() != type_filter:
            continue
        haystacks = [
            _normalize_text(entity.get("name")),
            _normalize_text(entity.get("id")),
            _normalize_text(entity.get("type")),
            _normalize_text(entity.get("summary")),
            _normalize_text(entity.get("source")),
        ]
        haystacks.extend(_normalize_text(value) for value in (entity.get("attributes") or {}).values())
        joined = " ".join(part for part in haystacks if part).lower()
        if needle not in joined:
            continue
        score = 0
        name = _normalize_text(entity.get("name")).lower()
        if name == needle:
            score += 100
        elif name.startswith(needle):
            score += 60
        elif needle in name:
            score += 40
        if needle in _normalize_text(entity.get("summary")).lower():
            score += 10
        matches.append((score, entity))
    matches.sort(key=lambda pair: (-pair[0], str(pair[1].get("name") or "")))
    return [entity for _, entity in matches[: max(1, min(limit, 100))]]


def merge_structured_memory(base: dict[str, Any] | None, patch: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged
