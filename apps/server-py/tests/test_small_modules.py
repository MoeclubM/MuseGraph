"""Tests for small modules needing coverage: ai router, export router,
auth logout, strict llm_json parsing, and task_state manager."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from tests.conftest import get_endpoint_globals


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


class TestAIModelsRouter:
    """Cover app/routers/ai.py lines 17-18: GET /api/ai/models."""

    @pytest.mark.asyncio
    async def test_list_models(self, client: AsyncClient, mock_db: AsyncMock):
        g = get_endpoint_globals("list_models")
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

    @pytest.mark.asyncio
    async def test_list_reranker_models(self, client: AsyncClient, mock_db: AsyncMock):
        g = get_endpoint_globals("list_reranker_models")
        fake_models = [
            {
                "id": "Qwen3-Reranker-0.6B",
                "name": "Qwen3-Reranker-0.6B",
                "provider": "telecom-qwen-memory",
            },
        ]
        mock_fn = AsyncMock(return_value=fake_models)
        orig = g["get_available_reranker_models"]
        g["get_available_reranker_models"] = mock_fn
        try:
            resp = await client.get("/api/ai/reranker-models")
        finally:
            g["get_available_reranker_models"] = orig

        assert resp.status_code == 200
        assert resp.json()["models"] == fake_models


class TestExportRouter:
    """Cover app/routers/export.py: project not found and forbidden paths."""

    @pytest.mark.asyncio
    async def test_export_project_not_found(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)
        resp = await client.post("/api/projects/proj-999/export/bundle")
        assert resp.status_code == 404
        assert "Project not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_forbidden(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        project = SimpleNamespace(id="proj-1", user_id="other-user", visibility="private", members=[], title="Secret")
        mock_db.execute.return_value = _scalar_one_or_none(project)
        resp = await client.post("/api/projects/proj-1/export/bundle")
        assert resp.status_code == 403


class TestBillingPricingCatalog:
    @pytest.mark.asyncio
    async def test_pricing_includes_provider_models_without_rules(self, client: AsyncClient, mock_db: AsyncMock):
        provider = SimpleNamespace(
            name="telecom-qwen-memory",
            provider="openai_compatible",
            is_active=True,
            models={
                "models": ["nvidia/nemotron-3-ultra-550b-a55b:free"],
                "embedding_models": ["Qwen3-Embedding-0.6B"],
                "reranker_models": ["Qwen3-Reranker-0.6B"],
            },
        )
        priced = SimpleNamespace(
            id="rule-1",
            model="gpt-4o-mini",
            billing_mode="TOKEN",
            input_price=1,
            output_price=2,
            token_unit=1000000,
            request_price=0,
            is_active=True,
        )
        mock_db.execute = AsyncMock(side_effect=[_scalars_all([provider]), _scalars_all([priced])])

        resp = await client.get("/api/billing/pricing")

        assert resp.status_code == 200
        rows = {item["model"]: item for item in resp.json()}
        assert rows["nvidia/nemotron-3-ultra-550b-a55b:free"]["has_pricing"] is False
        assert rows["nvidia/nemotron-3-ultra-550b-a55b:free"]["model_type"] == "chat"
        assert rows["Qwen3-Embedding-0.6B"]["model_type"] == "embedding"
        assert rows["Qwen3-Reranker-0.6B"]["model_type"] == "reranker"
        assert rows["gpt-4o-mini"]["has_pricing"] is True


class TestAuthLogout:
    """Cover app/routers/auth.py line 32: logout deletes cookie."""

    @pytest.mark.asyncio
    async def test_logout_deletes_cookie(self, client: AsyncClient, mock_db: AsyncMock):
        g = get_endpoint_globals("logout")
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
    """Cover app/services/llm_json.py strict object parsing behavior."""

    def test_extract_plain_json(self):
        from app.services.llm_json import extract_json_object
        result = extract_json_object('{"key": "value"}')
        assert result == {"key": "value"}

    def test_reject_fenced_json(self):
        from app.services.llm_json import extract_json_object
        raw = '```json\n{"a": 1}\n```'
        assert extract_json_object(raw) is None

    def test_reject_embedded_braces(self):
        """Embedded JSON in plain text is not accepted."""
        from app.services.llm_json import extract_json_object
        raw = 'Here is the result: {"name": "test", "count": 42} -- done'
        result = extract_json_object(raw)
        assert result is None

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
