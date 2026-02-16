"""Tests for authentication endpoints: /api/auth/*"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.auth import hash_password
from tests.conftest import FakeUser, app, get_db, get_current_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scalar_result(value):
    """Wrap a value so that ``result.scalar_one_or_none()`` returns it."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_scalars_first_result(value):
    result = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = value
    result.scalars.return_value = scalars
    return result


# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------


class TestRegister:
    """Registration endpoint tests."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Clear dependency overrides before each test."""
        app.dependency_overrides.clear()
        yield
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_register_success(self):
        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()
        now = datetime.now(timezone.utc)

        def _side_effect_add(obj):
            if hasattr(obj, "email") and hasattr(obj, "username"):
                obj.id = obj.id or "user-test-id"
                obj.balance = obj.balance or Decimal("0")
                obj.role = obj.role or "USER"
                obj.status = obj.status or "ACTIVE"
                obj.created_at = obj.created_at or now
            elif hasattr(obj, "token") and hasattr(obj, "expires_at"):
                obj.id = obj.id or "session-test-id"
                obj.created_at = obj.created_at or now

        mock_db.add = MagicMock(side_effect=_side_effect_add)
        mock_db.execute = AsyncMock(
            side_effect=[
                _make_scalar_result(None),  # no existing user
                _make_scalars_first_result(None),  # no default group
            ]
        )

        async def _override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/auth/register", json={
                "email": "new@example.com",
                "username": "newuser",
                "password": "securepass123",
            })

        assert resp.status_code == 201
        body = resp.json()
        assert isinstance(body["token"], str) and len(body["token"]) >= 32
        assert body["user"]["email"] == "new@example.com"
        assert body["user"]["username"] == "newuser"

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()
        existing = FakeUser(email="dup@example.com", username="other")
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(existing))

        async def _override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/auth/register", json={
                "email": "dup@example.com",
                "username": "dupuser",
                "password": "securepass123",
            })

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    """Login endpoint tests."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        app.dependency_overrides.clear()
        yield
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_login_success(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        user = FakeUser(
            email="login@example.com",
            username="loginuser",
            password_hash=hash_password("correctpassword"),
            status="ACTIVE",
        )
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(user))

        async def _override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/auth/login", json={
                "email": "login@example.com",
                "password": "correctpassword",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["token"], str) and len(body["token"]) >= 32
        assert body["user"]["email"] == "login@example.com"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self):
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        user = FakeUser(email="login@example.com", password_hash=hash_password("correctpassword"))
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(user))

        async def _override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = _override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/api/auth/login", json={
                "email": "login@example.com",
                "password": "wrongpassword",
            })

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------


class TestLogout:
    """Logout endpoint tests."""

    @pytest.mark.asyncio
    async def test_logout(self, client: AsyncClient, mock_db: AsyncMock):
        mock_db.execute = AsyncMock(return_value=_make_scalar_result(None))
        resp = await client.post(
            "/api/auth/logout",
            headers={"Authorization": "Bearer some-token"},
        )

        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------


class TestMe:
    """Current-user endpoint tests."""

    @pytest.mark.asyncio
    async def test_get_me(self, client: AsyncClient, fake_user: FakeUser):
        resp = await client.get("/api/auth/me")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == fake_user.id
        assert body["email"] == fake_user.email
        assert body["username"] == fake_user.username
        assert body["role"] == "USER"
