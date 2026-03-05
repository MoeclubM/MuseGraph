"""Tests for small modules needing coverage: ai router, export router,
auth logout, llm_json fallback, and task_state manager."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _get_endpoint_globals(app, endpoint_name: str) -> dict:
    """Get the __globals__ dict of a named endpoint to patch its imports."""
    for route in app.routes:
        if hasattr(route, "endpoint") and getattr(route, "name", "") == endpoint_name:
            return route.endpoint.__globals__
        if hasattr(route, "routes"):
            for sub in route.routes:
                if hasattr(sub, "endpoint") and getattr(sub, "name", "") == endpoint_name:
                    return sub.endpoint.__globals__
    raise RuntimeError(f"Endpoint {endpoint_name!r} not found")


class TestAIModelsRouter:
    """Cover app/routers/ai.py lines 17-18: GET /api/ai/models."""

    @pytest.mark.asyncio
    async def test_list_models(self, client: AsyncClient, mock_db: AsyncMock):
        from tests.conftest import app
        g = _get_endpoint_globals(app, "list_models")
        fake_models = [
            {"id": "gpt-4", "name": "GPT-4", "provider": "openai"},
            {"id": "claude-3", "name": "Claude 3", "provider": "anthropic"},
        ]
        mock_fn = AsyncMock(return_value=fake_models)
        orig = g["get_available_models"]
        g["get_available_models"] = mock_fn
        try:
            resp = await client.get("/api/ai/models")
        finally:
            g["get_available_models"] = orig

        assert resp.status_code == 200
        body = resp.json()
        assert body["models"] == fake_models
        assert len(body["models"]) == 2


class TestExportRouter:
    """Cover app/routers/export.py: project not found and forbidden paths."""

    @pytest.mark.asyncio
    async def test_export_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)
        resp = await client.post("/api/projects/proj-999/export/txt")
        assert resp.status_code == 404
        assert "Project not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_forbidden(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(id="proj-1", user_id="other-user", title="Secret")
        mock_db.execute.return_value = _scalar_one_or_none(project)
        resp = await client.post("/api/projects/proj-1/export/txt")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_export_unsupported_format(self, client: AsyncClient, mock_db: AsyncMock):
        resp = await client.post("/api/projects/proj-1/export/pdf")
        assert resp.status_code == 400
        assert "Unsupported format" in resp.json()["detail"]


class TestAuthLogout:
    """Cover app/routers/auth.py line 32: logout deletes cookie."""

    @pytest.mark.asyncio
    async def test_logout_deletes_cookie(self, client: AsyncClient, mock_db: AsyncMock):
        from tests.conftest import app
        g = _get_endpoint_globals(app, "logout")
        mock_del = AsyncMock(return_value=None)
        orig = g["delete_session"]
        g["delete_session"] = mock_del
        try:
            client.cookies.set("session_token", "tok-abc123")
            resp = await client.post(
                "/api/auth/logout",
            )
        finally:
            g["delete_session"] = orig

        assert resp.status_code == 204
        set_cookie = resp.headers.get("set-cookie", "")
        assert "session_token" in set_cookie

    @pytest.mark.asyncio
    async def test_logout_no_token(self, client: AsyncClient, mock_db: AsyncMock):
        """Logout without any token still succeeds."""
        resp = await client.post("/api/auth/logout")
        assert resp.status_code == 204


class TestLlmJsonExtract:
    """Cover app/services/llm_json.py lines 34-35: fallback brace extraction."""

    def test_extract_plain_json(self):
        from app.services.llm_json import extract_json_object
        result = extract_json_object('{"key": "value"}')
        assert result == {"key": "value"}

    def test_extract_fenced_json(self):
        from app.services.llm_json import extract_json_object
        raw = '```json\n{"a": 1}\n```'
        assert extract_json_object(raw) == {"a": 1}

    def test_extract_embedded_braces(self):
        """Lines 34-35: fallback to first { ... last } extraction."""
        from app.services.llm_json import extract_json_object
        raw = 'Here is the result: {"name": "test", "count": 42} -- done'
        result = extract_json_object(raw)
        assert result == {"name": "test", "count": 42}

    def test_extract_embedded_braces_invalid_json(self):
        from app.services.llm_json import extract_json_object
        raw = 'prefix {not valid json} suffix'
        assert extract_json_object(raw) is None

    def test_extract_empty_string(self):
        from app.services.llm_json import extract_json_object
        assert extract_json_object("") is None
        assert extract_json_object(None) is None

    def test_extract_no_braces(self):
        from app.services.llm_json import extract_json_object
        assert extract_json_object("just plain text") is None

    def test_extract_returns_none_for_list(self):
        from app.services.llm_json import extract_json_object
        assert extract_json_object('[1, 2, 3]') is None


class TestTaskStateManager:
    """Cover app/services/task_state.py lines 90, 101, 113, 130."""

    def _fresh_manager(self):
        """Create a fresh TaskManager instance backed by in-memory store only."""
        from app.services.task_state import TaskManager, _InMemoryTaskStore
        import threading
        mgr = object.__new__(TaskManager)
        mgr._memory = _InMemoryTaskStore()
        mgr._redis = None
        mgr._sqlite = None
        mgr._runners = {}
        mgr._runner_lock = threading.Lock()
        return mgr

    def test_update_nonexistent_task(self):
        """Line 90: update_task on missing task_id is a no-op."""
        from app.services.task_state import TaskStatus
        mgr = self._fresh_manager()
        mgr.update_task("nonexistent", status=TaskStatus.PROCESSING, progress=50)
        assert mgr.get_task("nonexistent") is None

    def test_complete_nonexistent_task(self):
        """Line 101: complete_task on missing task_id is a no-op."""
        mgr = self._fresh_manager()
        mgr.complete_task("nonexistent", result={"ok": True})
        assert mgr.get_task("nonexistent") is None

    def test_fail_nonexistent_task(self):
        """Line 113: fail_task on missing task_id is a no-op."""
        mgr = self._fresh_manager()
        mgr.fail_task("nonexistent", error="boom")
        assert mgr.get_task("nonexistent") is None

    def test_cleanup_old_tasks(self):
        """Line 130: cleanup_old_tasks removes old completed/failed tasks."""
        from app.services.task_state import TaskStatus
        mgr = self._fresh_manager()

        task = mgr.create_task("test_type")
        task.status = TaskStatus.COMPLETED
        task.created_at = datetime.now(timezone.utc) - timedelta(hours=48)

        recent = mgr.create_task("test_type")
        recent.status = TaskStatus.COMPLETED

        assert len(mgr._memory._tasks) == 2  # type: ignore[attr-defined]
        mgr.cleanup_old_tasks(max_age_hours=24)
        assert len(mgr._memory._tasks) == 1  # type: ignore[attr-defined]
        assert mgr.get_task(recent.task_id) is not None
        assert mgr.get_task(task.task_id) is None

    def test_cleanup_keeps_pending_tasks(self):
        """Cleanup does not remove old PENDING tasks."""
        mgr = self._fresh_manager()
        task = mgr.create_task("test_type")
        task.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
        mgr.cleanup_old_tasks(max_age_hours=24)
        assert mgr.get_task(task.task_id) is not None

    def test_create_and_get_task(self):
        mgr = self._fresh_manager()
        task = mgr.create_task("analysis", metadata={"project_id": "p1"})
        assert task.task_type == "analysis"
        fetched = mgr.get_task(task.task_id)
        assert fetched is not None
        assert fetched.metadata["project_id"] == "p1"

    def test_list_tasks_filter_by_type(self):
        mgr = self._fresh_manager()
        mgr.create_task("type_a")
        mgr.create_task("type_b")
        mgr.create_task("type_a")
        result = mgr.list_tasks(task_type="type_a")
        assert len(result) == 2

    def test_to_dict(self):
        mgr = self._fresh_manager()
        task = mgr.create_task("export")
        d = task.to_dict()
        assert d["task_type"] == "export"
        assert d["status"] == "pending"
        assert "task_id" in d
