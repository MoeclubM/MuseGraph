import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import PaymentConfig
from app.services.ai import DEFAULT_MODEL, call_llm
from app.services.cognee import get_graph_visualization, search_graph
from app.services.llm_json import extract_json_object

logger = logging.getLogger(__name__)

OASIS_ANALYSIS_MAX_TOKENS = 4096
OASIS_SIMULATION_CONFIG_MAX_TOKENS = 2048
OASIS_JSON_MAX_ATTEMPTS = 3


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
    "llm_request_timeout_seconds": 180,
    "llm_retry_count": 4,
    "llm_retry_interval_seconds": 2.0,
    "llm_prefer_stream": True,
    "llm_stream_fallback_nonstream": True,
    "llm_task_concurrency": 1,
    "llm_model_default_concurrency": 8,
    "llm_model_concurrency_overrides": {},
}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_model_concurrency_overrides(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in raw.items():
        model_name = str(key or "").strip().lower()
        if not model_name:
            continue
        try:
            normalized[model_name] = max(1, min(64, int(value)))
        except (TypeError, ValueError):
            continue
    return normalized


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
    try:
        payload["llm_request_timeout_seconds"] = max(
            5,
            min(1800, int(cfg.get("llm_request_timeout_seconds", payload["llm_request_timeout_seconds"]))),
        )
    except (TypeError, ValueError):
        pass
    try:
        payload["llm_retry_count"] = max(
            0,
            min(10, int(cfg.get("llm_retry_count", payload["llm_retry_count"]))),
        )
    except (TypeError, ValueError):
        pass
    try:
        payload["llm_retry_interval_seconds"] = max(
            0.0,
            min(60.0, float(cfg.get("llm_retry_interval_seconds", payload["llm_retry_interval_seconds"]))),
        )
    except (TypeError, ValueError):
        pass
    payload["llm_prefer_stream"] = _as_bool(
        cfg.get("llm_prefer_stream", payload["llm_prefer_stream"]),
        bool(payload["llm_prefer_stream"]),
    )
    payload["llm_stream_fallback_nonstream"] = _as_bool(
        cfg.get("llm_stream_fallback_nonstream", payload["llm_stream_fallback_nonstream"]),
        bool(payload["llm_stream_fallback_nonstream"]),
    )
    try:
        payload["llm_task_concurrency"] = max(
            1,
            min(64, int(cfg.get("llm_task_concurrency", payload["llm_task_concurrency"]))),
        )
    except (TypeError, ValueError):
        pass
    try:
        payload["llm_model_default_concurrency"] = max(
            1,
            min(64, int(cfg.get("llm_model_default_concurrency", payload["llm_model_default_concurrency"]))),
        )
    except (TypeError, ValueError):
        pass
    payload["llm_model_concurrency_overrides"] = _normalize_model_concurrency_overrides(
        cfg.get("llm_model_concurrency_overrides")
    )
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


def _extract_named_json_value(raw: str, key: str) -> Any | None:
    text = str(raw or "")
    if not text:
        return None
    pattern = re.compile(rf'"{re.escape(key)}"\s*:')
    decoder = json.JSONDecoder()
    for match in pattern.finditer(text):
        idx = match.end()
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            continue
        try:
            value, _ = decoder.raw_decode(text[idx:])
            return value
        except Exception:
            continue
    return None


def _salvage_oasis_analysis_payload(raw_content: str) -> dict[str, Any] | None:
    payload = {
        "scenario_summary": _extract_named_json_value(raw_content, "scenario_summary"),
        "continuation_guidance": {
            "must_follow": _extract_named_json_value(raw_content, "must_follow"),
            "next_steps": _extract_named_json_value(raw_content, "next_steps"),
            "avoid": _extract_named_json_value(raw_content, "avoid"),
        },
        "agent_profiles": _extract_named_json_value(raw_content, "agent_profiles"),
    }
    if not any(value not in (None, "", [], {}) for value in payload.values()):
        return None
    return payload


def _salvage_oasis_simulation_config_payload(raw_content: str) -> dict[str, Any] | None:
    payload = {
        "time_config": _extract_named_json_value(raw_content, "time_config"),
        "events": _extract_named_json_value(raw_content, "events"),
        "agent_activity": _extract_named_json_value(raw_content, "agent_activity"),
    }
    if not any(value not in (None, "", [], {}) for value in payload.values()):
        return None
    return payload


async def _call_llm_json_with_validation(
    *,
    model: str,
    prompt: str,
    db: AsyncSession,
    max_tokens: int,
    validator,
    repairer=None,
    max_attempts: int = OASIS_JSON_MAX_ATTEMPTS,
) -> dict[str, Any]:
    last_error: ValueError | None = None
    retry_prompt = prompt
    safe_attempts = max(1, int(max_attempts or 1))
    for attempt in range(safe_attempts):
        llm_result = await call_llm(model, retry_prompt, db, max_tokens=max_tokens)
        raw_content = str(llm_result.get("content") or "")
        parsed = extract_json_object(raw_content)
        candidates: list[tuple[str, dict[str, Any]]] = []
        if isinstance(parsed, dict):
            candidates.append(("parsed", parsed))
        repaired = repairer(raw_content) if repairer else None
        if isinstance(repaired, dict) and repaired and all(repaired != candidate for _, candidate in candidates):
            candidates.append(("repaired", repaired))

        if not candidates:
            last_error = ValueError("response_not_json_or_invalid_schema")
            logger.warning(
                "OASIS JSON response parse failed on attempt %s (preview=%s)",
                attempt + 1,
                raw_content[:400],
            )
            retry_prompt = _build_retry_prompt(prompt, str(last_error), raw_content)
            continue

        attempt_error: ValueError | None = None
        for source, candidate in candidates:
            try:
                validated = validator(candidate)
                if source == "repaired":
                    logger.warning(
                        "OASIS JSON response salvaged on attempt %s via field-level extraction",
                        attempt + 1,
                    )
                return validated
            except ValueError as exc:
                attempt_error = exc
                last_error = exc
                continue

        if attempt_error is not None:
            logger.warning(
                "OASIS JSON response validation failed on attempt %s: %s",
                attempt + 1,
                attempt_error,
            )
            retry_prompt = _build_retry_prompt(prompt, str(attempt_error), raw_content)
    if last_error is not None:
        raise last_error
    raise ValueError("response_not_json_or_invalid_schema")

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


def _build_oasis_summary_fallback(payload: dict[str, Any], graph_context: dict[str, Any]) -> str:
    parts: list[str] = []
    key_drivers = _safe_list(payload.get("key_drivers"), 3)
    if key_drivers:
        parts.append("Key drivers: " + "; ".join(key_drivers))
    risk_signals = _safe_list(payload.get("risk_signals"), 2)
    if risk_signals:
        parts.append("Risks: " + "; ".join(risk_signals))
    relationship_signals = _safe_list(graph_context.get("relationships"), 2)
    if relationship_signals:
        parts.append("Relationships: " + "; ".join(relationship_signals))
    top_nodes = graph_context.get("top_nodes") if isinstance(graph_context.get("top_nodes"), list) else []
    labels = [str(item.get("label") or "").strip() for item in top_nodes if isinstance(item, dict)]
    labels = [label for label in labels if label][:3]
    if labels:
        parts.append("Focus entities: " + ", ".join(labels))
    summary = " ".join(parts).strip()
    return summary[:400]


def sanitize_oasis_analysis(
    data: dict[str, Any],
    graph_context: dict[str, Any],
    *,
    max_agent_profiles: int = 16,
    strict: bool = False,
) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    summary = str(payload.get("scenario_summary") or "").strip()
    if not summary:
        summary = _build_oasis_summary_fallback(payload, graph_context)
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
        "Return JSON only with this exact schema:\n"
        "{\n"
        '  "scenario_summary": "...",\n'
        '  "continuation_guidance": {"must_follow":["..."], "next_steps":["..."], "avoid":["..."]},\n'
        '  "agent_profiles": [{"name":"...", "role":"...", "persona":"...", "stance":"...", "likely_actions":["..."]}]\n'
        "}\n"
        "Do not add any extra sections or summary lists outside this schema.\n\n"
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
        validator=lambda parsed: sanitize_oasis_analysis(
            parsed,
            graph_context,
            max_agent_profiles=int(cfg.get("max_agent_profiles") or 16),
            strict=True,
        ),
        repairer=_salvage_oasis_analysis_payload,
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
            "Return JSON only with this schema:",
            "{",
            '  "time_config": {"total_hours":72, "minutes_per_round":60, "peak_hours":[19,20,21,22], "off_peak_hours":[1,2,3,4,5]},',
            '  "events": [{"title":"...", "trigger_hour":12, "description":"..."}],',
            '  "agent_activity": [{"name":"...", "activity_level":0.6, "actions_per_hour":1.2, "response_delay_minutes":45, "stance":"..."}]',
            "}",
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
        repairer=_salvage_oasis_simulation_config_payload,
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


def _build_report_markdown(
    *,
    requirement: str | None,
    analysis: dict[str, Any] | None,
    run_result: dict[str, Any] | None,
) -> str:
    analysis_data = analysis if isinstance(analysis, dict) else {}
    run_data = run_result if isinstance(run_result, dict) else {}
    metrics = run_data.get("metrics") if isinstance(run_data.get("metrics"), dict) else {}

    lines = [
        "# OASIS Analysis Report",
        "",
        f"- Requirement: {(requirement or 'N/A').strip() or 'N/A'}",
        f"- Total Hours: {int(metrics.get('total_hours') or 0)}",
        f"- Total Rounds: {int(metrics.get('total_rounds') or 0)}",
        "",
        "## Executive Summary",
        str(analysis_data.get("scenario_summary") or "No summary available."),
    ]

    next_steps = _safe_list(
        (analysis_data.get("continuation_guidance") or {}).get("next_steps")
        if isinstance(analysis_data.get("continuation_guidance"), dict)
        else [],
        10,
    )
    if next_steps:
        lines.extend(["", "## Recommended Next Steps"])
        lines.extend([f"- {step}" for step in next_steps])

    return "\n".join(lines).strip()


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
        f"{prefix_block}"
        f"Requirement:\n{(requirement or '').strip()}\n\n"
        f"Package:\n{json.dumps(package, ensure_ascii=False)[:9000]}\n\n"
        f"Analysis:\n{json.dumps(analysis_data, ensure_ascii=False)[:9000]}\n\n"
        f"Run Result:\n{json.dumps(run_data, ensure_ascii=False)[:9000]}"
    )

    llm_result = await call_llm(selected_model, prompt, db)
    parsed = extract_json_object(str(llm_result.get("content") or ""))
    if not isinstance(parsed, dict):
        raise ValueError("oasis_report_llm_response_not_json_or_invalid_schema")

    title = str(parsed.get("title") or "OASIS Report").strip() or "OASIS Report"
    summary = str(parsed.get("executive_summary") or "").strip()
    if not summary:
        raise ValueError("oasis_report_executive_summary_missing")

    key_findings = _safe_list(parsed.get("key_findings"), 10)
    if not key_findings:
        raise ValueError("oasis_report_key_findings_missing")

    next_actions = _safe_list(parsed.get("next_actions"), 10)
    if not next_actions:
        raise ValueError("oasis_report_next_actions_missing")

    markdown = str(parsed.get("markdown") or "").strip() or _build_report_markdown(
        requirement=requirement,
        analysis=analysis_data,
        run_result=run_data,
    )

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
