from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import redis

from app.config import settings


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TaskRecord":
        created_raw = payload.get("created_at")
        updated_raw = payload.get("updated_at")
        created_at = datetime.fromisoformat(created_raw) if isinstance(created_raw, str) else datetime.now(timezone.utc)
        updated_at = datetime.fromisoformat(updated_raw) if isinstance(updated_raw, str) else created_at
        status_raw = str(payload.get("status") or TaskStatus.PENDING.value).lower()
        status = TaskStatus(status_raw) if status_raw in TaskStatus._value2member_map_ else TaskStatus.PENDING
        return cls(
            task_id=str(payload.get("task_id") or ""),
            task_type=str(payload.get("task_type") or ""),
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            progress=max(0, min(100, int(payload.get("progress") or 0))),
            message=str(payload.get("message") or ""),
            result=payload.get("result") if isinstance(payload.get("result"), dict) else None,
            error=str(payload.get("error")) if payload.get("error") is not None else None,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )


class _InMemoryTaskStore:
    def __init__(self):
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()

    def create_task(self, task: TaskRecord) -> None:
        with self._lock:
            self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def update_task(self, task: TaskRecord) -> None:
        with self._lock:
            self._tasks[task.task_id] = task

    def list_tasks(self, *, task_type: str | None, project_id: str | None, limit: int) -> list[TaskRecord]:
        with self._lock:
            tasks = list(self._tasks.values())
        if task_type:
            tasks = [t for t in tasks if t.task_type == task_type]
        if project_id:
            tasks = [t for t in tasks if str((t.metadata or {}).get("project_id") or "") == project_id]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[: max(1, limit)]

    def cleanup_old_tasks(self, *, max_age_hours: int) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        with self._lock:
            to_delete = [
                task_id
                for task_id, task in self._tasks.items()
                if task.created_at < cutoff and task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            ]
            for task_id in to_delete:
                del self._tasks[task_id]


class _SqliteTaskStore:
    def __init__(self, path: str):
        db_path = str(path or "").strip()
        if not db_path:
            raise ValueError("empty sqlite path")
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_records (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    metadata_json TEXT NOT NULL,
                    project_id TEXT,
                    user_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_task_records_created_at
                    ON task_records(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_task_records_project_created_at
                    ON task_records(project_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_task_records_type_created_at
                    ON task_records(task_type, created_at DESC);
                """
            )
            self._conn.commit()

    def _row_to_task(self, row: sqlite3.Row) -> TaskRecord | None:
        try:
            metadata = json.loads(str(row["metadata_json"] or "{}"))
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        try:
            result = json.loads(str(row["result_json"])) if row["result_json"] else None
            if result is not None and not isinstance(result, dict):
                result = None
        except Exception:
            result = None
        try:
            created_at = datetime.fromisoformat(str(row["created_at"]))
        except Exception:
            created_at = datetime.now(timezone.utc)
        try:
            updated_at = datetime.fromisoformat(str(row["updated_at"]))
        except Exception:
            updated_at = created_at
        status_raw = str(row["status"] or TaskStatus.PENDING.value).lower()
        status = TaskStatus(status_raw) if status_raw in TaskStatus._value2member_map_ else TaskStatus.PENDING
        return TaskRecord(
            task_id=str(row["task_id"] or ""),
            task_type=str(row["task_type"] or ""),
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            progress=max(0, min(100, int(row["progress"] or 0))),
            message=str(row["message"] or ""),
            result=result,
            error=str(row["error"]) if row["error"] is not None else None,
            metadata=metadata,
        )

    def upsert_task(self, task: TaskRecord) -> None:
        payload_result = json.dumps(task.result, ensure_ascii=False) if isinstance(task.result, dict) else None
        payload_metadata = json.dumps(task.metadata or {}, ensure_ascii=False)
        project_id = str((task.metadata or {}).get("project_id") or "").strip() or None
        user_id = str((task.metadata or {}).get("user_id") or "").strip() or None
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO task_records (
                    task_id, task_type, status, created_at, updated_at, progress, message,
                    result_json, error, metadata_json, project_id, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    task_type = excluded.task_type,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    progress = excluded.progress,
                    message = excluded.message,
                    result_json = excluded.result_json,
                    error = excluded.error,
                    metadata_json = excluded.metadata_json,
                    project_id = excluded.project_id,
                    user_id = excluded.user_id
                """,
                (
                    task.task_id,
                    task.task_type,
                    task.status.value,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                    int(task.progress),
                    str(task.message or ""),
                    payload_result,
                    task.error,
                    payload_metadata,
                    project_id,
                    user_id,
                ),
            )
            self._conn.commit()

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM task_records WHERE task_id = ? LIMIT 1",
                (task_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_task(row)

    def list_tasks(self, *, task_type: str | None, project_id: str | None, limit: int) -> list[TaskRecord]:
        params: list[Any] = []
        where: list[str] = []
        if task_type:
            where.append("task_type = ?")
            params.append(task_type)
        if project_id:
            where.append("project_id = ?")
            params.append(project_id)
        sql = "SELECT * FROM task_records"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        tasks: list[TaskRecord] = []
        for row in rows:
            task = self._row_to_task(row)
            if task:
                tasks.append(task)
        return tasks

    def cleanup_old_tasks(self, *, max_age_hours: int) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        with self._lock:
            self._conn.execute(
                """
                DELETE FROM task_records
                WHERE created_at < ?
                  AND status IN (?, ?, ?)
                """,
                (
                    cutoff.isoformat(),
                    TaskStatus.COMPLETED.value,
                    TaskStatus.FAILED.value,
                    TaskStatus.CANCELLED.value,
                ),
            )
            self._conn.commit()


class TaskManager:
    _instance: "TaskManager | None" = None
    _instance_lock = threading.Lock()

    _TASK_PREFIX = "musegraph:task:"
    _INDEX_ALL = "musegraph:tasks:index:all"
    _INDEX_PROJECT_PREFIX = "musegraph:tasks:index:project:"
    _INDEX_TYPE_PREFIX = "musegraph:tasks:index:type:"

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._memory = _InMemoryTaskStore()
                    cls._instance._redis = cls._instance._connect_redis()
                    cls._instance._sqlite = cls._instance._connect_sqlite()
                    cls._instance._runners: dict[str, asyncio.Task[Any]] = {}
                    cls._instance._runner_lock = threading.Lock()
        return cls._instance

    def _connect_redis(self) -> redis.Redis | None:
        try:
            client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            client.ping()
            return client
        except Exception:
            return None

    def _connect_sqlite(self) -> _SqliteTaskStore | None:
        try:
            return _SqliteTaskStore(settings.TASK_STATE_SQLITE_PATH)
        except Exception:
            return None

    def _task_key(self, task_id: str) -> str:
        return f"{self._TASK_PREFIX}{task_id}"

    def _project_index_key(self, project_id: str) -> str:
        return f"{self._INDEX_PROJECT_PREFIX}{project_id}"

    def _type_index_key(self, task_type: str) -> str:
        return f"{self._INDEX_TYPE_PREFIX}{task_type}"

    def _is_terminal_status(self, status_value: TaskStatus | str | None) -> bool:
        normalized = str(status_value or "").lower()
        return normalized in {
            TaskStatus.COMPLETED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }

    def _save_to_redis(self, task: TaskRecord) -> None:
        if not self._redis:
            return
        payload = json.dumps(task.to_dict(), ensure_ascii=False)
        created_ts = task.created_at.timestamp()
        task_key = self._task_key(task.task_id)
        project_id = str((task.metadata or {}).get("project_id") or "").strip()
        pipe = self._redis.pipeline()
        pipe.set(task_key, payload)
        pipe.zadd(self._INDEX_ALL, {task.task_id: created_ts})
        pipe.zadd(self._type_index_key(task.task_type), {task.task_id: created_ts})
        if project_id:
            pipe.zadd(self._project_index_key(project_id), {task.task_id: created_ts})
        pipe.execute()

    def _load_from_redis(self, task_id: str) -> TaskRecord | None:
        if not self._redis:
            return None
        raw = self._redis.get(self._task_key(task_id))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return None
            return TaskRecord.from_dict(payload)
        except Exception:
            return None

    def _save_to_sqlite(self, task: TaskRecord) -> None:
        if not self._sqlite:
            return
        self._sqlite.upsert_task(task)

    def _load_from_sqlite(self, task_id: str) -> TaskRecord | None:
        if not self._sqlite:
            return None
        return self._sqlite.get_task(task_id)

    def _list_ids_from_redis(self, *, task_type: str | None, project_id: str | None, limit: int) -> list[str]:
        if not self._redis:
            return []
        index_key = self._INDEX_ALL
        if project_id:
            index_key = self._project_index_key(project_id)
        elif task_type:
            index_key = self._type_index_key(task_type)
        return [
            str(task_id)
            for task_id in self._redis.zrevrange(index_key, 0, max(0, limit - 1))
            if task_id
        ]

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
        self._memory.create_task(task)
        try:
            self._save_to_redis(task)
        except Exception:
            pass
        try:
            self._save_to_sqlite(task)
        except Exception:
            pass
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        task = self._memory.get_task(task_id)
        if task:
            return task
        try:
            task = self._load_from_redis(task_id)
        except Exception:
            task = None
        if not task:
            try:
                task = self._load_from_sqlite(task_id)
            except Exception:
                task = None
        if task:
            self._memory.update_task(task)
        return task

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
        task = self.get_task(task_id)
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
        self._memory.update_task(task)
        try:
            self._save_to_redis(task)
        except Exception:
            pass
        try:
            self._save_to_sqlite(task)
        except Exception:
            pass

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

    def register_runner(self, task_id: str, runner: asyncio.Task[Any]) -> None:
        if not task_id:
            return
        with self._runner_lock:
            self._runners[task_id] = runner

    def unregister_runner(self, task_id: str) -> None:
        if not task_id:
            return
        with self._runner_lock:
            self._runners.pop(task_id, None)

    def cancel_task(self, task_id: str, message: str = "Task cancelled by user") -> TaskRecord | None:
        task = self.get_task(task_id)
        if not task:
            return None
        if self._is_terminal_status(task.status):
            return task
        with self._runner_lock:
            runner = self._runners.get(task_id)
        if runner and not runner.done():
            runner.cancel()
        self.update_task(
            task_id,
            status=TaskStatus.CANCELLED,
            message=message,
        )
        return self.get_task(task_id)

    def list_tasks(
        self,
        *,
        task_type: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[TaskRecord]:
        max_limit = max(1, limit)
        task_map: dict[str, TaskRecord] = {}

        def _collect(items: list[TaskRecord]) -> None:
            for item in items:
                if not item.task_id:
                    continue
                if task_type and item.task_type != task_type:
                    continue
                if project_id and str((item.metadata or {}).get("project_id") or "") != project_id:
                    continue
                task_map[item.task_id] = item
                if len(task_map) >= max_limit:
                    return

        try:
            task_ids = self._list_ids_from_redis(task_type=task_type, project_id=project_id, limit=max_limit)
            redis_tasks: list[TaskRecord] = []
            for task_id in task_ids:
                task = self.get_task(task_id)
                if not task:
                    continue
                redis_tasks.append(task)
            _collect(redis_tasks)
        except Exception:
            pass

        if len(task_map) < max_limit and self._sqlite:
            try:
                _collect(
                    self._sqlite.list_tasks(
                        task_type=task_type,
                        project_id=project_id,
                        limit=max_limit,
                    )
                )
            except Exception:
                pass

        if len(task_map) < max_limit:
            _collect(self._memory.list_tasks(task_type=task_type, project_id=project_id, limit=max_limit))

        tasks = sorted(task_map.values(), key=lambda item: item.created_at, reverse=True)
        return tasks[:max_limit]

    def cleanup_old_tasks(self, *, max_age_hours: int = 24) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        self._memory.cleanup_old_tasks(max_age_hours=max_age_hours)
        if self._sqlite:
            try:
                self._sqlite.cleanup_old_tasks(max_age_hours=max_age_hours)
            except Exception:
                pass
        if not self._redis:
            return
        try:
            stale_ids = [
                str(task_id)
                for task_id in self._redis.zrangebyscore(self._INDEX_ALL, 0, cutoff.timestamp())
                if task_id
            ]
            if not stale_ids:
                return
            for task_id in stale_ids:
                task = self._load_from_redis(task_id)
                if not task:
                    self._redis.zrem(self._INDEX_ALL, task_id)
                    continue
                if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    continue
                project_id = str((task.metadata or {}).get("project_id") or "").strip()
                pipe = self._redis.pipeline()
                pipe.delete(self._task_key(task_id))
                pipe.zrem(self._INDEX_ALL, task_id)
                pipe.zrem(self._type_index_key(task.task_type), task_id)
                if project_id:
                    pipe.zrem(self._project_index_key(project_id), task_id)
                pipe.execute()
        except Exception:
            pass


task_manager = TaskManager()
