import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai import DEFAULT_MODEL, call_llm
from app.services.cognee import get_graph_visualization, search_graph
from app.services.llm_json import extract_json_object


def _as_text_list(results: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for item in results:
        text = str(item.get("content") or "").strip()
        if text:
            texts.append(text)
    return texts


async def collect_graph_context(project_id: str, prompt: str | None = None) -> dict[str, Any]:
    focus = (prompt or "").strip() or "core entities, relationships, conflicts, and scenario progression"
    tasks = [
        search_graph(project_id, f"{focus}. Key stakeholders and roles.", "INSIGHTS", 10),
        search_graph(project_id, f"{focus}. Relationship structure and influence paths.", "GRAPH_COMPLETION", 8),
        search_graph(project_id, f"{focus}. Risks, controversies, and failure signals.", "GRAPH_SUMMARY_COMPLETION", 8),
        search_graph(project_id, f"{focus}. Timeline and event evolution.", "SUMMARIES", 8),
        get_graph_visualization(project_id),
    ]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    insights: list[dict[str, Any]] = raw[0] if isinstance(raw[0], list) else []
    relationships: list[dict[str, Any]] = raw[1] if isinstance(raw[1], list) else []
    risks: list[dict[str, Any]] = raw[2] if isinstance(raw[2], list) else []
    timeline: list[dict[str, Any]] = raw[3] if isinstance(raw[3], list) else []
    graph = raw[4] if isinstance(raw[4], dict) else {"nodes": [], "edges": []}

    return {
        "insights": _as_text_list(insights),
        "relationships": _as_text_list(relationships),
        "risk_signals": _as_text_list(risks),
        "timeline_signals": _as_text_list(timeline),
        "node_count": len(graph.get("nodes") or []),
        "edge_count": len(graph.get("edges") or []),
        "top_nodes": [
            {
                "label": str(n.get("label") or ""),
                "type": str(n.get("type") or "CONCEPT"),
            }
            for n in (graph.get("nodes") or [])[:16]
            if isinstance(n, dict)
        ],
    }


def _safe_list(value: Any, max_items: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            items.append(text)
        if len(items) >= max_items:
            break
    return items


def _safe_agent_profiles(value: Any, max_items: int = 16) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    profiles: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        role = str(item.get("role") or "").strip()
        persona = str(item.get("persona") or "").strip()
        if not name:
            continue
        profiles.append(
            {
                "name": name,
                "role": role,
                "persona": persona,
                "stance": str(item.get("stance") or "neutral").strip() or "neutral",
                "likely_actions": _safe_list(item.get("likely_actions"), 6),
            }
        )
        if len(profiles) >= max_items:
            break
    return profiles


def _safe_agent_activity(value: Any, max_items: int = 32) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "activity_level": max(0.0, min(1.0, float(item.get("activity_level") or 0.5))),
                "posts_per_hour": max(0.0, min(20.0, float(item.get("posts_per_hour") or 1.0))),
                "response_delay_minutes": max(1, min(720, int(item.get("response_delay_minutes") or 60))),
                "stance": str(item.get("stance") or "neutral").strip() or "neutral",
            }
        )
        if len(rows) >= max_items:
            break
    return rows


def sanitize_oasis_simulation_config(data: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    time_cfg = data.get("time_config") if isinstance(data.get("time_config"), dict) else {}
    events = data.get("events") if isinstance(data.get("events"), list) else []
    active_platforms = data.get("active_platforms") if isinstance(data.get("active_platforms"), list) else []
    if not active_platforms:
        active_platforms = ["twitter", "reddit"]

    event_items: list[dict[str, Any]] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        trigger_hour = int(item.get("trigger_hour") or 0)
        if not title:
            continue
        event_items.append(
            {
                "title": title,
                "trigger_hour": max(0, min(168, trigger_hour)),
                "description": str(item.get("description") or "").strip(),
            }
        )
        if len(event_items) >= 16:
            break

    agent_activity = _safe_agent_activity(data.get("agent_activity"), 48)
    if not agent_activity:
        for idx, profile in enumerate(profiles[:24]):
            name = str(profile.get("name") or f"Agent{idx + 1}")
            agent_activity.append(
                {
                    "name": name,
                    "activity_level": 0.45 + (idx % 6) * 0.08,
                    "posts_per_hour": 0.6 + (idx % 5) * 0.35,
                    "response_delay_minutes": 15 + (idx % 6) * 20,
                    "stance": str(profile.get("stance") or "neutral"),
                }
            )

    return {
        "active_platforms": [str(x).strip().lower() for x in active_platforms if str(x).strip()][:2] or ["twitter", "reddit"],
        "time_config": {
            "total_hours": max(6, min(336, int(time_cfg.get("total_hours") or 72))),
            "minutes_per_round": max(10, min(240, int(time_cfg.get("minutes_per_round") or 60))),
            "peak_hours": [
                int(x)
                for x in (time_cfg.get("peak_hours") or [19, 20, 21, 22])
                if isinstance(x, (int, float)) and 0 <= int(x) <= 23
            ][:8]
            or [19, 20, 21, 22],
            "off_peak_hours": [
                int(x)
                for x in (time_cfg.get("off_peak_hours") or [1, 2, 3, 4, 5])
                if isinstance(x, (int, float)) and 0 <= int(x) <= 23
            ][:8]
            or [1, 2, 3, 4, 5],
        },
        "events": event_items,
        "agent_activity": agent_activity,
    }


def sanitize_oasis_analysis(data: dict[str, Any], graph_context: dict[str, Any]) -> dict[str, Any]:
    summary = str(data.get("scenario_summary") or "").strip()
    return {
        "scenario_summary": summary,
        "key_drivers": _safe_list(data.get("key_drivers"), 10),
        "risk_signals": _safe_list(data.get("risk_signals"), 10),
        "opportunity_signals": _safe_list(data.get("opportunity_signals"), 10),
        "timeline": _safe_list(data.get("timeline"), 10),
        "continuation_guidance": {
            "must_follow": _safe_list((data.get("continuation_guidance") or {}).get("must_follow"), 8)
            if isinstance(data.get("continuation_guidance"), dict)
            else [],
            "next_steps": _safe_list((data.get("continuation_guidance") or {}).get("next_steps"), 8)
            if isinstance(data.get("continuation_guidance"), dict)
            else [],
            "avoid": _safe_list((data.get("continuation_guidance") or {}).get("avoid"), 8)
            if isinstance(data.get("continuation_guidance"), dict)
            else [],
        },
        "agent_profiles": _safe_agent_profiles(data.get("agent_profiles")),
        "evidence": {
            "insight_count": len(graph_context.get("insights") or []),
            "relationship_count": len(graph_context.get("relationships") or []),
            "risk_count": len(graph_context.get("risk_signals") or []),
            "node_count": int(graph_context.get("node_count") or 0),
            "edge_count": int(graph_context.get("edge_count") or 0),
        },
    }


def fallback_oasis_analysis(
    requirement: str | None,
    ontology: dict[str, Any] | None,
    graph_context: dict[str, Any],
) -> dict[str, Any]:
    entity_names = [
        str(item.get("name") or "")
        for item in (ontology or {}).get("entity_types", [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ][:10]
    guidance = [
        "Keep entity relationships consistent with the knowledge graph.",
        "Advance existing conflicts before introducing new branches.",
        "Ground new events in known stakeholders and motives.",
    ]
    if requirement:
        guidance.insert(0, f"Align with requirement: {requirement[:160]}")

    return {
        "scenario_summary": "OASIS analysis generated with fallback strategy due to limited structured model output.",
        "key_drivers": entity_names or ["CORE_CONCEPTS"],
        "risk_signals": (graph_context.get("risk_signals") or [])[:8],
        "opportunity_signals": (graph_context.get("insights") or [])[:8],
        "timeline": (graph_context.get("timeline_signals") or [])[:8],
        "continuation_guidance": {
            "must_follow": guidance,
            "next_steps": [
                "Reinforce cause-effect links between major entities.",
                "Reveal one high-impact relationship shift in the next section.",
            ],
            "avoid": ["Introducing unrelated entities without graph support."],
        },
        "agent_profiles": [],
        "simulation_config": {
            "active_platforms": ["twitter", "reddit"],
            "time_config": {
                "total_hours": 72,
                "minutes_per_round": 60,
                "peak_hours": [19, 20, 21, 22],
                "off_peak_hours": [1, 2, 3, 4, 5],
            },
            "events": [],
            "agent_activity": [],
        },
        "evidence": {
            "insight_count": len(graph_context.get("insights") or []),
            "relationship_count": len(graph_context.get("relationships") or []),
            "risk_count": len(graph_context.get("risk_signals") or []),
            "node_count": int(graph_context.get("node_count") or 0),
            "edge_count": int(graph_context.get("edge_count") or 0),
        },
    }


async def generate_oasis_analysis(
    *,
    project_id: str,
    text: str,
    ontology: dict[str, Any] | None,
    requirement: str | None,
    prompt: str | None,
    model: str | None,
    db: AsyncSession,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph_context = await collect_graph_context(project_id, prompt=prompt)
    selected_model = (model or "").strip() or DEFAULT_MODEL
    content_text = (text or "").strip()

    llm_prompt = (
        "You are an OASIS simulation analyst. Build a structured analysis for downstream continuation generation.\n"
        "Return JSON only with this exact schema:\n"
        "{\n"
        '  "scenario_summary": "...",\n'
        '  "key_drivers": ["..."],\n'
        '  "risk_signals": ["..."],\n'
        '  "opportunity_signals": ["..."],\n'
        '  "timeline": ["..."],\n'
        '  "continuation_guidance": {"must_follow":["..."], "next_steps":["..."], "avoid":["..."]},\n'
        '  "agent_profiles": [{"name":"...", "role":"...", "persona":"...", "stance":"...", "likely_actions":["..."]}]\n'
        "}\n"
        "Use concise, factual language. Keep each list item short.\n\n"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Prompt Focus:\n{(prompt or '').strip()}\n\n"
        f"Ontology:\n{json.dumps(ontology or {}, ensure_ascii=False)[:5000]}\n\n"
        f"Graph Context:\n{json.dumps(graph_context, ensure_ascii=False)[:9000]}\n\n"
        f"Text:\n{content_text[:8000]}"
    )

    try:
        llm_result = await call_llm(selected_model, llm_prompt, db)
        parsed = extract_json_object(str(llm_result.get("content") or ""))
        if parsed:
            return sanitize_oasis_analysis(parsed, graph_context), graph_context
    except Exception:
        pass

    return fallback_oasis_analysis(requirement, ontology, graph_context), graph_context


async def enrich_simulation_config(
    analysis: dict[str, Any],
    *,
    requirement: str | None,
    prompt: str | None,
    model: str | None,
    db: AsyncSession,
) -> dict[str, Any]:
    selected_model = (model or "").strip() or DEFAULT_MODEL
    profiles = analysis.get("agent_profiles") if isinstance(analysis, dict) else []
    guidance = analysis.get("continuation_guidance") if isinstance(analysis, dict) else {}
    sim_prompt = (
        "You are an OASIS simulation config planner. Return JSON only.\n"
        "Schema:\n"
        "{\n"
        '  "active_platforms": ["twitter","reddit"],\n'
        '  "time_config": {"total_hours":72, "minutes_per_round":60, "peak_hours":[19,20,21,22], "off_peak_hours":[1,2,3,4,5]},\n'
        '  "events": [{"title":"...", "trigger_hour":12, "description":"..."}],\n'
        '  "agent_activity": [{"name":"...", "activity_level":0.6, "posts_per_hour":1.2, "response_delay_minutes":45, "stance":"..."}]\n'
        "}\n"
        "Keep event and agent lists concise and realistic.\n\n"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Focus:\n{(prompt or '').strip()}\n\n"
        f"Summary:\n{str((analysis or {}).get('scenario_summary') or '')}\n\n"
        f"Guidance:\n{json.dumps(guidance or {}, ensure_ascii=False)}\n\n"
        f"Agent Profiles:\n{json.dumps(profiles or [], ensure_ascii=False)[:7000]}"
    )

    try:
        llm_result = await call_llm(selected_model, sim_prompt, db)
        parsed = extract_json_object(str(llm_result.get("content") or ""))
        if parsed:
            return sanitize_oasis_simulation_config(parsed, profiles if isinstance(profiles, list) else [])
    except Exception:
        pass

    return sanitize_oasis_simulation_config({}, profiles if isinstance(profiles, list) else [])


async def analyze_and_enrich_oasis(
    *,
    project_id: str,
    text: str,
    ontology: dict[str, Any] | None,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str | None,
    simulation_model: str | None,
    db: AsyncSession,
) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis, context = await generate_oasis_analysis(
        project_id=project_id,
        text=text,
        ontology=ontology,
        requirement=requirement,
        prompt=prompt,
        model=analysis_model,
        db=db,
    )
    analysis["simulation_config"] = await enrich_simulation_config(
        analysis,
        requirement=requirement,
        prompt=prompt,
        model=simulation_model,
        db=db,
    )
    return analysis, context


def _fallback_profiles_from_ontology(ontology: dict[str, Any] | None, limit: int = 20) -> list[dict[str, Any]]:
    entity_types = (ontology or {}).get("entity_types") if isinstance(ontology, dict) else []
    profiles: list[dict[str, Any]] = []
    if not isinstance(entity_types, list):
        return profiles
    for idx, entity in enumerate(entity_types):
        if not isinstance(entity, dict):
            continue
        name = str(entity.get("name") or "").strip()
        if not name:
            continue
        profiles.append(
            {
                "name": f"{name}_AGENT_{idx + 1}",
                "role": name,
                "persona": str(entity.get("description") or f"{name} participant"),
                "stance": "neutral",
                "likely_actions": ["comment", "share", "respond"],
            }
        )
        if len(profiles) >= limit:
            break
    return profiles


def build_oasis_package(
    *,
    project_id: str,
    project_title: str,
    requirement: str | None,
    ontology: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    component_models: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis_data = analysis if isinstance(analysis, dict) else {}
    sim_cfg = analysis_data.get("simulation_config") if isinstance(analysis_data.get("simulation_config"), dict) else {}
    profiles = analysis_data.get("agent_profiles") if isinstance(analysis_data.get("agent_profiles"), list) else []
    if not profiles:
        profiles = _fallback_profiles_from_ontology(ontology)

    simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
    prepared_at = datetime.utcnow().isoformat() + "Z"
    return {
        "simulation_id": simulation_id,
        "project_id": project_id,
        "project_title": project_title,
        "prepared_at": prepared_at,
        "simulation_requirement": (requirement or "").strip(),
        "ontology": ontology or {},
        "analysis_summary": str(analysis_data.get("scenario_summary") or ""),
        "continuation_guidance": analysis_data.get("continuation_guidance") or {},
        "profiles": profiles,
        "simulation_config": sim_cfg or sanitize_oasis_simulation_config({}, profiles),
        "component_models": component_models if isinstance(component_models, dict) else {},
    }


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_oasis_run_result(
    *,
    package: dict[str, Any],
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pkg = package if isinstance(package, dict) else {}
    sim_cfg = pkg.get("simulation_config") if isinstance(pkg.get("simulation_config"), dict) else {}
    time_cfg = sim_cfg.get("time_config") if isinstance(sim_cfg.get("time_config"), dict) else {}
    events = sim_cfg.get("events") if isinstance(sim_cfg.get("events"), list) else []
    agent_activity = sim_cfg.get("agent_activity") if isinstance(sim_cfg.get("agent_activity"), list) else []
    profiles = pkg.get("profiles") if isinstance(pkg.get("profiles"), list) else []
    total_hours = max(1, min(336, _to_int(time_cfg.get("total_hours"), 72)))
    minutes_per_round = max(1, min(240, _to_int(time_cfg.get("minutes_per_round"), 60)))
    total_rounds = max(1, (total_hours * 60) // minutes_per_round)
    active_agents = len(agent_activity) if agent_activity else len(profiles)

    total_posts_per_hour = sum(
        max(0.0, min(20.0, _to_float(item.get("posts_per_hour"), 0.0)))
        for item in agent_activity
        if isinstance(item, dict)
    )
    estimated_posts = int(round(total_posts_per_hour * total_hours)) if total_posts_per_hour > 0 else active_agents * total_hours

    normalized_events: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        title = str(event.get("title") or "").strip()
        if not title:
            continue
        normalized_events.append(
            {
                "title": title,
                "trigger_hour": max(0, min(total_hours, _to_int(event.get("trigger_hour"), 0))),
                "description": str(event.get("description") or "").strip(),
            }
        )
    normalized_events.sort(key=lambda item: item["trigger_hour"])

    highlights: list[str] = [
        f"Simulation projected for {total_hours}h across {total_rounds} rounds.",
        f"Estimated active agents: {active_agents}.",
        f"Estimated generated posts: {estimated_posts}.",
    ]
    for event in normalized_events[:8]:
        highlights.append(f"H+{event['trigger_hour']}: {event['title']}")

    analysis_data = analysis if isinstance(analysis, dict) else {}
    risk_signals = _safe_list(analysis_data.get("risk_signals"), 8)
    opportunity_signals = _safe_list(analysis_data.get("opportunity_signals"), 8)

    now = datetime.now(timezone.utc).isoformat()
    return {
        "run_id": f"run_{uuid.uuid4().hex[:12]}",
        "simulation_id": str(pkg.get("simulation_id") or f"sim_{uuid.uuid4().hex[:12]}"),
        "status": "completed",
        "started_at": now,
        "completed_at": now,
        "metrics": {
            "total_hours": total_hours,
            "minutes_per_round": minutes_per_round,
            "total_rounds": total_rounds,
            "active_agents": active_agents,
            "estimated_posts": estimated_posts,
            "event_count": len(normalized_events),
        },
        "triggered_events": normalized_events,
        "highlights": highlights,
        "risk_signals": risk_signals,
        "opportunity_signals": opportunity_signals,
    }


def _fallback_report_markdown(
    *,
    requirement: str | None,
    analysis: dict[str, Any] | None,
    run_result: dict[str, Any] | None,
) -> str:
    analysis_data = analysis if isinstance(analysis, dict) else {}
    run_data = run_result if isinstance(run_result, dict) else {}
    metrics = run_data.get("metrics") if isinstance(run_data.get("metrics"), dict) else {}
    lines: list[str] = [
        "# OASIS Analysis Report",
        "",
        "## Scenario Summary",
        str(analysis_data.get("scenario_summary") or "No scenario summary available."),
        "",
    ]
    requirement_text = (requirement or "").strip()
    if requirement_text:
        lines.extend(
            [
                "## Simulation Requirement",
                requirement_text,
                "",
            ]
        )
    lines.extend(
        [
            "## Simulation Metrics",
            f"- Total Hours: {metrics.get('total_hours', '-')}",
            f"- Minutes Per Round: {metrics.get('minutes_per_round', '-')}",
            f"- Total Rounds: {metrics.get('total_rounds', '-')}",
            f"- Active Agents: {metrics.get('active_agents', '-')}",
            f"- Estimated Posts: {metrics.get('estimated_posts', '-')}",
            "",
        ]
    )

    risk_signals = _safe_list(analysis_data.get("risk_signals"), 8)
    if risk_signals:
        lines.append("## Risk Signals")
        lines.extend([f"- {item}" for item in risk_signals])
        lines.append("")

    opportunity_signals = _safe_list(analysis_data.get("opportunity_signals"), 8)
    if opportunity_signals:
        lines.append("## Opportunity Signals")
        lines.extend([f"- {item}" for item in opportunity_signals])
        lines.append("")

    next_steps = _safe_list(((analysis_data.get("continuation_guidance") or {}).get("next_steps")), 8) if isinstance(analysis_data.get("continuation_guidance"), dict) else []
    if next_steps:
        lines.append("## Recommended Next Steps")
        lines.extend([f"- {item}" for item in next_steps])
        lines.append("")

    return "\n".join(lines).strip()


async def generate_oasis_report(
    *,
    package: dict[str, Any],
    analysis: dict[str, Any] | None,
    run_result: dict[str, Any] | None,
    requirement: str | None,
    model: str | None,
    db: AsyncSession,
) -> dict[str, Any]:
    selected_model = (model or "").strip() or DEFAULT_MODEL
    analysis_data = analysis if isinstance(analysis, dict) else {}
    run_data = run_result if isinstance(run_result, dict) else {}
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    generated_at = datetime.now(timezone.utc).isoformat()

    prompt = (
        "You are an OASIS simulation analyst. Generate a concise report as JSON only.\n"
        "Schema:\n"
        "{\n"
        '  "title": "...",\n'
        '  "executive_summary": "...",\n'
        '  "key_findings": ["..."],\n'
        '  "next_actions": ["..."],\n'
        '  "markdown": "..."\n'
        "}\n"
        "Keep findings concrete and avoid hype.\n\n"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Package:\n{json.dumps(package, ensure_ascii=False)[:9000]}\n\n"
        f"Analysis:\n{json.dumps(analysis_data, ensure_ascii=False)[:9000]}\n\n"
        f"Run Result:\n{json.dumps(run_data, ensure_ascii=False)[:9000]}"
    )

    parsed: dict[str, Any] | None = None
    try:
        llm_result = await call_llm(selected_model, prompt, db)
        parsed = extract_json_object(str(llm_result.get("content") or ""))
    except Exception:
        parsed = None

    fallback_markdown = _fallback_report_markdown(
        requirement=requirement,
        analysis=analysis_data,
        run_result=run_data,
    )
    title = "OASIS Simulation Report"
    summary = str(analysis_data.get("scenario_summary") or "").strip() or "No summary available."
    key_findings = _safe_list(analysis_data.get("key_drivers"), 8)
    next_actions = _safe_list(
        ((analysis_data.get("continuation_guidance") or {}).get("next_steps")),
        8,
    ) if isinstance(analysis_data.get("continuation_guidance"), dict) else []
    markdown = fallback_markdown

    if isinstance(parsed, dict):
        parsed_title = str(parsed.get("title") or "").strip()
        parsed_summary = str(parsed.get("executive_summary") or "").strip()
        parsed_markdown = str(parsed.get("markdown") or "").strip()
        if parsed_title:
            title = parsed_title
        if parsed_summary:
            summary = parsed_summary
        if parsed_markdown:
            markdown = parsed_markdown
        parsed_findings = _safe_list(parsed.get("key_findings"), 10)
        parsed_actions = _safe_list(parsed.get("next_actions"), 10)
        if parsed_findings:
            key_findings = parsed_findings
        if parsed_actions:
            next_actions = parsed_actions

    return {
        "report_id": report_id,
        "simulation_id": str(package.get("simulation_id") or ""),
        "generated_at": generated_at,
        "title": title,
        "executive_summary": summary,
        "key_findings": key_findings,
        "next_actions": next_actions,
        "markdown": markdown,
        "status": "completed",
    }
