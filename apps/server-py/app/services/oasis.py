import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import PaymentConfig
from app.services.ai import DEFAULT_MODEL, call_llm
from app.services.graph_service import get_graph_visualization, search_graph
from app.services.llm_runtime import default_llm_runtime_config, normalize_llm_runtime_config
from app.services.llm_json import StrictJsonSchemaModel, extract_json_object

logger = logging.getLogger(__name__)

OASIS_ANALYSIS_MAX_TOKENS = 4096
OASIS_SIMULATION_CONFIG_MAX_TOKENS = 2048
OASIS_REPORT_MAX_TOKENS = 4096
OASIS_JSON_MAX_ATTEMPTS = 3


class OasisContinuationGuidance(StrictJsonSchemaModel):
    must_follow: list[str]
    next_steps: list[str]
    avoid: list[str]


class OasisAgentProfile(StrictJsonSchemaModel):
    name: str
    role: str
    persona: str
    stance: str
    likely_actions: list[str]


class OasisAnalysisResponse(StrictJsonSchemaModel):
    scenario_summary: str
    continuation_guidance: OasisContinuationGuidance
    agent_profiles: list[OasisAgentProfile]


class OasisTimeConfig(StrictJsonSchemaModel):
    total_hours: int
    minutes_per_round: int
    peak_hours: list[int]
    off_peak_hours: list[int]


class OasisEvent(StrictJsonSchemaModel):
    title: str
    trigger_hour: int
    description: str


class OasisAgentActivity(StrictJsonSchemaModel):
    name: str
    activity_level: float
    actions_per_hour: float
    response_delay_minutes: int
    stance: str


class OasisSimulationConfigResponse(StrictJsonSchemaModel):
    time_config: OasisTimeConfig
    events: list[OasisEvent]
    agent_activity: list[OasisAgentActivity]


class OasisReportResponse(StrictJsonSchemaModel):
    title: str
    executive_summary: str
    key_findings: list[str]
    next_actions: list[str]
    markdown: str


DEFAULT_OASIS_CONFIG: dict[str, Any] = {
    "analysis_prompt_prefix": "",
    "simulation_prompt_prefix": "",
    "report_prompt_prefix": "",
    "max_agent_profiles": 16,
    "max_events": 16,
    "max_agent_activity": 48,
    "min_total_hours": 6,
    "max_total_hours": 336,
    "min_minutes_per_round": 10,
    "max_minutes_per_round": 240,
    "max_actions_per_hour": 20.0,
    "max_response_delay_minutes": 720,
    **default_llm_runtime_config(),
}

def normalize_oasis_config(raw: Any) -> dict[str, Any]:
    cfg = raw if isinstance(raw, dict) else {}
    payload = dict(DEFAULT_OASIS_CONFIG)

    payload["analysis_prompt_prefix"] = str(cfg.get("analysis_prompt_prefix") or "").strip()
    payload["simulation_prompt_prefix"] = str(cfg.get("simulation_prompt_prefix") or "").strip()
    payload["report_prompt_prefix"] = str(cfg.get("report_prompt_prefix") or "").strip()

    try:
        payload["max_agent_profiles"] = max(1, min(64, int(cfg.get("max_agent_profiles", payload["max_agent_profiles"]))))
    except (TypeError, ValueError):
        pass
    try:
        payload["max_events"] = max(1, min(64, int(cfg.get("max_events", payload["max_events"]))))
    except (TypeError, ValueError):
        pass
    try:
        payload["max_agent_activity"] = max(1, min(128, int(cfg.get("max_agent_activity", payload["max_agent_activity"]))))
    except (TypeError, ValueError):
        pass
    try:
        payload["min_total_hours"] = max(1, min(720, int(cfg.get("min_total_hours", payload["min_total_hours"]))))
    except (TypeError, ValueError):
        pass
    try:
        payload["max_total_hours"] = max(1, min(720, int(cfg.get("max_total_hours", payload["max_total_hours"]))))
    except (TypeError, ValueError):
        pass
    if payload["min_total_hours"] > payload["max_total_hours"]:
        payload["min_total_hours"], payload["max_total_hours"] = payload["max_total_hours"], payload["min_total_hours"]

    try:
        payload["min_minutes_per_round"] = max(1, min(720, int(cfg.get("min_minutes_per_round", payload["min_minutes_per_round"]))))
    except (TypeError, ValueError):
        pass
    try:
        payload["max_minutes_per_round"] = max(1, min(720, int(cfg.get("max_minutes_per_round", payload["max_minutes_per_round"]))))
    except (TypeError, ValueError):
        pass
    if payload["min_minutes_per_round"] > payload["max_minutes_per_round"]:
        payload["min_minutes_per_round"], payload["max_minutes_per_round"] = payload["max_minutes_per_round"], payload["min_minutes_per_round"]

    try:
        payload["max_actions_per_hour"] = max(0.2, min(100.0, float(cfg.get("max_actions_per_hour", payload["max_actions_per_hour"]))))
    except (TypeError, ValueError):
        pass
    try:
        payload["max_response_delay_minutes"] = max(1, min(2880, int(cfg.get("max_response_delay_minutes", payload["max_response_delay_minutes"]))))
    except (TypeError, ValueError):
        pass
    payload.update(normalize_llm_runtime_config(cfg))
    return payload


async def load_oasis_config(db: AsyncSession | None = None) -> dict[str, Any]:
    if db is None:
        return dict(DEFAULT_OASIS_CONFIG)
    result = await db.execute(select(PaymentConfig).where(PaymentConfig.type == "oasis"))
    item = result.scalar_one_or_none()
    cfg = None
    if item is not None:
        maybe_config = getattr(item, "config", None)
        if isinstance(maybe_config, dict):
            cfg = maybe_config
    return normalize_oasis_config(cfg)


def _as_text_list(results: list[dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    for item in results:
        text = str(item.get("content") or "").strip()
        if text:
            texts.append(text)
    return texts


async def collect_graph_context(project_id: str, prompt: str | None = None, *, db: AsyncSession | None = None) -> dict[str, Any]:
    focus = (prompt or "").strip() or "core entities, relationships, conflicts, and scenario progression"
    tasks = [
        search_graph(project_id, f"{focus}. Key stakeholders and roles.", "INSIGHTS", 10, db=db),
        search_graph(project_id, f"{focus}. Relationship structure and influence paths.", "GRAPH_COMPLETION", 8, db=db),
        search_graph(project_id, f"{focus}. Risks, controversies, and failure signals.", "GRAPH_SUMMARY_COMPLETION", 8, db=db),
        search_graph(project_id, f"{focus}. Timeline and event evolution.", "SUMMARIES", 8, db=db),
        get_graph_visualization(project_id, db=db),
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
def _build_retry_prompt(base_prompt: str, reason: str, raw_content: str) -> str:
    preview = str(raw_content or "").strip()[:1200]
    retry_note = (
        "\n\nIMPORTANT: The previous response was invalid for downstream parsing. "
        f"Reason: {reason}. "
        "Return exactly one complete JSON object matching the requested schema, with all required fields non-empty. "
        "Do not include markdown fences or extra commentary."
    )
    if preview:
        retry_note += f"\nPrevious response preview:\n{preview}"
    return f"{base_prompt}{retry_note}"


async def _call_llm_json_with_validation(
    *,
    model: str,
    prompt: str,
    db: AsyncSession,
    max_tokens: int,
    response_schema: type[StrictJsonSchemaModel],
    validator,
    max_attempts: int = OASIS_JSON_MAX_ATTEMPTS,
) -> dict[str, Any]:
    last_error: ValueError | None = None
    retry_prompt = prompt
    safe_attempts = max(1, int(max_attempts or 1))
    for attempt in range(safe_attempts):
        llm_result = await call_llm(
            model,
            retry_prompt,
            db,
            max_tokens=max_tokens,
            prefer_stream_override=False,
            stream_fallback_nonstream_override=False,
            response_schema=response_schema,
        )
        raw_content = str(llm_result.get("content") or "")
        parsed = extract_json_object(raw_content)
        if not isinstance(parsed, dict):
            last_error = ValueError("response_not_json_or_invalid_schema")
            logger.warning(
                "OASIS JSON response parse failed on attempt %s (preview=%s)",
                attempt + 1,
                raw_content[:400],
            )
            retry_prompt = _build_retry_prompt(prompt, str(last_error), raw_content)
            continue

        try:
            return validator(parsed)
        except ValueError as exc:
            last_error = exc
            logger.warning(
                "OASIS JSON response validation failed on attempt %s: %s",
                attempt + 1,
                exc,
            )
            retry_prompt = _build_retry_prompt(prompt, str(exc), raw_content)
    if last_error is not None:
        raise last_error
    raise ValueError("response_not_json_or_invalid_schema")

def _validate_oasis_report_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("oasis_report_llm_response_not_json_or_invalid_schema")

    title = str(payload.get("title") or "").strip()
    if not title:
        raise ValueError("oasis_report_title_missing")
    summary = str(payload.get("executive_summary") or "").strip()
    if not summary:
        raise ValueError("oasis_report_executive_summary_missing")

    key_findings = _safe_list(payload.get("key_findings"), 10)
    if not key_findings:
        raise ValueError("oasis_report_key_findings_missing")

    next_actions = _safe_list(payload.get("next_actions"), 10)
    if not next_actions:
        raise ValueError("oasis_report_next_actions_missing")

    markdown = str(payload.get("markdown") or "").strip()
    if not markdown:
        raise ValueError("oasis_report_markdown_missing")

    return {
        "title": title,
        "executive_summary": summary,
        "key_findings": key_findings,
        "next_actions": next_actions,
        "markdown": markdown,
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


def _safe_agent_profiles(
    value: Any,
    max_items: int = 16,
    *,
    strict: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    profiles: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        role = str(item.get("role") or "").strip()
        persona = str(item.get("persona") or "").strip()
        stance = str(item.get("stance") or "").strip()
        if not name:
            continue
        if strict and (not role or not persona or not stance):
            continue
        role = role or "Participant"
        persona = persona or f"{name} profile"
        stance = (stance or "neutral").strip().lower()
        profiles.append(
            {
                "name": name,
                "role": role,
                "persona": persona,
                "stance": stance,
                "likely_actions": _safe_list(item.get("likely_actions"), 6),
            }
        )
        if len(profiles) >= max_items:
            break
    return profiles


def _safe_agent_activity(
    value: Any,
    max_items: int = 32,
    *,
    max_actions_per_hour: float = 20.0,
    max_response_delay_minutes: int = 720,
    strict: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        stance = str(item.get("stance") or "").strip()
        activity_raw = item.get("activity_level")
        actions_raw = item.get("actions_per_hour")
        delay_raw = item.get("response_delay_minutes")
        if not name:
            continue
        if strict and (
            not stance
            or activity_raw is None
            or actions_raw is None
            or delay_raw is None
        ):
            continue
        try:
            activity_level = float(0.5 if activity_raw is None else activity_raw)
            actions_per_hour = float(1.0 if actions_raw is None else actions_raw)
            response_delay_minutes = int(45 if delay_raw is None else delay_raw)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "name": name,
                "activity_level": max(0.0, min(1.0, activity_level)),
                "actions_per_hour": max(0.0, min(max_actions_per_hour, actions_per_hour)),
                "response_delay_minutes": max(1, min(max_response_delay_minutes, response_delay_minutes)),
                "stance": (stance or "neutral").strip().lower(),
            }
        )
        if len(rows) >= max_items:
            break
    return rows


def sanitize_oasis_simulation_config(
    data: dict[str, Any],
    profiles: list[dict[str, Any]],
    *,
    max_events: int = 16,
    max_agent_activity: int = 48,
    min_total_hours: int = 6,
    max_total_hours: int = 336,
    min_minutes_per_round: int = 10,
    max_minutes_per_round: int = 240,
    max_actions_per_hour: float = 20.0,
    max_response_delay_minutes: int = 720,
    strict: bool = False,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        if strict:
            raise ValueError("simulation_config_not_object")
        data = {}

    normalized_profiles = _safe_agent_profiles(
        profiles,
        max_items=max(1, min(64, int(max_agent_activity or 48))),
        strict=False,
    )
    if strict and not normalized_profiles:
        raise ValueError("simulation_profiles_empty")

    raw_time_cfg = data.get("time_config")
    if strict and not isinstance(raw_time_cfg, dict):
        raise ValueError("simulation_time_config_missing")
    time_cfg_raw = raw_time_cfg if isinstance(raw_time_cfg, dict) else {}

    if strict:
        try:
            total_hours = int(time_cfg_raw.get("total_hours"))
            minutes_per_round = int(time_cfg_raw.get("minutes_per_round"))
        except (TypeError, ValueError):
            raise ValueError("simulation_time_config_invalid_numbers") from None
    else:
        total_hours = _to_int(time_cfg_raw.get("total_hours"), 72)
        minutes_per_round = _to_int(time_cfg_raw.get("minutes_per_round"), 60)

    peak_raw = time_cfg_raw.get("peak_hours")
    off_peak_raw = time_cfg_raw.get("off_peak_hours")
    if strict and (not isinstance(peak_raw, list) or not isinstance(off_peak_raw, list)):
        raise ValueError("simulation_time_config_missing_hours")

    peak_hours = [
        int(x)
        for x in (peak_raw if isinstance(peak_raw, list) else [19, 20, 21, 22])
        if isinstance(x, (int, float)) and 0 <= int(x) <= 23
    ][:8]
    off_peak_hours = [
        int(x)
        for x in (off_peak_raw if isinstance(off_peak_raw, list) else [1, 2, 3, 4])
        if isinstance(x, (int, float)) and 0 <= int(x) <= 23
    ][:8]
    if strict and (not peak_hours or not off_peak_hours):
        raise ValueError("simulation_time_config_invalid_hours")
    if not peak_hours:
        peak_hours = [19, 20, 21, 22]
    if not off_peak_hours:
        off_peak_hours = [1, 2, 3, 4]

    events_raw = data.get("events")
    if strict and not isinstance(events_raw, list):
        raise ValueError("simulation_events_missing")
    event_items: list[dict[str, Any]] = []
    for item in (events_raw if isinstance(events_raw, list) else []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        trigger_hour = _to_int(item.get("trigger_hour"), 0)
        if not title:
            continue
        event_items.append(
            {
                "title": title,
                "trigger_hour": max(0, min(168, trigger_hour)),
                "description": str(item.get("description") or "").strip(),
            }
        )
        if len(event_items) >= max(1, min(64, int(max_events or 16))):
            break

    agent_activity = _safe_agent_activity(
        data.get("agent_activity"),
        max(1, min(128, int(max_agent_activity or 48))),
        max_actions_per_hour=max(0.2, float(max_actions_per_hour or 20.0)),
        max_response_delay_minutes=max(1, int(max_response_delay_minutes or 720)),
        strict=strict,
    )
    if not agent_activity:
        if strict:
            raise ValueError("simulation_agent_activity_empty")
        agent_activity = [
            {
                "name": str(profile.get("name") or "").strip(),
                "activity_level": 0.6,
                "actions_per_hour": max(0.2, min(max_actions_per_hour, 1.2)),
                "response_delay_minutes": max(1, min(max_response_delay_minutes, 45)),
                "stance": str(profile.get("stance") or "neutral").strip().lower() or "neutral",
            }
            for profile in normalized_profiles
            if str(profile.get("name") or "").strip()
        ][: max(1, min(128, int(max_agent_activity or 48)))]

    bounded_min_total_hours = max(1, min(720, int(min_total_hours or 6)))
    bounded_max_total_hours = max(1, min(720, int(max_total_hours or 336)))
    if bounded_min_total_hours > bounded_max_total_hours:
        bounded_min_total_hours, bounded_max_total_hours = bounded_max_total_hours, bounded_min_total_hours

    bounded_min_minutes = max(1, min(720, int(min_minutes_per_round or 10)))
    bounded_max_minutes = max(1, min(720, int(max_minutes_per_round or 240)))
    if bounded_min_minutes > bounded_max_minutes:
        bounded_min_minutes, bounded_max_minutes = bounded_max_minutes, bounded_min_minutes

    return {
        "time_config": {
            "total_hours": max(bounded_min_total_hours, min(bounded_max_total_hours, total_hours)),
            "minutes_per_round": max(bounded_min_minutes, min(bounded_max_minutes, minutes_per_round)),
            "peak_hours": peak_hours,
            "off_peak_hours": off_peak_hours,
        },
        "events": event_items,
        "agent_activity": agent_activity,
    }


def sanitize_oasis_analysis(
    data: dict[str, Any],
    graph_context: dict[str, Any],
    *,
    max_agent_profiles: int = 16,
    strict: bool = False,
) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    summary = str(payload.get("scenario_summary") or "").strip()
    sanitized = {
        "scenario_summary": summary,
        "continuation_guidance": {
            "must_follow": _safe_list((payload.get("continuation_guidance") or {}).get("must_follow"), 8)
            if isinstance(payload.get("continuation_guidance"), dict)
            else [],
            "next_steps": _safe_list((payload.get("continuation_guidance") or {}).get("next_steps"), 8)
            if isinstance(payload.get("continuation_guidance"), dict)
            else [],
            "avoid": _safe_list((payload.get("continuation_guidance") or {}).get("avoid"), 8)
            if isinstance(payload.get("continuation_guidance"), dict)
            else [],
        },
        "agent_profiles": _safe_agent_profiles(
            payload.get("agent_profiles"),
            max_items=max(1, min(64, int(max_agent_profiles or 16))),
            strict=strict,
        ),
    }
    if strict and not sanitized["scenario_summary"]:
        raise ValueError("oasis_analysis_summary_empty")
    if strict and not sanitized["agent_profiles"]:
        raise ValueError("oasis_analysis_agent_profiles_empty")
    return sanitized


async def generate_oasis_analysis(
    *,
    project_id: str,
    text: str,
    ontology: dict[str, Any] | None,
    requirement: str | None,
    prompt: str | None,
    model: str | None,
    oasis_config: dict[str, Any] | None = None,
    db: AsyncSession,
) -> tuple[dict[str, Any], dict[str, Any]]:
    graph_context = await collect_graph_context(project_id, prompt=prompt, db=db)
    selected_model = (model or "").strip() or DEFAULT_MODEL
    content_text = (text or "").strip()
    if not content_text:
        raise ValueError("oasis_analysis_source_text_empty")

    cfg = normalize_oasis_config(oasis_config)
    prompt_prefix = str(cfg.get("analysis_prompt_prefix") or "").strip()
    prefix_block = f"Additional constraints:\n{prompt_prefix}\n\n" if prompt_prefix else ""
    llm_prompt = (
        "You are an OASIS simulation analyst. Build only the minimum analysis needed to prepare profiles and continue the scenario.\n"
        "Use the provided response schema.\n"
        "Keep the result minimal and concrete.\n\n"
        f"{prefix_block}"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Prompt Focus:\n{(prompt or '').strip()}\n\n"
        f"Ontology:\n{json.dumps(ontology or {}, ensure_ascii=False)[:5000]}\n\n"
        f"Graph Context:\n{json.dumps(graph_context, ensure_ascii=False)[:9000]}\n\n"
        f"Text:\n{content_text[:8000]}"
    )

    analysis_payload = await _call_llm_json_with_validation(
        model=selected_model,
        prompt=llm_prompt,
        db=db,
        max_tokens=OASIS_ANALYSIS_MAX_TOKENS,
        response_schema=OasisAnalysisResponse,
        validator=lambda parsed: sanitize_oasis_analysis(
            parsed,
            graph_context,
            max_agent_profiles=int(cfg.get("max_agent_profiles") or 16),
            strict=True,
        ),
        max_attempts=OASIS_JSON_MAX_ATTEMPTS,
    )
    return analysis_payload, graph_context


async def enrich_simulation_config(
    analysis: dict[str, Any],
    *,
    requirement: str | None,
    prompt: str | None,
    model: str | None,
    oasis_config: dict[str, Any] | None = None,
    db: AsyncSession,
) -> dict[str, Any]:
    selected_model = (model or "").strip() or DEFAULT_MODEL
    cfg = normalize_oasis_config(oasis_config)
    prompt_prefix = str(cfg.get("simulation_prompt_prefix") or "").strip()
    prefix_block = ["Additional constraints:", prompt_prefix, ""] if prompt_prefix else []
    profiles = analysis.get("agent_profiles") if isinstance(analysis, dict) else []
    guidance = analysis.get("continuation_guidance") if isinstance(analysis, dict) else {}
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("oasis_simulation_profiles_missing")
    sim_prompt = "\n".join(
        [
            "You are an OASIS simulation config planner for generic text analysis and scenario forecasting.",
            "Use the provided response schema.",
            "Rules:",
            "- This is not a social-media simulation.",
            "- Do not introduce platforms, posts, comments, hashtags, channels, or feed mechanics.",
            "- Keep event and agent lists concise and realistic.",
            "- Use only the provided agent roster.",
            *prefix_block,
            "Requirement:",
            (requirement or "").strip(),
            "",
            "Focus:",
            (prompt or "").strip(),
            "",
            "Summary:",
            str((analysis or {}).get("scenario_summary") or ""),
            "",
            "Guidance:",
            json.dumps(guidance or {}, ensure_ascii=False),
            "",
            "Agent Profiles:",
            json.dumps(profiles or [], ensure_ascii=False)[:7000],
        ]
    )

    return await _call_llm_json_with_validation(
        model=selected_model,
        prompt=sim_prompt,
        db=db,
        max_tokens=OASIS_SIMULATION_CONFIG_MAX_TOKENS,
        response_schema=OasisSimulationConfigResponse,
        validator=lambda parsed: sanitize_oasis_simulation_config(
            parsed,
            profiles if isinstance(profiles, list) else [],
            max_events=int(cfg.get("max_events") or 16),
            max_agent_activity=int(cfg.get("max_agent_activity") or 48),
            min_total_hours=int(cfg.get("min_total_hours") or 6),
            max_total_hours=int(cfg.get("max_total_hours") or 336),
            min_minutes_per_round=int(cfg.get("min_minutes_per_round") or 10),
            max_minutes_per_round=int(cfg.get("max_minutes_per_round") or 240),
            max_actions_per_hour=float(cfg.get("max_actions_per_hour") or 20.0),
            max_response_delay_minutes=int(cfg.get("max_response_delay_minutes") or 720),
            strict=True,
        ),
        max_attempts=OASIS_JSON_MAX_ATTEMPTS,
    )


async def analyze_and_enrich_oasis(
    *,
    project_id: str,
    text: str,
    ontology: dict[str, Any] | None,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str | None,
    simulation_model: str | None,
    oasis_config: dict[str, Any] | None = None,
    db: AsyncSession,
) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis, context = await generate_oasis_analysis(
        project_id=project_id,
        text=text,
        ontology=ontology,
        requirement=requirement,
        prompt=prompt,
        model=analysis_model,
        oasis_config=oasis_config,
        db=db,
    )
    analysis["simulation_config"] = await enrich_simulation_config(
        analysis,
        requirement=requirement,
        prompt=prompt,
        model=simulation_model,
        oasis_config=oasis_config,
        db=db,
    )
    return analysis, context
def build_oasis_package(
    *,
    project_id: str,
    project_title: str,
    requirement: str | None,
    ontology: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
    component_models: dict[str, Any] | None = None,
    oasis_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis_data = analysis if isinstance(analysis, dict) else {}
    cfg = normalize_oasis_config(oasis_config)

    scenario_summary = str(analysis_data.get("scenario_summary") or "").strip()
    if not scenario_summary:
        raise ValueError("oasis_package_analysis_summary_missing")

    profiles = _safe_agent_profiles(
        analysis_data.get("agent_profiles"),
        max_items=max(1, min(64, int(cfg.get("max_agent_profiles") or 16))),
        strict=True,
    )
    if not profiles:
        raise ValueError("oasis_package_agent_profiles_missing")

    raw_sim_cfg = analysis_data.get("simulation_config") if isinstance(analysis_data.get("simulation_config"), dict) else {}
    if not raw_sim_cfg:
        raise ValueError("oasis_package_simulation_config_missing")
    sim_cfg = sanitize_oasis_simulation_config(
        raw_sim_cfg,
        profiles,
        max_events=int(cfg.get("max_events") or 16),
        max_agent_activity=int(cfg.get("max_agent_activity") or 48),
        min_total_hours=int(cfg.get("min_total_hours") or 6),
        max_total_hours=int(cfg.get("max_total_hours") or 336),
        min_minutes_per_round=int(cfg.get("min_minutes_per_round") or 10),
        max_minutes_per_round=int(cfg.get("max_minutes_per_round") or 240),
        max_actions_per_hour=float(cfg.get("max_actions_per_hour") or 20.0),
        max_response_delay_minutes=int(cfg.get("max_response_delay_minutes") or 720),
        strict=True,
    )

    simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
    return {
        "simulation_id": simulation_id,
        "project_id": project_id,
        "simulation_requirement": (requirement or "").strip(),
        "profiles": profiles,
        "simulation_config": sim_cfg,
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

    total_actions_per_hour = sum(
        max(0.0, min(20.0, _to_float(item.get("actions_per_hour"), 0.0)))
        for item in agent_activity
        if isinstance(item, dict)
    )
    estimated_actions = int(round(total_actions_per_hour * total_hours)) if total_actions_per_hour > 0 else active_agents * total_hours

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

    return {
        "run_id": f"run_{uuid.uuid4().hex[:12]}",
        "simulation_id": str(pkg.get("simulation_id") or f"sim_{uuid.uuid4().hex[:12]}"),
        "status": "completed",
        "metrics": {
            "total_hours": total_hours,
            "minutes_per_round": minutes_per_round,
            "total_rounds": total_rounds,
            "active_agents": active_agents,
            "estimated_actions": estimated_actions,
            "event_count": len(normalized_events),
        },
    }


async def generate_oasis_report(
    *,
    package: dict[str, Any],
    analysis: dict[str, Any] | None,
    run_result: dict[str, Any] | None,
    requirement: str | None,
    model: str | None,
    oasis_config: dict[str, Any] | None = None,
    db: AsyncSession,
) -> dict[str, Any]:
    selected_model = (model or "").strip() or DEFAULT_MODEL
    cfg = normalize_oasis_config(oasis_config)
    prompt_prefix = str(cfg.get("report_prompt_prefix") or "").strip()
    prefix_block = f"Additional constraints:\n{prompt_prefix}\n\n" if prompt_prefix else ""
    analysis_data = analysis if isinstance(analysis, dict) else {}
    run_data = run_result if isinstance(run_result, dict) else {}
    report_id = f"report_{uuid.uuid4().hex[:12]}"
    generated_at = datetime.now(timezone.utc).isoformat()

    prompt = (
        "You are an OASIS simulation analyst. Generate a concise report.\n"
        "Use the provided response schema.\n"
        "Keep findings concrete and avoid hype.\n\n"
        f"{prefix_block}"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Package:\n{json.dumps(package, ensure_ascii=False)[:9000]}\n\n"
        f"Analysis:\n{json.dumps(analysis_data, ensure_ascii=False)[:9000]}\n\n"
        f"Run Result:\n{json.dumps(run_data, ensure_ascii=False)[:9000]}"
    )

    parsed = await _call_llm_json_with_validation(
        model=selected_model,
        prompt=prompt,
        db=db,
        max_tokens=OASIS_REPORT_MAX_TOKENS,
        response_schema=OasisReportResponse,
        validator=_validate_oasis_report_payload,
        max_attempts=OASIS_JSON_MAX_ATTEMPTS,
    )

    return {
        "report_id": report_id,
        "simulation_id": str(package.get("simulation_id") or ""),
        "generated_at": generated_at,
        "title": parsed["title"],
        "executive_summary": parsed["executive_summary"],
        "key_findings": parsed["key_findings"],
        "next_actions": parsed["next_actions"],
        "markdown": parsed["markdown"],
        "status": "completed",
    }
