import asyncio
import inspect
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any, Callable, Coroutine

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.dependencies import get_current_user
from app.models.project import ProjectChapter, TextProject
from app.models.user import User
from app.schemas.memory import (
    MemoryBuildRequest,
    MemoryPreviewRequest,
    MemoryPreviewResponse,
    MemoryTaskInfo,
    MemoryTaskListResponse,
    MemoryTaskStartResponse,
    MemoryTaskStatusResponse,
    MemoryOntologyGenerateRequest,
    MemoryOntologyResponse,
    MemorySearchRequest,
    MemoryStatusResponse,
    MemoryTextIngestRequest,
    MemoryVisualizationResponse,
)
from app.services.creative_memory import build_creative_memory_pack, render_creative_memory_block
from app.services.creative_workflow import (
    chapter_has_memory_material,
    chapter_memory_hash,
    chapter_memory_text,
    project_creative_state_hash,
    project_creative_state_text,
)
from app.services.memory_service import (
    build_memory,
    delete_memory as delete_memory_data,
    export_memory_data,
    get_memory_visualization,
    get_memory_visualization_for_group,
    memory_rag_query,
    has_memory_data,
    query_memory_timeline,
    search_memory,
)
from app.services.ai import llm_billing_scope, require_structured_json_model, resolve_explicit_component_model
from app.services.ontology import build_memory_input_with_ontology, generate_ontology
from app.services.project_access import (
    PROJECT_PERMISSION_BUILD_MEMORY,
    PROJECT_PERMISSION_RUN_AI,
    PROJECT_PERMISSION_VIEW,
    require_project_permission,
)
from app.services.project_workspace import write_project_workspace_version_snapshot_from_db
from app.services.task_state import TaskRecord, TaskStatus, task_manager
from app.routers.memory_utils import (
    MEMORY_BUILD_INCREMENTAL,
    MEMORY_BUILD_REBUILD,
    _build_memory_task_idempotency_key,
    _build_ontology_task_idempotency_key,
    _build_provenance,
    _build_text_ingest_task_idempotency_key,
    _hash_text,
    _normalize_chapter_ids,
    _normalize_memory_build_mode,
    _now_iso,
    _ontology_text_profile,
    _text_hash_or_empty,
)
from app.routers import memory_tasks

logger = logging.getLogger(__name__)

router = APIRouter()
_STALE_MEMORY_TASK_SECONDS = memory_tasks.STALE_MEMORY_TASK_SECONDS
_TERMINAL_TASK_STATUSES = memory_tasks.TERMINAL_TASK_STATUSES


async def _get_project(
    project_id: str,
    user: User,
    db: AsyncSession,
    permission: str = PROJECT_PERMISSION_VIEW,
) -> TextProject:
    try:
        UUID(str(project_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid project id") from None

    return await require_project_permission(project_id, user, db, permission)


def _require_ontology_and_memory(project: TextProject, action_name: str) -> None:
    if not project.ontology_schema:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ontology not generated. Please complete ontology first before {action_name}.",
        )
    if not project.memory_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Memory not built. Please build memory before {action_name}.",
        )


def _describe_task_exception(exc: Exception) -> str:
    message = str(exc or "").strip()
    if message:
        return message
    return f"{type(exc).__name__}: {exc!r}"


def _preview_memory_id_from_task(task: TaskRecord | None) -> str:
    if not task:
        return ""
    detail = task.progress_detail if isinstance(task.progress_detail, dict) else None
    memory_id = str((detail or {}).get("preview_memory_id") or "").strip()
    if memory_id:
        return memory_id
    metadata = task.metadata if isinstance(task.metadata, dict) else {}
    return str(metadata.get("preview_memory_id") or "").strip()


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


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
    # `greenlet_spawn has not been called` before memory extraction even starts.
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

    creative_state_text = project_creative_state_text(project)

    if normalized_chapter_ids:
        chapters = await _resolve_chapters_for_project(project, normalized_chapter_ids, db)
        chapter_text = "\n\n".join(
            chapter_memory_text(chapter)
            for chapter in chapters
            if chapter_has_memory_material(chapter)
        ).strip()
        text = provided_text or chapter_text
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail,
            )
        source_ids = [chapter.id for chapter in chapters]
        return text, _build_provenance(source_chapter_ids=source_ids, text=text)

    chapters = await _resolve_chapters_for_project(project, None, db)
    chapter_text = "\n\n".join(
        chapter_memory_text(chapter)
        for chapter in chapters
        if chapter_has_memory_material(chapter)
    ).strip()
    project_text = "\n\n".join(item for item in [creative_state_text, chapter_text] if item).strip()
    text = provided_text or project_text
    if not text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail,
        )
    return text, _build_provenance(source_chapter_ids=[], text=text)

def _extract_memory_build_state(project: TextProject) -> dict[str, Any]:
    creative_state = getattr(project, "creative_state", None)
    if not isinstance(creative_state, dict):
        return {}
    state = creative_state.get("memory_build_state")
    return state if isinstance(state, dict) else {}


def _extract_memory_build_hashes(project: TextProject) -> dict[str, str]:
    raw = _extract_memory_build_state(project).get("chapter_hashes")
    if not isinstance(raw, dict):
        return {}
    hashes: dict[str, str] = {}
    for key, value in raw.items():
        chapter_id = str(key or "").strip()
        hash_value = str(value or "").strip()
        if chapter_id and hash_value:
            hashes[chapter_id] = hash_value
    return hashes


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
    return memory_tasks._is_running_task_status(status_value)


def _is_stale_memory_task(task: TaskRecord) -> bool:
    return memory_tasks._is_stale_memory_task(task, stale_seconds=_STALE_MEMORY_TASK_SECONDS)


def _latest_running_memory_task(project_id: str) -> TaskRecord | None:
    return memory_tasks._latest_running_memory_task(
        project_id,
        manager=task_manager,
        stale_seconds=_STALE_MEMORY_TASK_SECONDS,
    )


async def _build_memory_freshness_payload(project: TextProject, db: AsyncSession) -> dict[str, Any]:
    state = _extract_memory_build_state(project)
    last_build_at = str(state.get("updated_at") or "").strip() or None
    memory_mode = str(state.get("mode") or "").strip() or None

    base_payload: dict[str, Any] = {
        "memory_freshness": "empty",
        "memory_reason": None,
        "memory_changed_count": 0,
        "memory_added_count": 0,
        "memory_modified_count": 0,
        "memory_removed_count": 0,
        "memory_last_build_at": last_build_at,
        "memory_mode": memory_mode,
        "memory_syncing_task_id": None,
    }

    if not project.ontology_schema:
        base_payload["memory_freshness"] = "no_ontology"
        base_payload["memory_reason"] = "ontology_missing"
        return base_payload

    running_task = _latest_running_memory_task(project.id)
    if running_task:
        base_payload["memory_freshness"] = "syncing"
        base_payload["memory_reason"] = "memory_build_task_running"
        base_payload["memory_syncing_task_id"] = running_task.task_id
        return base_payload

    if not project.memory_id:
        base_payload["memory_freshness"] = "empty"
        base_payload["memory_reason"] = "memory_missing"
        return base_payload

    if not await has_memory_data(project.id, db=db):
        base_payload["memory_freshness"] = "stale"
        base_payload["memory_reason"] = "memory_store_empty_or_unreadable"
        return base_payload

    previous_hashes_all = _extract_memory_build_hashes(project)
    previous_hashes = {
        chapter_id: content_hash
        for chapter_id, content_hash in previous_hashes_all.items()
        if chapter_id != "__manual__"
    }

    if not previous_hashes:
        base_payload["memory_freshness"] = "stale"
        base_payload["memory_reason"] = "memory_baseline_missing_or_scope_changed"
        return base_payload

    last_build_dt = _to_utc_datetime(last_build_at)
    if not last_build_dt:
        base_payload["memory_freshness"] = "stale"
        base_payload["memory_reason"] = "memory_build_timestamp_missing_or_invalid"
        return base_payload

    chapter_query = select(ProjectChapter).where(ProjectChapter.project_id == project.id)
    result = await db.execute(chapter_query)
    chapters = [chapter for chapter in result.scalars().all() if chapter_has_memory_material(chapter)]
    current_chapter_ids = {str(chapter.id) for chapter in chapters if str(chapter.id or "").strip()}
    current_hashes: dict[str, str] = {
        str(chapter.id): chapter_memory_hash(chapter)
        for chapter in chapters
        if str(chapter.id or "").strip()
    }
    if project_creative_state_text(project):
        current_chapter_ids.add("__creative_state__")
        current_hashes["__creative_state__"] = project_creative_state_hash(project)

    added = [chapter_id for chapter_id in current_chapter_ids if chapter_id not in previous_hashes]
    removed = [chapter_id for chapter_id in previous_hashes.keys() if chapter_id not in current_chapter_ids]
    modified = [
        chapter_id
        for chapter_id in (current_chapter_ids & set(previous_hashes.keys()))
        if current_hashes.get(chapter_id) != previous_hashes.get(chapter_id)
    ]

    changed_count = len(added) + len(modified) + len(removed)
    base_payload["memory_changed_count"] = changed_count
    base_payload["memory_added_count"] = len(added)
    base_payload["memory_modified_count"] = len(modified)
    base_payload["memory_removed_count"] = len(removed)

    if changed_count > 0:
        base_payload["memory_freshness"] = "stale"
        base_payload["memory_reason"] = "chapter_metadata_changed_after_last_memory_build"
        return base_payload

    base_payload["memory_freshness"] = "fresh"
    base_payload["memory_reason"] = "memory_synced_with_current_chapters"
    return base_payload


def _store_memory_build_state(
    project: TextProject,
    *,
    chapter_hashes: dict[str, str],
    mode: str,
    provenance: dict[str, Any],
    changed_chapter_ids: list[str] | None = None,
) -> None:
    state: dict[str, Any] = {
        "mode": _normalize_memory_build_mode(mode),
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
    creative_state = dict(getattr(project, "creative_state", None) or {})
    creative_state["memory_build_state"] = state
    project.creative_state = creative_state


def _merge_chapter_text_by_ids(chapters: list[ProjectChapter], include_ids: list[str]) -> str:
    include_set = {
        str(chapter_id)
        for chapter_id in include_ids
        if str(chapter_id or "").strip()
    }
    if not include_set:
        return ""
    return "\n\n".join(
        chapter_memory_text(chapter)
        for chapter in chapters
        if chapter.id in include_set and chapter_has_memory_material(chapter)
    ).strip()


def _task_to_schema(task: TaskRecord) -> MemoryTaskInfo:
    return memory_tasks._task_to_schema(task)


def _create_project_task(*, task_type: str, project_id: str, user_id: str, metadata: dict[str, Any] | None = None) -> TaskRecord:
    return memory_tasks._create_project_task(
        task_type=task_type,
        project_id=project_id,
        user_id=user_id,
        metadata=metadata,
        manager=task_manager,
    )


def _cancel_superseded_auto_memory_tasks(task: TaskRecord) -> None:
    memory_tasks._cancel_superseded_auto_memory_tasks(task, manager=task_manager)


def _start_project_task(
    *,
    task_type: str,
    project_id: str,
    user_id: str,
    worker: Callable[[str], Coroutine[Any, Any, None]],
    metadata: dict[str, Any] | None = None,
) -> MemoryTaskStartResponse:
    return memory_tasks._start_project_task(
        task_type=task_type,
        project_id=project_id,
        user_id=user_id,
        worker=worker,
        metadata=metadata,
        manager=task_manager,
        create_async_task=asyncio.create_task,
    )


def _ensure_task_project(task: TaskRecord | None, project_id: str) -> TaskRecord:
    return memory_tasks._ensure_task_project(task, project_id)


def _mark_task_cancelled(task_id: str, message: str = "Task cancelled by user") -> None:
    memory_tasks._mark_task_cancelled(
        task_id,
        message=message,
        manager=task_manager,
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

            selected_model = resolve_explicit_component_model(project, "ontology_generation", model)
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
            await db.flush()
            await write_project_workspace_version_snapshot_from_db(project, db, "Update project ontology")
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


async def _resolve_memory_build_plan(
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
        error_detail="No source text provided for memory build",
        db=db,
    )
    chapters = await _resolve_chapters_for_project(
        project,
        normalized_chapter_ids if normalized_chapter_ids else None,
        db,
    )
    chapter_hashes: dict[str, str] = {
        chapter.id: chapter_memory_hash(chapter)
        for chapter in chapters
        if chapter_has_memory_material(chapter)
    }
    if full_scope := len(normalized_chapter_ids) == 0:
        if project_creative_state_text(project):
            chapter_hashes["__creative_state__"] = project_creative_state_hash(project)
    previous_hashes = _extract_memory_build_hashes(project)

    requested_mode = _normalize_memory_build_mode(mode)
    effective_mode = requested_mode
    changed_chapter_ids: list[str] = list(chapter_hashes.keys())
    added_chapter_ids: list[str] = []
    modified_chapter_ids: list[str] = []
    removed_chapter_ids: list[str] = []
    build_text = resolved_text
    build_provenance = resolved_provenance
    skip_reason: str | None = None
    memory_exists = bool(project.memory_id)

    if requested_mode == MEMORY_BUILD_INCREMENTAL:
        if not memory_exists:
            raise ValueError("Incremental memory build requires existing cognee project memory. Use rebuild mode.")
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

                if (
                    "__creative_state__" in added_chapter_ids
                    or "__creative_state__" in modified_chapter_ids
                    or "__creative_state__" in removed_chapter_ids
                ):
                    raise ValueError(
                        "Incremental memory build does not support creative state changes. Use rebuild mode."
                    )

                if modified_chapter_ids and not full_scope:
                    raise ValueError(
                        "Incremental update for edited chapters requires full project scope. "
                        "Clear chapter selection or use rebuild mode."
                    )

                if modified_chapter_ids or removed_chapter_ids:
                    raise ValueError(
                        "Incremental memory build only supports newly added chapters. "
                        "Use rebuild mode after editing or removing existing chapters."
                    )

                changed_chapter_ids = list(added_chapter_ids)

                if effective_mode == MEMORY_BUILD_INCREMENTAL:
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
                        raise ValueError(
                            "Incremental memory build only supports additive text. "
                            "Use rebuild mode after removing chapter sources."
                        )

                if effective_mode != MEMORY_BUILD_REBUILD:
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


async def _execute_memory_build(
    *,
    project_id: str,
    project: TextProject,
    body_text: str | None,
    chapter_ids: list[str] | None,
    ontology: dict[str, Any] | None,
    mode: str | None,
    db: AsyncSession,
    progress_callback: Callable[..., None] | None = None,
    preview_memory_id_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if ontology:
        project.ontology_schema = ontology

    plan = await _resolve_memory_build_plan(
        body_text=body_text,
        chapter_ids=chapter_ids,
        project=project,
        mode=mode,
        db=db,
    )

    effective_mode = str(plan["effective_mode"])
    requested_mode = str(plan["requested_mode"])
    chapter_hashes: dict[str, str] = dict(plan["chapter_hashes"])
    previous_hashes: dict[str, str] = dict(plan["previous_hashes"])
    changed_chapter_ids: list[str] = list(plan["changed_chapter_ids"])
    added_chapter_ids: list[str] = list(plan.get("added_chapter_ids") or [])
    modified_chapter_ids: list[str] = list(plan.get("modified_chapter_ids") or [])
    removed_chapter_ids: list[str] = list(plan.get("removed_chapter_ids") or [])
    build_provenance: dict[str, Any] = dict(plan["build_provenance"])

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
        _store_memory_build_state(
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
            "memory_id": project.memory_id,
            "content_hash": build_provenance.get("content_hash"),
            "source_chapter_ids": build_provenance.get("source_chapter_ids"),
            "changed_chapter_ids": changed_chapter_ids,
            "added_chapter_ids": added_chapter_ids,
            "modified_chapter_ids": modified_chapter_ids,
            "removed_chapter_ids": removed_chapter_ids,
            "reason": plan["skip_reason"],
        }

    build_text = str(plan["build_text"])
    include_ontology_payload = effective_mode == MEMORY_BUILD_REBUILD
    memory_input = (
        build_memory_input_with_ontology(build_text, project.ontology_schema)
        if include_ontology_payload
        else build_text
    )
    memory_source_text = memory_input
    memory_model = require_structured_json_model(
        resolve_explicit_component_model(project, "memory_build"),
        "Memory build",
    )
    memory_embedding_model = resolve_explicit_component_model(project, "memory_embedding")

    preview_memory_id = project.memory_id or f"memory_{uuid4().hex[:16]}"
    if preview_memory_id_callback:
        preview_memory_id_callback(preview_memory_id)

    memory_id = await build_memory(
        project_id,
        memory_source_text,
        model=memory_model,
        embedding_model=memory_embedding_model or None,
        ontology=project.ontology_schema if include_ontology_payload else None,
        db=db,
        progress_callback=progress_callback,
        memory_id_override=preview_memory_id,
        reset=effective_mode == MEMORY_BUILD_REBUILD,
    )
    project.memory_id = memory_id
    # cognee owns graph extraction inside `cognify()`; no separate project_graph step.

    if effective_mode == MEMORY_BUILD_REBUILD:
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

    _store_memory_build_state(
        project,
        chapter_hashes=next_hashes,
        mode=effective_mode,
        provenance=build_provenance,
        changed_chapter_ids=changed_chapter_ids,
    )
    await db.flush()
    return {
        "status": "ok",
        "requested_mode": requested_mode,
        "mode": effective_mode,
        "memory_id": memory_id,
        "content_hash": build_provenance.get("content_hash"),
        "source_chapter_ids": build_provenance.get("source_chapter_ids"),
        "changed_chapter_ids": changed_chapter_ids,
        "added_chapter_ids": added_chapter_ids,
        "modified_chapter_ids": modified_chapter_ids,
        "removed_chapter_ids": removed_chapter_ids,
        "graph_nodes": 0,
        "graph_edges": 0,
        "graph_error": None,
    }


async def _run_memory_build_task(
    task_id: str,
    *,
    project_id: str,
    text: str | None,
    chapter_ids: list[str] | None,
    ontology: dict[str, Any] | None,
    build_mode: str | None = None,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading project context...",
        progress_detail={"stage": "setup"},
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")

            task_manager.update_task(task_id, progress=12, message="Resolving chapter source text...",
                                     progress_detail={"stage": "setup"})

            def _on_preview_memory_id(memory_id: str) -> None:
                task = task_manager.get_task(task_id)
                detail = dict(task.progress_detail or {}) if task and isinstance(task.progress_detail, dict) else {}
                detail["preview_memory_id"] = memory_id
                task_manager.update_task(task_id, progress_detail=detail)

            def _on_build_progress(progress: int, message: str, stage: str = "", detail: dict[str, Any] | None = None) -> None:
                bounded_progress = max(25, min(97, int(progress)))
                task = task_manager.get_task(task_id)
                existing_detail = task.progress_detail if task and isinstance(task.progress_detail, dict) else {}
                merged_detail: dict[str, Any] = dict(existing_detail)
                if stage:
                    merged_detail["stage"] = stage
                if detail:
                    merged_detail.update(detail)
                task_manager.update_task(
                    task_id,
                    progress=bounded_progress,
                    message=message,
                    progress_detail=merged_detail or None,
                )

            task_manager.update_task(task_id, progress=28, message="Building memory in segments...",
                                     progress_detail={"stage": "ingesting"})
            build_result = await _execute_memory_build(
                project_id=project_id,
                project=project,
                body_text=text,
                chapter_ids=chapter_ids,
                ontology=ontology,
                mode=build_mode,
                db=db,
                progress_callback=_on_build_progress,
                preview_memory_id_callback=_on_preview_memory_id,
            )
            await write_project_workspace_version_snapshot_from_db(project, db, "Build project memory")
            await db.commit()
            status = str(build_result.get("status") or "ok")
            is_incremental = str(build_result.get("mode") or "") == MEMORY_BUILD_INCREMENTAL
            if is_incremental:
                completion_message = "Knowledge memory updated incrementally"
            else:
                completion_message = "Knowledge memory built"
            if status == "skipped":
                completion_message = str(build_result.get("reason") or "No memory changes to apply")
            task_manager.complete_task(
                task_id,
                {
                    "memory_id": build_result.get("memory_id"),
                    "requested_mode": build_result.get("requested_mode"),
                    "mode": build_result.get("mode"),
                    "status": status,
                    "content_hash": build_result.get("content_hash"),
                    "source_chapter_ids": build_result.get("source_chapter_ids"),
                    "changed_chapter_ids": build_result.get("changed_chapter_ids"),
                    "added_chapter_ids": build_result.get("added_chapter_ids"),
                    "modified_chapter_ids": build_result.get("modified_chapter_ids"),
                    "removed_chapter_ids": build_result.get("removed_chapter_ids"),
                    "graph_nodes": build_result.get("graph_nodes"),
                    "graph_edges": build_result.get("graph_edges"),
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
            task_manager.fail_task(task_id, _describe_task_exception(exc), "Failed to build memory")


async def _run_text_ingest_task(
    task_id: str,
    *,
    project_id: str,
    user_id: str,
    text: str,
    source_title: str | None,
    requirement: str | None,
    ontology_model: str | None,
    build_mode: str | None,
) -> None:
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="Loading project context...",
        progress_detail={"stage": "setup"},
    )
    async with async_session() as db:
        try:
            result = await db.execute(select(TextProject).where(TextProject.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                raise RuntimeError("Project not found")

            source_text = str(text or "").strip()
            if not source_text:
                raise ValueError("No source text provided for text ingest")

            task_manager.update_task(task_id, progress=12, message="Storing source text as chapter...",
                                     progress_detail={"stage": "chapter"})
            chapters = await _resolve_chapters_for_project(project, None, db)
            chapter = ProjectChapter(
                project_id=project.id,
                title=(str(source_title or "").strip() or "Imported Source")[:255],
                content=source_text,
                status="draft",
                order_index=len(chapters),
            )
            db.add(chapter)
            await db.flush()

            task_manager.update_task(task_id, progress=25, message="Detecting text type and generating ontology...",
                                     progress_detail={"stage": "ontology"})
            selected_ontology_model = resolve_explicit_component_model(project, "ontology_generation", ontology_model)
            resolved_requirement = (requirement or "").strip() or None
            with llm_billing_scope(user_id=user_id, project_id=project.id):
                ontology = await generate_ontology(
                    text=source_text,
                    db=db,
                    requirement=resolved_requirement,
                    model=selected_ontology_model,
                )
            project.ontology_schema = ontology
            await db.flush()

            def _on_build_progress(progress: int, message: str, stage: str = "", detail: dict[str, Any] | None = None) -> None:
                bounded_progress = 42 + int(max(0, min(100, int(progress))) * 0.32)
                merged_detail = {"stage": stage or "memory"}
                if detail:
                    merged_detail.update(detail)
                task_manager.update_task(
                    task_id,
                    progress=max(42, min(76, bounded_progress)),
                    message=message,
                    progress_detail=merged_detail,
                )

            task_manager.update_task(task_id, progress=42, message="Analyzing relationships into memory...",
                                     progress_detail={"stage": "memory"})
            build_result = await _execute_memory_build(
                project_id=project_id,
                project=project,
                body_text=None,
                chapter_ids=[chapter.id],
                ontology=None,
                mode=build_mode,
                db=db,
                progress_callback=_on_build_progress,
            )

            await write_project_workspace_version_snapshot_from_db(project, db, "Update project graph")
            await db.commit()
            task_manager.complete_task(
                task_id,
                {
                    "chapter_id": chapter.id,
                    "ontology": ontology,
                    "text_profile": _ontology_text_profile(ontology),
                    "memory": build_result,
                },
                "Source text ingested; ontology and memory are ready",
            )
        except asyncio.CancelledError:
            await db.rollback()
            _mark_task_cancelled(task_id)
            raise
        except Exception as exc:
            await db.rollback()
            task_manager.fail_task(task_id, _describe_task_exception(exc), "Failed to ingest source text")


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_to_memory(
    project_id: str,
    body: MemoryBuildRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db, PROJECT_PERMISSION_BUILD_MEMORY)
    incoming_ontology = body.ontology if isinstance(body.ontology, dict) else None
    try:
        build_result = await _execute_memory_build(
            project_id=project_id,
            project=project,
            body_text=body.text,
            chapter_ids=body.chapter_ids,
            ontology=incoming_ontology,
            mode=body.build_mode,
            db=db,
        )
        await write_project_workspace_version_snapshot_from_db(project, db, "Build project memory")
        return build_result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/build/task", response_model=MemoryTaskStartResponse)
async def add_to_memory_task(
    project_id: str,
    body: MemoryBuildRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db, PROJECT_PERMISSION_BUILD_MEMORY)
    idempotency_key = _build_memory_task_idempotency_key(project_id, body)
    return _start_project_task(
        task_type="memory_build",
        project_id=project_id,
        user_id=user.id,
        metadata={
            "build_mode": _normalize_memory_build_mode(body.build_mode),
            "idempotency_key": idempotency_key,
        },
        worker=lambda task_id: _run_memory_build_task(
            task_id,
            project_id=project_id,
            text=body.text,
            chapter_ids=body.chapter_ids,
            ontology=body.ontology if isinstance(body.ontology, dict) else None,
            build_mode=body.build_mode,
        ),
    )


@router.post("/build/auto-sync/task", response_model=MemoryTaskStartResponse)
async def add_to_memory_auto_sync_task(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db, PROJECT_PERMISSION_BUILD_MEMORY)

    from app.routers.projects import _start_chapter_memory_refresh

    try:
        response = await _start_chapter_memory_refresh(
            project_id,
            user.id,
            "manual",
            respect_auto_sync_setting=False,
            require_ready=True,
        )
        if response is None:
            raise RuntimeError("Failed to start automatic memory sync task.")
        return response
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/ontology/generate", response_model=MemoryOntologyResponse)
async def generate_project_ontology(
    project_id: str,
    body: MemoryOntologyGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db, PROJECT_PERMISSION_BUILD_MEMORY)
    text, _ = await _resolve_text(
        body_text=body.text,
        chapter_ids=body.chapter_ids,
        project=project,
        error_detail="No source text provided for ontology generation",
        db=db,
    )
    try:
        model = resolve_explicit_component_model(project, "ontology_generation", body.model)
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
        await db.flush()
        await write_project_workspace_version_snapshot_from_db(project, db, "Update project ontology")
        return MemoryOntologyResponse(status="ok", ontology=ontology)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/ontology/generate/task", response_model=MemoryTaskStartResponse)
async def generate_project_ontology_task(
    project_id: str,
    body: MemoryOntologyGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db, PROJECT_PERMISSION_BUILD_MEMORY)
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


@router.post("/ingest/text/task", response_model=MemoryTaskStartResponse)
async def ingest_text_task(
    project_id: str,
    body: MemoryTextIngestRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db, PROJECT_PERMISSION_BUILD_MEMORY)
    requirement_provided = "requirement" in body.model_fields_set
    idempotency_key = _build_text_ingest_task_idempotency_key(project_id, body)
    return _start_project_task(
        task_type="text_ingest",
        project_id=project_id,
        user_id=user.id,
        metadata={
            "idempotency_key": idempotency_key,
            "source_title": str(body.source_title or "").strip() or None,
            "build_mode": _normalize_memory_build_mode(body.build_mode),
            "requirement_provided": requirement_provided,
            "ontology_model": str(body.ontology_model or "").strip() or None,
        },
        worker=lambda task_id: _run_text_ingest_task(
            task_id,
            project_id=project_id,
            user_id=user.id,
            text=body.text,
            source_title=body.source_title,
            requirement=body.requirement,
            ontology_model=body.ontology_model,
            build_mode=body.build_mode,
        ),
    )


@router.get("/tasks/{task_id}", response_model=MemoryTaskStatusResponse)
async def get_task_status(
    project_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    task = _ensure_task_project(task_manager.get_task(task_id), project_id)
    return MemoryTaskStatusResponse(status="ok", task=_task_to_schema(task))


@router.post("/tasks/{task_id}/cancel", response_model=MemoryTaskStatusResponse)
async def cancel_task(
    project_id: str,
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db, PROJECT_PERMISSION_RUN_AI)
    task = _ensure_task_project(task_manager.get_task(task_id), project_id)
    if task.status not in _TERMINAL_TASK_STATUSES:
        task = task_manager.cancel_task(task_id) or task
    return MemoryTaskStatusResponse(status="ok", task=_task_to_schema(task))


@router.get("/tasks", response_model=MemoryTaskListResponse)
async def list_tasks(
    project_id: str,
    task_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, user, db)
    tasks = task_manager.list_tasks(task_type=task_type, project_id=project_id, limit=limit)
    return MemoryTaskListResponse(status="ok", tasks=[_task_to_schema(task) for task in tasks])

@router.get("", response_model=MemoryStatusResponse)
async def get_memory_status(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    freshness_payload = await _build_memory_freshness_payload(project, db)
    text_profile = _ontology_text_profile(project.ontology_schema)
    if project.memory_id:
        return MemoryStatusResponse(
            memory_id=project.memory_id,
            status="ready",
            ontology_status="ready" if project.ontology_schema else "empty",
            **text_profile,
            **freshness_payload,
        )
    return MemoryStatusResponse(
        status="empty",
        ontology_status="ready" if project.ontology_schema else "empty",
        **text_profile,
        **freshness_payload,
    )


@router.post("/preview", response_model=MemoryPreviewResponse)
async def preview_creative_memory(
    project_id: str,
    body: MemoryPreviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db, PROJECT_PERMISSION_RUN_AI)
    try:
        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
        ):
            memory = await build_creative_memory_pack(
                project=project,
                project_id=project_id,
                op_type=body.op_type,
                input_text=body.input,
                db=db,
                reference_cards=body.reference_cards,
                workflow_step=body.workflow_step,
            )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Creative memory preview failed: {type(exc).__name__}: {exc}",
        ) from exc

    return MemoryPreviewResponse(
        status="ok",
        memory=memory,
        rendered_context=render_creative_memory_block(memory) if body.include_rendered_context else None,
    )


@router.post("/search")
async def search(
    project_id: str,
    body: MemorySearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db, PROJECT_PERMISSION_RUN_AI)
    if not project.memory_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No memory data for this project")
    try:
        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
        ):
            results = await search_memory(
                project_id,
                body.query,
                body.search_type,
                body.top_k,
                db=db,
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
            detail=f"Memory search failed: {type(exc).__name__}",
        ) from exc
    return {"results": results}


@router.post("/rag")
async def memory_rag(
    project_id: str,
    body: MemorySearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db, PROJECT_PERMISSION_RUN_AI)
    if not project.memory_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No memory data for this project")
    try:
        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
        ):
            result = await memory_rag_query(
                project_id,
                body.query,
                top_k=body.top_k,
                db=db,
            )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MemoryRAG query failed: {type(exc).__name__}",
        ) from exc
    return result


@router.get("/visualization", response_model=MemoryVisualizationResponse)
async def visualization(
    project_id: str,
    preview_task_id: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db)
    preview_memory_id = ""
    if preview_task_id:
        preview_task = _ensure_task_project(task_manager.get_task(preview_task_id), project_id)
        if preview_task.task_type != "memory_build":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preview task is not a memory build task")
        preview_memory_id = _preview_memory_id_from_task(preview_task)
    if not preview_memory_id and not project.memory_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No memory data for this project")

    try:
        with llm_billing_scope(
            user_id=user.id,
            project_id=project.id,
        ):
            if preview_memory_id:
                data = await get_memory_visualization_for_group(project_id, memory_id=preview_memory_id, db=db)
            else:
                data = await get_memory_visualization(
                    project_id,
                    db=db,
                )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory visualization failed: {type(exc).__name__}",
        ) from exc
    return MemoryVisualizationResponse(nodes=data["nodes"], edges=data["edges"])


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project(project_id, user, db, PROJECT_PERMISSION_BUILD_MEMORY)
    if project.memory_id:
        try:
            memory_model = resolve_explicit_component_model(project, "memory_build")
            memory_embedding_model = resolve_explicit_component_model(project, "memory_embedding")
            await _await_if_needed(
                delete_memory_data(
                    project_id,
                    model=memory_model,
                    embedding_model=memory_embedding_model or None,
                    db=db,
                )
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to delete memory: {exc}",
            ) from exc
        project.memory_id = None
        creative_state = dict(getattr(project, "creative_state", None) or {})
        creative_state.pop("memory_build_state", None)
        project.creative_state = creative_state or None
        await db.flush()
        await write_project_workspace_version_snapshot_from_db(project, db, "Update memory input state")
        await db.commit()
    return None


@router.get("/export")
async def export_memory(
    project_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all memory data as JSON (no visualization caps)."""
    project = await _get_project(project_id, user, db)
    if not project.memory_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No memory data for this project")
    try:
        result = await export_memory_data(project_id, db=db)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory export failed: {type(exc).__name__}",
        ) from exc
    return result


@router.get("/timeline")
async def get_memory_timeline(
    project_id: str,
    at: str | None = Query(default=None, description="ISO timestamp for point-in-time query"),
    from_: str | None = Query(default=None, alias="from", description="Start of time range (ISO)"),
    to: str | None = Query(default=None, description="End of time range (ISO)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query the memory at a point in time or over a time range."""
    project = await _get_project(project_id, user, db)
    if not project.memory_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No memory data for this project")
    if at and (from_ or to):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use either 'at' for point-in-time or 'from'/'to' for range, not both",
        )
    try:
        result = await query_memory_timeline(
            project_id,
            at_timestamp=at,
            from_timestamp=from_,
            to_timestamp=to,
            db=db,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Timeline query failed: {type(exc).__name__}",
        ) from exc
    return result
