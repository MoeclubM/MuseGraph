from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskRecord:
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: int = 0
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class InMemoryTaskManager:
    _instance: "InMemoryTaskManager | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: dict[str, TaskRecord] = {}
                    cls._instance._tasks_lock = threading.Lock()
        return cls._instance

    def create_task(self, task_type: str, metadata: dict[str, Any] | None = None) -> TaskRecord:
        now = datetime.now(timezone.utc)
        task = TaskRecord(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )
        with self._tasks_lock:
            self._tasks[task.task_id] = task
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def update_task(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        progress: int | None = None,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.updated_at = datetime.now(timezone.utc)
            if status is not None:
                task.status = status
            if progress is not None:
                task.progress = max(0, min(100, int(progress)))
            if message is not None:
                task.message = message
            if result is not None:
                task.result = result
            if error is not None:
                task.error = error

    def complete_task(self, task_id: str, result: dict[str, Any] | None = None, message: str = "Task completed") -> None:
        self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message=message,
            result=result,
        )

    def fail_task(self, task_id: str, error: str, message: str = "Task failed") -> None:
        self.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message=message,
            error=error,
        )

    def list_tasks(
        self,
        *,
        task_type: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[TaskRecord]:
        with self._tasks_lock:
            tasks = list(self._tasks.values())
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        if project_id:
            tasks = [t for t in tasks if str((t.metadata or {}).get("project_id") or "") == project_id]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[: max(1, limit)]

    def cleanup_old_tasks(self, *, max_age_hours: int = 24) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        with self._tasks_lock:
            to_delete = [
                tid
                for tid, task in self._tasks.items()
                if task.created_at < cutoff and task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            ]
            for tid in to_delete:
                del self._tasks[tid]


task_manager = InMemoryTaskManager()

