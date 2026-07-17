"""Tests for admin provider-model management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from app.services.task_state import TaskStatus, task_manager

def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _http_models_client(model_ids: list[str | dict]):
    class _FakeResponse:
        text = ""
        status_code = 200

        def json(self):
            return {"data": [item if isinstance(item, dict) else {"id": item} for item in model_ids]}

        def raise_for_status(self):
            return None

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return _FakeResponse()

    return _FakeAsyncClient


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
    async def test_list_provider_reranker_models_normalizes(self, admin_client: AsyncClient, mock_db: AsyncMock):
        provider = SimpleNamespace(
            id="provider-1",
            name="NewAPI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url="https://example.com/v1",
            models={
                "models": ["gpt-4o-mini"],
                "embedding_models": ["Qwen3-Embedding-0.6B"],
                "reranker_models": ["Qwen3-Reranker-0.6B"],
            },
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        resp = await admin_client.get("/api/admin/providers/provider-1/reranker-models")

        assert resp.status_code == 200
        assert resp.json()["reranker_models"] == ["Qwen3-Reranker-0.6B"]

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
    async def test_add_provider_reranker_model(self, admin_client: AsyncClient, mock_db: AsyncMock):
        provider = SimpleNamespace(
            id="provider-1",
            name="NewAPI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url="https://example.com/v1",
            models={"models": ["gpt-4o-mini"], "embedding_models": ["Qwen3-Embedding-0.6B"]},
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/reranker-models",
            json={"model": "Qwen3-Reranker-0.6B"},
        )

        assert resp.status_code == 200
        assert resp.json()["reranker_models"] == ["Qwen3-Reranker-0.6B"]
        assert provider.models == {
            "models": ["gpt-4o-mini"],
            "embedding_models": ["Qwen3-Embedding-0.6B"],
            "reranker_models": ["Qwen3-Reranker-0.6B"],
        }
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
    async def test_remove_provider_reranker_model(self, admin_client: AsyncClient, mock_db: AsyncMock):
        provider = SimpleNamespace(
            id="provider-1",
            name="NewAPI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url="https://example.com/v1",
            models={
                "models": ["gpt-4o-mini"],
                "embedding_models": ["Qwen3-Embedding-0.6B"],
                "reranker_models": ["Qwen3-Reranker-0.6B"],
            },
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        resp = await admin_client.delete(
            "/api/admin/providers/provider-1/reranker-models",
            params={"model": "Qwen3-Reranker-0.6B"},
        )

        assert resp.status_code == 200
        assert resp.json()["reranker_models"] == []
        assert provider.models == {
            "models": ["gpt-4o-mini"],
            "embedding_models": ["Qwen3-Embedding-0.6B"],
        }
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_provider_removes_orphan_pricing_and_project_references(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ):
        provider = SimpleNamespace(
            id="provider-1",
            name="primary-provider",
            provider="openai_compatible",
            api_key="sk-test",
            base_url="https://example.com/v1",
            models={
                "models": ["MiniMax-M2.5", "Shared-Model"],
                "embedding_models": ["Qwen3-Embedding-0.6B"],
                "reranker_models": ["Qwen3-Reranker-0.6B"],
            },
        )
        remaining_provider = SimpleNamespace(
            id="provider-2",
            name="secondary-provider",
            provider="openai_compatible",
            api_key="sk-test-2",
            base_url="https://example.org/v1",
            models={"models": ["Shared-Model"], "embedding_models": ["Embed-Only"]},
        )
        orphan_rule = SimpleNamespace(id="rule-1", model="MiniMax-M2.5")
        shared_rule = SimpleNamespace(id="rule-2", model="Shared-Model")
        project = SimpleNamespace(
            id=str(uuid.uuid4()),
            component_models={
                "memory_build": "MiniMax-M2.5",
                "memory_embedding": "Qwen3-Embedding-0.6B",
                "memory_reranker": "Qwen3-Reranker-0.6B",
                "default": "Shared-Model",
            },
        )
        untouched_project = SimpleNamespace(
            id=str(uuid.uuid4()),
            component_models={"default": "Other-Model"},
        )
        mock_db.execute.side_effect = [
            _scalar_one_or_none(provider),
            _scalars_all([remaining_provider]),
            _scalars_all([orphan_rule]),
            _scalars_all([project, untouched_project]),
        ]

        resp = await admin_client.delete("/api/admin/providers/provider-1")

        assert resp.status_code == 204
        mock_db.delete.assert_any_await(orphan_rule)
        mock_db.delete.assert_any_await(provider)
        assert project.component_models == {"default": "Shared-Model"}
        assert untouched_project.component_models == {"default": "Other-Model"}

    @pytest.mark.asyncio
    async def test_delete_provider_keeps_shared_model_references(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ):
        provider = SimpleNamespace(
            id="provider-1",
            name="primary-provider",
            provider="openai_compatible",
            api_key="sk-test",
            base_url="https://example.com/v1",
            models={"models": ["Shared-Model"], "embedding_models": []},
        )
        remaining_provider = SimpleNamespace(
            id="provider-2",
            name="secondary-provider",
            provider="openai_compatible",
            api_key="sk-test-2",
            base_url="https://example.org/v1",
            models={"models": ["Shared-Model"], "embedding_models": []},
        )
        project = SimpleNamespace(
            id=str(uuid.uuid4()),
            component_models={"default": "Shared-Model"},
        )
        mock_db.execute.side_effect = [
            _scalar_one_or_none(provider),
            _scalars_all([remaining_provider]),
        ]

        resp = await admin_client.delete("/api/admin/providers/provider-1")

        assert resp.status_code == 204
        mock_db.delete.assert_called_once_with(provider)
        assert project.component_models == {"default": "Shared-Model"}

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

        monkeypatch.setattr(
            "app.routers.admin.httpx.AsyncClient",
            _http_models_client(["gpt-4.1-mini", "gpt-4o-mini"]),
        )

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

        monkeypatch.setattr(
            "app.routers.admin.httpx.AsyncClient",
            _http_models_client(["Qwen3-Embedding-0.6B", "text-embedding-3-small"]),
        )

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/embedding-models/discover",
            params={"persist": "true"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["discovered"] == ["Qwen3-Embedding-0.6B", "text-embedding-3-small"]
        assert body["persistable_discovered"] == ["Qwen3-Embedding-0.6B", "text-embedding-3-small"]
        assert body["not_persisted_discovered"] == []
        assert body["embedding_models"] == ["Qwen3-Embedding-0.6B", "text-embedding-3-small"]
        assert body["persisted"] is True
        assert provider.models == {
            "models": ["gpt-4o-mini"],
            "embedding_models": ["Qwen3-Embedding-0.6B", "text-embedding-3-small"]
        }
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_discover_provider_reranker_models_persist(self, admin_client: AsyncClient, mock_db: AsyncMock, monkeypatch):
        provider = SimpleNamespace(
            id="provider-1",
            name="NewAPI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models={"models": ["gpt-4o-mini"], "embedding_models": ["Qwen3-Embedding-0.6B"]},
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        monkeypatch.setattr(
            "app.routers.admin.httpx.AsyncClient",
            _http_models_client(["Qwen3-Reranker-0.6B", "jina-reranker-v2-base-multilingual"]),
        )

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/reranker-models/discover",
            params={"persist": "true"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["discovered"] == ["Qwen3-Reranker-0.6B", "jina-reranker-v2-base-multilingual"]
        assert body["persistable_discovered"] == ["Qwen3-Reranker-0.6B", "jina-reranker-v2-base-multilingual"]
        assert body["not_persisted_discovered"] == []
        assert body["reranker_models"] == ["Qwen3-Reranker-0.6B", "jina-reranker-v2-base-multilingual"]
        assert provider.models == {
            "models": ["gpt-4o-mini"],
            "embedding_models": ["Qwen3-Embedding-0.6B"],
            "reranker_models": ["Qwen3-Reranker-0.6B", "jina-reranker-v2-base-multilingual"],
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

        monkeypatch.setattr(
            "app.routers.admin.httpx.AsyncClient",
            _http_models_client(["gpt-4.1-mini", "Qwen3-Embedding-0.6B", "text-embedding-3-small"]),
        )

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/embedding-models/discover",
            params={"persist": "true"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["discovered"] == ["Qwen3-Embedding-0.6B", "gpt-4.1-mini", "text-embedding-3-small"]
        assert body["persistable_discovered"] == ["Qwen3-Embedding-0.6B", "text-embedding-3-small"]
        assert body["not_persisted_discovered"] == ["gpt-4.1-mini"]
        assert body["not_persisted_reason"] == "model_kind_not_confirmed"
        assert body["embedding_models"] == ["Qwen3-Embedding-0.6B", "text-embedding-3-small"]
        assert provider.models == {
            "models": ["gpt-4o-mini"],
            "embedding_models": ["Qwen3-Embedding-0.6B", "text-embedding-3-small"]
        }

    @pytest.mark.asyncio
    async def test_discover_provider_reranker_models_does_not_persist_chat_results(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch,
    ):
        provider = SimpleNamespace(
            id="provider-1",
            name="NewAPI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models={"models": ["gpt-4o-mini"], "embedding_models": ["Qwen3-Embedding-0.6B"]},
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        monkeypatch.setattr(
            "app.routers.admin.httpx.AsyncClient",
            _http_models_client(["gpt-4.1-mini", "Qwen3-Reranker-0.6B"]),
        )

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/reranker-models/discover",
            params={"persist": "true"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["discovered"] == ["Qwen3-Reranker-0.6B", "gpt-4.1-mini"]
        assert body["persistable_discovered"] == ["Qwen3-Reranker-0.6B"]
        assert body["not_persisted_discovered"] == ["gpt-4.1-mini"]
        assert body["not_persisted_reason"] == "model_kind_not_confirmed"
        assert body["reranker_models"] == ["Qwen3-Reranker-0.6B"]
        assert provider.models == {
            "models": ["gpt-4o-mini"],
            "embedding_models": ["Qwen3-Embedding-0.6B"],
            "reranker_models": ["Qwen3-Reranker-0.6B"],
        }

    @pytest.mark.asyncio
    async def test_discover_provider_embedding_models_persists_structurally_identified_results(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
        monkeypatch,
    ):
        provider = SimpleNamespace(
            id="provider-1",
            name="NewAPI",
            provider="openai_compatible",
            api_key="sk-test",
            base_url=None,
            models={"models": ["gpt-4o-mini"], "embedding_models": []},
        )
        mock_db.execute.return_value = _scalar_one_or_none(provider)

        monkeypatch.setattr(
            "app.routers.admin.httpx.AsyncClient",
            _http_models_client([
                {"id": "vector-v1", "type": "embedding"},
                {"id": "chat-v1", "type": "chat"},
            ]),
        )

        resp = await admin_client.post(
            "/api/admin/providers/provider-1/embedding-models/discover",
            params={"persist": "true"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["discovered"] == ["chat-v1", "vector-v1"]
        assert body["persistable_discovered"] == ["vector-v1"]
        assert body["not_persisted_discovered"] == ["chat-v1"]
        assert body["embedding_models"] == ["vector-v1"]
        assert provider.models == {
            "models": ["gpt-4o-mini"],
            "embedding_models": ["vector-v1"],
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

        monkeypatch.setattr(
            "app.routers.admin.httpx.AsyncClient",
            _http_models_client(["gpt-4.1-mini", "Qwen3-Embedding-0.6B"]),
        )

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
            "embedding_models": ["Qwen3-Embedding-0.6B"]
        }

    @pytest.mark.asyncio
    async def test_create_provider_rejects_provider_alias(self, admin_client: AsyncClient, mock_db: AsyncMock):
        resp = await admin_client.post(
            "/api/admin/providers",
            json={
                "name": "openai-alias-provider",
                "provider": "openai",
                "api_key": "sk-test",
            },
        )
        assert resp.status_code == 400
        assert "provider must be one of" in resp.json()["detail"]

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


class TestPricingRules:

    @pytest.mark.asyncio
    async def test_list_pricing_includes_registered_unpriced_models(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ):
        provider = SimpleNamespace(
            id="provider-newapi",
            name="NewAPI Telecom",
            provider="openai_compatible",
            api_key="sk-test",
            base_url="https://provider.example/v1",
            models={
                "models": ["nvidia/nemotron-3-ultra-550b-a55b:free"],
                "embedding_models": ["Qwen3-Embedding-0.6B"],
                "reranker_models": ["Qwen3-Reranker-0.6B"],
            },
        )
        priced_rule = SimpleNamespace(
            id="rule-embed",
            model="Qwen3-Embedding-0.6B",
            billing_mode="TOKEN",
            input_price=Decimal("0.010000"),
            output_price=Decimal("0"),
            token_unit=1_000_000,
            request_price=Decimal("0"),
            is_active=True,
        )
        mock_db.execute.side_effect = [
            _scalars_all([provider]),
            _scalars_all([priced_rule]),
        ]

        resp = await admin_client.get("/api/admin/pricing")

        assert resp.status_code == 200
        body = {item["model"]: item for item in resp.json()}
        assert body["nvidia/nemotron-3-ultra-550b-a55b:free"] == {
            "id": None,
            "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "model_type": "chat",
            "providers": ["NewAPI Telecom"],
            "has_pricing": False,
            "billing_mode": "TOKEN",
            "input_price": 0.0,
            "output_price": 0.0,
            "token_unit": 1_000_000,
            "request_price": 0.0,
            "is_active": False,
        }
        assert body["Qwen3-Embedding-0.6B"]["model_type"] == "embedding"
        assert body["Qwen3-Embedding-0.6B"]["has_pricing"] is True
        assert body["Qwen3-Reranker-0.6B"]["model_type"] == "reranker"
        assert body["Qwen3-Reranker-0.6B"]["has_pricing"] is False

    @pytest.mark.asyncio
    async def test_update_pricing_renames_provider_and_project_model_references(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ):
        rule = SimpleNamespace(
            id="rule-1",
            model="MiniMax-M2.5",
            billing_mode="TOKEN",
            input_price=Decimal("0.120000"),
            output_price=Decimal("0.340000"),
            token_unit=1_000_000,
            request_price=Decimal("0"),
            is_active=True,
        )
        provider = SimpleNamespace(
            id="provider-1",
            name="primary-provider",
            provider="openai_compatible",
            api_key="sk-test",
            base_url="https://example.com/v1",
            models={
                "models": ["MiniMax-M2.5", "MiniMax-M2.7"],
                "embedding_models": ["MiniMax-M2.5", "Qwen3-Embedding-0.6B"],
                "reranker_models": ["MiniMax-M2.5", "Qwen3-Reranker-0.6B"],
            },
        )
        untouched_provider = SimpleNamespace(
            id="provider-2",
            name="secondary-provider",
            provider="openai_compatible",
            api_key="sk-test-2",
            base_url="https://example.org/v1",
            models={"models": ["Other-Model"], "embedding_models": ["Embed-Only"], "reranker_models": ["Rerank-Only"]},
        )
        project = SimpleNamespace(
            id=str(uuid.uuid4()),
            component_models={
                "operation_create": "MiniMax-M2.5",
                "memory_embedding": "MiniMax-M2.5",
                "memory_reranker": "MiniMax-M2.5",
                "default": "MiniMax-M2.7",
            },
        )
        untouched_project = SimpleNamespace(
            id=str(uuid.uuid4()),
            component_models={"default": "Other-Model"},
        )
        mock_db.execute.side_effect = [
            _scalar_one_or_none(rule),
            _scalar_one_or_none(None),
            _scalars_all([provider, untouched_provider]),
            _scalars_all([project, untouched_project]),
        ]

        resp = await admin_client.put(
            "/api/admin/pricing/rule-1",
            json={
                "model": "MiniMax-M2.7",
                "billing_mode": "TOKEN",
                "input_price": 0.12,
                "output_price": 0.34,
                "token_unit": 1_000_000,
                "is_active": True,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["model"] == "MiniMax-M2.7"
        assert provider.models == {
            "models": ["MiniMax-M2.7"],
            "embedding_models": ["MiniMax-M2.7", "Qwen3-Embedding-0.6B"],
            "reranker_models": ["MiniMax-M2.7", "Qwen3-Reranker-0.6B"],
        }
        assert untouched_provider.models == {
            "models": ["Other-Model"],
            "embedding_models": ["Embed-Only"],
            "reranker_models": ["Rerank-Only"],
        }
        assert project.component_models == {
            "operation_create": "MiniMax-M2.7",
            "memory_embedding": "MiniMax-M2.7",
            "memory_reranker": "MiniMax-M2.7",
            "default": "MiniMax-M2.7",
        }
        assert untouched_project.component_models == {"default": "Other-Model"}
        mock_db.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_update_pricing_rejects_duplicate_model_name(
        self,
        admin_client: AsyncClient,
        mock_db: AsyncMock,
    ):
        rule = SimpleNamespace(
            id="rule-1",
            model="MiniMax-M2.5",
            billing_mode="TOKEN",
            input_price=Decimal("0.120000"),
            output_price=Decimal("0.340000"),
            token_unit=1_000_000,
            request_price=Decimal("0"),
            is_active=True,
        )
        existing = SimpleNamespace(id="rule-2", model="MiniMax-M2.7")
        mock_db.execute.side_effect = [
            _scalar_one_or_none(rule),
            _scalar_one_or_none(existing),
        ]

        resp = await admin_client.put(
            "/api/admin/pricing/rule-1",
            json={
                "model": "MiniMax-M2.7",
                "billing_mode": "TOKEN",
                "input_price": 0.12,
                "output_price": 0.34,
                "token_unit": 1_000_000,
                "is_active": True,
            },
        )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Pricing rule for this model already exists"
        mock_db.flush.assert_not_awaited()


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

    @pytest.mark.asyncio
    async def test_reset_user_password(self, admin_client: AsyncClient, mock_db: AsyncMock):
        user = SimpleNamespace(id="user-4", password_hash="old")
        mock_db.execute.return_value = _scalar_one_or_none(user)

        resp = await admin_client.post(
            "/api/admin/users/user-4/password",
            json={"password": "newpass123"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert user.password_hash != "old"
        mock_db.flush.assert_awaited()


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


class TestLlmRuntimeAdminConfig:

    @pytest.mark.asyncio
    async def test_get_llm_runtime_config_returns_defaults(self, admin_client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalar_one_or_none(None)

        resp = await admin_client.get("/api/admin/llm-runtime-config")

        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_request_timeout_seconds"] == 180
        assert body["llm_retry_count"] == 4
        assert body["llm_task_concurrency"] == 4
        assert body["llm_model_default_concurrency"] == 8

    @pytest.mark.asyncio
    async def test_put_llm_runtime_config_merges_fields(self, admin_client: AsyncClient, mock_db: AsyncMock):
        existing = SimpleNamespace(
            id="cfg-1",
            name="llm_runtime",
            type="llm_runtime",
            is_active=True,
            config={
                "llm_request_timeout_seconds": 120,
                "llm_retry_count": 1,
            },
        )
        mock_db.execute.return_value = _scalar_one_or_none(existing)

        resp = await admin_client.put(
            "/api/admin/llm-runtime-config",
            json={"llm_retry_count": 2, "llm_task_concurrency": 6},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["llm_request_timeout_seconds"] == 120
        assert body["llm_retry_count"] == 2
        assert body["llm_task_concurrency"] == 6
        assert existing.config["llm_retry_count"] == 2


class TestPaymentAdapters:

    @pytest.mark.asyncio
    async def test_list_payment_adapters_empty(self, admin_client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute.return_value = _scalars_all([])

        resp = await admin_client.get("/api/admin/payment-adapters")

        assert resp.status_code == 200
        assert resp.json()["adapters"] == []

    @pytest.mark.asyncio
    async def test_create_payment_adapter_requires_fields_when_enabled(self, admin_client: AsyncClient, mock_db: AsyncMock):
        resp = await admin_client.post(
            "/api/admin/payment-adapters",
            json={
                "adapter_type": "epay",
                "display_name": "EPay Main",
                "enabled": True,
                "config": {"url": "", "pid": "", "key": ""},
            },
        )

        assert resp.status_code == 400
        assert "requires url, pid and key" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_payment_adapter_keeps_existing_key(self, admin_client: AsyncClient, mock_db: AsyncMock):
        existing = SimpleNamespace(
            id="adapter-1",
            adapter_type="epay",
            display_name="EPay Main",
            enabled=True,
            sort_order=0,
            config={
                "url": "https://pay.example.com",
                "pid": "10001",
                "key": "secret-key",
                "payment_types": ["alipay"],
                "notify_url": "",
                "return_url": "",
            },
            created_at=None,
            updated_at=None,
        )
        mock_db.execute.return_value = _scalar_one_or_none(existing)

        resp = await admin_client.put(
            "/api/admin/payment-adapters/adapter-1",
            json={
                "config": {
                    "url": "https://pay.example.com",
                    "pid": "10001",
                    "key": "",
                    "payment_types": ["alipay", "wxpay"],
                },
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert body["config"]["has_key"] is True
        assert body["config"]["payment_types"] == ["alipay", "wxpay"]

