"""
Prediction service - MiroFish-style knowledge graph enhanced prediction.
Uses Cognee's native search to extract entity relationships and predict
logical continuations before generating text.
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import TextProject


async def get_graph_context(project_id: str) -> dict[str, Any]:
    """Extract entity relationships from the knowledge graph using Cognee search."""
    context: dict[str, Any] = {"entities": [], "relationships": [], "insights": []}
    try:
        from app.services.cognee import search_graph

        # Use INSIGHTS for entity/relationship understanding
        insights = await search_graph(
            project_id,
            "key entities, characters, themes, and their relationships",
            search_type="INSIGHTS",
            top_k=10,
        )
        context["insights"] = [i.get("content", "") for i in insights if i.get("content")]

        # Use GRAPH_COMPLETION for structured relationship context
        graph_results = await search_graph(
            project_id,
            "entity relationships and plot structure",
            search_type="GRAPH_COMPLETION",
            top_k=5,
        )
        context["relationships"] = [
            r.get("content", "") for r in graph_results if r.get("content")
        ]

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


def build_prediction_prompt(
    input_text: str,
    graph_context: dict[str, Any],
    oasis_analysis: dict[str, Any] | None,
    simulation_requirement: str | None,
    base_prompt: str,
) -> str:
    """Build an enhanced continuation prompt using knowledge graph context."""
    oasis_context = _format_oasis_context(oasis_analysis)
    if not graph_context["insights"] and not graph_context["relationships"] and not oasis_context:
        return base_prompt

    context_parts = []

    if graph_context["insights"]:
        insights_text = "\n".join(f"- {i}" for i in graph_context["insights"])
        context_parts.append(f"Key insights from knowledge graph:\n{insights_text}")

    if graph_context["relationships"]:
        rel_text = "\n".join(f"- {r}" for r in graph_context["relationships"])
        context_parts.append(f"Entity relationships and structure:\n{rel_text}")

    if oasis_context:
        context_parts.append(f"OASIS analysis context:\n{oasis_context}")

    requirement_text = (simulation_requirement or "").strip()
    if requirement_text:
        context_parts.append(f"Simulation requirement:\n{requirement_text}")

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
- Keep the same writing style, tone, and language as the original text

## Text to Continue
{input_text}

Continue the text naturally, ensuring logical coherence with the knowledge graph context above. Write in the same language as the input text."""
    
    return enhanced_prompt


async def get_enhanced_prompt(
    project_id: str,
    op_type: str,
    input_text: str,
    base_prompt: str,
    db: AsyncSession,
) -> str:
    """Get an enhanced prompt for operations that benefit from graph context.
    
    Currently enhances: CONTINUE, CREATE (when project has existing content)
    """
    if op_type not in ("CONTINUE", "CREATE"):
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
    if not has_graph and not has_oasis:
        return base_prompt

    graph_context = {"entities": [], "relationships": [], "insights": []}
    if has_graph:
        graph_context = await get_graph_context(project_id)

    if not graph_context["insights"] and not graph_context["relationships"] and not has_oasis:
        return base_prompt
    
    return build_prediction_prompt(
        input_text,
        graph_context,
        project.oasis_analysis if isinstance(project.oasis_analysis, dict) else None,
        project.simulation_requirement,
        base_prompt,
    )
