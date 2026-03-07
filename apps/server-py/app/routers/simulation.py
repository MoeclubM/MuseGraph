import asyncio
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.dependencies import get_current_user
from app.models.project import ProjectChapter, TextProject
from app.models.runtime import SimulationRuntime
from app.models.user import User
from app.services.ai import DEFAULT_MODEL, call_llm, llm_billing_scope, resolve_component_model
from app.services.llm_json import extract_json_object
from app.services.oasis import analyze_and_enrich_oasis, build_oasis_package, build_oasis_run_result, load_oasis_config
from app.services.task_state import TaskStatus, task_manager

router = APIRouter()
logger = logging.getLogger(__name__)

SIMULATION_RUN_JSON_MAX_ATTEMPTS = 3
SIMULATION_RUN_MAX_TOKENS_BASE = 2048
SIMULATION_RUN_MAX_TOKENS_PER_ROUND = 1200
SIMULATION_RUN_MAX_TOKENS_CEILING = 16384


class SimulationCreateRequest(BaseModel):
    project_id: str
    graph_id: str | None = None
    enable_twitter: bool = True
    enable_reddit: bool = True
    chapter_ids: list[str] | None = None


class SimulationPrepareRequest(BaseModel):
    simulation_id: str
    force_regenerate: bool = False
    use_llm_for_profiles: bool = True
    parallel_profile_count: int = Field(default=5, ge=1, le=20)
    chapter_ids: list[str] | None = None


class SimulationPrepareStatusRequest(BaseModel):
    task_id: str | None = None
    simulation_id: str | None = None


class SimulationStartRequest(BaseModel):
    simulation_id: str
    platform: str | None = None
    max_rounds: int | None = Field(default=None, ge=1, le=10000)
    enable_graph_memory_update: bool = False
    force_restart: bool = False
    chapter_ids: list[str] | None = None


class SimulationStopRequest(BaseModel):
    simulation_id: str


class InterviewRequest(BaseModel):
    simulation_id: str
    agent_id: str | int | None = None
    prompt: str = Field(min_length=1)


class InterviewBatchItem(BaseModel):
    agent_id: str | int | None = None
    prompt: str = Field(min_length=1)


class InterviewBatchRequest(BaseModel):
    simulation_id: str
    interviews: list[InterviewBatchItem]


class InterviewHistoryRequest(BaseModel):
    simulation_id: str
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class EnvRequest(BaseModel):
    simulation_id: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _split_timeline(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    round_map: dict[int, dict[str, Any]] = {}
    for item in posts:
        round_num = int(item.get("round_num") or 0)
        bucket = round_map.setdefault(round_num, {"round_num": round_num, "posts": []})
        bucket["posts"].append(item)
    return [round_map[key] for key in sorted(round_map.keys())]


def _normalize_chapter_ids(chapter_ids: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in chapter_ids or []:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_provenance(*, source_chapter_ids: list[str], text: str) -> dict[str, Any]:
    return {
        "source_chapter_ids": source_chapter_ids,
        "content_hash": _hash_text(text),
        "generated_at": _now_iso(),
    }


def _inject_provenance(payload: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    payload["source_chapter_ids"] = list(provenance.get("source_chapter_ids") or [])
    payload["content_hash"] = str(provenance.get("content_hash") or "")
    payload["generated_at"] = str(provenance.get("generated_at") or _now_iso())
    payload["provenance"] = {
        "source_chapter_ids": payload["source_chapter_ids"],
        "content_hash": payload["content_hash"],
        "generated_at": payload["generated_at"],
    }
    return payload


def _read_provenance(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    source_chapter_ids = payload.get("source_chapter_ids")
    content_hash = payload.get("content_hash")
    generated_at = payload.get("generated_at")
    if isinstance(payload.get("provenance"), dict):
        nested = payload["provenance"]
        if source_chapter_ids is None:
            source_chapter_ids = nested.get("source_chapter_ids")
        if not content_hash:
            content_hash = nested.get("content_hash")
        if not generated_at:
            generated_at = nested.get("generated_at")

    normalized_ids = _normalize_chapter_ids(source_chapter_ids if isinstance(source_chapter_ids, list) else None)
    hash_value = str(content_hash or "").strip()
    generated = str(generated_at or "").strip() or _now_iso()
    if not hash_value:
        return None
    return {
        "source_chapter_ids": normalized_ids,
        "content_hash": hash_value,
        "generated_at": generated,
    }


def _chapter_sort_key(chapter: ProjectChapter) -> tuple[int, datetime, str]:
    created_at = getattr(chapter, "created_at", None) or datetime.min.replace(tzinfo=timezone.utc)
    return (
        int(getattr(chapter, "order_index", 0) or 0),
        created_at,
        str(getattr(chapter, "id", "")),
    )


async def _resolve_chapters_for_project(
    project: TextProject,
    chapter_ids: list[str] | None,
    db: AsyncSession,
) -> list[ProjectChapter]:
    normalized = _normalize_chapter_ids(chapter_ids)
    if normalized:
        result = await db.execute(
            select(ProjectChapter).where(
                ProjectChapter.project_id == project.id,
                ProjectChapter.id.in_(normalized),
            )
        )
        chapters = result.scalars().all()
        chapter_map = {chapter.id: chapter for chapter in chapters}
        missing = [chapter_id for chapter_id in normalized if chapter_id not in chapter_map]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid chapter_ids for project: {', '.join(missing)}",
            )
        return sorted(chapters, key=_chapter_sort_key)

    existing = getattr(project, "chapters", None)
    if isinstance(existing, list):
        return sorted(existing, key=_chapter_sort_key)

    result = await db.execute(
        select(ProjectChapter).where(ProjectChapter.project_id == project.id)
    )
    chapters = result.scalars().all()
    return sorted(chapters, key=_chapter_sort_key)


async def _resolve_text_for_project(
    project: TextProject,
    *,
    chapter_ids: list[str] | None,
    db: AsyncSession,
) -> tuple[str, dict[str, Any]]:
    normalized = _normalize_chapter_ids(chapter_ids)
    if normalized:
        result = await db.execute(
            select(ProjectChapter).where(
                ProjectChapter.project_id == project.id,
                ProjectChapter.id.in_(normalized),
            )
        )
        chapters = result.scalars().all()
        chapter_map = {chapter.id: chapter for chapter in chapters}
        missing = [chapter_id for chapter_id in normalized if chapter_id not in chapter_map]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid chapter_ids for project: {', '.join(missing)}",
            )
        chapters = sorted(chapters, key=lambda c: (c.order_index, c.created_at, c.id))
        text = "\n\n".join((chapter.content or "").strip() for chapter in chapters if chapter.content is not None).strip()
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected chapters have no text content",
            )
        return text, _build_provenance(source_chapter_ids=[chapter.id for chapter in chapters], text=text)

    chapters = await _resolve_chapters_for_project(project, None, db)
    chapter_text = "\n\n".join((chapter.content or "").strip() for chapter in chapters if chapter.content is not None).strip()
    text = chapter_text
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project has no text content",
        )
    return text, _build_provenance(source_chapter_ids=[], text=text)


async def _refresh_project_analysis_with_provenance(
    project: TextProject,
    *,
    text: str,
    provenance: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    existing = _ensure_dict(project.oasis_analysis)
    existing_provenance = _read_provenance(existing)
    if existing and existing_provenance and existing_provenance.get("content_hash") == provenance.get("content_hash"):
        return existing

    requirement = (project.simulation_requirement or "").strip() or None
    if not requirement:
        raise ValueError("simulation_requirement_missing")

    analysis_model = resolve_component_model(project, "oasis_analysis")
    simulation_model = resolve_component_model(project, "oasis_simulation_config")
    oasis_config = await load_oasis_config(db)
    with llm_billing_scope(
        user_id=project.user_id,
        project_id=project.id,
    ):
        analysis_payload, _ = await analyze_and_enrich_oasis(
            project_id=project.id,
            text=text,
            ontology=_ensure_dict(project.ontology_schema),
            requirement=requirement,
            prompt=None,
            analysis_model=analysis_model,
            simulation_model=simulation_model,
            oasis_config=oasis_config,
            db=db,
        )
    analysis_payload = dict(analysis_payload or {})
    analysis_payload = _inject_provenance(analysis_payload, provenance)
    project.oasis_analysis = analysis_payload
    await db.flush()
    return analysis_payload


def _build_sectioned_profiles(
    package: dict[str, Any], project: TextProject
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profiles = _ensure_list(package.get("profiles"))
    config = _ensure_dict(package.get("simulation_config"))

    if profiles:
        return [p for p in profiles if isinstance(p, dict)], config

    analysis = _ensure_dict(project.oasis_analysis)
    agent_profiles = _ensure_list(analysis.get("agent_profiles"))
    if agent_profiles:
        return [p for p in agent_profiles if isinstance(p, dict)], config

    raise ValueError("simulation_profiles_missing")


def _resolve_prepared_runtime(
    package: dict[str, Any], project: TextProject
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    profiles, config = _build_sectioned_profiles(package, project)
    if not config:
        raise ValueError("simulation_config_missing")
    return profiles, config


def _get_sim_metadata(sim: SimulationRuntime) -> dict[str, Any]:
    meta = getattr(sim, "metadata_", None)
    if meta is None:
        meta = getattr(sim, "metadata", None)
    return _ensure_dict(meta)


def _resolve_simulation_runtime_provenance(sim: SimulationRuntime) -> dict[str, Any] | None:
    for payload in (_ensure_dict(sim.simulation_config), _ensure_dict(sim.run_state), _get_sim_metadata(sim)):
        provenance = _read_provenance(payload)
        if provenance:
            return provenance
    return None


def _simulation_runtime_is_prepared(
    sim: SimulationRuntime,
    *,
    provenance: dict[str, Any] | None = None,
) -> bool:
    profiles = [item for item in _ensure_list(sim.profiles) if isinstance(item, dict)]
    config = _ensure_dict(sim.simulation_config)
    if not profiles or not config or not _ensure_dict(config.get("time_config")):
        return False
    if provenance is None:
        return True
    runtime_provenance = _resolve_simulation_runtime_provenance(sim)
    return bool(runtime_provenance) and runtime_provenance.get("content_hash") == provenance.get("content_hash")


def _apply_prepared_runtime(
    sim: SimulationRuntime,
    *,
    profiles: list[dict[str, Any]],
    config: dict[str, Any],
    provenance: dict[str, Any],
) -> None:
    existing_meta = _get_sim_metadata(sim)
    sim.status = "ready"
    sim.profiles = [item for item in profiles if isinstance(item, dict)]
    sim.simulation_config = _inject_provenance(dict(config), provenance)
    sim.run_state = {
        "status": "ready",
        "is_running": False,
        "current_round": 0,
        "total_rounds": int(_ensure_dict(config.get("time_config")).get("total_hours") or 72),
        "source_chapter_ids": provenance.get("source_chapter_ids", []),
        "content_hash": provenance.get("content_hash", ""),
        "generated_at": provenance.get("generated_at", _now_iso()),
        "updated_at": _now_iso(),
    }
    sim.env_status = {
        "alive": True,
        "status": "ready",
        "updated_at": _now_iso(),
    }
    sim.metadata_ = {
        **existing_meta,
        "source_chapter_ids": list(provenance.get("source_chapter_ids") or []),
        "content_hash": str(provenance.get("content_hash") or ""),
        "generated_at": str(provenance.get("generated_at") or _now_iso()),
    }


def _serialize_simulation(sim: SimulationRuntime) -> dict[str, Any]:
    return {
        "simulation_id": sim.simulation_id,
        "project_id": sim.project_id,
        "status": sim.status,
        "simulation_config": _ensure_dict(sim.simulation_config),
        "profiles": _ensure_list(sim.profiles),
        "run_state": _ensure_dict(sim.run_state),
        "env_status": _ensure_dict(sim.env_status),
        "metadata": _get_sim_metadata(sim),
        "created_at": sim.created_at.isoformat() if sim.created_at else None,
        "updated_at": sim.updated_at.isoformat() if sim.updated_at else None,
    }


async def _get_project_for_user(project_id: str, user: User, db: AsyncSession) -> TextProject:
    result = await db.execute(select(TextProject).where(TextProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return project


async def _get_simulation_for_user(simulation_id: str, user: User, db: AsyncSession) -> SimulationRuntime:
    result = await db.execute(
        select(SimulationRuntime).where(SimulationRuntime.simulation_id == simulation_id)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Simulation not found")
    if sim.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return sim


def _normalize_platform(platform: str | None) -> str | None:
    value = str(platform or "").strip().lower()
    if value in {"twitter", "reddit"}:
        return value
    return None


def _build_simulation_retry_prompt(base_prompt: str, reason: str, raw_content: str) -> str:
    preview = str(raw_content or "").strip()[:1200]
    retry_note = (
        "\n\nIMPORTANT: The previous response was invalid for downstream parsing. "
        f"Reason: {reason}. "
        "Return exactly one complete JSON object matching the requested schema, with all required fields populated. "
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


def _salvage_simulation_run_payload(raw_content: str) -> dict[str, Any] | None:
    payload = {
        "rounds": _extract_named_json_value(raw_content, "rounds"),
    }
    if not any(value not in (None, "", [], {}) for value in payload.values()):
        return None
    return payload


def _resolve_simulation_run_max_tokens(total_rounds: int) -> int:
    safe_rounds = max(1, int(total_rounds or 1))
    estimated = SIMULATION_RUN_MAX_TOKENS_BASE + (safe_rounds * SIMULATION_RUN_MAX_TOKENS_PER_ROUND)
    return max(
        SIMULATION_RUN_MAX_TOKENS_BASE,
        min(SIMULATION_RUN_MAX_TOKENS_CEILING, estimated),
    )


async def _build_run_artifacts_with_llm(
    sim: SimulationRuntime,
    project: TextProject,
    run_result: dict[str, Any],
    max_rounds: int | None,
    db: AsyncSession,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    metrics = _ensure_dict(run_result.get("metrics"))
    total_rounds = int(metrics.get("total_rounds") or 0)
    if max_rounds:
        total_rounds = min(total_rounds or max_rounds, max_rounds)
    total_rounds = max(1, min(total_rounds or 24, 120))
    run_max_tokens = _resolve_simulation_run_max_tokens(total_rounds)

    profiles = [p for p in _ensure_list(sim.profiles) if isinstance(p, dict)]
    if not profiles:
        raise ValueError("simulation_profiles_missing")

    config = _ensure_dict(sim.simulation_config)
    time_cfg = _ensure_dict(config.get("time_config"))
    events = [e for e in _ensure_list(config.get("events")) if isinstance(e, dict)]
    activity = [a for a in _ensure_list(config.get("agent_activity")) if isinstance(a, dict)]
    platforms = [
        str(x).strip().lower()
        for x in _ensure_list(config.get("active_platforms"))
        if str(x).strip().lower() in {"twitter", "reddit"}
    ]
    if not platforms:
        raise ValueError("simulation_platforms_missing")

    analysis = _ensure_dict(project.oasis_analysis)
    guidance = _ensure_dict(analysis.get("continuation_guidance"))
    model = resolve_component_model(project, "oasis_simulation")

    prompt = (
        "You are generating realistic multi-round social simulation content.\n"
        "Return JSON only with this schema:\n"
        "{\n"
        '  "rounds": [\n'
        "    {\n"
        '      "round": 1,\n'
        '      "posts": [{"agent":"...", "platform":"twitter|reddit", "content":"..."}],\n'
        '      "comments": [{"agent":"...", "platform":"twitter|reddit", "content":"..."}],\n'
        '      "actions": [{"agent":"...", "action_type":"post|comment|react|share", "summary":"..."}]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules:\n"
        f"- Generate exactly {total_rounds} rounds with coherent progression.\n"
        "- Keep content concise and grounded in the configured simulation setup.\n"
        "- Respect role consistency for each agent.\n"
        "- Reflect configured events near their trigger hour.\n"
        "- Avoid generic filler text.\n"
        "- Keep each round compact while preserving coherence.\n\n"
        f"Simulation requirement:\n{(project.simulation_requirement or '').strip()}\n\n"
        f"Scenario summary:\n{str(analysis.get('scenario_summary') or '').strip()}\n\n"
        f"Continuation guidance:\n{json.dumps(guidance, ensure_ascii=False)[:3000]}\n\n"
        f"Time config:\n{json.dumps(time_cfg, ensure_ascii=False)}\n\n"
        f"Events:\n{json.dumps(events[:16], ensure_ascii=False)}\n\n"
        f"Platforms:\n{json.dumps(platforms, ensure_ascii=False)}\n\n"
        f"Agent profiles:\n{json.dumps(profiles[:20], ensure_ascii=False)[:9000]}\n\n"
        f"Agent activity:\n{json.dumps(activity[:30], ensure_ascii=False)[:6000]}"
    )

    parsed: dict[str, Any] | None = None
    retry_prompt = prompt
    last_error: ValueError | None = None
    for attempt in range(SIMULATION_RUN_JSON_MAX_ATTEMPTS):
        with llm_billing_scope(
            user_id=sim.user_id,
            project_id=project.id,
        ):
            llm_result = await call_llm(model=model, prompt=retry_prompt, db=db, max_tokens=run_max_tokens)
        raw_content = str(llm_result.get("content") or "")
        initial = extract_json_object(raw_content)
        candidates: list[tuple[str, dict[str, Any]]] = []
        if isinstance(initial, dict):
            candidates.append(("parsed", initial))
        repaired = _salvage_simulation_run_payload(raw_content)
        if isinstance(repaired, dict) and repaired and all(repaired != candidate for _, candidate in candidates):
            candidates.append(("repaired", repaired))

        if not candidates:
            last_error = ValueError("simulation_run_llm_response_not_json_or_invalid_schema")
            logger.warning(
                "Simulation run JSON parse failed on attempt %s (preview=%s)",
                attempt + 1,
                raw_content[:400],
            )
            retry_prompt = _build_simulation_retry_prompt(prompt, str(last_error), raw_content)
            continue

        for source, candidate in candidates:
            rounds = candidate.get("rounds")
            if isinstance(rounds, list) and rounds:
                parsed = candidate
                if source == "repaired":
                    logger.warning(
                        "Simulation run JSON salvaged on attempt %s via field-level extraction",
                        attempt + 1,
                    )
                break
            last_error = ValueError("simulation_run_rounds_missing")
        if parsed is not None:
            break
        logger.warning(
            "Simulation run JSON validation failed on attempt %s: %s",
            attempt + 1,
            last_error,
        )
        retry_prompt = _build_simulation_retry_prompt(prompt, str(last_error), raw_content)

    if not isinstance(parsed, dict):
        raise last_error or ValueError("simulation_run_llm_response_not_json_or_invalid_schema")

    rounds = parsed.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        raise ValueError("simulation_run_rounds_missing")

    posts: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    start_ts = _now_iso()
    profile_names = [str(p.get("name") or "").strip() for p in profiles if str(p.get("name") or "").strip()]
    if not profile_names:
        raise ValueError("simulation_profile_names_missing")

    round_rows: list[tuple[int, dict[str, Any]]] = []
    for idx, item in enumerate(rounds):
        if not isinstance(item, dict):
            continue
        try:
            round_num = int(item.get("round") or item.get("round_num") or (idx + 1))
        except Exception:
            round_num = idx + 1
        round_rows.append((max(1, min(total_rounds, round_num)), item))

    round_rows.sort(key=lambda x: x[0])
    if not round_rows:
        raise ValueError("simulation_round_rows_empty")

    for round_num, row in round_rows[:total_rounds]:
        default_platform = platforms[(round_num - 1) % len(platforms)]

        row_posts = row.get("posts") if isinstance(row.get("posts"), list) else []
        if not row_posts:
            continue

        for p_idx, post_item in enumerate(row_posts[:6]):
            if not isinstance(post_item, dict):
                continue
            agent = str(post_item.get("agent") or "").strip()
            if not agent or agent not in profile_names:
                continue
            platform = _normalize_platform(str(post_item.get("platform") or ""))
            if not platform:
                platform = default_platform
            content = str(post_item.get("content") or "").strip()
            if not content:
                continue
            post_id = f"post_{sim.simulation_id}_{round_num}_{p_idx + 1}"
            posts.append(
                {
                    "id": post_id,
                    "round_num": round_num,
                    "agent": agent,
                    "platform": platform,
                    "content": content,
                    "created_at": start_ts,
                }
            )
            actions.append(
                {
                    "action_id": f"act_post_{sim.simulation_id}_{round_num}_{p_idx + 1}",
                    "round_num": round_num,
                    "agent": agent,
                    "action_type": "post",
                    "summary": content[:240],
                    "created_at": start_ts,
                }
            )

        row_comments = row.get("comments") if isinstance(row.get("comments"), list) else []
        for c_idx, comment_item in enumerate(row_comments[:6]):
            if not isinstance(comment_item, dict):
                continue
            agent = str(comment_item.get("agent") or "").strip()
            if not agent or agent not in profile_names:
                continue
            platform = _normalize_platform(str(comment_item.get("platform") or ""))
            if not platform:
                platform = default_platform
            content = str(comment_item.get("content") or "").strip()
            if not content:
                continue
            comments.append(
                {
                    "id": f"comment_{sim.simulation_id}_{round_num}_{c_idx + 1}",
                    "round_num": round_num,
                    "agent": agent,
                    "platform": platform,
                    "content": content,
                    "created_at": start_ts,
                }
            )
            actions.append(
                {
                    "action_id": f"act_comment_{sim.simulation_id}_{round_num}_{c_idx + 1}",
                    "round_num": round_num,
                    "agent": agent,
                    "action_type": "comment",
                    "summary": content[:240],
                    "created_at": start_ts,
                }
            )

        row_actions = row.get("actions") if isinstance(row.get("actions"), list) else []
        for a_idx, action_item in enumerate(row_actions[:10]):
            if not isinstance(action_item, dict):
                continue
            action_type = str(action_item.get("action_type") or "").strip().lower()
            summary = str(action_item.get("summary") or "").strip()
            if action_type in {"post", "comment"} or not summary:
                continue
            agent = str(action_item.get("agent") or "").strip()
            if not agent or agent not in profile_names:
                continue
            actions.append(
                {
                    "action_id": f"act_extra_{sim.simulation_id}_{round_num}_{a_idx + 1}",
                    "round_num": round_num,
                    "agent": agent,
                    "action_type": action_type if action_type else "react",
                    "summary": summary[:240],
                    "created_at": start_ts,
                }
            )

    if not posts:
        raise ValueError("simulation_posts_empty_after_llm_generation")

    metrics["total_rounds"] = total_rounds
    metrics["estimated_posts"] = len(posts)
    metrics["generated_mode"] = "llm"
    metrics["generated_model"] = model
    run_result["metrics"] = metrics
    return run_result, posts, comments, actions


async def _run_prepare_task(
    task_id: str,
    simulation_id: str,
    chapter_ids: list[str] | None,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading simulation state...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(
                select(SimulationRuntime).where(SimulationRuntime.simulation_id == simulation_id)
            )
            sim = result.scalar_one_or_none()
            if not sim:
                raise RuntimeError("Simulation not found")
            project_result = await db.execute(select(TextProject).where(TextProject.id == sim.project_id))
            project = project_result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")
            requirement = (project.simulation_requirement or "").strip()
            if not requirement:
                raise RuntimeError("Project missing simulation requirement")

            existing_meta = _get_sim_metadata(sim)
            selected_chapter_ids = chapter_ids
            if selected_chapter_ids is None:
                selected_chapter_ids = _ensure_list(existing_meta.get("source_chapter_ids")) or None

            task_manager.update_task(task_id, progress=20, message="Resolving chapter source text...")
            text, provenance = await _resolve_text_for_project(
                project,
                chapter_ids=selected_chapter_ids,
                db=db,
            )

            task_manager.update_task(task_id, progress=35, message="Collecting OASIS package...")
            analysis = await _refresh_project_analysis_with_provenance(
                project,
                text=text,
                provenance=provenance,
                db=db,
            )
            package = _ensure_dict(analysis.get("latest_package"))
            package_provenance = _read_provenance(package)
            if not package or not package_provenance or package_provenance.get("content_hash") != provenance.get("content_hash"):
                oasis_config = await load_oasis_config(db)
                package = build_oasis_package(
                    project_id=project.id,
                    project_title=project.title,
                    requirement=requirement,
                    ontology=_ensure_dict(project.ontology_schema),
                    analysis=analysis,
                    component_models=project.component_models if isinstance(project.component_models, dict) else None,
                    oasis_config=oasis_config,
                )
                package = _inject_provenance(package, provenance)
                analysis["latest_package"] = package
                project.oasis_analysis = analysis

            task_manager.update_task(task_id, progress=55, message="Preparing profiles and simulation config...")
            profiles, config = _resolve_prepared_runtime(package, project)

            task_manager.update_task(task_id, progress=85, message="Saving prepared runtime...")
            _apply_prepared_runtime(
                sim,
                profiles=profiles,
                config=config,
                provenance=provenance,
            )
            await db.flush()
            await db.commit()

            task_manager.complete_task(
                task_id,
                result={
                    "simulation_id": simulation_id,
                    "profile_count": len(profiles),
                    "expected_entities_count": len(profiles),
                    "source_chapter_ids": provenance.get("source_chapter_ids", []),
                    "content_hash": provenance.get("content_hash", ""),
                },
                message="Simulation prepared",
            )
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, str(exc), "Simulation prepare failed")


async def _interview_single(
    db: AsyncSession,
    sim: SimulationRuntime,
    prompt: str,
    agent_id: str | int | None,
) -> dict[str, Any]:
    project_result = await db.execute(select(TextProject).where(TextProject.id == sim.project_id))
    project = project_result.scalar_one_or_none()
    profiles = [p for p in _ensure_list(sim.profiles) if isinstance(p, dict)]
    index = 0
    if isinstance(agent_id, int):
        index = max(0, min(agent_id, max(0, len(profiles) - 1)))
    elif isinstance(agent_id, str):
        for i, profile in enumerate(profiles):
            if str(profile.get("name") or "") == agent_id:
                index = i
                break
    if not profiles:
        raise RuntimeError("simulation_profiles_missing")
    profile = profiles[index]
    model = resolve_component_model(project, "oasis_report") if project else DEFAULT_MODEL

    llm_prompt = (
        "You are role-playing as a simulation agent. Keep answer concise and scenario-consistent.\n\n"
        f"Agent profile: {profile}\n"
        f"Simulation requirement: {project.simulation_requirement if project else ''}\n\n"
        f"User prompt: {prompt}"
    )
    content = ""
    with llm_billing_scope(
        user_id=sim.user_id,
        project_id=sim.project_id,
    ):
        llm_result = await call_llm(model=model, prompt=llm_prompt, db=db)
    content = str(llm_result.get("content") or "").strip()

    if not content:
        raise RuntimeError("simulation_interview_llm_empty_response")

    row = {
        "simulation_id": sim.simulation_id,
        "agent": str(profile.get("name") or "agent"),
        "agent_role": str(profile.get("role") or ""),
        "prompt": prompt,
        "response": content,
        "created_at": _now_iso(),
    }
    history = _ensure_list(sim.interview_history)
    history.append(row)
    sim.interview_history = history[-500:]
    return row


@router.post("/create")
async def create_simulation(
    body: SimulationCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_for_user(body.project_id, user, db)
    if not project.cognee_dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project graph not built. Please build graph before creating simulation.",
        )

    simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
    _, provenance = await _resolve_text_for_project(
        project,
        chapter_ids=body.chapter_ids,
        db=db,
    )
    sim = SimulationRuntime(
        simulation_id=simulation_id,
        project_id=project.id,
        user_id=project.user_id,
        status="created",
        simulation_config=_inject_provenance({}, provenance),
        profiles=[],
        run_state={
            "status": "created",
            "is_running": False,
            "current_round": 0,
            "source_chapter_ids": provenance.get("source_chapter_ids", []),
            "content_hash": provenance.get("content_hash", ""),
            "generated_at": provenance.get("generated_at", _now_iso()),
        },
        actions=[],
        posts=[],
        comments=[],
        interview_history=[],
        env_status={"alive": False, "status": "created", "updated_at": _now_iso()},
        metadata_={
            "graph_id": body.graph_id or project.cognee_dataset_id,
            "enable_twitter": body.enable_twitter,
            "enable_reddit": body.enable_reddit,
            "source_chapter_ids": list(provenance.get("source_chapter_ids") or []),
            "content_hash": str(provenance.get("content_hash") or ""),
            "generated_at": str(provenance.get("generated_at") or _now_iso()),
        },
    )
    db.add(sim)
    await db.flush()
    return {
        "status": "ok",
        "data": {
            "simulation_id": simulation_id,
            "project_id": project.id,
            "graph_id": project.cognee_dataset_id,
            "status": sim.status,
        },
    }


@router.post("/prepare")
async def prepare_simulation(
    body: SimulationPrepareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(body.simulation_id, user, db)
    selected_chapter_ids = body.chapter_ids
    selected_provenance: dict[str, Any] | None = None
    if selected_chapter_ids is not None:
        project = await _get_project_for_user(sim.project_id, user, db)
        _, selected_provenance = await _resolve_text_for_project(
            project,
            chapter_ids=selected_chapter_ids,
            db=db,
        )
        meta = _get_sim_metadata(sim)
        meta["source_chapter_ids"] = list(selected_provenance.get("source_chapter_ids") or [])
        meta["content_hash"] = str(selected_provenance.get("content_hash") or "")
        meta["generated_at"] = str(selected_provenance.get("generated_at") or _now_iso())
        sim.metadata_ = meta
    if sim.status == "ready" and not body.force_regenerate and _simulation_runtime_is_prepared(sim, provenance=selected_provenance):
        return {
            "status": "ok",
            "data": {
                "simulation_id": sim.simulation_id,
                "already_prepared": True,
                "message": "Simulation already prepared",
            },
        }

    task_manager.cleanup_old_tasks(max_age_hours=168)
    task = task_manager.create_task(
        "simulation_prepare",
        metadata={"simulation_id": sim.simulation_id, "project_id": sim.project_id, "user_id": user.id},
    )
    sim.status = "preparing"
    await db.flush()
    asyncio.create_task(_run_prepare_task(task.task_id, sim.simulation_id, selected_chapter_ids))
    return {
        "status": "ok",
        "data": {
            "simulation_id": sim.simulation_id,
            "task_id": task.task_id,
            "message": "Prepare task started",
        },
    }


@router.post("/prepare/status")
async def get_prepare_status(
    body: SimulationPrepareStatusRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.simulation_id:
        sim = await _get_simulation_for_user(body.simulation_id, user, db)
        if sim.status == "ready":
            return {
                "status": "ok",
                "data": {
                    "status": "ready",
                    "progress": 100,
                    "simulation_id": sim.simulation_id,
                    "message": "Simulation prepared",
                },
            }
    if not body.task_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="task_id or simulation_id required")
    task = task_manager.get_task(body.task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return {"status": "ok", "data": task.to_dict()}


@router.get("/list")
async def list_simulations(
    project_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SimulationRuntime)
    if not user.is_admin:
        stmt = stmt.where(SimulationRuntime.user_id == user.id)
    if project_id:
        stmt = stmt.where(SimulationRuntime.project_id == project_id)
    stmt = stmt.order_by(desc(SimulationRuntime.created_at)).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {"status": "ok", "data": [_serialize_simulation(row) for row in rows], "count": len(rows)}


@router.get("/history")
async def get_simulation_history(
    limit: int = Query(default=20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SimulationRuntime)
    if not user.is_admin:
        stmt = stmt.where(SimulationRuntime.user_id == user.id)
    stmt = stmt.order_by(desc(SimulationRuntime.updated_at)).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    enriched = []
    for sim in rows:
        run_state = _ensure_dict(sim.run_state)
        enriched.append(
            {
                "simulation_id": sim.simulation_id,
                "project_id": sim.project_id,
                "status": sim.status,
                "profile_count": len(_ensure_list(sim.profiles)),
                "simulation_requirement": "",
                "run_status": run_state.get("status"),
                "current_round": run_state.get("current_round", 0),
                "total_rounds": run_state.get("total_rounds", 0),
                "created_at": sim.created_at.isoformat() if sim.created_at else None,
                "updated_at": sim.updated_at.isoformat() if sim.updated_at else None,
            }
        )
    return {"status": "ok", "data": enriched, "count": len(enriched)}


@router.post("/start")
async def start_simulation(
    body: SimulationStartRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        sim = await _get_simulation_for_user(body.simulation_id, user, db)
        if sim.status == "preparing" and not body.force_restart and not _simulation_runtime_is_prepared(sim):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Simulation is still preparing. Wait for /api/simulation/prepare to finish.",
            )
        if sim.status not in {"created", "ready", "completed", "stopped", "preparing"} and not body.force_restart:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Simulation not runnable: {sim.status}")

        project = await _get_project_for_user(sim.project_id, user, db)
        selected_chapter_ids = body.chapter_ids
        if selected_chapter_ids is None:
            selected_chapter_ids = _ensure_list(_get_sim_metadata(sim).get("source_chapter_ids")) or None
        source_text, provenance = await _resolve_text_for_project(
            project,
            chapter_ids=selected_chapter_ids,
            db=db,
        )
        analysis = await _refresh_project_analysis_with_provenance(
            project,
            text=source_text,
            provenance=provenance,
            db=db,
        )
        package = _ensure_dict(analysis.get("latest_package"))
        package_provenance = _read_provenance(package)
        if not package or not package_provenance or package_provenance.get("content_hash") != provenance.get("content_hash"):
            oasis_config = await load_oasis_config(db)
            package = build_oasis_package(
                project_id=project.id,
                project_title=project.title,
                requirement=(project.simulation_requirement or "").strip(),
                ontology=_ensure_dict(project.ontology_schema),
                analysis=analysis,
                component_models=project.component_models if isinstance(project.component_models, dict) else None,
                oasis_config=oasis_config,
            )
            package = _inject_provenance(package, provenance)
            analysis["latest_package"] = package
            project.oasis_analysis = analysis

        profiles, config = _resolve_prepared_runtime(package, project)
        _apply_prepared_runtime(
            sim,
            profiles=profiles,
            config=config,
            provenance=provenance,
        )

        run_result = build_oasis_run_result(package=package, analysis=analysis)
        run_result = _inject_provenance(run_result, provenance)
        analysis["latest_package"] = package
        analysis["latest_run"] = run_result
        project.oasis_analysis = analysis
        run_result, posts, comments, actions = await _build_run_artifacts_with_llm(
            sim=sim,
            project=project,
            run_result=run_result,
            max_rounds=body.max_rounds,
            db=db,
        )

        sim.status = "completed"
        sim.posts = posts
        sim.comments = comments
        sim.actions = actions
        sim.run_state = {
            "status": "completed",
            "is_running": False,
            "current_round": _ensure_dict(run_result.get("metrics")).get("total_rounds", 0),
            "total_rounds": _ensure_dict(run_result.get("metrics")).get("total_rounds", 0),
            "platform": body.platform or "multi",
            "source_chapter_ids": provenance.get("source_chapter_ids", []),
            "content_hash": provenance.get("content_hash", ""),
            "generated_at": provenance.get("generated_at", _now_iso()),
            "run_result": run_result,
            "updated_at": _now_iso(),
        }
        sim.env_status = {
            "alive": True,
            "status": "running_completed",
            "updated_at": _now_iso(),
        }
        meta = _get_sim_metadata(sim)
        meta["source_chapter_ids"] = list(provenance.get("source_chapter_ids") or [])
        meta["content_hash"] = str(provenance.get("content_hash") or "")
        meta["generated_at"] = str(provenance.get("generated_at") or _now_iso())
        sim.metadata_ = meta
        await db.flush()
        return {
            "status": "ok",
            "data": {
                "simulation_id": sim.simulation_id,
                "status": sim.status,
                "process_pid": None,
                "run_result": run_result,
            },
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.post("/stop")
async def stop_simulation(
    body: SimulationStopRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(body.simulation_id, user, db)
    run_state = _ensure_dict(sim.run_state)
    run_state["status"] = "stopped"
    run_state["is_running"] = False
    run_state["updated_at"] = _now_iso()
    sim.run_state = run_state
    sim.status = "stopped"
    sim.env_status = {"alive": False, "status": "stopped", "updated_at": _now_iso()}
    await db.flush()
    return {"status": "ok", "data": {"simulation_id": sim.simulation_id, "status": "stopped"}}


@router.get("/{simulation_id}/run-status")
async def get_run_status(
    simulation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    run_state = _ensure_dict(sim.run_state)
    return {
        "status": "ok",
        "data": {
            "simulation_id": sim.simulation_id,
            "status": run_state.get("status", sim.status),
            "is_running": bool(run_state.get("is_running", False)),
            "current_round": int(run_state.get("current_round") or 0),
            "total_rounds": int(run_state.get("total_rounds") or 0),
            "metrics": _ensure_dict(_ensure_dict(run_state.get("run_result")).get("metrics")),
        },
    }


@router.get("/{simulation_id}/run-status/detail")
async def get_run_status_detail(
    simulation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    run_state = _ensure_dict(sim.run_state)
    actions = _ensure_list(sim.actions)
    return {
        "status": "ok",
        "data": {
            "simulation_id": sim.simulation_id,
            "status": run_state.get("status", sim.status),
            "run_state": run_state,
            "recent_actions": actions[-100:],
        },
    }


@router.get("/{simulation_id}/actions")
async def get_actions(
    simulation_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    actions = _ensure_list(sim.actions)
    sliced = actions[offset : offset + limit]
    return {"status": "ok", "data": sliced, "count": len(actions)}


@router.get("/{simulation_id}/timeline")
async def get_timeline(
    simulation_id: str,
    start_round: int = Query(default=0, ge=0),
    end_round: int | None = Query(default=None, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    timeline = _split_timeline(_ensure_list(sim.posts))
    if start_round:
        timeline = [item for item in timeline if int(item.get("round_num") or 0) >= start_round]
    if end_round is not None:
        timeline = [item for item in timeline if int(item.get("round_num") or 0) <= end_round]
    return {"status": "ok", "data": timeline, "count": len(timeline)}


@router.get("/{simulation_id}/agent-stats")
async def get_agent_stats(
    simulation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    profiles = [p for p in _ensure_list(sim.profiles) if isinstance(p, dict)]
    posts = _ensure_list(sim.posts)
    comments = _ensure_list(sim.comments)

    stats: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        name = str(profile.get("name") or "")
        if not name:
            continue
        stats[name] = {"agent": name, "posts": 0, "comments": 0}
    for post in posts:
        agent = str(post.get("agent") or "")
        if agent:
            stats.setdefault(agent, {"agent": agent, "posts": 0, "comments": 0})
            stats[agent]["posts"] += 1
    for comment in comments:
        agent = str(comment.get("agent") or "")
        if agent:
            stats.setdefault(agent, {"agent": agent, "posts": 0, "comments": 0})
            stats[agent]["comments"] += 1
    return {"status": "ok", "data": list(stats.values()), "count": len(stats)}


@router.get("/{simulation_id}/posts")
async def get_posts(
    simulation_id: str,
    platform: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    posts = _ensure_list(sim.posts)
    if platform:
        posts = [p for p in posts if str(p.get("platform") or "").lower() == platform.lower()]
    sliced = posts[offset : offset + limit]
    return {"status": "ok", "data": sliced, "count": len(posts)}


@router.get("/{simulation_id}/comments")
async def get_comments(
    simulation_id: str,
    platform: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    comments = _ensure_list(sim.comments)
    if platform:
        comments = [p for p in comments if str(p.get("platform") or "").lower() == platform.lower()]
    sliced = comments[offset : offset + limit]
    return {"status": "ok", "data": sliced, "count": len(comments)}


@router.get("/{simulation_id}/profiles")
async def get_profiles(
    simulation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    profiles = _ensure_list(sim.profiles)
    return {"status": "ok", "data": {"profiles": profiles, "total_expected": len(profiles)}}


@router.get("/{simulation_id}/config")
async def get_simulation_config(
    simulation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    return {"status": "ok", "data": _ensure_dict(sim.simulation_config)}


@router.post("/interview")
async def interview_one(
    body: InterviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        sim = await _get_simulation_for_user(body.simulation_id, user, db)
        row = await _interview_single(db, sim, body.prompt, body.agent_id)
        await db.flush()
        return {"status": "ok", "data": row}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.post("/interview/batch")
async def interview_batch(
    body: InterviewBatchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        sim = await _get_simulation_for_user(body.simulation_id, user, db)
        rows: list[dict[str, Any]] = []
        for item in body.interviews[:100]:
            rows.append(await _interview_single(db, sim, item.prompt, item.agent_id))
        await db.flush()
        return {"status": "ok", "data": rows, "count": len(rows)}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.post("/interview/all")
async def interview_all(
    body: InterviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        sim = await _get_simulation_for_user(body.simulation_id, user, db)
        profiles = [p for p in _ensure_list(sim.profiles) if isinstance(p, dict)]
        rows: list[dict[str, Any]] = []
        for idx, _ in enumerate(profiles[:64]):
            rows.append(await _interview_single(db, sim, body.prompt, idx))
        await db.flush()
        return {"status": "ok", "data": rows, "count": len(rows)}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


@router.post("/interview/history")
async def get_interview_history(
    body: InterviewHistoryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(body.simulation_id, user, db)
    rows = _ensure_list(sim.interview_history)
    sliced = rows[body.offset : body.offset + body.limit]
    return {"status": "ok", "data": sliced, "count": len(rows)}


@router.post("/env-status")
async def get_env_status(
    body: EnvRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(body.simulation_id, user, db)
    env = _ensure_dict(sim.env_status)
    return {
        "status": "ok",
        "data": {
            "simulation_id": sim.simulation_id,
            "env_alive": bool(env.get("alive", False)),
            "env_status": env,
        },
    }


@router.post("/close-env")
async def close_simulation_env(
    body: EnvRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(body.simulation_id, user, db)
    sim.env_status = {"alive": False, "status": "closed", "updated_at": _now_iso()}
    if sim.status == "running":
        sim.status = "stopped"
    await db.flush()
    return {"status": "ok", "data": {"simulation_id": sim.simulation_id, "closed": True}}


@router.get("/{simulation_id}")
async def get_simulation(
    simulation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sim = await _get_simulation_for_user(simulation_id, user, db)
    result = _serialize_simulation(sim)
    result["run_instructions"] = {
        "start_endpoint": "/api/simulation/start",
        "stop_endpoint": "/api/simulation/stop",
        "report_endpoint": "/api/report/generate",
    }
    return {"status": "ok", "data": result}
