"""
Prediction service - knowledge-graph enhanced prediction.
Uses the active graph runtime to extract relationships and predict
logical continuations before generating text.
"""
import asyncio
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import TextProject
from app.services.llm_json import extract_json_object


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
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
        if len(deduped) >= 96:
            break
    return deduped


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


def _score_text_match(
    *,
    query_norm: str,
    tokens: list[str],
    values: list[str],
    exact_weight: int = 6,
    token_weight: int = 1,
) -> int:
    if not values:
        return 0
    haystack = _normalize_match_text(" ".join(str(value or "") for value in values))
    if not haystack:
        return 0
    score = 0
    for value in values:
        current = _normalize_match_text(value)
        if current and query_norm and current in query_norm:
            score += exact_weight
    for token in tokens:
        if token in haystack:
            score += token_weight
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
    fallback_count_when_no_query: int = 0,
) -> list[dict[str, Any]]:
    if not items:
        return []

    explicit_order: list[str] = []
    explicit_seen: set[str] = set()
    for raw in explicit_ids:
        key = str(raw or "").strip()
        if not key or key in explicit_seen:
            continue
        explicit_seen.add(key)
        explicit_order.append(key)

    item_map: dict[str, dict[str, Any]] = {}
    ranked: list[tuple[int, int, str, dict[str, Any]]] = []
    for idx, item in enumerate(items):
        item_id = str(item.get(id_field) or "").strip()
        if not item_id:
            continue
        item_map[item_id] = item
        values = [str(item.get(field) or "") for field in text_fields]
        score = _score_text_match(query_norm=query_norm, tokens=query_tokens, values=values)
        if item_id in explicit_seen:
            score += 200
        ranked.append((score, idx, item_id, item))

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

    ranked.sort(key=lambda row: (-row[0], row[1]))
    for score, _idx, item_id, item in ranked:
        if item_id in selected_ids:
            continue
        if score <= 0 and query_norm:
            continue
        selected.append(item)
        selected_ids.add(item_id)
        if len(selected) >= limit:
            break

    if selected:
        return selected[:limit]
    if not query_norm and fallback_count_when_no_query > 0:
        return items[: min(limit, fallback_count_when_no_query)]
    return []


def build_reference_rag_context(
    reference_cards: dict[str, Any] | None,
    *,
    focus_text: str,
) -> dict[str, Any]:
    if not isinstance(reference_cards, dict):
        return {
            "character_lines": [],
            "glossary_lines": [],
            "worldbook_lines": [],
            "query_terms": [],
            "alias_expansions": [],
        }

    query_norm = _normalize_match_text(focus_text)
    query_tokens = _query_tokens(focus_text)

    raw_characters = [item for item in reference_cards.get("characters") or [] if isinstance(item, dict)]
    raw_glossary_terms = [dict(item) for item in reference_cards.get("glossary_terms") or [] if isinstance(item, dict)]
    raw_worldbook_entries = [dict(item) for item in reference_cards.get("worldbook_entries") or [] if isinstance(item, dict)]
    for row in raw_glossary_terms:
        row["alias_text"] = " ".join(_safe_str_list(row.get("aliases"), limit=20))
    for row in raw_worldbook_entries:
        row["tag_text"] = " ".join(_safe_str_list(row.get("tags"), limit=20))

    selected_characters = _pick_ranked_items(
        items=raw_characters,
        id_field="id",
        explicit_ids=_safe_str_list(reference_cards.get("explicit_character_ids"), limit=128),
        query_norm=query_norm,
        query_tokens=query_tokens,
        text_fields=["name", "role", "profile", "notes"],
        limit=8,
        fallback_count_when_no_query=4,
    )
    selected_glossary_terms = _pick_ranked_items(
        items=raw_glossary_terms,
        id_field="id",
        explicit_ids=_safe_str_list(reference_cards.get("explicit_glossary_term_ids"), limit=256),
        query_norm=query_norm,
        query_tokens=query_tokens,
        text_fields=["term", "alias_text", "definition", "notes"],
        limit=14,
        fallback_count_when_no_query=8,
    )
    selected_worldbook_entries = _pick_ranked_items(
        items=raw_worldbook_entries,
        id_field="id",
        explicit_ids=_safe_str_list(reference_cards.get("explicit_worldbook_entry_ids"), limit=256),
        query_norm=query_norm,
        query_tokens=query_tokens,
        text_fields=["title", "category", "tag_text", "content", "notes"],
        limit=10,
        fallback_count_when_no_query=6,
    )

    character_lines: list[str] = []
    query_terms: list[str] = []
    alias_expansions: list[str] = []
    seen_query_terms: set[str] = set()
    seen_alias_expansions: set[str] = set()

    for row in selected_characters:
        name = _truncate(row.get("name"), 120)
        role = _truncate(row.get("role"), 80)
        profile = _truncate(row.get("profile"), 180)
        notes = _truncate(row.get("notes"), 140)
        if not name:
            continue
        detail_bits = [bit for bit in [role, profile, notes] if bit]
        character_lines.append(
            f"- {name}" + (f": {' | '.join(detail_bits)}" if detail_bits else "")
        )
        term_key = name.strip()
        if term_key and term_key not in seen_query_terms:
            seen_query_terms.add(term_key)
            query_terms.append(term_key)

    glossary_lines: list[str] = []
    for row in selected_glossary_terms:
        term = _truncate(row.get("term"), 120)
        definition = _truncate(row.get("definition"), 220)
        notes = _truncate(row.get("notes"), 140)
        aliases = _safe_str_list(row.get("aliases"), limit=10)
        if not term:
            continue
        alias_text = _truncate(", ".join(aliases), 140) if aliases else ""
        line_parts: list[str] = [f"- {term}"]
        if alias_text:
            line_parts.append(f"aliases: {alias_text}")
        if definition:
            line_parts.append(f"definition: {definition}")
        if notes:
            line_parts.append(f"notes: {notes}")
        glossary_lines.append(" | ".join(line_parts))

        if term not in seen_query_terms:
            seen_query_terms.add(term)
            query_terms.append(term)

        alias_hits = []
        for alias in aliases:
            alias_norm = _normalize_match_text(alias)
            if alias_norm and query_norm and alias_norm in query_norm:
                alias_hits.append(alias)
        for alias in alias_hits:
            expansion = f"{alias} -> {term}"
            if expansion in seen_alias_expansions:
                continue
            seen_alias_expansions.add(expansion)
            alias_expansions.append(expansion)

    worldbook_lines: list[str] = []
    for row in selected_worldbook_entries:
        title = _truncate(row.get("title"), 140)
        category = _truncate(row.get("category"), 80)
        content = _truncate(row.get("content"), 260)
        notes = _truncate(row.get("notes"), 140)
        tags = _safe_str_list(row.get("tags"), limit=12)
        if not title:
            continue
        pieces: list[str] = [f"- {title}"]
        if category:
            pieces.append(f"category: {category}")
        if tags:
            pieces.append(f"tags: {_truncate(', '.join(tags), 140)}")
        if content:
            pieces.append(f"content: {content}")
        if notes:
            pieces.append(f"notes: {notes}")
        worldbook_lines.append(" | ".join(pieces))

        if title not in seen_query_terms:
            seen_query_terms.add(title)
            query_terms.append(title)
        for tag in tags[:6]:
            if tag and tag not in seen_query_terms:
                seen_query_terms.add(tag)
                query_terms.append(tag)

    return {
        "character_lines": character_lines,
        "glossary_lines": glossary_lines,
        "worldbook_lines": worldbook_lines,
        "query_terms": query_terms[:40],
        "alias_expansions": alias_expansions[:20],
    }


def _build_reference_query_hint(reference_context: dict[str, Any] | None) -> str:
    if not isinstance(reference_context, dict):
        return ""
    terms = _safe_str_list(reference_context.get("query_terms"), limit=40)
    alias_expansions = _safe_str_list(reference_context.get("alias_expansions"), limit=20)
    rows: list[str] = []
    if terms:
        rows.append("Anchors: " + ", ".join(terms))
    if alias_expansions:
        rows.append("Alias normalization: " + "; ".join(alias_expansions))
    return _truncate("\n".join(rows), 1200)


def _format_reference_context_block(reference_context: dict[str, Any] | None) -> str:
    if not isinstance(reference_context, dict):
        return ""
    character_lines = _safe_str_list(reference_context.get("character_lines"), limit=8)
    glossary_lines = _safe_str_list(reference_context.get("glossary_lines"), limit=14)
    worldbook_lines = _safe_str_list(reference_context.get("worldbook_lines"), limit=10)
    query_terms = _safe_str_list(reference_context.get("query_terms"), limit=24)
    alias_expansions = _safe_str_list(reference_context.get("alias_expansions"), limit=20)

    sections: list[str] = []
    if character_lines:
        sections.append("Reference characters:\n" + "\n".join(character_lines))
    if glossary_lines:
        sections.append("Reference glossary terms:\n" + "\n".join(glossary_lines))
    if worldbook_lines:
        sections.append("Triggered worldbook entries:\n" + "\n".join(worldbook_lines))
    if alias_expansions:
        sections.append("Alias normalization:\n" + "\n".join(f"- {row}" for row in alias_expansions))
    if query_terms:
        sections.append("Retrieval anchors:\n" + "\n".join(f"- {term}" for term in query_terms))
    return "\n\n".join(sections)


def _has_reference_signal(reference_context: dict[str, Any] | None) -> bool:
    if not isinstance(reference_context, dict):
        return False
    for key in ("character_lines", "glossary_lines", "worldbook_lines", "query_terms"):
        values = reference_context.get(key)
        if isinstance(values, list) and values:
            return True
    return False


def _token_set(text: str | None) -> set[str]:
    return set(_query_tokens(text))


def _token_overlap(query_tokens: set[str], content: str) -> float:
    if not query_tokens:
        return 0.0
    content_tokens = _token_set(content)
    if not content_tokens:
        return 0.0
    return len(query_tokens & content_tokens) / max(1, len(query_tokens))


def _build_retrieval_query_groups(
    *,
    focus_text: str,
    reference_context: dict[str, Any] | None,
) -> list[str]:
    focus = _truncate(focus_text, 320)
    query_terms = _safe_str_list((reference_context or {}).get("query_terms"), limit=30)
    alias_expansions = _safe_str_list((reference_context or {}).get("alias_expansions"), limit=12)

    candidates: list[str] = []
    if focus:
        candidates.append(focus)
    if query_terms:
        candidates.append(" ".join(query_terms[:4]))
    for idx in range(0, len(query_terms), 3):
        group = query_terms[idx : idx + 3]
        if len(group) >= 2:
            candidates.append(" ".join(group))
    for row in alias_expansions:
        if "->" in row:
            left, right = row.split("->", 1)
            pair = f"{left.strip()} {right.strip()}".strip()
            if pair:
                candidates.append(pair)

    deduped: list[str] = []
    seen: set[str] = set()
    for row in candidates:
        value = _truncate(row, 360).strip()
        if not value:
            continue
        norm = _normalize_match_text(value)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append(value)
        if len(deduped) >= 8:
            break
    return deduped


def _normalize_search_rows(rows: Any) -> list[dict[str, Any]]:
    if isinstance(rows, Exception) or not isinstance(rows, list):
        return []
    parsed: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        score_raw = item.get("reranker_score", item.get("score", 0))
        try:
            score = float(score_raw)
        except Exception:
            score = 0.0
        parsed.append(
            {
                "content": content,
                "score": max(0.0, min(1.0, score)),
                "type": str(item.get("type") or "").strip(),
            }
        )
    return parsed


def _rank_search_rows(
    rows: list[dict[str, Any]],
    *,
    focus_text: str,
    limit: int,
    max_chars: int,
    require_overlap_for_low_score: bool = False,
) -> list[str]:
    if not rows:
        return []

    focus_tokens = _token_set(focus_text)
    scored: list[tuple[float, int, str]] = []
    seen_norm: set[str] = set()
    for idx, row in enumerate(rows):
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        norm = _normalize_match_text(content)
        if not norm or norm in seen_norm:
            continue
        seen_norm.add(norm)

        score = float(row.get("score") or 0.0)
        overlap = _token_overlap(focus_tokens, content)
        if require_overlap_for_low_score and focus_tokens and overlap <= 0 and score < 0.35:
            continue

        row_type = str(row.get("type") or "").strip()
        type_bonus = 0.06 if row_type in {"TextSummary", "Entity", "EntityType"} else 0.0
        rank_score = (score * 0.65) + (overlap * 0.35) + type_bonus

        rendered = content
        if row_type:
            rendered = f"[{row_type}] {content}"
        rendered = _truncate(rendered, max_chars)
        scored.append((rank_score, idx, rendered))

    scored.sort(key=lambda item: (-item[0], item[1]))

    lines: list[str] = []
    for _score, _idx, rendered in scored:
        lines.append(rendered)
        if len(lines) >= limit:
            break
    return lines


async def get_graph_context(
    project_id: str,
    focus_text: str = "",
    *,
    db: AsyncSession | None = None,
    use_reranker: bool = False,
    reranker_model: str | None = None,
    reranker_top_n: int | None = None,
    reference_query_hint: str = "",
    retrieval_queries: list[str] | None = None,
) -> dict[str, Any]:
    """Extract entity relationships from the knowledge graph using Cognee search."""
    context: dict[str, Any] = {
        "entities": [],
        "relationships": [],
        "insights": [],
        "summaries": [],
        "chunks": [],
        "rag_completions": [],
        "reference_hint": "",
        "retrieval_queries": [],
    }
    try:
        from app.services.graph_service import search_graph

        focus = (focus_text or "").strip()
        hint = _truncate(reference_query_hint, 1000).strip()
        focus_query = focus[:1200] if focus else "current narrative context and next logical development"
        chunk_query = focus[:900] if focus else "most relevant evidence chunks for continuity"
        summary_query = focus[:900] if focus else "core storyline, timeline, and entity state summaries"
        graph_query = focus[:900] if focus else "entity relationships and plot structure"
        if hint:
            focus_query = _truncate(f"{focus_query}\n\nReference anchors:\n{hint}", 2200)
            chunk_query = _truncate(f"{chunk_query}\n\nReference anchors:\n{hint}", 1800)
            summary_query = _truncate(f"{summary_query}\n\nReference anchors:\n{hint}", 1800)
            graph_query = _truncate(f"{graph_query}\n\nReference anchors:\n{hint}", 1800)
            context["reference_hint"] = hint
        search_kwargs = {
            "db": db,
            "use_reranker": bool(use_reranker),
            "reranker_model": reranker_model,
            "reranker_top_n": reranker_top_n,
        }

        query_jobs: list[tuple[str, str]] = []
        for query in retrieval_queries or []:
            clean_query = _truncate(query, 360).strip()
            if not clean_query:
                continue
            query_jobs.append(("CHUNKS", clean_query))
            query_jobs.append(("INSIGHTS", clean_query))
            if len(query_jobs) >= 12:
                break
        if query_jobs:
            context["retrieval_queries"] = [item[1] for item in query_jobs[::2]]

        tasks = [
            search_graph(
                project_id,
                "key entities, characters, themes, and their relationships",
                search_type="INSIGHTS",
                top_k=8,
                **search_kwargs,
            ),
            search_graph(
                project_id,
                graph_query,
                search_type="GRAPH_COMPLETION",
                top_k=6,
                **search_kwargs,
            ),
            search_graph(
                project_id,
                summary_query,
                search_type="SUMMARIES",
                top_k=6,
                **search_kwargs,
            ),
            search_graph(
                project_id,
                chunk_query,
                search_type="CHUNKS",
                top_k=10,
                **search_kwargs,
            ),
            search_graph(
                project_id,
                focus_query,
                search_type="RAG_COMPLETION",
                top_k=4,
                **search_kwargs,
            ),
        ]
        for job_type, job_query in query_jobs:
            tasks.append(
                search_graph(
                    project_id,
                    job_query,
                    search_type=job_type,
                    top_k=4 if job_type == "CHUNKS" else 3,
                    **search_kwargs,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        base_insights = _normalize_search_rows(results[0])
        base_relationships = _normalize_search_rows(results[1])
        base_summaries = _normalize_search_rows(results[2])
        base_chunks = _normalize_search_rows(results[3])
        base_rag = _normalize_search_rows(results[4])

        extra_chunk_rows: list[dict[str, Any]] = []
        extra_insight_rows: list[dict[str, Any]] = []
        for idx, job in enumerate(query_jobs, start=5):
            parsed_rows = _normalize_search_rows(results[idx])
            if not parsed_rows:
                continue
            if job[0] == "CHUNKS":
                extra_chunk_rows.extend(parsed_rows)
            else:
                extra_insight_rows.extend(parsed_rows)

        context["insights"] = _rank_search_rows(
            base_insights + extra_insight_rows,
            focus_text=focus,
            limit=10,
            max_chars=420,
            require_overlap_for_low_score=True,
        )
        context["relationships"] = _rank_search_rows(
            base_relationships,
            focus_text=focus,
            limit=8,
            max_chars=400,
            require_overlap_for_low_score=False,
        )
        context["summaries"] = _rank_search_rows(
            base_summaries,
            focus_text=focus,
            limit=6,
            max_chars=360,
            require_overlap_for_low_score=True,
        )
        context["chunks"] = _rank_search_rows(
            base_chunks + extra_chunk_rows,
            focus_text=focus,
            limit=10,
            max_chars=300,
            require_overlap_for_low_score=True,
        )
        context["rag_completions"] = _rank_search_rows(
            base_rag,
            focus_text=focus,
            limit=4,
            max_chars=360,
            require_overlap_for_low_score=False,
        )

    except Exception:
        pass  # Graph not available, continue without context

    return context


def _format_oasis_context(oasis_analysis: dict[str, Any] | None) -> str:
    if not oasis_analysis or not isinstance(oasis_analysis, dict):
        return ""
    guidance = oasis_analysis.get("continuation_guidance") or {}
    must_follow = guidance.get("must_follow") if isinstance(guidance, dict) else []
    next_steps = guidance.get("next_steps") if isinstance(guidance, dict) else []
    avoid = guidance.get("avoid") if isinstance(guidance, dict) else []
    agent_profiles = oasis_analysis.get("agent_profiles") or []
    simulation_config = oasis_analysis.get("simulation_config") or {}

    lines: list[str] = []
    summary = str(oasis_analysis.get("scenario_summary") or "").strip()
    if summary:
        lines.append(f"Scenario summary: {summary}")
    if must_follow:
        lines.append("Must-follow constraints:\n" + "\n".join(f"- {x}" for x in must_follow[:8]))
    if next_steps:
        lines.append("Suggested next steps:\n" + "\n".join(f"- {x}" for x in next_steps[:8]))
    if avoid:
        lines.append("Avoid:\n" + "\n".join(f"- {x}" for x in avoid[:8]))
    if agent_profiles:
        profile_lines = []
        for p in agent_profiles[:8]:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "").strip()
            role = str(p.get("role") or "").strip()
            stance = str(p.get("stance") or "").strip()
            if name:
                profile_lines.append(f"- {name} ({role or 'unknown role'}, stance: {stance or 'neutral'})")
        if profile_lines:
            lines.append("Agent profile anchors:\n" + "\n".join(profile_lines))
    if isinstance(simulation_config, dict) and simulation_config:
        time_cfg = simulation_config.get("time_config") if isinstance(simulation_config.get("time_config"), dict) else {}
        events = simulation_config.get("events") if isinstance(simulation_config.get("events"), list) else []
        agent_activity = simulation_config.get("agent_activity") if isinstance(simulation_config.get("agent_activity"), list) else []
        sim_lines: list[str] = []
        total_hours = time_cfg.get("total_hours")
        minutes_per_round = time_cfg.get("minutes_per_round")
        if total_hours:
            sim_lines.append(f"- total_hours: {total_hours}")
        if minutes_per_round:
            sim_lines.append(f"- minutes_per_round: {minutes_per_round}")
        if events:
            sim_lines.append(f"- planned_events: {len(events)}")
        if agent_activity:
            sim_lines.append(f"- active_agents_configured: {len(agent_activity)}")
        if sim_lines:
            lines.append("Simulation plan:\n" + "\n".join(sim_lines))
    return "\n\n".join(lines)


def _safe_list(value: Any, limit: int = 10) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            rows.append(text)
        if len(rows) >= limit:
            break
    return rows


def _extract_reference_cards_block(base_prompt: str) -> str:
    marker = "## Reference Cards"
    prompt = str(base_prompt or "")
    if marker in prompt:
        return prompt.split(marker, 1)[1].strip()
    legacy_marker = "## Character Cards"
    if legacy_marker in prompt:
        return prompt.split(legacy_marker, 1)[1].strip()
    return ""


def _format_structure_context(structure_analysis: dict[str, Any] | None) -> str:
    if not isinstance(structure_analysis, dict):
        return ""
    narrative = structure_analysis.get("narrative_state")
    narrative_summary = ""
    if isinstance(narrative, dict):
        phase = str(narrative.get("phase") or "").strip()
        summary = str(narrative.get("summary") or "").strip()
        if phase and summary:
            narrative_summary = f"{phase}: {summary}"
        elif summary:
            narrative_summary = summary
        elif phase:
            narrative_summary = phase
    elif isinstance(narrative, str):
        narrative_summary = narrative.strip()

    core_entities = structure_analysis.get("core_entities")
    entity_lines: list[str] = []
    if isinstance(core_entities, list):
        for item in core_entities[:10]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            role = str(item.get("role") or "").strip()
            state = str(item.get("state") or "").strip()
            if not name:
                continue
            detail_parts = [x for x in [role, state] if x]
            entity_lines.append(f"- {name}" + (f" ({'; '.join(detail_parts)})" if detail_parts else ""))

    active_conflicts = _safe_list(structure_analysis.get("active_conflicts"), 10)
    hard_constraints = _safe_list(structure_analysis.get("hard_constraints"), 10)
    style_anchors = _safe_list(structure_analysis.get("style_anchors"), 8)
    next_beats = _safe_list(structure_analysis.get("next_beats"), 10)
    unknowns = _safe_list(structure_analysis.get("unknowns"), 8)

    lines: list[str] = []
    if narrative_summary:
        lines.append(f"Narrative state: {narrative_summary}")
    if entity_lines:
        lines.append("Core entities:\n" + "\n".join(entity_lines))
    if active_conflicts:
        lines.append("Active conflicts:\n" + "\n".join(f"- {x}" for x in active_conflicts))
    if hard_constraints:
        lines.append("Hard constraints:\n" + "\n".join(f"- {x}" for x in hard_constraints))
    if style_anchors:
        lines.append("Style anchors:\n" + "\n".join(f"- {x}" for x in style_anchors))
    if next_beats:
        lines.append("Next beats:\n" + "\n".join(f"- {x}" for x in next_beats))
    if unknowns:
        lines.append("Open unknowns:\n" + "\n".join(f"- {x}" for x in unknowns))
    return "\n\n".join(lines)


async def analyze_structure(
    *,
    project: TextProject,
    input_text: str,
    graph_context: dict[str, Any],
    analysis_model: str | None,
    db: AsyncSession,
) -> dict[str, Any] | None:
    text = (input_text or "").strip()
    if not text and not (project.simulation_requirement or "").strip():
        return None

    try:
        from app.services.ai import call_llm, resolve_component_model
    except Exception:
        return None

    model = resolve_component_model(
        project,
        "operation_analyze",
        analysis_model,
    )
    if not model:
        model = resolve_component_model(project, "oasis_analysis")

    oasis = project.oasis_analysis if isinstance(project.oasis_analysis, dict) else {}
    oasis_summary = str(oasis.get("scenario_summary") or "").strip()

    prompt = (
        "You are a narrative planning analyst for long-form generation.\n"
        "Return JSON only with this schema:\n"
        "{\n"
        '  "narrative_state": {"phase": "...", "summary": "..."},\n'
        '  "core_entities": [{"name":"...", "role":"...", "state":"..."}],\n'
        '  "active_conflicts": ["..."],\n'
        '  "hard_constraints": ["..."],\n'
        '  "style_anchors": ["..."],\n'
        '  "next_beats": ["..."],\n'
        '  "unknowns": ["..."]\n'
        "}\n"
        "Keep each item concise, concrete, and grounded in provided evidence.\n\n"
        f"Project title: {(project.title or '').strip()}\n"
        f"Project description: {(project.description or '').strip()}\n"
        f"Simulation requirement: {(project.simulation_requirement or '').strip()}\n"
        f"OASIS summary: {oasis_summary}\n\n"
        f"Knowledge graph context:\n{json.dumps(graph_context, ensure_ascii=False)[:9000]}\n\n"
        f"Input text:\n{text[:12000]}"
    )

    try:
        result = await call_llm(model=model, prompt=prompt, db=db)
        parsed = extract_json_object(str(result.get("content") or ""))
        if not isinstance(parsed, dict):
            return None
        narrative = parsed.get("narrative_state")
        if not isinstance(narrative, dict):
            narrative = {"phase": "", "summary": str(narrative or "").strip()}
        sanitized = {
            "narrative_state": {
                "phase": str(narrative.get("phase") or "").strip(),
                "summary": str(narrative.get("summary") or "").strip(),
            },
            "core_entities": [
                {
                    "name": str(item.get("name") or "").strip(),
                    "role": str(item.get("role") or "").strip(),
                    "state": str(item.get("state") or "").strip(),
                }
                for item in (parsed.get("core_entities") or [])[:12]
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ],
            "active_conflicts": _safe_list(parsed.get("active_conflicts"), 12),
            "hard_constraints": _safe_list(parsed.get("hard_constraints"), 12),
            "style_anchors": _safe_list(parsed.get("style_anchors"), 10),
            "next_beats": _safe_list(parsed.get("next_beats"), 12),
            "unknowns": _safe_list(parsed.get("unknowns"), 10),
        }
        has_signal = any(
            [
                sanitized["narrative_state"]["summary"],
                sanitized["core_entities"],
                sanitized["active_conflicts"],
                sanitized["hard_constraints"],
                sanitized["next_beats"],
            ]
        )
        return sanitized if has_signal else None
    except Exception:
        return None


def build_prediction_prompt(
    input_text: str,
    graph_context: dict[str, Any],
    oasis_analysis: dict[str, Any] | None,
    simulation_requirement: str | None,
    structure_analysis: dict[str, Any] | None,
    base_prompt: str,
    reference_rag_context: dict[str, Any] | None = None,
) -> str:
    """Build an enhanced continuation prompt using knowledge graph context."""
    oasis_context = _format_oasis_context(oasis_analysis)
    structure_context = _format_structure_context(structure_analysis)
    reference_context = _format_reference_context_block(reference_rag_context)
    reference_cards = _extract_reference_cards_block(base_prompt)
    if (
        not graph_context["insights"]
        and not graph_context["relationships"]
        and not graph_context.get("summaries")
        and not graph_context.get("chunks")
        and not graph_context.get("rag_completions")
        and not graph_context.get("reference_hint")
        and not oasis_context
        and not structure_context
        and not reference_context
        and not reference_cards
        and not (simulation_requirement or "").strip()
    ):
        return base_prompt

    context_parts = []

    if reference_context:
        context_parts.append(reference_context)
    elif reference_cards:
        context_parts.append(f"Reference cards:\n{reference_cards}")

    if graph_context["insights"]:
        insights_text = "\n".join(f"- {i}" for i in graph_context["insights"])
        context_parts.append(f"Key insights from knowledge graph:\n{insights_text}")

    if graph_context["relationships"]:
        rel_text = "\n".join(f"- {r}" for r in graph_context["relationships"])
        context_parts.append(f"Entity relationships and structure:\n{rel_text}")

    if graph_context.get("summaries"):
        summary_text = "\n".join(f"- {s}" for s in graph_context["summaries"][:6])
        context_parts.append(f"Graph summaries:\n{summary_text}")

    if graph_context.get("chunks"):
        chunk_text = "\n".join(f"- {c}" for c in graph_context["chunks"][:8])
        context_parts.append(f"Relevant document chunks:\n{chunk_text}")

    if graph_context.get("rag_completions"):
        rag_text = "\n".join(f"- {c}" for c in graph_context["rag_completions"][:4])
        context_parts.append(f"RAG completion hints:\n{rag_text}")
    if graph_context.get("reference_hint"):
        context_parts.append(f"Reference retrieval hint:\n{graph_context['reference_hint']}")
    if graph_context.get("retrieval_queries"):
        query_text = "\n".join(f"- {query}" for query in graph_context["retrieval_queries"][:8])
        context_parts.append(f"Retrieval query plan:\n{query_text}")

    if oasis_context:
        context_parts.append(f"OASIS analysis context:\n{oasis_context}")

    requirement_text = (simulation_requirement or "").strip()
    if requirement_text:
        context_parts.append(f"Simulation requirement:\n{requirement_text}")

    if structure_context:
        context_parts.append(f"Narrative structure analysis:\n{structure_context}")

    graph_section = "\n\n".join(context_parts)
    
    enhanced_prompt = f"""You are a creative writing assistant with deep understanding of the story's world.

## Knowledge Graph Context
The following entities, relationships, and insights have been extracted from the text's knowledge graph. Use them to ensure logical consistency and coherent character/plot development in your continuation.

{graph_section}

## Prediction Guidelines
- Maintain consistency with established entity relationships
- Develop existing plot threads naturally based on the entity graph
- Ensure character actions align with their established relationships
- Introduce new developments that logically follow from the knowledge graph structure
- Respect OASIS scenario constraints and continuation guidance
- Respect narrative constraints/conflicts even when graph context is sparse
- Keep the same writing style, tone, and language as the original text

## Text to Continue
{input_text}

Continue the text naturally, ensuring logical coherence with the knowledge graph context above. Write in the same language as the input text."""
    
    return enhanced_prompt


def build_rag_prompt_for_operation(
    *,
    op_type: str,
    input_text: str,
    graph_context: dict[str, Any],
    oasis_analysis: dict[str, Any] | None,
    simulation_requirement: str | None,
    structure_analysis: dict[str, Any] | None,
    base_prompt: str,
    reference_rag_context: dict[str, Any] | None = None,
) -> str:
    """Build a generic RAG-augmented prompt for non-continuation operations."""
    oasis_context = _format_oasis_context(oasis_analysis)
    structure_context = _format_structure_context(structure_analysis)
    reference_context = _format_reference_context_block(reference_rag_context)
    context_parts: list[str] = []

    if reference_context:
        context_parts.append(reference_context)
    if graph_context.get("insights"):
        context_parts.append(
            "Graph insights:\n"
            + "\n".join(f"- {item}" for item in graph_context["insights"][:10])
        )
    if graph_context.get("relationships"):
        context_parts.append(
            "Graph relationships:\n"
            + "\n".join(f"- {item}" for item in graph_context["relationships"][:10])
        )
    if graph_context.get("summaries"):
        context_parts.append(
            "Graph summaries:\n"
            + "\n".join(f"- {item}" for item in graph_context["summaries"][:6])
        )
    if graph_context.get("chunks"):
        context_parts.append(
            "Relevant chunks:\n"
            + "\n".join(f"- {item}" for item in graph_context["chunks"][:8])
        )
    if graph_context.get("rag_completions"):
        context_parts.append(
            "RAG completions:\n"
            + "\n".join(f"- {item}" for item in graph_context["rag_completions"][:4])
        )
    if graph_context.get("reference_hint"):
        context_parts.append(f"Reference retrieval hint:\n{graph_context['reference_hint']}")
    if graph_context.get("retrieval_queries"):
        context_parts.append(
            "Retrieval query plan:\n"
            + "\n".join(f"- {query}" for query in graph_context["retrieval_queries"][:8])
        )
    if oasis_context:
        context_parts.append(f"OASIS context:\n{oasis_context}")
    requirement_text = (simulation_requirement or "").strip()
    if requirement_text:
        context_parts.append(f"Requirement:\n{requirement_text}")
    if structure_context:
        context_parts.append(f"Narrative structure:\n{structure_context}")

    if not context_parts:
        return base_prompt

    rag_context = "\n\n".join(context_parts)
    return (
        f"{base_prompt}\n\n"
        "## Retrieved Graph Context (RAG)\n"
        f"{rag_context}\n\n"
        f"## Execution Rules for {op_type}\n"
        "- Treat retrieved graph context as factual constraints.\n"
        "- Keep output consistent with entities and relationships.\n"
        "- If context conflicts with input text, explicitly resolve the conflict in output.\n"
    )


async def get_enhanced_prompt(
    project_id: str,
    op_type: str,
    input_text: str,
    base_prompt: str,
    db: AsyncSession,
    analysis_model: str | None = None,
    reference_cards: dict[str, Any] | None = None,
) -> str:
    """Get a RAG-enhanced prompt for all core operation types."""
    if op_type not in ("CREATE", "CONTINUE", "ANALYZE", "REWRITE", "SUMMARIZE"):
        return base_prompt
    
    # Check if project has a knowledge graph
    result = await db.execute(
        select(TextProject).where(TextProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        return base_prompt

    has_graph = bool(project.cognee_dataset_id)
    has_oasis = isinstance(project.oasis_analysis, dict) and bool(project.oasis_analysis)
    reference_rag_context = build_reference_rag_context(
        reference_cards,
        focus_text=input_text,
    )
    retrieval_queries = _build_retrieval_query_groups(
        focus_text=input_text,
        reference_context=reference_rag_context,
    )
    reference_query_hint = _build_reference_query_hint(reference_rag_context)
    reranker_model = ""
    if has_graph:
        try:
            from app.services.ai import resolve_component_model

            reranker_model = resolve_component_model(
                project,
                "graph_reranker",
                fallback_model="",
            )
        except Exception:
            reranker_model = ""
    graph_context = {
        "entities": [],
        "relationships": [],
        "insights": [],
        "summaries": [],
        "chunks": [],
        "rag_completions": [],
    }
    if has_graph:
        graph_context = await get_graph_context(
            project_id,
            focus_text=input_text,
            db=db,
            use_reranker=bool(reranker_model),
            reranker_model=reranker_model or None,
            reranker_top_n=8,
            reference_query_hint=reference_query_hint,
            retrieval_queries=retrieval_queries,
        )

    structure = await analyze_structure(
        project=project,
        input_text=input_text,
        graph_context=graph_context,
        analysis_model=analysis_model,
        db=db,
    )
    requirement_text = (project.simulation_requirement or "").strip()
    if (
        not graph_context["insights"]
        and not graph_context["relationships"]
        and not graph_context.get("summaries")
        and not graph_context.get("chunks")
        and not graph_context.get("rag_completions")
        and not graph_context.get("reference_hint")
        and not has_oasis
        and not structure
        and not requirement_text
        and not _has_reference_signal(reference_rag_context)
    ):
        return base_prompt
    
    oasis = project.oasis_analysis if isinstance(project.oasis_analysis, dict) else None
    if op_type in ("CREATE", "CONTINUE"):
        return build_prediction_prompt(
            input_text,
            graph_context,
            oasis,
            requirement_text,
            structure,
            base_prompt,
            reference_rag_context,
        )
    return build_rag_prompt_for_operation(
        op_type=op_type,
        input_text=input_text,
        graph_context=graph_context,
        oasis_analysis=oasis,
        simulation_requirement=requirement_text,
        structure_analysis=structure,
        base_prompt=base_prompt,
        reference_rag_context=reference_rag_context,
    )
