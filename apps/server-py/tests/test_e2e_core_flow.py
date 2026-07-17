"""Core end-to-end API flow tests aligned with current product scope."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from tests.conftest import get_endpoint_globals


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _chapter(chapter_id: str, content: str):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=chapter_id,
        project_id="11111111-1111-4111-8111-111111111111",
        title="Main Draft",
        content=content,
        status="draft",
        blueprint=None,
        plan=None,
        summary=None,
        continuity_notes=None,
        order_index=0,
        created_at=now,
        updated_at=now,
    )


class TestE2EMemoryTaskFlow:
    @pytest.mark.asyncio
    async def test_memory_ontology_task_create_and_list(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        from app.services.task_state import task_manager

        task_manager.cleanup_old_tasks(max_age_hours=0)
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            chapters=[_chapter("ch-1", "hello world")],
            memory_id="dataset-1",
            ontology_schema={},
        )
        g = get_endpoint_globals("generate_project_ontology_task")

        def _fake_start_project_task(task_type, project_id, user_id, metadata, worker):
            task = task_manager.create_task(
                task_type,
                metadata={
                    **(metadata or {}),
                    "project_id": project_id,
                    "user_id": user_id,
                },
            )
            return g["MemoryTaskStartResponse"](status="ok", task=g["_task_to_schema"](task))

        mock_db.execute.return_value = _scalar_one_or_none(project)
        orig_start = g["_start_project_task"]
        g["_start_project_task"] = _fake_start_project_task
        try:
            start_resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/memory/ontology/generate/task",
                json={"text": "chapter text", "model": "MiniMax-M2.5"},
            )
        finally:
            g["_start_project_task"] = orig_start

        assert start_resp.status_code == 200
        task_id = start_resp.json()["task"]["task_id"]

        mock_db.execute.return_value = _scalar_one_or_none(project)
        list_resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/memory/tasks")
        assert list_resp.status_code == 200
        task_ids = [item["task_id"] for item in list_resp.json()["tasks"]]
        assert task_id in task_ids


class TestE2EPaymentFlow:
    @pytest.mark.asyncio
    async def test_recharge_create_callback_query(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        epay_config = SimpleNamespace(
            id="epay-1",
            adapter_type="epay",
            enabled=True,
            config={
                "url": "https://pay.example.com",
                "pid": "10001",
                "key": "secret-key",
                "payment_types": ["alipay"],
            },
        )
        mock_db.execute.return_value = _scalar_one_or_none(epay_config)
        create_resp = await client.post(
            "/api/payment/create",
            json={
                "type": "RECHARGE",
                "amount": 18.5,
                "payment_adapter_id": "epay-1",
                "payment_method": "alipay",
            },
        )
        assert create_resp.status_code == 200
        order_no = create_resp.json()["order_no"]

        callback_globals = get_endpoint_globals("payment_callback")
        fake_order = SimpleNamespace(order_no=order_no)
        mock_cb = AsyncMock(return_value=fake_order)
        orig_cb = callback_globals["process_payment_callback"]
        callback_globals["process_payment_callback"] = mock_cb
        try:
            cb_resp = await client.get(
                "/api/payment/callback",
                params={"order_no": order_no, "payment_id": "PAY-OK-1"},
            )
        finally:
            callback_globals["process_payment_callback"] = orig_cb
        assert cb_resp.status_code == 200
        assert cb_resp.json()["order_no"] == order_no

        queried_order = SimpleNamespace(
            order_no=order_no,
            user_id=fake_user.id,
            type="RECHARGE",
            amount=Decimal("18.50"),
            status="PENDING",
            payment_adapter_id="epay-1",
            payment_method="alipay",
            paid_at=None,
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(queried_order)
        query_resp = await client.get(f"/api/payment/order/{order_no}")
        assert query_resp.status_code == 200
        assert query_resp.json()["order_no"] == order_no
