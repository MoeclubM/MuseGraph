import asyncio
import hashlib
import inspect
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any, Callable, Coroutine

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session, get_db
from app.dependencies import get_current_user
from app.models.project import ProjectChapter, TextProject
from app.models.user import User
from app.schemas.graph import (
    GraphBuildRequest,
    GraphOasisAnalyzeRequest,
    GraphOasisAnalyzeResponse,
    GraphOasisPrepareRequest,
    GraphOasisPrepareResponse,
    GraphOasisReportRequest,
    GraphOasisReportResponse,
    GraphOasisRunRequest,
    GraphOasisRunResponse,
    GraphTaskInfo,
    GraphTaskListResponse,
    GraphTaskStartResponse,
    GraphTaskStatusResponse,
    GraphOntologyGenerateRequest,
    GraphOntologyResponse,
    GraphSearchRequest,
    GraphStatusResponse,
    GraphVisualizationResponse,
)
from app.services.graph_service import (
    GraphBuildPartialFailure,
    build_graph,
    delete_graph as delete_graph_data,
    get_graph_visualization,
    get_graph_visualization_for_group,
    has_graph_data,
    search_graph,
)
from app.services.ai import llm_billing_scope, resolve_component_model
from app.services.oasis import (
    analyze_and_enrich_oasis,
    build_oasis_package,
    build_oasis_run_result,
    generate_oasis_report,
    load_oasis_config,
)
from app.services.ontology import build_graph_input_with_ontology, generate_ontology
from app.services.task_state import TaskRecord, TaskStatus, task_manager

router = APIRouter()
GRAPH_BUILD_REBUILD = "rebuild"
GRAPH_BUILD_INCREMENTAL = "incremental"
_STALE_GRAPH_TASK_SECONDS = 120
_TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
_RERANKER_SEARCH_TYPES = {"RAG_COMPLETION", "GRAPH_COMPLETION", "GRAPH_SUMMARY_COMPLETION"}


async def _get_project(project_id: str, user: User, db: AsyncSession) -> TextProject:
    try:
        UUID(str(project_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid project id") from None

    result = await db.execute(select(TextProject).where(TextProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return project


def _require_ontology_and_graph(project: TextProject, action_name: str) -> None:
    if not project.ontology_schema:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ontology not generated. Please complete ontology first before {action_name}.",
        )
    if not project.graph_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Graph not built. Please build graph before {action_name}.",
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _describe_task_exception(exc: Exception) -> str:
    message = str(exc or "").strip()
    if message:
        return message
    return f"{type(exc).__name__}: {exc!r}"


def _preview_graph_id_from_task(task: TaskRecord | None) -> str:
    if not task:
        return ""
    detail = task.progress_detail if isinstance(task.progress_detail, dict) else None
    graph_id = str((detail or {}).get("preview_graph_id") or "").strip()
    if graph_id:
        return graph_id
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    return str(metadata.get("preview_graph_id") or "").strip()


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


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


def _normalize_int_list(values: list[Any] | None) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw in values or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_json_payload(payload: Any) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        encoded = str(payload)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text_hash_or_empty(text: str | None) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    return _hash_text(normalized)


def _build_task_idempotency_key(*, task_type: str, project_id: str, payload: dict[str, Any]) -> str:
    task = str(task_type or "").strip().lower() or "task"
    fingerprint = _hash_json_payload(
        {
            "task_type": task,
            "project_id": str(project_id or "").strip(),
            "payload": payload,
        }
    )
    return f"{task}:{fingerprint[:24]}"


def _build_graph_task_idempotency_key(project_id: str, body: GraphBuildRequest) -> str:
    return _build_task_idempotency_key(
        task_type="graph_build",
        project_id=project_id,
        payload={
            "chapter_ids": _normalize_chapter_ids(body.chapter_ids),
            "build_mode": _normalize_graph_build_mode(body.build_mode),
            "resume_failed": bool(body.resume_failed),
            "text_hash": _text_hash_or_empty(body.text),
            "ontology_hash": _hash_json_payload(body.ontology) if isinstance(body.ontology, dict) else "",
        },
    )


def _build_ontology_task_idempotency_key(project_id: str, body: GraphOntologyGenerateRequest) -> str:
    return _build_task_idempotency_key(
        task_type="ontology_generate",
        project_id=project_id,
        payload={
            "chapter_ids": _normalize_chapter_ids(body.chapter_ids),
            "text_hash": _text_hash_or_empty(body.text),
            "model": str(body.model or "").strip(),
            "requirement": str(body.requirement or "").strip(),
        },
    )


def _build_oasis_analyze_task_idempotency_key(project_id: str, body: GraphOasisAnalyzeRequest) -> str:
    return _build_task_idempotency_key(
        task_type="oasis_analyze",
        project_id=project_id,
        payload={
            "chapter_ids": _normalize_chapter_ids(body.chapter_ids),
            "text_hash": _text_hash_or_empty(body.text),
            "prompt_hash": _text_hash_or_empty(body.prompt),
            "analysis_model": str(body.analysis_model or "").strip(),
            "simulation_model": str(body.simulation_model or "").strip(),
            "requirement": str(body.requirement or "").strip(),
            "requirement_provided": "requirement" in body.model_fields_set,
        },
    )


def _build_oasis_prepare_task_idempotency_key(project_id: str, body: GraphOasisPrepareRequest) -> str:
    return _build_task_idempotency_key(
        task_type="oasis_prepare",
        project_id=project_id,
        payload={
            "chapter_ids": _normalize_chapter_ids(body.chapter_ids),
            "text_hash": _text_hash_or_empty(body.text),
            "prompt_hash": _text_hash_or_empty(body.prompt),
            "analysis_model": str(body.analysis_model or "").strip(),
            "simulation_model": str(body.simulation_model or "").strip(),
            "requirement": str(body.requirement or "").strip(),
            "requirement_provided": "requirement" in body.model_fields_set,
        },
    )


def _build_oasis_run_task_idempotency_key(project_id: str, body: GraphOasisRunRequest) -> str:
    return _build_task_idempotency_key(
        task_type="oasis_run",
        project_id=project_id,
        payload={
            "chapter_ids": _normalize_chapter_ids(body.chapter_ids),
            "package_hash": _hash_json_payload(body.package) if isinstance(body.package, dict) else "",
        },
    )


def _build_oasis_report_task_idempotency_key(project_id: str, body: GraphOasisReportRequest) -> str:
    return _build_task_idempotency_key(
        task_type="oasis_report",
        project_id=project_id,
        payload={
            "chapter_ids": _normalize_chapter_ids(body.chapter_ids),
            "report_model": str(body.report_model or "").strip(),
        },
    )


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


async def _resolve_chapters_for_project(
    project: TextProject,
    chapter_ids: list[str] | None,
    db: AsyncSession,
) -> list[ProjectChapter]:
    if chapter_ids:
        result = await db.execute(
            select(ProjectChapter).where(
                ProjectChapter.project_id == project.id,
                ProjectChapter.id.in_(chapter_ids),
            )
        )
        chapters = result.scalars().all()
        chapter_map = {chapter.id: chapter for chapter in chapters}
        missing = [chapter_id for chapter_id in chapter_ids if chapter_id not in chapter_map]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid chapter_ids for project: {', '.join(missing)}",
            )
        return sorted(chapters, key=lambda c: (c.order_index, c.created_at, c.id))

    # Avoid async lazy-loading on project.chapters here. In background workers the
    # relationship may not be greenlet-enabled, which turns an ordinary rebuild into
    # `greenlet_spawn has not been called` before graph extraction even starts.
    result = await db.execute(
        select(ProjectChapter).where(ProjectChapter.project_id == project.id)
    )
    chapters = result.scalars().all()
    return sorted(chapters, key=lambda c: (c.order_index, c.created_at, c.id))


async def _resolve_text(
    *,
    body_text: str | None,
    chapter_ids: list[str] | None,
    project: TextProject,
    error_detail: str,
    db: AsyncSession,
) -> tuple[str, dict[str, Any]]:
    normalized_chapter_ids = _normalize_chapter_ids(chapter_ids)
    provided_text = (body_text or "").strip()

    if normalized_chapter_ids:
        chapters = await _resolve_chapters_for_project(project, normalized_chapter_ids, db)
        chapter_text = "\n\n".join((chapter.content or "").strip() for chapter in chapters if chapter.content is not None).strip()
        text = provided_text or chapter_text
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail,
            )
        source_ids = [chapter.id for chapter in chapters]
        return text, _build_provenance(source_chapter_ids=source_ids, text=text)

    chapters = await _resolve_chapters_for_project(project, None, db)
    chapter_text = "\n\n".join((chapter.content or "").strip() for chapter in chapters if chapter.content is not None).strip()
    text = provided_text or chapter_text
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail,
        )
    return text, _build_provenance(source_chapter_ids=[], text=text)



def _resolve_requirement(body_requirement: str | None, project: TextProject) -> str | None:
    if body_requirement is None:
        return (project.simulation_requirement or "").strip() or None
    return body_requirement.strip() or None


def _resolve_requirement_input(*, requirement: str | None, provided: bool, project: TextProject) -> str | None:
    if provided:
        return (requirement or "").strip() or None
    return _resolve_requirement(None, project)


def _resolve_analysis_model(project: TextProject, body: GraphOasisAnalyzeRequest | GraphOasisPrepareRequest) -> str:
    return resolve_component_model(project, "oasis_analysis", body.analysis_model)


def _resolve_simulation_model(project: TextProject, body: GraphOasisAnalyzeRequest | GraphOasisPrepareRequest) -> str:
    return resolve_component_model(project, "oasis_simulation_config", body.simulation_model)


def _resolve_report_model(project: TextProject, body: GraphOasisReportRequest) -> str:
    return resolve_component_model(project, "oasis_report", body.report_model)


def _get_project_analysis(project: TextProject) -> dict[str, Any] | None:
    analysis = getattr(project, "oasis_analysis", None)
    return analysis if isinstance(analysis, dict) else None


def _store_analysis_payload(project: TextProject, **fields: Any) -> dict[str, Any]:
    existing_analysis = getattr(project, "oasis_analysis", None)
    base = dict(existing_analysis or {})
    for key, value in fields.items():
        base[key] = value
    project.oasis_analysis = base
    return base


def _normalize_graph_build_mode(mode: str | None) -> str:
    value = str(mode or "").strip().lower()
    if value == GRAPH_BUILD_INCREMENTAL:
        return GRAPH_BUILD_INCREMENTAL
    return GRAPH_BUILD_REBUILD


def _extract_graph_build_state(project: TextProject) -> dict[str, Any]:
    analysis = _get_project_analysis(project)
    if not analysis:
        return {}
    state = analysis.get("_graph_build_state")
    return state if isinstance(state, dict) else {}


def _extract_graph_build_hashes(project: TextProject) -> dict[str, str]:
    raw = _extract_graph_build_state(project).get("chapter_hashes")
    if not isinstance(raw, dict):
        return {}
    hashes: dict[str, str] = {}
    for key, value in raw.items():
        chapter_id = str(key or "").strip()
        hash_value = str(value or "").strip()
        if chapter_id and hash_value:
            hashes[chapter_id] = hash_value
    return hashes


def _extract_graph_build_resume_state(project: TextProject) -> dict[str, Any]:
    raw = _extract_graph_build_state(project).get("resume")
    return raw if isinstance(raw, dict) else {}


def _to_utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_running_task_status(status_value: TaskStatus | str | None) -> bool:
    normalized = str(status_value.value if isinstance(status_value, TaskStatus) else status_value or "").strip().lower()
    return normalized in {"pending", "processing"}


def _is_stale_graph_task(task: TaskRecord) -> bool:
    updated_at = task.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - updated_at.astimezone(timezone.utc)).total_seconds()
    return age_seconds > _STALE_GRAPH_TASK_SECONDS


def _latest_running_graph_task(project_id: str) -> TaskRecord | None:
    tasks = task_manager.list_tasks(task_type="graph_build", project_id=project_id, limit=20)
    for task in tasks:
        if _is_running_task_status(task.status):
            if _is_stale_graph_task(task):
                if task_manager.has_active_runner(task.task_id):
                    return task
                task_manager.fail_task(
                    task.task_id,
                    "Graph build task became stale with no progress heartbeat.",
                    "Graph build task timed out",
                )
                continue
            return task
    return None


async def _build_graph_freshness_payload(project: TextProject, db: AsyncSession) -> dict[str, Any]:
    state = _extract_graph_build_state(project)
    resume_state = _extract_graph_build_resume_state(project)
    failed_chunk_indices = _normalize_int_list(resume_state.get("failed_chunk_indices"))
    last_build_at = str(state.get("updated_at") or "").strip() or None
    graph_mode = str(state.get("mode") or "").strip() or None

    base_payload: dict[str, Any] = {
        "graph_freshness": "empty",
        "graph_reason": None,
        "graph_changed_count": 0,
        "graph_added_count": 0,
        "graph_modified_count": 0,
        "graph_removed_count": 0,
        "graph_last_build_at": last_build_at,
        "graph_mode": graph_mode,
        "graph_syncing_task_id": None,
        "graph_resume_available": bool(failed_chunk_indices),
        "graph_resume_failed_chunks": len(failed_chunk_indices),
        "graph_resume_mode": str(resume_state.get("mode") or "").strip() or None,
    }

    if not project.ontology_schema:
        base_payload["graph_freshness"] = "no_ontology"
        base_payload["graph_reason"] = "ontology_missing"
        return base_payload

    running_task = _latest_running_graph_task(project.id)
    if running_task:
        base_payload["graph_freshness"] = "syncing"
        base_payload["graph_reason"] = "graph_build_task_running"
        base_payload["graph_syncing_task_id"] = running_task.task_id
        return base_payload

    if failed_chunk_indices:
        base_payload["graph_freshness"] = "stale"
        base_payload["graph_reason"] = "graph_build_incomplete_resume_available"
        return base_payload

    if not project.graph_id:
        base_payload["graph_freshness"] = "empty"
        base_payload["graph_reason"] = "graph_missing"
        return base_payload

    if not await has_graph_data(project.id, db=db):
        base_payload["graph_freshness"] = "stale"
        base_payload["graph_reason"] = "graph_store_empty_or_unreadable"
        return base_payload

    source_ids_raw = state.get("source_chapter_ids") if isinstance(state.get("source_chapter_ids"), list) else []
    source_ids = _normalize_chapter_ids(source_ids_raw)
    source_id_set = set(source_ids)
    previous_hashes_all = _extract_graph_build_hashes(project)
    previous_chapter_ids = (
        {chapter_id for chapter_id in previous_hashes_all.keys() if chapter_id in source_id_set}
        if source_ids
        else {chapter_id for chapter_id in previous_hashes_all.keys() if chapter_id != "__manual__"}
    )

    if not previous_chapter_ids:
        base_payload["graph_freshness"] = "stale"
        base_payload["graph_reason"] = "graph_baseline_missing_or_scope_changed"
        return base_payload

    last_build_dt = _to_utc_datetime(last_build_at)
    if not last_build_dt:
        base_payload["graph_freshness"] = "stale"
        base_payload["graph_reason"] = "graph_build_timestamp_missing_or_invalid"
        return base_payload

    chapter_query = select(ProjectChapter.id, ProjectChapter.updated_at).where(ProjectChapter.project_id == project.id)
    if source_ids:
        chapter_query = chapter_query.where(ProjectChapter.id.in_(source_ids))
    result = await db.execute(chapter_query)
    chapter_rows = result.all()
    current_chapter_ids = {str(row[0]) for row in chapter_rows if str(row[0] or "").strip()}
    current_updated_at: dict[str, datetime | None] = {
        str(row[0]): _to_utc_datetime(row[1])
        for row in chapter_rows
        if str(row[0] or "").strip()
    }

    added = [chapter_id for chapter_id in current_chapter_ids if chapter_id not in previous_chapter_ids]
    removed = [chapter_id for chapter_id in previous_chapter_ids if chapter_id not in current_chapter_ids]
    modified = [
        chapter_id
        for chapter_id in (current_chapter_ids & previous_chapter_ids)
        if (current_updated_at.get(chapter_id) or last_build_dt) > last_build_dt
    ]

    changed_count = len(added) + len(modified) + len(removed)
    base_payload["graph_changed_count"] = changed_count
    base_payload["graph_added_count"] = len(added)
    base_payload["graph_modified_count"] = len(modified)
    base_payload["graph_removed_count"] = len(removed)

    if changed_count > 0:
        base_payload["graph_freshness"] = "stale"
        base_payload["graph_reason"] = "chapter_metadata_changed_after_last_graph_build"
        return base_payload

    base_payload["graph_freshness"] = "fresh"
    base_payload["graph_reason"] = "graph_synced_with_current_chapters"
    return base_payload


def _store_graph_build_state(
    project: TextProject,
    *,
    chapter_hashes: dict[str, str],
    mode: str,
    provenance: dict[str, Any],
    changed_chapter_ids: list[str] | None = None,
    resume_state: dict[str, Any] | None = None,
) -> None:
    state: dict[str, Any] = {
        "mode": _normalize_graph_build_mode(mode),
        "chapter_hashes": {
            str(chapter_id): str(content_hash)
            for chapter_id, content_hash in (chapter_hashes or {}).items()
            if str(chapter_id or "").strip() and str(content_hash or "").strip()
        },
        "source_chapter_ids": list(provenance.get("source_chapter_ids") or []),
        "content_hash": str(provenance.get("content_hash") or ""),
        "updated_at": _now_iso(),
    }
    if changed_chapter_ids is not None:
        state["changed_chapter_ids"] = [
            str(chapter_id)
            for chapter_id in changed_chapter_ids
            if str(chapter_id or "").strip()
        ]
    if isinstance(resume_state, dict) and resume_state:
        state["resume"] = resume_state
    _store_analysis_payload(project, _graph_build_state=state)


def _merge_chapter_text_by_ids(chapters: list[ProjectChapter], include_ids: list[str]) -> str:
    include_set = {
        str(chapter_id)
        for chapter_id in include_ids
        if str(chapter_id or "").strip()
    }
    if not include_set:
        return ""
    return "\n\n".join(
        (chapter.content or "").strip()
        for chapter in chapters
        if chapter.id in include_set and (chapter.content or "").strip()
    ).strip()


def _graph_build_resume_matches(
    *,
    resume_state: dict[str, Any],
    provenance: dict[str, Any],
) -> bool:
    if not resume_state:
        return False
    resume_hash = str(resume_state.get("content_hash") or "").strip()
    current_hash = str(provenance.get("content_hash") or "").strip()
    if not resume_hash or not current_hash or resume_hash != current_hash:
        return False
    resume_source_ids = _normalize_chapter_ids(resume_state.get("source_chapter_ids"))
    current_source_ids = _normalize_chapter_ids(provenance.get("source_chapter_ids"))
    return resume_source_ids == current_source_ids


def _build_graph_resume_state(
    *,
    graph_id: str,
    mode: str,
    provenance: dict[str, Any],
    selected_chunk_indices: list[int],
    completed_chunk_indices: list[int],
    failed_chunk_indices: list[int],
    total_chunks: int,
    failed_errors: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "graph_id": str(graph_id or "").strip(),
        "mode": _normalize_graph_build_mode(mode),
        "content_hash": str(provenance.get("content_hash") or "").strip(),
        "source_chapter_ids": _normalize_chapter_ids(provenance.get("source_chapter_ids")),
        "selected_chunk_indices": _normalize_int_list(selected_chunk_indices),
        "completed_chunk_indices": _normalize_int_list(completed_chunk_indices),
        "failed_chunk_indices": _normalize_int_list(failed_chunk_indices),
        "total_chunks": max(0, int(total_chunks or 0)),
        "updated_at": _now_iso(),
    }
    if isinstance(failed_errors, dict) and failed_errors:
        payload["failed_errors"] = {
            str(key): str(value or "").strip()
            for key, value in failed_errors.items()
            if str(key or "").strip() and str(value or "").strip()
        }
    return payload


def _is_payload_matching_provenance(payload: dict[str, Any] | None, provenance: dict[str, Any]) -> bool:
    payload_provenance = _read_provenance(payload)
    if not payload_provenance:
        return False
    return payload_provenance.get("content_hash") == provenance.get("content_hash")


def _build_and_store_oasis_package(
    *,
    project: TextProject,
    analysis: dict[str, Any],
    requirement: str | None,
    provenance: dict[str, Any],
    oasis_config: dict[str, Any] | None,
) -> dict[str, Any]:
    package = build_oasis_package(
        project_id=project.id,
        project_title=project.title,
        requirement=requirement,
        ontology=project.ontology_schema,
        analysis=analysis,
        component_models=project.component_models if isinstance(project.component_models, dict) else None,
        oasis_config=oasis_config,
    )
    package = _inject_provenance(package, provenance)
    _store_analysis_payload(project, latest_package=package)
    return package


def _ensure_oasis_package(
    *,
    project: TextProject,
    analysis: dict[str, Any],
    requirement: str | None,
    provenance: dict[str, Any],
    oasis_config: dict[str, Any] | None,
    package_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package = package_override if isinstance(package_override, dict) else (
        analysis.get("latest_package") if isinstance(analysis.get("latest_package"), dict) else None
    )
    if not _is_payload_matching_provenance(package, provenance):
        package = _build_and_store_oasis_package(
            project=project,
            analysis=analysis,
            requirement=requirement,
            provenance=provenance,
            oasis_config=oasis_config,
        )
    return package


def _ensure_oasis_run_result(
    *,
    analysis: dict[str, Any],
    package: dict[str, Any],
    provenance: dict[str, Any],
    project: TextProject,
) -> dict[str, Any]:
    run_result = analysis.get("latest_run") if isinstance(analysis.get("latest_run"), dict) else None
    if not _is_payload_matching_provenance(run_result, provenance):
        run_result = build_oasis_run_result(package=package, analysis=analysis)
        run_result = _inject_provenance(run_result, provenance)
        _store_analysis_payload(project, latest_run=run_result)
    return run_result


async def _resolve_oasis_runtime_context(
    *,
    project: TextProject,
    project_id: str,
    chapter_ids: list[str] | None,
    error_detail: str,
    billing_user_id: str | None,
    db: AsyncSession,
) -> tuple[dict[str, Any], str | None, dict[str, Any], dict[str, Any] | None]:
    text, provenance = await _resolve_text(
        body_text=None,
        chapter_ids=chapter_ids,
        project=project,
        error_detail=error_detail,
        db=db,
    )
    requirement = _resolve_requirement(None, project)
    analysis_model = resolve_component_model(project, "oasis_analysis")
    simulation_model = resolve_component_model(project, "oasis_simulation_config")
    oasis_config = await load_oasis_config(db)
    analysis = await _ensure_analysis_for_provenance(
        project=project,
        project_id=project_id,
        text=text,
        requirement=requirement,
        prompt=None,
        analysis_model=analysis_model,
        simulation_model=simulation_model,
        oasis_config=oasis_config,
        billing_user_id=billing_user_id,
        provenance=provenance,
        db=db,
    )
    return analysis, requirement, provenance, oasis_config


def _task_to_schema(task: TaskRecord) -> GraphTaskInfo:
    return GraphTaskInfo.model_validate(task.to_dict())


def _create_project_task(*, task_type: str, project_id: str, user_id: str, metadata: dict[str, Any] | None = None) -> TaskRecord:
    task_manager.cleanup_old_tasks(max_age_hours=168)
    task_metadata: dict[str, Any] = {
        "project_id": project_id,
        "user_id": user_id,
    }
    if metadata:
        task_metadata.update(metadata)
    return task_manager.create_task(task_type, task_metadata)


def _cancel_superseded_auto_graph_tasks(task: TaskRecord) -> None:
    task_type = str(getattr(task, "task_type", "") or "").strip()
    if task_type != "graph_build":
        return
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    if not bool(metadata.get("auto_created")):
        return
    if str(metadata.get("trigger_source_kind") or "").strip().lower() != "chapter":
        return

    keep_task_id = str(getattr(task, "task_id", "") or "").strip()
    project_id = str(metadata.get("project_id") or "").strip()
    keep_idempotency_key = str(metadata.get("idempotency_key") or "").strip()
    keep_created_at = getattr(task, "created_at", None)
    if not keep_task_id or not project_id or keep_created_at is None:
        return
    if keep_created_at.tzinfo is None:
        keep_created_at = keep_created_at.replace(tzinfo=timezone.utc)

    for candidate in task_manager.list_tasks(task_type=task_type, project_id=project_id, limit=200):
        if candidate.task_id == keep_task_id:
            continue
        if candidate.status in _TERMINAL_TASK_STATUSES:
            continue
        candidate_metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
        if not bool(candidate_metadata.get("auto_created")):
            continue
        if str(candidate_metadata.get("trigger_source_kind") or "").strip().lower() != "chapter":
            continue
        if str(candidate_metadata.get("idempotency_key") or "").strip() == keep_idempotency_key:
            continue
        candidate_created_at = getattr(candidate, "created_at", None)
        if candidate_created_at is None:
            continue
        if candidate_created_at.tzinfo is None:
            candidate_created_at = candidate_created_at.replace(tzinfo=timezone.utc)
        if candidate_created_at >= keep_created_at:
            continue
        task_manager.cancel_task(
            candidate.task_id,
            message="Cancelled because a newer automatic graph sync task was scheduled",
        )


def _start_project_task(
    *,
    task_type: str,
    project_id: str,
    user_id: str,
    worker: Callable[[str], Coroutine[Any, Any, None]],
    metadata: dict[str, Any] | None = None,
) -> GraphTaskStartResponse:
    task_metadata: dict[str, Any] = dict(metadata or {})
    idempotency_key = str(task_metadata.get("idempotency_key") or "").strip()
    if idempotency_key:
        existing = task_manager.find_inflight_task_by_idempotency(
            task_type=task_type,
            project_id=project_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return GraphTaskStartResponse(status="accepted", task=_task_to_schema(existing))

    task = _create_project_task(
        task_type=task_type,
        project_id=project_id,
        user_id=user_id,
        metadata=task_metadata,
    )
    _cancel_superseded_auto_graph_tasks(task)

    async def _runner() -> None:
        try:
            await worker(task.task_id)
        finally:
            task_manager.unregister_runner(task.task_id)

    runner = asyncio.create_task(_runner())
    task_manager.register_runner(task.task_id, runner)
    return GraphTaskStartResponse(status="accepted", task=_task_to_schema(task))


def _ensure_task_project(task: TaskRecord | None, project_id: str) -> TaskRecord:
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if str((task.metadata or {}).get("project_id") or "") != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def _mark_task_cancelled(task_id: str, message: str = "Task cancelled by user") -> None:
    task = task_manager.get_task(task_id)
    if not task:
        return
    if task.status in _TERMINAL_TASK_STATUSES:
        return
    task_manager.update_task(
        task_id,
        status=TaskStatus.CANCELLED,
        message=message,
    )


async def _run_ontology_task(
    task_id: str,
    *,
    project_id: str,
    text: str | None,
    chapter_ids: list[str] | None,
    requirement: str | None,
    model: str | None,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading project context...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")

            task_manager.update_task(task_id, progress=18, message="Resolving chapter source text...")
            resolved_text, provenance = await _resolve_text(
                body_text=text,
                chapter_ids=chapter_ids,
                project=project,
                error_detail="No source text provided for ontology generation",
                db=db,
            )

            text_size = len(resolved_text)
            approx_segments = max(1, (text_size + 7999) // 8000)
            task_manager.update_task(
                task_id,
                progress=35,
                message=f"Preparing ontology from {text_size} chars ({approx_segments} segments)...",
            )

            selected_model = resolve_component_model(project, "ontology_generation", model)
            task_manager.update_task(task_id, progress=62, message="Generating ontology schema...")
            with llm_billing_scope(
                user_id=project.user_id,
                project_id=project.id,
            ):
                ontology = await generate_ontology(
                    text=resolved_text,
                    db=db,
                    requirement=requirement,
                    model=selected_model,
                )
            project.ontology_schema = ontology
            if requirement is not None:
                project.simulation_requirement = requirement.strip() or None
            await db.flush()
            await db.commit()
            task_manager.complete_task(
                task_id,
                {
                    "ontology": ontology,
                    "content_hash": provenance.get("content_hash"),
                    "source_chapter_ids": provenance.get("source_chapter_ids"),
                },
                "Ontology generated",
            )
        except asyncio.CancelledError:
            await db.rollback()
            _mark_task_cancelled(task_id)
            raise
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, _describe_task_exception(exc), "Failed to generate ontology")


async def _resolve_graph_build_plan(
    *,
    body_text: str | None,
    chapter_ids: list[str] | None,
    project: TextProject,
    mode: str | None,
    db: AsyncSession,
) -> dict[str, Any]:
    normalized_chapter_ids = _normalize_chapter_ids(chapter_ids)
    resolved_text, resolved_provenance = await _resolve_text(
        body_text=body_text,
        chapter_ids=normalized_chapter_ids,
        project=project,
        error_detail="No source text provided for graph build",
        db=db,
    )
    chapters = await _resolve_chapters_for_project(
        project,
        normalized_chapter_ids if normalized_chapter_ids else None,
        db,
    )
    chapter_hashes: dict[str, str] = {
        chapter.id: _hash_text((chapter.content or "").strip())
        for chapter in chapters
    }
    previous_hashes = _extract_graph_build_hashes(project)

    requested_mode = _normalize_graph_build_mode(mode)
    effective_mode = requested_mode
    changed_chapter_ids: list[str] = list(chapter_hashes.keys())
    added_chapter_ids: list[str] = []
    modified_chapter_ids: list[str] = []
    removed_chapter_ids: list[str] = []
    build_text = resolved_text
    build_provenance = resolved_provenance
    skip_reason: str | None = None
    mode_reason: str | None = None
    graph_exists = bool(project.graph_id)
    full_scope = len(normalized_chapter_ids) == 0

    if requested_mode == GRAPH_BUILD_INCREMENTAL:
        if not graph_exists:
            effective_mode = GRAPH_BUILD_REBUILD
            mode_reason = "Incremental update requested without existing graph; switched to full rebuild."
        else:
            if chapter_hashes:
                added_chapter_ids = [
                    chapter_id
                    for chapter_id, content_hash in chapter_hashes.items()
                    if chapter_id not in previous_hashes
                ]
                modified_chapter_ids = [
                    chapter_id
                    for chapter_id, content_hash in chapter_hashes.items()
                    if chapter_id in previous_hashes and previous_hashes.get(chapter_id) != content_hash
                ]
                if full_scope:
                    removed_chapter_ids = [
                        chapter_id
                        for chapter_id in previous_hashes.keys()
                        if chapter_id != "__manual__" and chapter_id not in chapter_hashes
                    ]

                if modified_chapter_ids and not full_scope:
                    raise ValueError(
                        "Incremental update for edited chapters requires full project scope. "
                        "Clear chapter selection or use rebuild mode."
                    )

                if modified_chapter_ids or removed_chapter_ids:
                    effective_mode = GRAPH_BUILD_REBUILD
                    mode_reason = "Detected edited/removed chapters; switched to full rebuild to prevent stale graph data."
                    changed_chapter_ids = list(chapter_hashes.keys())
                    build_text = resolved_text
                    build_provenance = resolved_provenance
                else:
                    changed_chapter_ids = list(added_chapter_ids)

                if effective_mode == GRAPH_BUILD_INCREMENTAL:
                    if not changed_chapter_ids:
                        skip_reason = "No chapter changes detected for incremental update."
                        build_text = ""
                    else:
                        delta_text = _merge_chapter_text_by_ids(chapters, changed_chapter_ids)
                        if not delta_text:
                            skip_reason = "Changed chapters contain no text to ingest."
                            build_text = ""
                        else:
                            build_text = delta_text
                            build_provenance = _build_provenance(
                                source_chapter_ids=changed_chapter_ids,
                                text=build_text,
                            )
            else:
                if full_scope:
                    removed_chapter_ids = [
                        chapter_id
                        for chapter_id in previous_hashes.keys()
                        if chapter_id != "__manual__"
                    ]
                    if removed_chapter_ids:
                        effective_mode = GRAPH_BUILD_REBUILD
                        mode_reason = (
                            "Detected removed chapter sources with empty chapter set; switched to full rebuild."
                        )
                        changed_chapter_ids = list(removed_chapter_ids)
                        build_text = resolved_text
                        build_provenance = resolved_provenance

                if effective_mode != GRAPH_BUILD_REBUILD:
                    current_hash = _hash_text(resolved_text)
                    previous_manual_hash = previous_hashes.get("__manual__", "")
                    if current_hash == previous_manual_hash:
                        skip_reason = "No text changes detected for incremental update."
                        build_text = ""
                        changed_chapter_ids = []
                    else:
                        changed_chapter_ids = ["__manual__"]
                else:
                    if not changed_chapter_ids:
                        changed_chapter_ids = ["__manual__"]

    return {
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "mode_reason": mode_reason,
        "resolved_text": resolved_text,
        "resolved_provenance": resolved_provenance,
        "build_text": build_text,
        "build_provenance": build_provenance,
        "skip_reason": skip_reason,
        "chapter_hashes": chapter_hashes,
        "previous_hashes": previous_hashes,
        "changed_chapter_ids": changed_chapter_ids,
        "added_chapter_ids": added_chapter_ids,
        "modified_chapter_ids": modified_chapter_ids,
        "removed_chapter_ids": removed_chapter_ids,
        "full_scope": full_scope,
    }


async def _execute_graph_build(
    *,
    project_id: str,
    project: TextProject,
    body_text: str | None,
    chapter_ids: list[str] | None,
    ontology: dict[str, Any] | None,
    mode: str | None,
    resume_failed: bool = False,
    db: AsyncSession,
    progress_callback: Callable[[int, str], None] | None = None,
    preview_graph_id_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if ontology:
        project.ontology_schema = ontology
    if not project.ontology_schema:
        raise RuntimeError("Ontology not generated. Please generate ontology first.")

    resume_state = _extract_graph_build_resume_state(project)
    plan_chapter_ids = chapter_ids
    if resume_failed and not _normalize_chapter_ids(chapter_ids):
        resume_source_ids = _normalize_chapter_ids(resume_state.get("source_chapter_ids"))
        if resume_source_ids:
            plan_chapter_ids = resume_source_ids

    plan = await _resolve_graph_build_plan(
        body_text=body_text,
        chapter_ids=plan_chapter_ids,
        project=project,
        mode=mode,
        db=db,
    )

    effective_mode = str(plan["effective_mode"])
    requested_mode = str(plan["requested_mode"])
    mode_reason = str(plan.get("mode_reason") or "").strip() or None
    chapter_hashes: dict[str, str] = dict(plan["chapter_hashes"])
    previous_hashes: dict[str, str] = dict(plan["previous_hashes"])
    changed_chapter_ids: list[str] = list(plan["changed_chapter_ids"])
    added_chapter_ids: list[str] = list(plan.get("added_chapter_ids") or [])
    modified_chapter_ids: list[str] = list(plan.get("modified_chapter_ids") or [])
    removed_chapter_ids: list[str] = list(plan.get("removed_chapter_ids") or [])
    build_provenance: dict[str, Any] = dict(plan["build_provenance"])
    resume_graph_id = ""
    resume_chunk_indices: list[int] = []

    if plan["skip_reason"]:
        next_hashes = dict(previous_hashes)
        for chapter_id in changed_chapter_ids:
            if chapter_id in chapter_hashes:
                next_hashes[chapter_id] = chapter_hashes[chapter_id]
        if plan["full_scope"]:
            next_hashes = {
                chapter_id: content_hash
                for chapter_id, content_hash in next_hashes.items()
                if chapter_id in chapter_hashes
            }
        _store_graph_build_state(
            project,
            chapter_hashes=next_hashes,
            mode=effective_mode,
            provenance=build_provenance,
            changed_chapter_ids=changed_chapter_ids,
        )
        await db.flush()
        return {
            "status": "skipped",
            "requested_mode": requested_mode,
            "mode": effective_mode,
            "mode_reason": mode_reason,
            "graph_id": project.graph_id,
            "content_hash": build_provenance.get("content_hash"),
            "source_chapter_ids": build_provenance.get("source_chapter_ids"),
            "changed_chapter_ids": changed_chapter_ids,
            "added_chapter_ids": added_chapter_ids,
            "modified_chapter_ids": modified_chapter_ids,
            "removed_chapter_ids": removed_chapter_ids,
            "reason": plan["skip_reason"],
        }

    build_text = str(plan["build_text"])
    graph_input = build_graph_input_with_ontology(build_text, project.ontology_schema)
    graph_source_text = graph_input
    ontology_default_model = resolve_component_model(project, "ontology_generation")
    graph_model = resolve_component_model(project, "graph_build", fallback_model=ontology_default_model)
    graph_embedding_model = resolve_component_model(
        project,
        "graph_embedding",
        fallback_model="",
    )

    if resume_failed:
        if not _graph_build_resume_matches(resume_state=resume_state, provenance=build_provenance):
            raise ValueError("No matching failed graph build is available to continue.")
        resume_graph_id = str(resume_state.get("graph_id") or "").strip()
        resume_chunk_indices = _normalize_int_list(resume_state.get("failed_chunk_indices"))
        if not resume_graph_id or not resume_chunk_indices:
            raise ValueError("No failed graph chunks are available to continue.")
        effective_mode = _normalize_graph_build_mode(resume_state.get("mode") or effective_mode)
        mode_reason = "Continuing previously failed graph build chunks."
    else:
        existing_state = _extract_graph_build_state(project)
        if isinstance(existing_state.get("resume"), dict):
            next_state = dict(existing_state)
            next_state.pop("resume", None)
            _store_analysis_payload(project, _graph_build_state=next_state)
            await db.flush()

    preview_graph_id = resume_graph_id or project.graph_id or f"graphiti_{uuid4().hex[:16]}"
    if preview_graph_id_callback:
        preview_graph_id_callback(preview_graph_id)

    if not resume_failed and effective_mode == GRAPH_BUILD_REBUILD and project.graph_id:
        if progress_callback:
            progress_callback(25, "Cleaning previous graph...")
        try:
            await _await_if_needed(
                delete_graph_data(
                    project_id,
                    model=graph_model,
                    embedding_model=graph_embedding_model or None,
                    db=db,
                )
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to clear previous graph before rebuild: {exc}") from exc
        project.graph_id = None
        await db.flush()

    try:
        graph_id = await build_graph(
            project_id,
            graph_source_text,
            model=graph_model,
            embedding_model=graph_embedding_model or None,
            ontology=project.ontology_schema,
            db=db,
            progress_callback=progress_callback,
            graph_id_override=preview_graph_id,
            chunk_indices=resume_chunk_indices or None,
            continue_on_error=True,
        )
    except GraphBuildPartialFailure as exc:
        effective_graph_id = str(exc.graph_id or resume_graph_id or project.graph_id or "").strip()
        _store_graph_build_state(
            project,
            chapter_hashes=previous_hashes,
            mode=effective_mode,
            provenance=build_provenance,
            changed_chapter_ids=changed_chapter_ids,
            resume_state=_build_graph_resume_state(
                graph_id=effective_graph_id,
                mode=effective_mode,
                provenance=build_provenance,
                selected_chunk_indices=exc.selected_chunk_indices,
                completed_chunk_indices=exc.completed_chunk_indices,
                failed_chunk_indices=exc.failed_chunk_indices,
                total_chunks=exc.total_chunks,
                failed_errors=exc.failed_errors,
            ),
        )
        await db.flush()
        failed_count = len(exc.failed_chunk_indices)
        selected_count = len(exc.selected_chunk_indices)
        return {
            "status": "partial_failed",
            "requested_mode": requested_mode,
            "mode": effective_mode,
            "mode_reason": mode_reason,
            "graph_id": project.graph_id,
            "resume_graph_id": effective_graph_id or None,
            "content_hash": build_provenance.get("content_hash"),
            "source_chapter_ids": build_provenance.get("source_chapter_ids"),
            "changed_chapter_ids": changed_chapter_ids,
            "added_chapter_ids": added_chapter_ids,
            "modified_chapter_ids": modified_chapter_ids,
            "removed_chapter_ids": removed_chapter_ids,
            "selected_chunk_indices": exc.selected_chunk_indices,
            "completed_chunk_indices": exc.completed_chunk_indices,
            "failed_chunk_indices": exc.failed_chunk_indices,
            "failed_chunk_count": failed_count,
            "total_chunks": exc.total_chunks,
            "resume_available": failed_count > 0,
            "reason": f"{failed_count}/{max(1, selected_count)} graph chunks failed. Continue is available.",
            "failed_errors": exc.failed_errors,
        }
    project.graph_id = graph_id

    if effective_mode == GRAPH_BUILD_REBUILD:
        next_hashes = dict(chapter_hashes)
    else:
        next_hashes = dict(previous_hashes)
        for chapter_id in changed_chapter_ids:
            if chapter_id in chapter_hashes:
                next_hashes[chapter_id] = chapter_hashes[chapter_id]
        if plan["full_scope"]:
            next_hashes = {
                chapter_id: content_hash
                for chapter_id, content_hash in next_hashes.items()
                if chapter_id in chapter_hashes
            }

    _store_graph_build_state(
        project,
        chapter_hashes=next_hashes,
        mode=effective_mode,
        provenance=build_provenance,
        changed_chapter_ids=changed_chapter_ids,
        resume_state=None,
    )
    await db.flush()
    return {
        "status": "ok",
        "requested_mode": requested_mode,
        "mode": effective_mode,
        "mode_reason": mode_reason,
        "graph_id": graph_id,
        "content_hash": build_provenance.get("content_hash"),
        "source_chapter_ids": build_provenance.get("source_chapter_ids"),
        "changed_chapter_ids": changed_chapter_ids,
        "added_chapter_ids": added_chapter_ids,
        "modified_chapter_ids": modified_chapter_ids,
        "removed_chapter_ids": removed_chapter_ids,
    }


async def _run_graph_build_task(
    task_id: str,
    *,
    project_id: str,
    text: str | None,
    chapter_ids: list[str] | None,
    ontology: dict[str, Any] | None,
    build_mode: str | None = None,
    resume_failed: bool = False,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading project context...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")

            task_manager.update_task(task_id, progress=12, message="Resolving chapter source text...")

            def _on_preview_graph_id(graph_id: str) -> None:
                task = task_manager.get_task(task_id)
                detail = dict(task.progress_detail or {}) if task and isinstance(task.progress_detail, dict) else {}
                detail["preview_graph_id"] = graph_id
                task_manager.update_task(task_id, progress_detail=detail)

            def _on_build_progress(progress: int, message: str) -> None:
                bounded_progress = max(25, min(97, int(progress)))
                task = task_manager.get_task(task_id)
                detail = task.progress_detail if task and isinstance(task.progress_detail, dict) else None
                task_manager.update_task(task_id, progress=bounded_progress, message=message, progress_detail=detail)

            task_manager.update_task(task_id, progress=28, message="Building graph in segments...")
            build_result = await _execute_graph_build(
                project_id=project_id,
                project=project,
                body_text=text,
                chapter_ids=chapter_ids,
                ontology=ontology,
                mode=build_mode,
                resume_failed=resume_failed,
                db=db,
                progress_callback=_on_build_progress,
                preview_graph_id_callback=_on_preview_graph_id,
            )
            await db.commit()
            status = str(build_result.get("status") or "ok")
            is_incremental = str(build_result.get("mode") or "") == GRAPH_BUILD_INCREMENTAL
            completion_message = "Knowledge graph updated incrementally" if is_incremental else "Knowledge graph built"
            if status == "skipped":
                completion_message = str(build_result.get("reason") or "No graph changes to apply")
            elif status == "partial_failed":
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    progress=max(0, min(99, int(task_manager.get_task(task_id).progress if task_manager.get_task(task_id) else 0))),
                    message=str(build_result.get("reason") or "Graph build partially failed"),
                    error=str(build_result.get("reason") or "Graph build partially failed"),
                    result={
                        "graph_id": build_result.get("graph_id"),
                        "resume_graph_id": build_result.get("resume_graph_id"),
                        "requested_mode": build_result.get("requested_mode"),
                        "mode": build_result.get("mode"),
                        "mode_reason": build_result.get("mode_reason"),
                        "status": status,
                        "content_hash": build_result.get("content_hash"),
                        "source_chapter_ids": build_result.get("source_chapter_ids"),
                        "changed_chapter_ids": build_result.get("changed_chapter_ids"),
                        "added_chapter_ids": build_result.get("added_chapter_ids"),
                        "modified_chapter_ids": build_result.get("modified_chapter_ids"),
                        "removed_chapter_ids": build_result.get("removed_chapter_ids"),
                        "selected_chunk_indices": build_result.get("selected_chunk_indices"),
                        "completed_chunk_indices": build_result.get("completed_chunk_indices"),
                        "failed_chunk_indices": build_result.get("failed_chunk_indices"),
                        "failed_chunk_count": build_result.get("failed_chunk_count"),
                        "total_chunks": build_result.get("total_chunks"),
                        "resume_available": build_result.get("resume_available"),
                        "reason": build_result.get("reason"),
                        "failed_errors": build_result.get("failed_errors"),
                    },
                )
                return
            elif build_result.get("mode_reason"):
                completion_message = str(build_result.get("mode_reason"))
            task_manager.complete_task(
                task_id,
                {
                    "graph_id": build_result.get("graph_id"),
                    "requested_mode": build_result.get("requested_mode"),
                    "mode": build_result.get("mode"),
                    "mode_reason": build_result.get("mode_reason"),
                    "status": status,
                    "content_hash": build_result.get("content_hash"),
                    "source_chapter_ids": build_result.get("source_chapter_ids"),
                    "changed_chapter_ids": build_result.get("changed_chapter_ids"),
                    "added_chapter_ids": build_result.get("added_chapter_ids"),
                    "modified_chapter_ids": build_result.get("modified_chapter_ids"),
                    "removed_chapter_ids": build_result.get("removed_chapter_ids"),
                    "reason": build_result.get("reason"),
                },
                completion_message,
            )
        except asyncio.CancelledError:
            await db.rollback()
            _mark_task_cancelled(task_id)
            raise
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, _describe_task_exception(exc), "Failed to build graph")


async def _generate_and_store_oasis_analysis(
    *,
    project: TextProject,
    project_id: str,
    text: str,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str,
    simulation_model: str,
    oasis_config: dict[str, Any] | None,
    billing_user_id: str | None,
    provenance: dict[str, Any],
    db: AsyncSession,
) -> tuple[dict, dict]:
    with llm_billing_scope(
        user_id=billing_user_id,
        project_id=project_id,
    ):
        analysis, context = await analyze_and_enrich_oasis(
            project_id=project_id,
            text=text,
            ontology=project.ontology_schema,
            requirement=requirement,
            prompt=prompt,
            analysis_model=analysis_model,
            simulation_model=simulation_model,
            oasis_config=oasis_config,
            db=db,
        )
    analysis_payload = _inject_provenance(dict(analysis or {}), provenance)
    context_payload = _inject_provenance(dict(context or {}), provenance)
    project.oasis_analysis = analysis_payload
    await db.flush()
    return analysis_payload, context_payload


async def _ensure_analysis_for_provenance(
    *,
    project: TextProject,
    project_id: str,
    text: str,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str,
    simulation_model: str,
    oasis_config: dict[str, Any] | None,
    billing_user_id: str | None,
    provenance: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    existing_analysis = _get_project_analysis(project)
    existing_provenance = _read_provenance(existing_analysis)
    if (
        existing_analysis
        and existing_provenance
        and existing_provenance.get("content_hash") == provenance.get("content_hash")
    ):
        return existing_analysis

    analysis, _ = await _generate_and_store_oasis_analysis(
        project=project,
        project_id=project_id,
        text=text,
        requirement=requirement,
        prompt=prompt,
        analysis_model=analysis_model,
        simulation_model=simulation_model,
        oasis_config=oasis_config,
        billing_user_id=billing_user_id,
        provenance=provenance,
        db=db,
    )
    return analysis



async def _prepare_and_store_oasis_package(
    *,
    project: TextProject,
    project_id: str,
    text: str,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str,
    simulation_model: str,
    oasis_config: dict[str, Any] | None,
    billing_user_id: str | None,
    provenance: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    analysis = await _ensure_analysis_for_provenance(
        project=project,
        project_id=project_id,
        text=text,
        requirement=requirement,
        prompt=prompt,
        analysis_model=analysis_model,
        simulation_model=simulation_model,
        oasis_config=oasis_config,
        billing_user_id=billing_user_id,
        provenance=provenance,
        db=db,
    )
    package = _build_and_store_oasis_package(
        project=project,
        analysis=analysis,
        requirement=requirement,
        provenance=provenance,
        oasis_config=oasis_config,
    )
    await db.flush()
    return package


async def _run_analyze_task(
    task_id: str,
    *,
    project_id: str,
    text: str | None,
    chapter_ids: list[str] | None,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str | None,
    simulation_model: str | None,
    requirement_provided: bool,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading project context...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")

            _require_ontology_and_graph(project, "OASIS analysis")
            effective_requirement = _resolve_requirement_input(
                requirement=requirement,
                provided=requirement_provided,
                project=project,
            )
            if requirement_provided:
                project.simulation_requirement = effective_requirement

            selected_analysis_model = analysis_model or resolve_component_model(project, "oasis_analysis")
            selected_simulation_model = simulation_model or resolve_component_model(project, "oasis_simulation_config")
            oasis_config = await load_oasis_config(db)

            task_manager.update_task(task_id, progress=30, message="Resolving chapter source text...")
            resolved_text, provenance = await _resolve_text(
                body_text=text,
                chapter_ids=chapter_ids,
                project=project,
                error_detail="No source text provided for OASIS analysis",
                db=db,
            )
            task_manager.update_task(task_id, progress=60, message="Generating OASIS analysis...")
            analysis, context = await _generate_and_store_oasis_analysis(
                project=project,
                project_id=project_id,
                text=resolved_text,
                requirement=effective_requirement,
                prompt=prompt,
                analysis_model=selected_analysis_model,
                simulation_model=selected_simulation_model,
                oasis_config=oasis_config,
                billing_user_id=project.user_id,
                provenance=provenance,
                db=db,
            )
            await db.commit()
            task_manager.complete_task(
                task_id,
                {"analysis": analysis, "context": context},
                "OASIS analysis generated",
            )
        except asyncio.CancelledError:
            await db.rollback()
            _mark_task_cancelled(task_id)
            raise
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, _describe_task_exception(exc), "Failed to generate OASIS analysis")


async def _run_prepare_task(
    task_id: str,
    *,
    project_id: str,
    text: str | None,
    chapter_ids: list[str] | None,
    requirement: str | None,
    prompt: str | None,
    analysis_model: str | None,
    simulation_model: str | None,
    requirement_provided: bool,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading project context...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")

            _require_ontology_and_graph(project, "OASIS preparation")
            effective_requirement = _resolve_requirement_input(
                requirement=requirement,
                provided=requirement_provided,
                project=project,
            )
            if requirement_provided:
                project.simulation_requirement = effective_requirement
            selected_analysis_model = analysis_model or resolve_component_model(project, "oasis_analysis")
            selected_simulation_model = simulation_model or resolve_component_model(project, "oasis_simulation_config")
            oasis_config = await load_oasis_config(db)

            task_manager.update_task(task_id, progress=35, message="Preparing OASIS package...")
            resolved_text, provenance = await _resolve_text(
                body_text=text,
                chapter_ids=chapter_ids,
                project=project,
                error_detail="No source text provided for OASIS analysis",
                db=db,
            )
            package = await _prepare_and_store_oasis_package(
                project=project,
                project_id=project_id,
                text=resolved_text,
                requirement=effective_requirement,
                prompt=prompt,
                analysis_model=selected_analysis_model,
                simulation_model=selected_simulation_model,
                oasis_config=oasis_config,
                billing_user_id=project.user_id,
                provenance=provenance,
                db=db,
            )
            await db.commit()
            task_manager.complete_task(
                task_id,
                {"package": package},
                "OASIS package prepared",
            )
        except asyncio.CancelledError:
            await db.rollback()
            _mark_task_cancelled(task_id)
            raise
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, _describe_task_exception(exc), "Failed to prepare OASIS package")


async def _run_simulation_task(
    task_id: str,
    *,
    project_id: str,
    package_override: dict[str, Any] | None,
    chapter_ids: list[str] | None,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading OASIS package...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")
            _require_ontology_and_graph(project, "OASIS simulation")

            task_manager.update_task(task_id, progress=25, message="Resolving chapter source text...")
            analysis, requirement, provenance, oasis_config = await _resolve_oasis_runtime_context(
                project=project,
                project_id=project_id,
                chapter_ids=chapter_ids,
                error_detail="No source text provided for OASIS simulation",
                billing_user_id=project.user_id,
                db=db,
            )

            package = _ensure_oasis_package(
                project=project,
                analysis=analysis,
                requirement=requirement,
                provenance=provenance,
                oasis_config=oasis_config,
                package_override=package_override,
            )

            task_manager.update_task(task_id, progress=40, message="Running simulation estimation...")
            run_result = _ensure_oasis_run_result(
                analysis=analysis,
                package=package,
                provenance=provenance,
                project=project,
            )
            await db.flush()
            await db.commit()
            task_manager.complete_task(
                task_id,
                {"run_result": run_result},
                "OASIS simulation run completed",
            )
        except asyncio.CancelledError:
            await db.rollback()
            _mark_task_cancelled(task_id)
            raise
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, _describe_task_exception(exc), "Failed to run OASIS simulation")


async def _run_report_task(
    task_id: str,
    *,
    project_id: str,
    report_model: str | None,
    chapter_ids: list[str] | None,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading run artifacts...",
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")
            _require_ontology_and_graph(project, "OASIS report generation")

            task_manager.update_task(task_id, progress=25, message="Resolving chapter source text...")
            analysis, requirement, provenance, oasis_config = await _resolve_oasis_runtime_context(
                project=project,
                project_id=project_id,
                chapter_ids=chapter_ids,
                error_detail="No source text provided for OASIS report",
                billing_user_id=project.user_id,
                db=db,
            )

            package = _ensure_oasis_package(
                project=project,
                analysis=analysis,
                requirement=requirement,
                provenance=provenance,
                oasis_config=oasis_config,
            )
            run_result = _ensure_oasis_run_result(
                analysis=analysis,
                package=package,
                provenance=provenance,
                project=project,
            )

            selected_report_model = report_model or resolve_component_model(project, "oasis_report")
            task_manager.update_task(task_id, progress=45, message="Generating OASIS report...")
            with llm_billing_scope(
                user_id=project.user_id,
                project_id=project.id,
            ):
                report = await generate_oasis_report(
                    package=package,
                    analysis=analysis,
                    run_result=run_result,
                    requirement=(project.simulation_requirement or "").strip() or None,
                    model=selected_report_model,
                    oasis_config=oasis_config,
                    db=db,
                )
            report = _inject_provenance(report, provenance)
            _store_analysis_payload(project, latest_report=report)
            await db.flush()
            await db.commit()
            task_manager.complete_task(
                task_id,
                {"report": report},
                "OASIS report generated",
            )
        except asyncio.CancelledError:
            await db.rollback()
            _mark_task_cancelled(task_id)
            raise
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, _describe_task_exception(exc), "Failed to generate OASIS report")


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_to_graph(
    project_id: str,
    body: GraphBuildRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    incoming_ontology = body.ontology if isinstance(body.ontology, dict) else None
    if not incoming_ontology and not project.ontology_schema:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ontology not generated. Please generate ontology first.",
        )
    try:
        build_result = await _execute_graph_build(
            project_id=project_id,
            project=project,
            body_text=body.text,
            chapter_ids=body.chapter_ids,
            ontology=incoming_ontology,
            mode=body.build_mode,
            resume_failed=body.resume_failed,
            db=db,
        )
        if str(build_result.get("status") or "") == "partial_failed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(build_result.get("reason") or "Graph build partially failed"),
            )
        return build_result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/build/task", response_model=GraphTaskStartResponse)
async def add_to_graph_task(
    project_id: str,
    body: GraphBuildRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    idempotency_key = _build_graph_task_idempotency_key(project_id, body)
    return _start_project_task(
        task_type="graph_build",
        project_id=project_id,
        user_id=user.id,
        metadata={
            "build_mode": _normalize_graph_build_mode(body.build_mode),
            "resume_failed": bool(body.resume_failed),
            "idempotency_key": idempotency_key,
        },
        worker=lambda task_id: _run_graph_build_task(
            task_id,
            project_id=project_id,
            text=body.text,
            chapter_ids=body.chapter_ids,
            ontology=body.ontology if isinstance(body.ontology, dict) else None,
            build_mode=body.build_mode,
            resume_failed=body.resume_failed,
        ),
    )


@router.post("/build/auto-sync/task", response_model=GraphTaskStartResponse)
async def add_to_graph_auto_sync_task(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)

    from app.routers.projects import _start_chapter_graph_refresh

    try:
        response = await _start_chapter_graph_refresh(
            project_id,
            user.id,
            "manual",
            respect_auto_sync_setting=False,
            require_ready=True,
        )
        if response is None:
            raise RuntimeError("Failed to start automatic graph sync task.")
        return response
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/ontology/generate", response_model=GraphOntologyResponse)
async def generate_project_ontology(
    project_id: str,
    body: GraphOntologyGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    text, _ = await _resolve_text(
        body_text=body.text,
        chapter_ids=body.chapter_ids,
        project=project,
        error_detail="No source text provided for ontology generation",
        db=db,
    )
    try:
        model = resolve_component_model(project, "ontology_generation", body.model)
        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
        ):
            ontology = await generate_ontology(
                text=text,
                db=db,
                requirement=body.requirement,
                model=model,
            )
        project.ontology_schema = ontology
        if body.requirement is not None:
            project.simulation_requirement = body.requirement.strip() or None
        await db.flush()
        return GraphOntologyResponse(status="ok", ontology=ontology)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/ontology/generate/task", response_model=GraphTaskStartResponse)
async def generate_project_ontology_task(
    project_id: str,
    body: GraphOntologyGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    idempotency_key = _build_ontology_task_idempotency_key(project_id, body)
    return _start_project_task(
        task_type="ontology_generate",
        project_id=project_id,
        user_id=user.id,
        metadata={
            "idempotency_key": idempotency_key,
            "model": str(body.model or "").strip() or None,
        },
        worker=lambda task_id: _run_ontology_task(
            task_id,
            project_id=project_id,
            text=body.text,
            chapter_ids=body.chapter_ids,
            requirement=body.requirement,
            model=body.model,
        ),
    )


@router.post("/oasis/analyze", response_model=GraphOasisAnalyzeResponse)
async def analyze_with_oasis(
    project_id: str,
    body: GraphOasisAnalyzeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS analysis")
    text, provenance = await _resolve_text(
        body_text=body.text,
        chapter_ids=body.chapter_ids,
        project=project,
        error_detail="No source text provided for OASIS analysis",
        db=db,
    )
    requirement_provided = "requirement" in body.model_fields_set
    requirement = _resolve_requirement_input(
        requirement=body.requirement,
        provided=requirement_provided,
        project=project,
    )
    analysis_model = _resolve_analysis_model(project, body)
    simulation_model = _resolve_simulation_model(project, body)
    oasis_config = await load_oasis_config(db)
    if requirement_provided:
        project.simulation_requirement = requirement

    try:
        analysis, context = await _generate_and_store_oasis_analysis(
            project=project,
            project_id=project_id,
            text=text,
            requirement=requirement,
            prompt=body.prompt,
            analysis_model=analysis_model,
            simulation_model=simulation_model,
            oasis_config=oasis_config,
            billing_user_id=user.id,
            provenance=provenance,
            db=db,
        )
        return GraphOasisAnalyzeResponse(status="ok", analysis=analysis, context=context)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/oasis/analyze/task", response_model=GraphTaskStartResponse)
async def analyze_with_oasis_task(
    project_id: str,
    body: GraphOasisAnalyzeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS analysis")
    requirement_provided = "requirement" in body.model_fields_set
    idempotency_key = _build_oasis_analyze_task_idempotency_key(project_id, body)
    return _start_project_task(
        task_type="oasis_analyze",
        project_id=project_id,
        user_id=user.id,
        metadata={
            "idempotency_key": idempotency_key,
            "requirement_provided": requirement_provided,
        },
        worker=lambda task_id: _run_analyze_task(
            task_id,
            project_id=project_id,
            text=body.text,
            chapter_ids=body.chapter_ids,
            requirement=body.requirement,
            prompt=body.prompt,
            analysis_model=body.analysis_model,
            simulation_model=body.simulation_model,
            requirement_provided=requirement_provided,
        ),
    )


@router.post("/oasis/prepare", response_model=GraphOasisPrepareResponse)
async def prepare_oasis_package(
    project_id: str,
    body: GraphOasisPrepareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS preparation")
    resolved_text, provenance = await _resolve_text(
        body_text=body.text,
        chapter_ids=body.chapter_ids,
        project=project,
        error_detail="No source text provided for OASIS analysis",
        db=db,
    )
    requirement_provided = "requirement" in body.model_fields_set
    requirement = _resolve_requirement_input(
        requirement=body.requirement,
        provided=requirement_provided,
        project=project,
    )
    analysis_model = _resolve_analysis_model(project, body)
    simulation_model = _resolve_simulation_model(project, body)
    oasis_config = await load_oasis_config(db)
    if requirement_provided:
        project.simulation_requirement = requirement
    try:
        package = await _prepare_and_store_oasis_package(
            project=project,
            project_id=project_id,
            text=resolved_text,
            requirement=requirement,
            prompt=body.prompt,
            analysis_model=analysis_model,
            simulation_model=simulation_model,
            oasis_config=oasis_config,
            billing_user_id=user.id,
            provenance=provenance,
            db=db,
        )
        return GraphOasisPrepareResponse(status="ok", package=package)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/oasis/prepare/task", response_model=GraphTaskStartResponse)
async def prepare_oasis_package_task(
    project_id: str,
    body: GraphOasisPrepareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS preparation")
    idempotency_key = _build_oasis_prepare_task_idempotency_key(project_id, body)
    return _start_project_task(
        task_type="oasis_prepare",
        project_id=project_id,
        user_id=user.id,
        metadata={
            "idempotency_key": idempotency_key,
        },
        worker=lambda task_id: _run_prepare_task(
            task_id,
            project_id=project_id,
            text=body.text,
            chapter_ids=body.chapter_ids,
            requirement=body.requirement,
            prompt=body.prompt,
            analysis_model=_resolve_analysis_model(project, body),
            simulation_model=_resolve_simulation_model(project, body),
            requirement_provided="requirement" in body.model_fields_set,
        ),
    )


@router.post("/oasis/run", response_model=GraphOasisRunResponse)
async def run_oasis_simulation(
    project_id: str,
    body: GraphOasisRunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        project = await _get_project(project_id, user, db)
        _require_ontology_and_graph(project, "OASIS simulation")
        analysis, requirement, provenance, oasis_config = await _resolve_oasis_runtime_context(
            project=project,
            project_id=project_id,
            chapter_ids=body.chapter_ids,
            error_detail="No source text provided for OASIS simulation",
            billing_user_id=user.id,
            db=db,
        )
        package = _ensure_oasis_package(
            project=project,
            analysis=analysis,
            requirement=requirement,
            provenance=provenance,
            oasis_config=oasis_config,
            package_override=body.package if isinstance(body.package, dict) else None,
        )
        run_result = _ensure_oasis_run_result(
            analysis=analysis,
            package=package,
            provenance=provenance,
            project=project,
        )
        await db.flush()
        return GraphOasisRunResponse(status="ok", run_result=run_result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.post("/oasis/run/task", response_model=GraphTaskStartResponse)
async def run_oasis_simulation_task(
    project_id: str,
    body: GraphOasisRunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS simulation")
    package_override = body.package if isinstance(body.package, dict) else None
    idempotency_key = _build_oasis_run_task_idempotency_key(project_id, body)
    return _start_project_task(
        task_type="oasis_run",
        project_id=project_id,
        user_id=user.id,
        metadata={
            "idempotency_key": idempotency_key,
            "has_package_override": bool(package_override),
        },
        worker=lambda task_id: _run_simulation_task(
            task_id,
            project_id=project_id,
            package_override=package_override,
            chapter_ids=body.chapter_ids,
        ),
    )


@router.post("/oasis/report", response_model=GraphOasisReportResponse)
async def generate_oasis_report_sync(
    project_id: str,
    body: GraphOasisReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        project = await _get_project(project_id, user, db)
        _require_ontology_and_graph(project, "OASIS report generation")
        analysis, requirement, provenance, oasis_config = await _resolve_oasis_runtime_context(
            project=project,
            project_id=project_id,
            chapter_ids=body.chapter_ids,
            error_detail="No source text provided for OASIS report",
            billing_user_id=user.id,
            db=db,
        )
        package = _ensure_oasis_package(
            project=project,
            analysis=analysis,
            requirement=requirement,
            provenance=provenance,
            oasis_config=oasis_config,
        )
        run_result = _ensure_oasis_run_result(
            analysis=analysis,
            package=package,
            provenance=provenance,
            project=project,
        )

        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
        ):
            report = await generate_oasis_report(
                package=package,
                analysis=analysis,
                run_result=run_result,
                requirement=(project.simulation_requirement or "").strip() or None,
                model=_resolve_report_model(project, body),
                oasis_config=oasis_config,
                db=db,
            )
        report = _inject_provenance(report, provenance)
        _store_analysis_payload(project, latest_report=report)
        await db.flush()
        return GraphOasisReportResponse(status="ok", report=report)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))


@router.post("/oasis/report/task", response_model=GraphTaskStartResponse)
async def generate_oasis_report_task(
    project_id: str,
    body: GraphOasisReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    _require_ontology_and_graph(project, "OASIS report generation")
    idempotency_key = _build_oasis_report_task_idempotency_key(project_id, body)
    return _start_project_task(
        task_type="oasis_report",
        project_id=project_id,
        user_id=user.id,
        metadata={
            "idempotency_key": idempotency_key,
            "report_model": _resolve_report_model(project, body),
        },
        worker=lambda task_id: _run_report_task(
            task_id,
            project_id=project_id,
            report_model=_resolve_report_model(project, body),
            chapter_ids=body.chapter_ids,
        ),
    )


@router.get("/tasks/{task_id}", response_model=GraphTaskStatusResponse)
async def get_task_status(
    project_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    task = _ensure_task_project(task_manager.get_task(task_id), project_id)
    return GraphTaskStatusResponse(status="ok", task=_task_to_schema(task))


@router.post("/tasks/{task_id}/cancel", response_model=GraphTaskStatusResponse)
async def cancel_task(
    project_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    task = _ensure_task_project(task_manager.get_task(task_id), project_id)
    if task.status not in _TERMINAL_TASK_STATUSES:
        task = task_manager.cancel_task(task_id) or task
    return GraphTaskStatusResponse(status="ok", task=_task_to_schema(task))


@router.get("/tasks", response_model=GraphTaskListResponse)
async def list_tasks(
    project_id: str,
    task_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    tasks = task_manager.list_tasks(task_type=task_type, project_id=project_id, limit=limit)
    return GraphTaskListResponse(status="ok", tasks=[_task_to_schema(task) for task in tasks])


# Backward-compatible aliases.
@router.get("/oasis/tasks/{task_id}", response_model=GraphTaskStatusResponse)
async def get_oasis_task_status(
    project_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_task_status(project_id, task_id, user, db)


@router.post("/oasis/tasks/{task_id}/cancel", response_model=GraphTaskStatusResponse)
async def cancel_oasis_task(
    project_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await cancel_task(project_id, task_id, user, db)


@router.get("/oasis/tasks", response_model=GraphTaskListResponse)
async def list_oasis_tasks(
    project_id: str,
    task_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_tasks(project_id, task_type, limit, user, db)


@router.get("", response_model=GraphStatusResponse)
async def get_graph_status(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    freshness_payload = await _build_graph_freshness_payload(project, db)
    if project.graph_id:
        return GraphStatusResponse(
            graph_id=project.graph_id,
            status="ready",
            ontology_status="ready" if project.ontology_schema else "empty",
            oasis_status="ready" if project.oasis_analysis else "empty",
            **freshness_payload,
        )
    return GraphStatusResponse(
        status="empty",
        ontology_status="ready" if project.ontology_schema else "empty",
        oasis_status="ready" if project.oasis_analysis else "empty",
        **freshness_payload,
    )


@router.post("/search")
async def search(
    project_id: str,
    body: GraphSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    if not project.graph_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No graph data for this project")
    reranker_enabled_for_type = body.search_type in _RERANKER_SEARCH_TYPES
    use_reranker = bool(body.use_reranker and reranker_enabled_for_type)
    selected_reranker_model: str | None = None
    if use_reranker:
        selected_reranker_model = resolve_component_model(
            project,
            "graph_reranker",
            fallback_model="",
        )
    try:
        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
        ):
            results = await search_graph(
                project_id,
                body.query,
                body.search_type,
                body.top_k,
                db=db,
                use_reranker=use_reranker,
                reranker_model=selected_reranker_model,
                reranker_top_n=body.reranker_top_n,
            )
    except RuntimeError as exc:
        # Convert downstream provider/embedding failures into explicit API errors.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph search failed: {type(exc).__name__}",
        ) from exc
    return {"results": results}


@router.get("/visualization", response_model=GraphVisualizationResponse)
async def visualization(
    project_id: str,
    preview_task_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    preview_graph_id = ""
    if preview_task_id:
        preview_task = _ensure_task_project(task_manager.get_task(preview_task_id), project_id)
        if preview_task.task_type != "graph_build":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preview task is not a graph build task")
        preview_graph_id = _preview_graph_id_from_task(preview_task)

    model_project = project if hasattr(project, "component_models") else None
    graph_model = resolve_component_model(model_project, "graph_build")
    alias_model = resolve_component_model(
        model_project,
        "graph_entity_resolution",
        fallback_model=graph_model,
    )
    try:
        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
        ):
            if preview_graph_id:
                data = await get_graph_visualization_for_group(project_id, graph_id=preview_graph_id, db=db)
            else:
                data = await get_graph_visualization(
                    project_id,
                    db=db,
                    alias_model=alias_model,
                )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph visualization failed: {type(exc).__name__}",
        ) from exc
    return GraphVisualizationResponse(nodes=data["nodes"], edges=data["edges"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_graph(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    if project.graph_id:
        try:
            ontology_default_model = resolve_component_model(project, "ontology_generation")
            graph_model = resolve_component_model(project, "graph_build", fallback_model=ontology_default_model)
            graph_embedding_model = resolve_component_model(
                project,
                "graph_embedding",
                fallback_model="",
            )
            await _await_if_needed(
                delete_graph_data(
                    project_id,
                    model=graph_model,
                    embedding_model=graph_embedding_model or None,
                    db=db,
                )
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to delete graph: {exc}",
            ) from exc
        project.graph_id = None
        analysis = _get_project_analysis(project)
        if analysis:
            analysis.pop("_graph_build_state", None)
            project.oasis_analysis = analysis
        await db.flush()
        await db.commit()
    return None

