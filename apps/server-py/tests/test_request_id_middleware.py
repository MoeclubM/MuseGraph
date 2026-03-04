from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_sets_request_id_header_when_missing():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.headers.get("X-Request-Id")


@pytest.mark.asyncio
async def test_health_preserves_request_id_header_when_provided():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health", headers={"X-Request-Id": "req-123"})

    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == "req-123"
