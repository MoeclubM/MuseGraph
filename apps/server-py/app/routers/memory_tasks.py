import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from fastapi import HTTPException, status

from app.schemas.memory import MemoryTaskInfo, MemoryTaskStartResponse
from app.services.task_state import TaskRecord, TaskStatus, task_manager

STALE_MEMORY_TASK_SECONDS = 120
TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}


def _is_running_task_status(status_value: TaskStatus | str | None) -> bool:
    normalized = str(status_value.value if isinstance(status_value, TaskStatus) else status_value or "").strip().lower()
    return normalized in {TaskStatus.PENDING.value, TaskStatus.PROCESSING.value}


def _is_stale_memory_task(task: TaskRecord, *, stale_seconds: int = STALE_MEMORY_TASK_SECONDS) -> bool:
    updated_at = task.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - updated_at.astimezone(timezone.utc)).total_seconds()
    return age_seconds > stale_seconds


def _latest_running_memory_task(
    project_id: str,
    *,
    manager: Any = task_manager,
    stale_seconds: int = STALE_MEMORY_TASK_SECONDS,
) -> TaskRecord | None:
    tasks = manager.list_tasks(task_type="memory_build", project_id=project_id, limit=20)
    for task in tasks:
        if _is_running_task_status(task.status):
            if _is_stale_memory_task(task, stale_seconds=stale_seconds):
                if manager.has_active_runner(task.task_id):
                    return task
                manager.fail_task(
                    task.task_id,
                    "Memory build task became stale with no progress heartbeat.",
                    message="Memory build task timed out",
                )
                continue
            return task
    return None


def _task_to_schema(task: TaskRecord) -> MemoryTaskInfo:
    return MemoryTaskInfo.model_validate(task.to_dict())


def _create_project_task(
    *,
    task_type: str,
    project_id: str,
    user_id: str,
    metadata: dict[str, Any] | None = None,
    manager: Any = task_manager,
) -> TaskRecord:
    manager.cleanup_old_tasks(max_age_hours=168)
    task_metadata: dict[str, Any] = {
        "project_id": project_id,
        "user_id": user_id,
    }
    if metadata:
        task_metadata.update(metadata)
    return manager.create_task(task_type, task_metadata)


def _cancel_superseded_auto_memory_tasks(
    task: TaskRecord,
    *,
    manager: Any = task_manager,
) -> None:
    task_type = str(getattr(task, "task_type", "") or "").strip()
    if task_type != "memory_build":
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

    for candidate in manager.list_tasks(task_type=task_type, project_id=project_id, limit=200):
        if candidate.task_id == keep_task_id:
            continue
        if candidate.status in TERMINAL_TASK_STATUSES:
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
        manager.cancel_task(
            candidate.task_id,
            message="Cancelled because a newer automatic memory sync task was scheduled",
        )


def _start_project_task(
    *,
    task_type: str,
    project_id: str,
    user_id: str,
    worker: Callable[[str], Coroutine[Any, Any, None]],
    metadata: dict[str, Any] | None = None,
    manager: Any = task_manager,
    create_async_task: Callable[[Coroutine[Any, Any, None]], Any] = asyncio.create_task,
) -> MemoryTaskStartResponse:
    task_metadata: dict[str, Any] = dict(metadata or {})
    idempotency_key = str(task_metadata.get("idempotency_key") or "").strip()
    if idempotency_key:
        existing = manager.find_inflight_task_by_idempotency(
            task_type=task_type,
            project_id=project_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return MemoryTaskStartResponse(status="accepted", task=_task_to_schema(existing))

    task = _create_project_task(
        task_type=task_type,
        project_id=project_id,
        user_id=user_id,
        metadata=task_metadata,
        manager=manager,
    )
    _cancel_superseded_auto_memory_tasks(task, manager=manager)

    async def _runner() -> None:
        try:
            await worker(task.task_id)
        finally:
            manager.unregister_runner(task.task_id)

    runner = create_async_task(_runner())
    manager.register_runner(task.task_id, runner)
    return MemoryTaskStartResponse(status="accepted", task=_task_to_schema(task))


def _ensure_task_project(task: TaskRecord | None, project_id: str) -> TaskRecord:
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if str((task.metadata or {}).get("project_id") or "") != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def _mark_task_cancelled(
    task_id: str,
    message: str = "Task cancelled by user",
    *,
    manager: Any = task_manager,
) -> None:
    task = manager.get_task(task_id)
    if not task:
        return
    if task.status in TERMINAL_TASK_STATUSES:
        return
    manager.update_task(
        task_id,
        status=TaskStatus.CANCELLED,
        message=message,
    )
