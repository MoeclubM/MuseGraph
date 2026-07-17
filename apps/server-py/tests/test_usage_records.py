"""Usage detail APIs, retention config, and cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.services.usage_retention import (
    default_usage_retention_config,
    enforce_usage_retention,
    normalize_usage_retention_config,
    upsert_usage_retention_config,
)


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalar(value):
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _one(row):
    result = MagicMock()
    result.one.return_value = row
    return result


class TestUsageRetentionConfig:
    def test_normalize_empty_means_unlimited(self):
        cfg = normalize_usage_retention_config({})
        assert cfg == default_usage_retention_config()

    def test_normalize_positive_ints(self):
        cfg = normalize_usage_retention_config({"retention_days": 30, "max_records": 10000})
        assert cfg["retention_days"] == 30
        assert cfg["max_records"] == 10000


@pytest.mark.asyncio
async def test_enforce_retention_deletes_by_age(mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch):
    delete_result = MagicMock()
    delete_result.rowcount = 3
    mock_db.execute = AsyncMock(side_effect=[delete_result])
    mock_db.flush = AsyncMock()

    monkeypatch.setattr(
        "app.services.usage_retention.get_usage_retention_config",
        AsyncMock(return_value={"retention_days": 7, "max_records": None}),
    )
    stats = await enforce_usage_retention(mock_db)

    assert stats["deleted_by_age"] == 3
    assert stats["deleted_by_count"] == 0


@pytest.mark.asyncio
async def test_get_my_usage_details(client: AsyncClient, mock_db: AsyncMock, fake_user):
    from tests.conftest import TEST_USER_ID

    now = datetime.now(timezone.utc)
    usage = SimpleNamespace(
        id="u1",
        user_id=TEST_USER_ID,
        project_id="p1",
        operation_id=None,
        model="gpt-test",
        provider="openai",
        input_tokens=10,
        output_tokens=20,
        cost=Decimal("0.001"),
        billing_mode="TOKEN",
        request_id="req-1",
        status="SUCCESS",
        source="llm",
        metadata_json=None,
        created_at=now,
    )
    list_result = MagicMock()
    list_result.all.return_value = [(usage, fake_user.email, fake_user.nickname, "My Project")]
    count_result = _scalar(1)

    mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

    resp = await client.get("/api/users/me/usage/details?page=1&page_size=20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["records"]) == 1
    assert body["records"][0]["model"] == "gpt-test"
    assert body["records"][0]["project_title"] == "My Project"


@pytest.mark.asyncio
async def test_admin_usage_records_list(admin_client: AsyncClient, mock_db: AsyncMock):
    mock_db.execute = AsyncMock(
        side_effect=[
            _scalar(0),
            MagicMock(all=MagicMock(return_value=[])),
        ]
    )

    resp = await admin_client.get("/api/admin/usage-records")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_upsert_retention_via_service(mock_db: AsyncMock):
    mock_db.execute = AsyncMock(return_value=_scalar_one_or_none(None))
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()

    cfg = await upsert_usage_retention_config(mock_db, {"retention_days": 90, "max_records": 500000})
    assert cfg["retention_days"] == 90
    assert cfg["max_records"] == 500000

