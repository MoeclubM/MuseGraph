"""Tests for admin provider-model management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from app.services.task_state import TaskStatus, task_manager

def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


class TestProviderModels:

    @pytest.mark.asyncio
    async def test_list_provider_models_normalizes(self, admin_client: AsyncClient, mock_db: AsyncMock):
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models={"models": ["gpt-4o-mini", "gpt-4o"]},
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        resp = await admin_client.get("/api/admin/providers/provider-1/models")

        assert resp.status_code == 200
        assert resp.json()["models"] == ["gpt-4o-mini", "gpt-4o"]

    @pytest.mark.asyncio
    async def test_add_provider_model(self, admin_client: AsyncClient, mock_db: AsyncMock):
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models=["gpt-4o-mini"],
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/models",
            json={"model": "gpt-4.1-mini"},
        )

        assert resp.status_code == 200
        assert resp.json()["models"] == ["gpt-4o-mini", "gpt-4.1-mini"]
        assert provider.models == ["gpt-4o-mini", "gpt-4.1-mini"]
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_remove_provider_model(self, admin_client: AsyncClient, mock_db: AsyncMock):
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models=["gpt-4o-mini", "gpt-4.1-mini"],
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        resp = await admin_client.delete(
            "/api/admin/providers/provider-1/models",
            params={"model": "gpt-4.1-mini"},
        )

        assert resp.status_code == 200
        assert resp.json()["models"] == ["gpt-4o-mini"]
        assert provider.models == ["gpt-4o-mini"]
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_discover_provider_models_persist(self, admin_client: AsyncClient, mock_db: AsyncMock, monkeypatch):
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models=["gpt-4o-mini"],
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        class _FakeModels:
            async def list(self):
                return SimpleNamespace(data=[
                    SimpleNamespace(id="gpt-4.1-mini"),
                    SimpleNamespace(id="gpt-4o-mini"),
                ])

        class _FakeOpenAI:
            def __init__(self, *args, **kwargs):
                self.models = _FakeModels()

        monkeypatch.setattr("openai.AsyncOpenAI", _FakeOpenAI)

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/models/discover",
            params={"persist": "true"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["discovered"] == ["gpt-4.1-mini", "gpt-4o-mini"]
        assert body["models"] == ["gpt-4.1-mini", "gpt-4o-mini"]
        assert body["persisted"] is True
        assert provider.models == ["gpt-4.1-mini", "gpt-4o-mini"]
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_discover_provider_embedding_models_persist(self, admin_client: AsyncClient, mock_db: AsyncMock, monkeypatch):
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models=["gpt-4o-mini"],
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        class _FakeModels:
            async def list(self):
                return SimpleNamespace(data=[
                    SimpleNamespace(id="Qwen3-Embedding-0.6B"),
                    SimpleNamespace(id="text-embedding-3-small"),
                ])

        class _FakeOpenAI:
            def __init__(self, *args, **kwargs):
                self.models = _FakeModels()

        monkeypatch.setattr("openai.AsyncOpenAI", _FakeOpenAI)

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/embedding-models/discover",
            params={"persist": "true"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["discovered"] == ["Qwen3-Embedding-0.6B", "text-embedding-3-small"]
        assert body["embedding_models"] == ["Qwen3-Embedding-0.6B", "text-embedding-3-small"]
        assert body["persisted"] is True
        assert provider.models == {
            "models": ["gpt-4o-mini"],
            "embedding_models": ["Qwen3-Embedding-0.6B", "text-embedding-3-small"],
        }
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_discover_provider_embedding_models_keeps_mixed_results(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch,
    ):
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models={"models": ["gpt-4o-mini"], "embedding_models": []},
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        class _FakeModels:
            async def list(self):
                return SimpleNamespace(
                    data=[
                        SimpleNamespace(id="gpt-4.1-mini"),
                        SimpleNamespace(id="Qwen3-Embedding-0.6B"),
                        SimpleNamespace(id="text-embedding-3-small"),
                    ]
                )

        class _FakeOpenAI:
            def __init__(self, *args, **kwargs):
                self.models = _FakeModels()

        monkeypatch.setattr("openai.AsyncOpenAI", _FakeOpenAI)

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/embedding-models/discover",
            params={"persist": "true"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["discovered"] == ["Qwen3-Embedding-0.6B", "gpt-4.1-mini", "text-embedding-3-small"]
        assert body["embedding_models"] == ["Qwen3-Embedding-0.6B", "gpt-4.1-mini", "text-embedding-3-small"]
        assert provider.models == {
            "models": ["gpt-4o-mini"],
            "embedding_models": ["Qwen3-Embedding-0.6B", "gpt-4.1-mini", "text-embedding-3-small"],
        }

    @pytest.mark.asyncio
    async def test_discover_provider_chat_models_keeps_mixed_results(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch,
    ):
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models={"models": [], "embedding_models": ["Qwen3-Embedding-0.6B"]},
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        class _FakeModels:
            async def list(self):
                return SimpleNamespace(
                    data=[
                        SimpleNamespace(id="gpt-4.1-mini"),
                        SimpleNamespace(id="Qwen3-Embedding-0.6B"),
                    ]
                )

        class _FakeOpenAI:
            def __init__(self, *args, **kwargs):
                self.models = _FakeModels()

        monkeypatch.setattr("openai.AsyncOpenAI", _FakeOpenAI)

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/models/discover",
            params={"persist": "true"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["discovered"] == ["Qwen3-Embedding-0.6B", "gpt-4.1-mini"]
        assert body["models"] == ["Qwen3-Embedding-0.6B", "gpt-4.1-mini"]
        assert provider.models == {
            "models": ["Qwen3-Embedding-0.6B", "gpt-4.1-mini"],
            "embedding_models": ["Qwen3-Embedding-0.6B"],
        }

    @pytest.mark.asyncio
    async def test_create_provider_accepts_openai_alias(self, admin_client: AsyncClient, mock_db: AsyncMock):
        resp = await admin_client.post(
            "/api/admin/providers",
            json={
                "name": "openai-alias-provider",
                "provider": "openai",
                "api_key": "sk-test",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "openai_compatible"

    @pytest.mark.asyncio
    async def test_create_provider_rejects_models_field(self, admin_client: AsyncClient, mock_db: AsyncMock):
        resp = await admin_client.post(
            "/api/admin/providers",
            json={
                "name": "bad-provider",
                "provider": "openai_compatible",
                "api_key": "sk-test",
                "models": ["gpt-4o-mini"],
            },
        )
        assert resp.status_code == 400
        assert "managed via /api/admin/providers/{provider_id}/models" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_provider_rejects_models_field(self, admin_client: AsyncClient, mock_db: AsyncMock):
        resp = await admin_client.put(
            "/api/admin/providers/provider-1",
            json={"models": ["gpt-4o-mini"]},
        )
        assert resp.status_code == 400
        assert "managed via /api/admin/providers/{provider_id}/models" in resp.json()["detail"]


def _scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _scalars_all(items: list):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _all(items: list):
    result = MagicMock()
    result.all.return_value = items
    return result


def _scalars_first(item):
    result = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = item
    result.scalars.return_value = scalars
    return result


class TestAdminUsers:

    @pytest.mark.asyncio
    async def test_list_users_uses_is_admin(self, admin_client: AsyncClient, mock_db: AsyncMock):
        user = SimpleNamespace(
            id="user-1",
            email="u@example.com",
            nickname="User 1",
            is_admin=True,
            status="ACTIVE",
            balance=0,
            group_id=None,
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.side_effect = [
            _scalar(1),
            _scalars_all([user]),
            _all([]),
            _all([]),
        ]

        resp = await admin_client.get("/api/admin/users")
        assert resp.status_code == 200
        body = resp.json()
        assert body["users"][0]["is_admin"] is True
        assert "role" not in body["users"][0]

    @pytest.mark.asyncio
    async def test_create_user(self, admin_client: AsyncClient, mock_db: AsyncMock):
        now = datetime.now(timezone.utc)

        def _side_effect_add(obj):
            if hasattr(obj, "email") and hasattr(obj, "password_hash"):
                obj.id = obj.id or "user-2"
                obj.balance = obj.balance or 0
                obj.status = obj.status or "ACTIVE"
                obj.created_at = obj.created_at or now

        mock_db.add = MagicMock(side_effect=_side_effect_add)
        mock_db.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(None),  # no existing email
                _scalars_first(None),       # no default group
            ]
        )

        resp = await admin_client.post(
            "/api/admin/users",
            json={
                "email": "new@example.com",
                "password": "Password123!",
                "nickname": "New User",
                "is_admin": True,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "new@example.com"
        assert body["is_admin"] is True

    @pytest.mark.asyncio
    async def test_delete_user(self, admin_client: AsyncClient, mock_db: AsyncMock):
        user = SimpleNamespace(id="user-3")
        mock_db.execute.return_value = _scalar_one_or_none(user)

        resp = await admin_client.delete("/api/admin/users/user-3")
        assert resp.status_code == 204
        mock_db.delete.assert_awaited_once_with(user)


class TestAdminTasks:

    @pytest.mark.asyncio
    async def test_list_tasks_with_filters(self, admin_client: AsyncClient):
        task_type = f"admin-task-test-{uuid.uuid4().hex}"
        task_one = task_manager.create_task(task_type, metadata={"user_id": "user-1", "project_id": "project-1"})
        task_two = task_manager.create_task(task_type, metadata={"user_id": "user-2", "project_id": "project-1"})
        task_manager.update_task(
            task_one.task_id,
            status=TaskStatus.PROCESSING,
            progress=30,
            message="Building",
            progress_detail={"stage": "build", "step": "collect", "processed": 3, "total": 10},
        )
        task_manager.update_task(task_two.task_id, status=TaskStatus.COMPLETED, progress=100, message="Done")

        resp = await admin_client.get(
            "/api/admin/tasks",
            params={"task_type": task_type, "status": "processing", "user_id": "user-1", "limit": 200},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["tasks"][0]["task_id"] == task_one.task_id
        assert body["tasks"][0]["status"] == "processing"
        assert body["tasks"][0]["progress_detail"]["stage"] == "build"

    @pytest.mark.asyncio
    async def test_get_task_detail_not_found(self, admin_client: AsyncClient):
        resp = await admin_client.get(f"/api/admin/tasks/missing-task-{uuid.uuid4().hex}")

        assert resp.status_code == 404
        assert "Task not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_cancel_task(self, admin_client: AsyncClient):
        task = task_manager.create_task(
            f"admin-cancel-test-{uuid.uuid4().hex}",
            metadata={"user_id": "user-1", "project_id": "project-2"},
        )
        task_manager.update_task(task.task_id, status=TaskStatus.PROCESSING, progress=45, message="Running")

        resp = await admin_client.post(f"/api/admin/tasks/{task.task_id}/cancel")

        assert resp.status_code == 200
        body = resp.json()
        assert body["task"]["status"] == "cancelled"
        assert body["task"]["task_id"] == task.task_id


class TestPaymentConfig:

    @pytest.mark.asyncio
    async def test_get_payment_config_default(self, admin_client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await admin_client.get("/api/admin/payment-config")

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["has_key"] is False

    @pytest.mark.asyncio
    async def test_update_payment_config_requires_fields_when_enabled(self, admin_client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await admin_client.put(
            "/api/admin/payment-config",
            json={"enabled": True, "url": "", "pid": "", "key": ""},
        )

        assert resp.status_code == 400
        assert "requires url, pid and key" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_payment_config_keeps_existing_key(self, admin_client: AsyncClient, mock_db: AsyncMock):
        existing = SimpleNamespace(
            type="epay",
            is_active=True,
            config={
                "url": "https://pay.example.com",
                "pid": "10001",
                "key": "secret-key",
                "payment_type": "alipay",
                "notify_url": "",
                "return_url": "",
            },
        )
        mock_db.execute.return_value = _scalar_one_or_none(existing)

        resp = await admin_client.put(
            "/api/admin/payment-config",
            json={
                "enabled": True,
                "url": "https://pay.example.com",
                "pid": "10001",
                "key": "",
                "payment_type": "wxpay",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["has_key"] is True
        assert body["payment_type"] == "wxpay"


class TestOasisConfig:

    @pytest.mark.asyncio
    async def test_get_oasis_config_default(self, admin_client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await admin_client.get("/api/admin/oasis-config")

        assert resp.status_code == 200
        body = resp.json()
        assert body["max_agent_profiles"] == 16
        assert body["llm_request_timeout_seconds"] == 180
        assert body["llm_retry_count"] == 4
        assert body["llm_retry_interval_seconds"] == 2.0
        assert body["llm_prefer_stream"] is True
        assert body["llm_stream_fallback_nonstream"] is True
        assert body["llm_task_concurrency"] == 1
        assert body["llm_model_default_concurrency"] == 8
        assert body["llm_model_concurrency_overrides"] == {}

    @pytest.mark.asyncio
    async def test_update_oasis_config_clamps_llm_retry_settings(self, admin_client: AsyncClient, mock_db: AsyncMock):
        existing = SimpleNamespace(type="oasis", is_active=True, config={})
        mock_db.execute.return_value = _scalar_one_or_none(existing)

        resp = await admin_client.put(
            "/api/admin/oasis-config",
            json={
                "llm_request_timeout_seconds": 99999,
                "llm_retry_count": -3,
                "llm_retry_interval_seconds": 999,
                "llm_task_concurrency": 999,
                "llm_model_default_concurrency": 0,
                "llm_model_concurrency_overrides": {
                    "gpt-4o-mini": 999,
                    "": 3,
                    "invalid": "abc",
                },
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_request_timeout_seconds"] == 1800
        assert body["llm_retry_count"] == 0
        assert body["llm_retry_interval_seconds"] == 60.0
        assert body["llm_task_concurrency"] == 64
        assert body["llm_model_default_concurrency"] == 1
        assert body["llm_model_concurrency_overrides"] == {"gpt-4o-mini": 64}

    @pytest.mark.asyncio
    async def test_update_oasis_config_partial_merge_preserves_existing_fields(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ):
        existing = SimpleNamespace(
            type="oasis",
            is_active=True,
            config={
                "analysis_prompt_prefix": "existing-analysis",
                "max_events": 22,
                "llm_request_timeout_seconds": 90,
                "llm_retry_count": 4,
                "llm_retry_interval_seconds": 2.5,
                "llm_prefer_stream": False,
                "llm_stream_fallback_nonstream": False,
                "llm_task_concurrency": 3,
                "llm_model_default_concurrency": 6,
                "llm_model_concurrency_overrides": {"gpt-4o-mini": 4},
            },
        )
        mock_db.execute.return_value = _scalar_one_or_none(existing)

        resp = await admin_client.put(
            "/api/admin/oasis-config",
            json={
                "llm_retry_count": 1,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["analysis_prompt_prefix"] == "existing-analysis"
        assert body["max_events"] == 22
        assert body["llm_request_timeout_seconds"] == 90
        assert body["llm_retry_count"] == 1
        assert body["llm_retry_interval_seconds"] == 2.5
        assert body["llm_prefer_stream"] is False
        assert body["llm_stream_fallback_nonstream"] is False
        assert body["llm_task_concurrency"] == 3
        assert body["llm_model_default_concurrency"] == 6
        assert body["llm_model_concurrency_overrides"] == {"gpt-4o-mini": 4}
