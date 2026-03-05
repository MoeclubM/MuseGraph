from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


def _scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all(values):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
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


@pytest.fixture()
def _create_operation_globals():
    from tests.conftest import app

    return _get_endpoint_globals(app, "create_operation")


@pytest.mark.asyncio
async def test_list_project_characters(client: AsyncClient, mock_db: AsyncMock, fake_user):
    now = datetime.now(timezone.utc)
    project = SimpleNamespace(
        id="proj-1",
        user_id=fake_user.id,
        characters=[
            SimpleNamespace(
                id="char-2",
                project_id="proj-1",
                name="Beta",
                role="support",
                profile=None,
                notes=None,
                order_index=1,
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id="char-1",
                project_id="proj-1",
                name="Alpha",
                role="lead",
                profile="hero",
                notes="main",
                order_index=0,
                created_at=now,
                updated_at=now,
            ),
        ],
    )
    mock_db.execute.return_value = _scalar_one_or_none(project)

    resp = await client.get("/api/projects/proj-1/characters")
    assert resp.status_code == 200
    data = resp.json()
    assert [item["id"] for item in data] == ["char-1", "char-2"]


@pytest.mark.asyncio
async def test_create_operation_includes_character_context(
    client: AsyncClient,
    mock_db: AsyncMock,
    fake_user,
    _create_operation_globals: dict,
):
    project = SimpleNamespace(
        id="proj-1",
        user_id=fake_user.id,
        chapters=[],
        characters=[],
        component_models={},
        cognee_dataset_id=None,
    )
    character = SimpleNamespace(
        id="char-1",
        project_id="proj-1",
        name="林默",
        role="主角",
        profile="理性、克制，善于推理",
        notes="对旧案有执念",
        order_index=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    op = SimpleNamespace(
        id="op-1",
        project_id="proj-1",
        type="CREATE",
        input="prompt",
        output="result",
        model="MiniMax-M2.5",
        input_tokens=10,
        output_tokens=20,
        cost=0.001,
        status="COMPLETED",
        error=None,
        progress=100,
        message="Done",
        metadata_={"source_character_ids": ["char-1"]},
        created_at=datetime.now(timezone.utc),
    )

    mock_db.execute.side_effect = [
        _scalar_one_or_none(project),
        _scalars_all([character]),
    ]
    mock_db.flush = AsyncMock()

    mock_run = AsyncMock(return_value=op)
    orig = _create_operation_globals["run_operation"]
    _create_operation_globals["run_operation"] = mock_run
    try:
        resp = await client.post(
            "/api/projects/proj-1/operation",
            json={
                "type": "CREATE",
                "input": "write",
                "character_ids": ["char-1"],
                "use_rag": False,
            },
        )
    finally:
        _create_operation_globals["run_operation"] = orig

    assert resp.status_code == 200
    kwargs = mock_run.await_args.kwargs
    assert "林默" in kwargs["character_context"]
    assert kwargs["reference_cards"]["characters"][0]["name"] == "林默"
    assert kwargs["use_rag"] is False

    added_operation = mock_db.add.call_args.args[0]
    assert added_operation.metadata_ == {"source_character_ids": ["char-1"]}


@pytest.mark.asyncio
async def test_create_operation_rejects_invalid_character_ids(
    client: AsyncClient,
    mock_db: AsyncMock,
    fake_user,
):
    project = SimpleNamespace(
        id="proj-1",
        user_id=fake_user.id,
        chapters=[],
        characters=[],
        component_models={},
        cognee_dataset_id=None,
    )
    mock_db.execute.side_effect = [
        _scalar_one_or_none(project),
        _scalars_all([]),
    ]

    resp = await client.post(
        "/api/projects/proj-1/operation",
        json={
            "type": "CREATE",
            "input": "write",
            "character_ids": ["missing-char"],
        },
    )
    assert resp.status_code == 400
    assert "Invalid character_ids" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_operation_rejects_invalid_glossary_term_ids(
    client: AsyncClient,
    mock_db: AsyncMock,
    fake_user,
):
    project = SimpleNamespace(
        id="proj-1",
        user_id=fake_user.id,
        chapters=[],
        characters=[],
        glossary_terms=[],
        component_models={},
        cognee_dataset_id=None,
    )
    mock_db.execute.side_effect = [
        _scalar_one_or_none(project),
        _scalars_all([]),
    ]

    resp = await client.post(
        "/api/projects/proj-1/operation",
        json={
            "type": "CREATE",
            "input": "write",
            "glossary_term_ids": ["missing-term"],
        },
    )
    assert resp.status_code == 400
    assert "Invalid glossary_term_ids" in resp.json()["detail"]
