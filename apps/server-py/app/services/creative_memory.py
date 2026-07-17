"""Universal creative memory assembly.

This module builds one typed memory packet for all writing operations. It keeps
dynamic cognee retrieval, structured project memory, reference cards,
ontology, and stored analysis in one place so operation prompts do not depend
on a single retrieval-only path or on static "dump every card" context.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectChapter, TextProject
from app.services.creative_workflow import (
    build_workflow_memory,
    chapter_has_memory_material,
    chapter_memory_hash,
    project_creative_state_hash,
    project_creative_state_text,
    render_workflow_memory,
)


DYNAMIC_MEMORY_KEYS = (
    "typed_insights",
    "relationships",
    "continuity_state",
    "source_evidence",
    "summaries",
    "generation_hints",
    "style_voice",
)

MEMORY_REQUIRED_OPERATIONS = {
    "AGENT_TASK",
    "AGENT_SUGGEST",
    "CONTINUE",
    "CONSISTENCY_CHECK",
    "REWRITE",
    "SUMMARIZE",
}


TEXT_TYPE_STRATEGIES: dict[str, dict[str, Any]] = {
    "fiction": {
        "label": "Fiction / narrative prose",
        "retrieval_focus": "characters, relationships, events, timeline, conflicts, foreshadowing, causal consequences, current states",
        "rules": [
            "Respect established character state, relationship direction, timeline, secrets, promises, and unresolved conflict.",
            "Use retrieved events as continuity anchors; new beats must follow the known causal chain.",
            "Style memory matters: preserve voice, pacing, emotional temperature, and recurring motifs.",
        ],
    },
    "screenplay": {
        "label": "Screenplay / script",
        "retrieval_focus": "characters, scenes, beats, dialogue dynamics, locations, timeline, conflicts, reveals",
        "rules": [
            "Preserve scene logic, character objectives, dialogue subtext, and visual continuity.",
            "Use retrieved beats and relationships to choose the next scene action.",
        ],
    },
    "game_lore": {
        "label": "Game lore / interactive world",
        "retrieval_focus": "factions, locations, items, quests, rules, mechanics, history, dependencies, player-facing consequences",
        "rules": [
            "Respect world rules, faction incentives, item constraints, quest state, and location history.",
            "Prefer actionable lore hooks that can drive gameplay or future content.",
        ],
    },
    "nonfiction": {
        "label": "Nonfiction / explanatory writing",
        "retrieval_focus": "claims, evidence, examples, definitions, counterpoints, chronology, conclusions",
        "rules": [
            "Separate claim, evidence, example, and interpretation; do not treat unsupported inference as fact.",
            "Keep terminology and definitions stable across the output.",
        ],
    },
    "academic": {
        "label": "Academic / research writing",
        "retrieval_focus": "claims, evidence, citations, terminology, methodology, assumptions, limitations, counterarguments",
        "rules": [
            "Preserve citation boundaries and distinguish cited evidence from analysis.",
            "Track definitions, assumptions, methodology, and limitations explicitly.",
        ],
    },
    "business": {
        "label": "Business / strategy writing",
        "retrieval_focus": "products, stakeholders, audiences, value propositions, risks, metrics, decisions, constraints",
        "rules": [
            "Keep audience, objective, metric, constraint, and decision state explicit.",
            "Do not blur product facts, strategic assumptions, and messaging recommendations.",
        ],
    },
    "marketing": {
        "label": "Marketing / brand writing",
        "retrieval_focus": "audience, product, pain points, benefits, proof points, objections, brand voice, channel, conversion goal",
        "rules": [
            "Preserve brand voice, audience segment, promise, proof, objections, and conversion goal.",
            "Use retrieved constraints to avoid off-brand or unsupported claims.",
        ],
    },
    "poetry": {
        "label": "Poetry / lyrical prose",
        "retrieval_focus": "themes, images, motifs, emotion, rhythm, voice, symbolic relationships",
        "rules": [
            "Treat relationships as thematic, imagistic, and emotional unless the source makes them factual.",
            "Prioritize motif continuity, rhythm, voice, and emotional progression.",
        ],
    },
    "product_doc": {
        "label": "Product documentation / specifications",
        "retrieval_focus": "products, features, specifications, requirements, user stories, acceptance criteria, versions, compatibility, dependencies, known issues, release notes",
        "rules": [
            "Maintain specification accuracy; distinguish must-have, should-have, and nice-to-have requirements.",
            "Track version changes, compatibility constraints, and dependency relationships between features.",
        ],
    },
    "resume": {
        "label": "Resume / CV / professional profile",
        "retrieval_focus": "candidate, experience, skills, education, achievements, certifications, projects, metrics, keywords, target role",
        "rules": [
            "Preserve factual accuracy of dates, titles, organizations, and quantifiable achievements.",
            "Maintain consistent formatting, tense, and keyword alignment with the target role or industry.",
        ],
    },
    "business_report": {
        "label": "Business report / analysis",
        "retrieval_focus": "findings, data, analysis, recommendations, stakeholders, metrics, assumptions, risks, conclusions, methodology, appendices",
        "rules": [
            "Separate data, analysis, interpretation, and recommendation; do not conflate correlation with causation.",
            "Preserve metric definitions, data sources, time ranges, and assumption boundaries across sections.",
        ],
    },
    "technical": {
        "label": "Technical documentation / reference",
        "retrieval_focus": "systems, APIs, configurations, procedures, dependencies, error handling, prerequisites, parameters, constraints, version requirements",
        "rules": [
            "Preserve technical accuracy, parameter names, types, defaults, and constraint boundaries.",
            "Maintain consistent terminology and cross-reference integrity between procedures, APIs, and configuration entries.",
        ],
    },
    "other": {
        "label": "General creative writing",
        "retrieval_focus": "entities, concepts, events, definitions, constraints, style, goals, unresolved questions",
        "rules": [
            "Use retrieved memory as project facts and constraints.",
            "Keep terminology, relationships, and style consistent with the source.",
        ],
    },
}

OPERATION_FOCUS: dict[str, str] = {
    "CREATE": "creation goal, required constraints, reusable world or concept anchors, target style",
    "CONTINUE": "current state, next logical step, unresolved threads, continuity hazards, style anchors",
    "AGENT_TASK": "user intent, text type, reusable structure, domain entities, relationships, retrieval plan, graph facts, writing deliverable",
    "AGENT_SUGGEST": "current cursor context, next likely continuation, consistency risks, style anchors, relevant memory evidence, insertable text",
    "CONSISTENCY_CHECK": "contradictions, factual conflicts, sequence conflicts, terminology drift, relationship conflicts, unresolved requirements",
    "ANALYZE": "structure, relationships, claims, evidence, gaps, contradictions, implications",
    "REWRITE": "facts to preserve, constraints, terminology, voice, style, relationship/state consistency",
    "SUMMARIZE": "core facts, hierarchy, timeline, claims, decisions, conclusions, unresolved items",
}



def _truncate(value: str | None, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 3)] + "..."


def _normalize_match_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _query_tokens(value: str | None) -> list[str]:
    query = _normalize_match_text(value)
    if not query:
        return []
    tokens = re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{1,8}", query)
    rows: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        rows.append(token)
        if len(rows) >= 96:
            break
    return rows


def _safe_str_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        rows.append(text)
        if len(rows) >= limit:
            break
    return rows


def _score_text_match(*, query_norm: str, tokens: list[str], values: list[str]) -> int:
    haystack = _normalize_match_text(" ".join(str(value or "") for value in values))
    if not haystack:
        return 0
    score = 0
    for value in values:
        current = _normalize_match_text(value)
        if current and query_norm and current in query_norm:
            score += 6
    for token in tokens:
        if token in haystack:
            score += 1
    return score


def _pick_ranked_items(
    *,
    items: list[dict[str, Any]],
    id_field: str,
    explicit_ids: list[str],
    query_norm: str,
    query_tokens: list[str],
    text_fields: list[str],
    limit: int,
    empty_focus_count: int,
) -> list[dict[str, Any]]:
    explicit_order: list[str] = []
    explicit_seen: set[str] = set()
    for raw in explicit_ids:
        item_id = str(raw or "").strip()
        if not item_id or item_id in explicit_seen:
            continue
        explicit_seen.add(item_id)
        explicit_order.append(item_id)

    item_map: dict[str, dict[str, Any]] = {}
    ranked: list[tuple[int, int, str, dict[str, Any]]] = []
    for index, item in enumerate(items):
        item_id = str(item.get(id_field) or "").strip()
        if not item_id:
            continue
        item_map[item_id] = item
        score = _score_text_match(
            query_norm=query_norm,
            tokens=query_tokens,
            values=[str(item.get(field) or "") for field in text_fields],
        )
        if item_id in explicit_seen:
            score += 200
        ranked.append((score, index, item_id, item))

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for item_id in explicit_order:
        item = item_map.get(item_id)
        if not item:
            continue
        selected.append(item)
        selected_ids.add(item_id)
        if len(selected) >= limit:
            return selected

    if not query_norm:
        target_count = min(limit, max(empty_focus_count, len(selected)))
        for _score, _index, item_id, item in ranked:
            if item_id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(item_id)
            if len(selected) >= target_count:
                break
        return selected

    ranked.sort(key=lambda row: (-row[0], row[1]))
    for score, _index, item_id, item in ranked:
        if item_id in selected_ids:
            continue
        if query_norm and score <= 0:
            continue
        selected.append(item)
        selected_ids.add(item_id)
        if len(selected) >= limit:
            break

    if selected:
        return selected
    return []


def _resolve_text_type(project: TextProject) -> str:
    raw_ontology = getattr(project, "ontology_schema", None)
    ontology = raw_ontology if isinstance(raw_ontology, dict) else {}
    text_type = str(ontology.get("text_type") or "").strip().lower()
    return text_type if text_type in TEXT_TYPE_STRATEGIES else "other"


def _ontology_memory(ontology: dict[str, Any]) -> dict[str, Any]:
    memory_dimensions = []
    for item in ontology.get("memory_dimensions") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        desc = str(item.get("description") or "").strip()
        memory_dimensions.append(f"{name}" + (f": {desc}" if desc else ""))

    entity_types = []
    for item in ontology.get("entity_types") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        desc = str(item.get("description") or "").strip()
        entity_types.append(f"{name}" + (f": {desc}" if desc else ""))

    edge_types = []
    for item in ontology.get("edge_types") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        source = str(item.get("source_type") or "").strip()
        target = str(item.get("target_type") or "").strip()
        desc = str(item.get("description") or "").strip()
        direction = f" ({source} -> {target})" if source or target else ""
        edge_types.append(f"{name}{direction}" + (f": {desc}" if desc else ""))

    return {
        "text_type": str(ontology.get("text_type") or "").strip(),
        "text_type_confidence": ontology.get("text_type_confidence"),
        "text_type_reason": str(ontology.get("text_type_reason") or "").strip(),
        "analysis_summary": str(ontology.get("analysis_summary") or "").strip(),
        "memory_dimensions": memory_dimensions[:16],
        "entity_types": entity_types[:24],
        "edge_types": edge_types[:32],
    }


def _creative_state_text(project: TextProject) -> str:
    state = getattr(project, "creative_state", None)
    if not isinstance(state, dict) or not state:
        return ""
    return json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)


def _creative_state_ledger(project: TextProject) -> dict[str, Any]:
    """Build a state ledger from agent_workspace.structured_memory, dynamically.
    Every non-empty key becomes a ledger section; no text-type assumptions."""
    state = getattr(project, "creative_state", None)
    if not isinstance(state, dict) or not state:
        return {"sections": [], "query_text": ""}
    ws = state.get("agent_workspace") if isinstance(state.get("agent_workspace"), dict) else {}
    sm = ws.get("structured_memory") if isinstance(ws.get("structured_memory"), dict) else {}
    sections = []
    for key, value in sm.items():
        if value in (None, "", [], {}):
            continue
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        sections.append({"key": key, "label": key, "text": _truncate(text, 900)})
    for k in ("text_type", "task_kind"):
        v = ws.get(k)
        if v and isinstance(v, str) and v.strip():
            sections.append({"key": k, "label": k, "text": v.strip()})
    return {
        "sections": sections,
        "query_text": _truncate(
            "\n".join(f"{item['label']}: {item['text']}" for item in sections),
            4200,
        ),
    }


def build_reference_memory(reference_cards: dict[str, Any] | None, *, focus_text: str) -> dict[str, Any]:
    query_norm = _normalize_match_text(focus_text)
    query_tokens = _query_tokens(focus_text)
    cards = reference_cards if isinstance(reference_cards, dict) else {}

    raw_characters = [item for item in cards.get("characters") or [] if isinstance(item, dict)]
    raw_glossary = [dict(item) for item in cards.get("glossary_terms") or [] if isinstance(item, dict)]
    raw_worldbook = [dict(item) for item in cards.get("worldbook_entries") or [] if isinstance(item, dict)]
    for row in raw_glossary:
        row["alias_text"] = " ".join(_safe_str_list(row.get("aliases"), limit=20))
    for row in raw_worldbook:
        row["tag_text"] = " ".join(_safe_str_list(row.get("tags"), limit=20))

    characters = _pick_ranked_items(
        items=raw_characters,
        id_field="id",
        explicit_ids=_safe_str_list(cards.get("explicit_character_ids"), limit=128),
        query_norm=query_norm,
        query_tokens=query_tokens,
        text_fields=["name", "role", "profile", "notes"],
        limit=8,
        empty_focus_count=4,
    )
    glossary_terms = _pick_ranked_items(
        items=raw_glossary,
        id_field="id",
        explicit_ids=_safe_str_list(cards.get("explicit_glossary_term_ids"), limit=256),
        query_norm=query_norm,
        query_tokens=query_tokens,
        text_fields=["term", "alias_text", "definition", "notes"],
        limit=14,
        empty_focus_count=8,
    )
    worldbook_entries = _pick_ranked_items(
        items=raw_worldbook,
        id_field="id",
        explicit_ids=_safe_str_list(cards.get("explicit_worldbook_entry_ids"), limit=256),
        query_norm=query_norm,
        query_tokens=query_tokens,
        text_fields=["title", "category", "tag_text", "content", "notes"],
        limit=10,
        empty_focus_count=6,
    )

    query_terms: list[str] = []
    alias_expansions: list[str] = []
    seen_terms: set[str] = set()
    seen_aliases: set[str] = set()

    character_lines: list[str] = []
    for row in characters:
        name = _truncate(row.get("name"), 120)
        if not name:
            continue
        detail = " | ".join(
            value
            for value in [
                _truncate(row.get("role"), 80),
                _truncate(row.get("profile"), 180),
                _truncate(row.get("notes"), 140),
            ]
            if value
        )
        character_lines.append(f"- {name}" + (f": {detail}" if detail else ""))
        if name not in seen_terms:
            seen_terms.add(name)
            query_terms.append(name)

    glossary_lines: list[str] = []
    for row in glossary_terms:
        term = _truncate(row.get("term"), 120)
        if not term:
            continue
        aliases = _safe_str_list(row.get("aliases"), limit=10)
        parts = [f"- {term}"]
        if aliases:
            parts.append(f"aliases: {_truncate(', '.join(aliases), 140)}")
        definition = _truncate(row.get("definition"), 220)
        if definition:
            parts.append(f"definition: {definition}")
        notes = _truncate(row.get("notes"), 140)
        if notes:
            parts.append(f"notes: {notes}")
        glossary_lines.append(" | ".join(parts))
        if term not in seen_terms:
            seen_terms.add(term)
            query_terms.append(term)
        for alias in aliases:
            alias_norm = _normalize_match_text(alias)
            if alias_norm and query_norm and alias_norm in query_norm:
                expansion = f"{alias} -> {term}"
                if expansion not in seen_aliases:
                    seen_aliases.add(expansion)
                    alias_expansions.append(expansion)

    worldbook_lines: list[str] = []
    for row in worldbook_entries:
        title = _truncate(row.get("title"), 140)
        if not title:
            continue
        tags = _safe_str_list(row.get("tags"), limit=12)
        parts = [f"- {title}"]
        category = _truncate(row.get("category"), 80)
        if category:
            parts.append(f"category: {category}")
        if tags:
            parts.append(f"tags: {_truncate(', '.join(tags), 140)}")
        content = _truncate(row.get("content"), 260)
        if content:
            parts.append(f"content: {content}")
        notes = _truncate(row.get("notes"), 140)
        if notes:
            parts.append(f"notes: {notes}")
        worldbook_lines.append(" | ".join(parts))
        for value in [title, *tags[:6]]:
            if value and value not in seen_terms:
                seen_terms.add(value)
                query_terms.append(value)

    return {
        "characters": character_lines,
        "glossary_terms": glossary_lines,
        "worldbook_entries": worldbook_lines,
        "query_terms": query_terms[:40],
        "alias_expansions": alias_expansions[:20],
    }


def _reference_hint(reference_memory: dict[str, Any]) -> str:
    rows: list[str] = []
    terms = _safe_str_list(reference_memory.get("query_terms"), limit=40)
    aliases = _safe_str_list(reference_memory.get("alias_expansions"), limit=20)
    if terms:
        rows.append("Anchors: " + ", ".join(terms))
    if aliases:
        rows.append("Alias normalization: " + "; ".join(aliases))
    return _truncate("\n".join(rows), 1200)


def _build_query_plan(
    *,
    text_type: str,
    op_type: str,
    focus_text: str,
    creative_state_hint: str,
    reference_memory: dict[str, Any],
    ontology_memory: dict[str, Any],
    workflow_memory: dict[str, Any],
) -> list[dict[str, Any]]:
    strategy = TEXT_TYPE_STRATEGIES[text_type]
    operation_focus = OPERATION_FOCUS.get(op_type, OPERATION_FOCUS["ANALYZE"])
    focus = _truncate(focus_text, 900)
    anchors = ", ".join(_safe_str_list(reference_memory.get("query_terms"), limit=16))
    memory_dimensions = ", ".join(_safe_str_list(ontology_memory.get("memory_dimensions"), limit=12))
    ontology_entities = ", ".join(_safe_str_list(ontology_memory.get("entity_types"), limit=12))
    workflow_step = str(workflow_memory.get("workflow_step") or "").strip()
    latest = workflow_memory.get("latest_content_chapter") if isinstance(workflow_memory.get("latest_content_chapter"), dict) else {}
    next_planned = workflow_memory.get("next_planned_chapter") if isinstance(workflow_memory.get("next_planned_chapter"), dict) else {}
    target_chapters = [
        item
        for item in workflow_memory.get("target_chapters") or []
        if isinstance(item, dict) and item.get("title")
    ]
    workflow_hint = "; ".join(
        item
        for item in [
            f"workflow_step={workflow_step}" if workflow_step else "",
            f"written_chapters={workflow_memory.get('written_chapter_count')}/{workflow_memory.get('chapter_count')}",
            "targets=" + ", ".join(str(item.get("title")) for item in target_chapters[:4]) if target_chapters else "",
            f"latest={latest.get('title')}" if latest.get("title") else "",
            f"next_planned={next_planned.get('title')}" if next_planned.get("title") else "",
        ]
        if item
    )
    retrieval_focus = strategy["retrieval_focus"]
    base = "\n".join(
        item
        for item in [
            focus,
            f"Operation focus: {operation_focus}",
            f"Text type focus: {retrieval_focus}",
            f"Reference anchors: {anchors}" if anchors else "",
            f"Creative state: {_truncate(creative_state_hint, 900)}" if creative_state_hint else "",
            f"Memory dimensions: {memory_dimensions}" if memory_dimensions else "",
            f"Ontology entities: {ontology_entities}" if ontology_entities else "",
            f"Workflow state: {workflow_hint}" if workflow_hint else "",
        ]
        if item
    )
    return [
        {
            "lane": "typed_insights",
            "search_type": "INSIGHTS",
            "query": _truncate(f"{base}\nFind decisive facts, constraints, and implications.", 1800),
            "top_k": 8,
        },
        {
            "lane": "relationships",
            "search_type": "MEMORY_COMPLETION",
            "query": _truncate(f"{base}\nRecover relations, dependencies, states, timeline, and causality.", 1800),
            "top_k": 8,
        },
        {
            "lane": "continuity_state",
            "search_type": "MEMORY_COMPLETION",
            "query": _truncate(
                f"{base}\nRecover latest character states, reader/character knowledge boundaries, open loops, unresolved conflicts, promises, secrets, and continuity hazards.",
                1800,
            ),
            "top_k": 8,
        },
        {
            "lane": "source_evidence",
            "search_type": "CHUNKS",
            "query": _truncate(f"{base}\nRetrieve source passages that prove or constrain the operation.", 1800),
            "top_k": 10,
        },
        {
            "lane": "summaries",
            "search_type": "SUMMARIES",
            "query": _truncate(f"{base}\nRetrieve compact project summaries and state snapshots.", 1800),
            "top_k": 6,
        },
        {
            "lane": "generation_hints",
            "search_type": "RAG_COMPLETION",
            "query": _truncate(f"{base}\nReturn continuation or execution hints grounded in memory.", 1800),
            "top_k": 4,
        },
        {
            "lane": "style_voice",
            "search_type": "INSIGHTS",
            "query": _truncate(f"{base}\nRetrieve style, voice, pacing, motif, format, and genre execution anchors.", 1800),
            "top_k": 4,
        },
    ]


def _normalize_search_rows(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        raise TypeError("Memory search returned non-list result")
    out: list[str] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            raise TypeError("Memory search returned non-object row")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        row_type = str(item.get("type") or "").strip()
        rendered = f"[{row_type}] {content}" if row_type else content
        rendered = _truncate(rendered, 460)
        key = _normalize_match_text(rendered)
        if key in seen:
            continue
        seen.add(key)
        out.append(rendered)
    return out


async def _project_has_persisted_text(project_id: str, project: TextProject, db: AsyncSession) -> bool:
    raw_chapters = getattr(project, "__dict__", {}).get("chapters")
    if isinstance(raw_chapters, list):
        for chapter in raw_chapters:
            if str(getattr(chapter, "content", "") or "").strip():
                return True
        return False

    result = await db.execute(
        select(ProjectChapter.id)
        .where(ProjectChapter.project_id == project_id)
        .where(ProjectChapter.content.is_not(None))
        .where(func.length(func.trim(ProjectChapter.content)) > 0)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _memory_build_hashes(project: TextProject) -> dict[str, str]:
    creative_state = getattr(project, "creative_state", None)
    if not isinstance(creative_state, dict):
        return {}
    state = creative_state.get("memory_build_state")
    if not isinstance(state, dict):
        return {}
    raw_hashes = state.get("chapter_hashes")
    if not isinstance(raw_hashes, dict):
        return {}
    hashes: dict[str, str] = {}
    for key, value in raw_hashes.items():
        chapter_id = str(key or "").strip()
        content_hash = str(value or "").strip()
        if chapter_id and content_hash:
            hashes[chapter_id] = content_hash
    return hashes


async def _current_chapter_hashes(
    project_id: str,
    project: TextProject,
    db: AsyncSession,
    *,
    include_creative_state: bool = True,
) -> dict[str, str]:
    raw_chapters = getattr(project, "__dict__", {}).get("chapters")
    if isinstance(raw_chapters, list):
        hashes = {
            str(getattr(chapter, "id", "") or "").strip(): chapter_memory_hash(chapter)
            for chapter in raw_chapters
            if str(getattr(chapter, "id", "") or "").strip()
            and chapter_has_memory_material(chapter)
        }
        if include_creative_state and project_creative_state_text(project):
            hashes["__creative_state__"] = project_creative_state_hash(project)
        return hashes

    result = await db.execute(
        select(ProjectChapter)
        .where(ProjectChapter.project_id == project_id)
    )
    hashes = {
        str(chapter.id): chapter_memory_hash(chapter)
        for chapter in result.scalars().all()
        if str(chapter.id or "").strip() and chapter_has_memory_material(chapter)
    }
    if include_creative_state and project_creative_state_text(project):
        hashes["__creative_state__"] = project_creative_state_hash(project)
    return hashes


async def _assert_fresh_project_memory(
    project_id: str,
    project: TextProject,
    db: AsyncSession,
    *,
    include_creative_state: bool = True,
) -> None:
    ignored_hash_keys = {"__manual__"}
    if not include_creative_state:
        ignored_hash_keys.add("__creative_state__")
    previous_hashes = {
        chapter_id: content_hash
        for chapter_id, content_hash in _memory_build_hashes(project).items()
        if chapter_id not in ignored_hash_keys
    }
    if not previous_hashes:
        raise RuntimeError("Cognee project memory is stale: chapter baseline is missing. Rebuild project memory before writing.")

    current_hashes = await _current_chapter_hashes(
        project_id,
        project,
        db,
        include_creative_state=include_creative_state,
    )
    missing = sorted(chapter_id for chapter_id in current_hashes.keys() if chapter_id not in previous_hashes)
    removed = sorted(chapter_id for chapter_id in previous_hashes.keys() if chapter_id not in current_hashes)
    modified = sorted(
        chapter_id
        for chapter_id, content_hash in current_hashes.items()
        if chapter_id in previous_hashes and previous_hashes[chapter_id] != content_hash
    )
    if missing or removed or modified:
        if modified or removed:
            raise RuntimeError(
                "Cognee project memory is stale after edited or removed chapters; rebuild before writing. "
                f"added={len(missing)} modified={len(modified)} removed={len(removed)}"
            )
        raise RuntimeError(
            "Cognee project memory is stale after newly added chapters; run incremental memory sync or rebuild before writing. "
            f"added={len(missing)} modified={len(modified)} removed={len(removed)}"
        )


def _dynamic_memory_has_rows(memory: dict[str, Any]) -> bool:
    if str(memory.get("retrieval_context") or "").strip():
        return True
    for key in DYNAMIC_MEMORY_KEYS:
        if isinstance(memory.get(key), list) and memory[key]:
            return True
    return False


async def build_creative_memory_pack(
    *,
    project: TextProject,
    project_id: str,
    op_type: str,
    input_text: str,
    db: AsyncSession,
    reference_cards: dict[str, Any] | None = None,
    workflow_step: str | None = None,
) -> dict[str, Any]:
    normalized_op = (op_type or "").upper()
    raw_ontology = getattr(project, "ontology_schema", None)
    ontology = raw_ontology if isinstance(raw_ontology, dict) else {}
    text_type = _resolve_text_type(project)
    strategy = TEXT_TYPE_STRATEGIES[text_type]
    ontology_block = _ontology_memory(ontology)
    reference_memory = build_reference_memory(reference_cards, focus_text=input_text)
    target_chapter_ids = _safe_str_list(
        (reference_cards if isinstance(reference_cards, dict) else {}).get("explicit_chapter_ids"),
        limit=32,
    )
    workflow_memory = build_workflow_memory(
        project,
        workflow_step=workflow_step,
        target_chapter_ids=target_chapter_ids,
    )
    creative_state_text = _creative_state_text(project)
    creative_state_ledger = _creative_state_ledger(project)
    creative_state_hint = str(creative_state_ledger.get("query_text") or creative_state_text)
    query_plan = _build_query_plan(
        text_type=text_type,
        op_type=normalized_op,
        focus_text=input_text,
        creative_state_hint=creative_state_hint,
        reference_memory=reference_memory,
        ontology_memory=ontology_block,
        workflow_memory=workflow_memory,
    )

    memory_id = str(getattr(project, "memory_id", "") or "").strip()
    has_persisted_text = await _project_has_persisted_text(project_id, project, db)
    has_creative_state = bool(creative_state_text)
    require_dynamic_memory = bool(
        isinstance(reference_cards, dict)
        and reference_cards.get("require_dynamic_memory") is True
    )
    skip_dynamic_memory = bool(
        isinstance(reference_cards, dict)
        and reference_cards.get("skip_dynamic_memory") is True
    )
    if require_dynamic_memory and skip_dynamic_memory:
        raise RuntimeError("skip_dynamic_memory cannot be combined with require_dynamic_memory.")
    # AGENT_TASK plans/builds memory via tools by default. Long-form generation
    # passes require_dynamic_memory=True so planning/drafting cannot silently run
    # without cognee retrieval.
    if normalized_op == "AGENT_TASK":
        requires_fresh_memory = require_dynamic_memory and has_persisted_text
    else:
        requires_fresh_memory = has_persisted_text or (
            has_creative_state and normalized_op in MEMORY_REQUIRED_OPERATIONS
        )
    dynamic_memory: dict[str, Any] = {
        "enabled": bool(memory_id) and not skip_dynamic_memory,
        "skipped": skip_dynamic_memory,
        "retrieval_context": "",
    }
    for key in DYNAMIC_MEMORY_KEYS:
        dynamic_memory[key] = []
    if requires_fresh_memory:
        if normalized_op == "CREATE":
            raise RuntimeError("CREATE is not allowed after persisted project text exists. Use CONTINUE or REWRITE.")
        if not memory_id:
            raise RuntimeError("Cognee project memory is required before running writing operations on established project state.")
        await _assert_fresh_project_memory(
            project_id,
            project,
            db,
            include_creative_state=normalized_op != "AGENT_TASK",
        )

    if require_dynamic_memory and not memory_id:
        raise RuntimeError("Cognee dynamic retrieval is required for this Agent task.")

    if memory_id and not skip_dynamic_memory:
        from app.services import memory_backend

        memory_query = _truncate(
            query_plan[1]["query"] + "\n" + _reference_hint(reference_memory),
            2200,
        )
        retrieved = await memory_backend.retrieve(
            project_id=project_id,
            project=project,
            query_plan=query_plan,
            context_query=memory_query,
            db=db,
        )
        for key in DYNAMIC_MEMORY_KEYS:
            dynamic_memory[key] = _normalize_search_rows(retrieved.get(key))
        dynamic_memory["retrieval_context"] = _truncate(str(retrieved.get("retrieval_context") or "").strip(), 2400)
        if (requires_fresh_memory or require_dynamic_memory) and not _dynamic_memory_has_rows(dynamic_memory):
            raise RuntimeError("Cognee retrieval returned no dynamic memory for a project with established project state.")

    return {
        "text_type": text_type,
        "text_type_label": strategy["label"],
        "operation": normalized_op,
        "retrieval_strategy": {
            "type_focus": strategy["retrieval_focus"],
            "operation_focus": OPERATION_FOCUS.get(normalized_op, OPERATION_FOCUS["ANALYZE"]),
            "query_plan": [
                {
                    "lane": item["lane"],
                    "search_type": item["search_type"],
                    "query": item["query"],
                }
                for item in query_plan
            ],
        },
        "project_memory": {
            "title": str(getattr(project, "title", "") or "").strip(),
            "description": str(getattr(project, "description", "") or "").strip(),
            "creative_state": creative_state_text,
        },
        "creative_state_memory": creative_state_ledger,
        "ontology": ontology_block,
        "reference_memory": reference_memory,
        "workflow_memory": workflow_memory,
        "dynamic_memory": dynamic_memory,
        "rules": strategy["rules"],
    }


def render_creative_memory_block(memory: dict[str, Any]) -> str:
    sections: list[str] = []
    sections.append(
        f"Text type: {memory.get('text_type_label')} ({memory.get('text_type')})\n"
        f"Operation: {memory.get('operation')}\n"
        f"Retrieval focus: {memory.get('retrieval_strategy', {}).get('type_focus')}\n"
        f"Operation focus: {memory.get('retrieval_strategy', {}).get('operation_focus')}"
    )

    project_memory = memory.get("project_memory") if isinstance(memory.get("project_memory"), dict) else {}
    project_lines = []
    for key, label in [("title", "Title"), ("description", "Description"), ("requirement", "Requirement")]:
        value = str(project_memory.get(key) or "").strip()
        if value:
            project_lines.append(f"- {label}: {_truncate(value, 700)}")
    creative_state = str(project_memory.get("creative_state") or "").strip()
    if creative_state:
        project_lines.append("Creative architecture state:\n" + _truncate(creative_state, 1800))
    if project_lines:
        sections.append("Project memory:\n" + "\n".join(project_lines))

    creative_state_memory = memory.get("creative_state_memory") if isinstance(memory.get("creative_state_memory"), dict) else {}
    creative_sections = [
        item
        for item in creative_state_memory.get("sections") or []
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    if creative_sections:
        sections.append(
            "Structured creative state ledger:\n"
            + "\n\n".join(
                f"{item.get('label')}:\n{item.get('text')}"
                for item in creative_sections[:18]
            )
        )

    ontology = memory.get("ontology") if isinstance(memory.get("ontology"), dict) else {}
    ontology_lines: list[str] = []
    if ontology.get("text_type_reason"):
        ontology_lines.append(f"- Type reason: {_truncate(ontology.get('text_type_reason'), 500)}")
    if ontology.get("analysis_summary"):
        ontology_lines.append(f"- Schema summary: {_truncate(ontology.get('analysis_summary'), 700)}")
    if ontology.get("memory_dimensions"):
        ontology_lines.append("Memory dimensions:\n" + "\n".join(f"- {x}" for x in ontology["memory_dimensions"][:16]))
    if ontology.get("entity_types"):
        ontology_lines.append("Entity types:\n" + "\n".join(f"- {x}" for x in ontology["entity_types"][:16]))
    if ontology.get("edge_types"):
        ontology_lines.append("Relation types:\n" + "\n".join(f"- {x}" for x in ontology["edge_types"][:20]))
    if ontology_lines:
        sections.append("Ontology memory:\n" + "\n".join(ontology_lines))

    reference_memory = memory.get("reference_memory") if isinstance(memory.get("reference_memory"), dict) else {}
    reference_sections = []
    for key, label in [
        ("characters", "Character / actor cards"),
        ("glossary_terms", "Terms / concept cards"),
        ("worldbook_entries", "World / setting cards"),
        ("alias_expansions", "Alias normalization"),
    ]:
        rows = _safe_str_list(reference_memory.get(key), limit=16)
        if rows:
            reference_sections.append(f"{label}:\n" + "\n".join(rows if key != "alias_expansions" else [f"- {x}" for x in rows]))
    if reference_sections:
        sections.append("Structured reference memory:\n" + "\n\n".join(reference_sections))

    workflow_memory = memory.get("workflow_memory") if isinstance(memory.get("workflow_memory"), dict) else {}
    workflow_block = render_workflow_memory(workflow_memory)
    if workflow_block:
        sections.append(workflow_block)

    dynamic_memory = memory.get("dynamic_memory") if isinstance(memory.get("dynamic_memory"), dict) else {}
    dynamic_sections = []
    if dynamic_memory.get("retrieval_context"):
        dynamic_sections.append("Cognee retrieval context:\n" + str(dynamic_memory["retrieval_context"]))
    for key, label in [
        ("typed_insights", "Typed memory insights"),
        ("relationships", "Relationships / dependencies"),
        ("continuity_state", "Continuity state / open loops"),
        ("summaries", "Summaries / state snapshots"),
        ("source_evidence", "Source evidence chunks"),
        ("generation_hints", "Grounded generation hints"),
        ("style_voice", "Style / voice anchors"),
    ]:
        rows = _safe_str_list(dynamic_memory.get(key), limit=10)
        if rows:
            dynamic_sections.append(f"{label}:\n" + "\n".join(f"- {x}" for x in rows))
    if dynamic_sections:
        sections.append("Dynamic retrieval memory:\n" + "\n\n".join(dynamic_sections))

    rules = _safe_str_list(memory.get("rules"), limit=8)
    if rules:
        sections.append("Type-specific execution rules:\n" + "\n".join(f"- {row}" for row in rules))

    query_plan = memory.get("retrieval_strategy", {}).get("query_plan")
    if isinstance(query_plan, list) and query_plan:
        rows = []
        for item in query_plan[:8]:
            if isinstance(item, dict):
                rows.append(f"- {item.get('lane')} / {item.get('search_type')}: {_truncate(item.get('query'), 260)}")
        if rows:
            sections.append("Retrieval query plan:\n" + "\n".join(rows))

    return "## Creative Memory Context\n" + "\n\n".join(sections).strip()


async def get_creative_memory_enhanced_prompt(
    project_id: str,
    op_type: str,
    input_text: str,
    base_prompt: str,
    db: AsyncSession,
    *,
    reference_cards: dict[str, Any] | None = None,
    workflow_step: str | None = None,
) -> str:
    normalized_op = (op_type or "").upper()
    if normalized_op not in OPERATION_FOCUS:
        raise ValueError(f"Unsupported creative memory operation: {op_type!r}")

    result = await db.execute(select(TextProject).where(TextProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise RuntimeError("Project not found while building creative memory")

    memory = await build_creative_memory_pack(
        project=project,
        project_id=project_id,
        op_type=normalized_op,
        input_text=input_text,
        db=db,
        reference_cards=reference_cards,
        workflow_step=workflow_step,
    )
    memory_block = render_creative_memory_block(memory)
    return (
        f"{base_prompt}\n\n"
        f"{memory_block}\n\n"
        "Use the Creative Memory Context as the authoritative project memory for this operation. "
        "Follow the type-specific execution rules and the retrieved constraints before producing the final output."
    )


def debug_memory_json(memory: dict[str, Any]) -> str:
    return json.dumps(memory, ensure_ascii=False, indent=2, sort_keys=True)
