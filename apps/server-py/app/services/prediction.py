"""
Prediction service - MiroFish-style knowledge graph enhanced prediction.
Uses Cognee's native search to extract entity relationships and predict
logical continuations before generating text.
"""
import asyncio
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import TextProject
from app.services.llm_json import extract_json_object


def _dedupe_lines(rows: list[str], *, limit: int, max_chars: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for row in rows:
        text = str(row or "").strip()
        if not text:
            continue
        normalized = " ".join(text.split()).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        if len(text) > max_chars:
            text = text[: max(1, max_chars - 3)] + "..."
        result.append(text)
        if len(result) >= limit:
            break
    return result


async def get_graph_context(
    project_id: str,
    focus_text: str = "",
    *,
    db: AsyncSession | None = None,
    use_reranker: bool = False,
    reranker_model: str | None = None,
    reranker_top_n: int | None = None,
) -> dict[str, Any]:
    """Extract entity relationships from the knowledge graph using Cognee search."""
    context: dict[str, Any] = {
        "entities": [],
        "relationships": [],
        "insights": [],
        "summaries": [],
        "chunks": [],
        "rag_completions": [],
    }
    try:
        from app.services.cognee import search_graph

        focus = (focus_text or "").strip()
        focus_query = focus[:1200] if focus else "current narrative context and next logical development"
        chunk_query = focus[:900] if focus else "most relevant evidence chunks for continuity"
        summary_query = focus[:900] if focus else "core storyline, timeline, and entity state summaries"
        graph_query = focus[:900] if focus else "entity relationships and plot structure"
        search_kwargs = {
            "db": db,
            "use_reranker": bool(use_reranker),
            "reranker_model": reranker_model,
            "reranker_top_n": reranker_top_n,
        }

        results = await asyncio.gather(
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
            return_exceptions=True,
        )

        def _contents(rows: Any) -> list[str]:
            if isinstance(rows, Exception) or not isinstance(rows, list):
                return []
            return [str(item.get("content") or "").strip() for item in rows if isinstance(item, dict)]

        context["insights"] = _dedupe_lines(_contents(results[0]), limit=8, max_chars=400)
        context["relationships"] = _dedupe_lines(_contents(results[1]), limit=8, max_chars=400)
        context["summaries"] = _dedupe_lines(_contents(results[2]), limit=6, max_chars=360)
        context["chunks"] = _dedupe_lines(_contents(results[3]), limit=8, max_chars=280)
        context["rag_completions"] = _dedupe_lines(_contents(results[4]), limit=4, max_chars=360)

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
) -> str:
    """Build an enhanced continuation prompt using knowledge graph context."""
    oasis_context = _format_oasis_context(oasis_analysis)
    structure_context = _format_structure_context(structure_analysis)
    if (
        not graph_context["insights"]
        and not graph_context["relationships"]
        and not graph_context.get("summaries")
        and not graph_context.get("chunks")
        and not graph_context.get("rag_completions")
        and not oasis_context
        and not structure_context
        and not (simulation_requirement or "").strip()
    ):
        return base_prompt

    context_parts = []

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
) -> str:
    """Build a generic RAG-augmented prompt for non-continuation operations."""
    oasis_context = _format_oasis_context(oasis_analysis)
    structure_context = _format_structure_context(structure_analysis)
    context_parts: list[str] = []

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
        and not has_oasis
        and not structure
        and not requirement_text
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
        )
    return build_rag_prompt_for_operation(
        op_type=op_type,
        input_text=input_text,
        graph_context=graph_context,
        oasis_analysis=oasis,
        simulation_requirement=requirement_text,
        structure_analysis=structure,
        base_prompt=base_prompt,
    )
