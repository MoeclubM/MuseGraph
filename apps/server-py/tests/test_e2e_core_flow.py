"""Core end-to-end API flow tests aligned with current product scope."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _get_endpoint_globals(app, endpoint_name: str) -> dict:
    for route in app.routes:
        if hasattr(route, "endpoint") and getattr(route, "name", "") == endpoint_name:
            return route.endpoint.__globals__
        if hasattr(route, "routes"):
            for sub in route.routes:
                if hasattr(sub, "endpoint") and getattr(sub, "name", "") == endpoint_name:
                    return sub.endpoint.__globals__
    raise RuntimeError(f"Endpoint {endpoint_name!r} not found")


def _prepared_package(g: dict, provenance: dict, *, profile_name: str = "Agent1") -> dict:
    return g["_inject_provenance"](
        {
            "profiles": [
                {
                    "name": profile_name,
                    "role": "participant",
                    "persona": "Tracks narrative shifts",
                    "stance": "neutral",
                    "likely_actions": ["Track developments"],
                }
            ],
            "simulation_config": {
                "time_config": {
                    "total_hours": 24,
                    "minutes_per_round": 60,
                    "peak_hours": [19, 20],
                    "off_peak_hours": [1, 2],
                },
                "events": [{"title": "Kickoff", "trigger_hour": 1, "description": "Start"}],
                "agent_activity": [
                    {
                        "name": profile_name,
                        "activity_level": 0.6,
                        "actions_per_hour": 1.0,
                        "response_delay_minutes": 30,
                        "stance": "neutral",
                    }
                ],
            },
        },
        provenance,
    )


def _chapter(chapter_id: str, content: str):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=chapter_id,
        project_id="11111111-1111-4111-8111-111111111111",
        title="Main Draft",
        content=content,
        order_index=0,
        created_at=now,
        updated_at=now,
    )


class TestE2EGraphTaskFlow:
    @pytest.mark.asyncio
    async def test_graph_ontology_task_create_and_list(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        from app.services.task_state import task_manager
        from tests.conftest import app

        task_manager.cleanup_old_tasks(max_age_hours=0)
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            chapters=[_chapter("ch-1", "hello world")],
            graph_id="dataset-1",
            ontology_schema={},
        )
        g = _get_endpoint_globals(app, "generate_project_ontology_task")

        def _fake_start_project_task(task_type, project_id, user_id, metadata, worker):
            task = task_manager.create_task(
                task_type,
                metadata={
                    **(metadata or {}),
                    "project_id": project_id,
                    "user_id": user_id,
                },
            )
            return g["GraphTaskStartResponse"](status="ok", task=g["_task_to_schema"](task))

        mock_db.execute.return_value = _scalar_one_or_none(project)
        orig_start = g["_start_project_task"]
        g["_start_project_task"] = _fake_start_project_task
        try:
            start_resp = await client.post(
                "/api/projects/11111111-1111-4111-8111-111111111111/graphs/ontology/generate/task",
                json={"text": "chapter text", "model": "MiniMax-M2.5"},
            )
        finally:
            g["_start_project_task"] = orig_start

        assert start_resp.status_code == 200
        task_id = start_resp.json()["task"]["task_id"]

        mock_db.execute.return_value = _scalar_one_or_none(project)
        list_resp = await client.get("/api/projects/11111111-1111-4111-8111-111111111111/graphs/tasks")
        assert list_resp.status_code == 200
        task_ids = [item["task_id"] for item in list_resp.json()["tasks"]]
        assert task_id in task_ids


class TestE2EPaymentFlow:
    @pytest.mark.asyncio
    async def test_recharge_create_callback_query(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        from tests.conftest import app

        epay_config = SimpleNamespace(
            id="epay-1",
            type="epay",
            is_active=True,
            config={
                "url": "https://pay.example.com",
                "pid": "10001",
                "key": "secret-key",
                "payment_type": "alipay",
            },
        )
        mock_db.execute.return_value = _scalar_one_or_none(epay_config)
        create_resp = await client.post(
            "/api/payment/create",
            json={"type": "RECHARGE", "amount": 18.5, "payment_method": "alipay"},
        )
        assert create_resp.status_code == 200
        order_no = create_resp.json()["order_no"]

        callback_globals = _get_endpoint_globals(app, "payment_callback")
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
            payment_method="alipay",
            paid_at=None,
            created_at=datetime.now(timezone.utc),
        )
        mock_db.execute.return_value = _scalar_one_or_none(queried_order)
        query_resp = await client.get(f"/api/payment/order/{order_no}")
        assert query_resp.status_code == 200
        assert query_resp.json()["order_no"] == order_no


class TestE2ESimulationFlow:
    @pytest.mark.asyncio
    async def test_simulation_start_then_get_run_status(self, client: AsyncClient, mock_db: AsyncMock, fake_user):
        from tests.conftest import app

        sim = SimpleNamespace(
            simulation_id="sim-e2e-1",
            project_id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            status="ready",
            profiles=[{"name": "Agent1"}],
            simulation_config={},
            run_state={},
            posts=[],
            comments=[],
            actions=[],
            env_status={},
            metadata_={},
        )
        project = SimpleNamespace(
            id="11111111-1111-4111-8111-111111111111",
            user_id=fake_user.id,
            title="E2E Project",
            simulation_requirement="Focus on consistency",
            oasis_analysis={},
            ontology_schema={},
            component_models=None,
            chapters=[_chapter("ch-1", "Some content")],
        )
        g = _get_endpoint_globals(app, "start_simulation")
        expected_provenance = g["_build_provenance"](source_chapter_ids=[], text="Some content")
        package = _prepared_package(g, expected_provenance)
        mock_refresh = AsyncMock(return_value={"latest_package": package})
        mock_build = AsyncMock(
            return_value=(
                {"metrics": {"total_rounds": 3}},
                [{"action_id": "a1"}],
            )
        )

        mock_db.execute.side_effect = [
            _scalar_one_or_none(sim),
            _scalar_one_or_none(project),
        ]
        orig_refresh = g["_refresh_project_analysis_with_provenance"]
        orig_build = g["_build_run_artifacts_with_llm"]
        g["_refresh_project_analysis_with_provenance"] = mock_refresh
        g["_build_run_artifacts_with_llm"] = mock_build
        try:
            start_resp = await client.post(
                "/api/simulation/start",
                json={"simulation_id": "sim-e2e-1"},
            )
        finally:
            g["_refresh_project_analysis_with_provenance"] = orig_refresh
            g["_build_run_artifacts_with_llm"] = orig_build

        assert start_resp.status_code == 200
        assert start_resp.json()["data"]["status"] == "completed"

        mock_db.execute.side_effect = None
        mock_db.execute.return_value = _scalar_one_or_none(sim)
        status_resp = await client.get("/api/simulation/sim-e2e-1/run-status")
        assert status_resp.status_code == 200
        assert status_resp.json()["data"]["status"] == "completed"


