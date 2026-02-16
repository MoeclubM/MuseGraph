"""
Shared pytest fixtures for MuseGraph server-py test suite.

All database and Redis interactions are mocked so tests run
without any real infrastructure.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Patch heavy / side-effect-laden modules BEFORE importing the application.
# This prevents real connections to PostgreSQL, Redis, MinIO, Cognee, etc.
# ---------------------------------------------------------------------------

# 1. Patch storage (MinIO) so ensure_bucket() is a no-op
_storage_mock = MagicMock()
_storage_mock.ensure_bucket = MagicMock()

# 2. Patch redis module-level client
_redis_mock = AsyncMock()
_redis_mock.get = AsyncMock(return_value=None)
_redis_mock.set = AsyncMock()
_redis_mock.delete = AsyncMock()

with (
    patch.dict("sys.modules", {"app.services.cognee": MagicMock()}),
    patch("app.storage.ensure_bucket", _storage_mock.ensure_bucket),
    patch("app.storage.minio_client", MagicMock()),
    patch("app.redis.redis_client", _redis_mock),
    patch("app.redis.get_redis", AsyncMock(return_value=_redis_mock)),
):
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Fake user object that mimics the SQLAlchemy User model
# ---------------------------------------------------------------------------

TEST_USER_ID = str(uuid.uuid4())
TEST_USER_EMAIL = "test@example.com"
TEST_USER_USERNAME = "testuser"


class FakeUser:
    """Lightweight stand-in for ``app.models.user.User``."""

    def __init__(
        self,
        *,
        id: str = TEST_USER_ID,
        email: str = TEST_USER_EMAIL,
        username: str = TEST_USER_USERNAME,
        nickname: str = "Test User",
        avatar: str | None = None,
        balance: Decimal = Decimal("100.0000"),
        role: str = "USER",
        group_id: str | None = None,
        status: str = "ACTIVE",
        password_hash: str = "hashed",
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.id = id
        self.email = email
        self.username = username
        self.nickname = nickname
        self.avatar = avatar
        self.balance = balance
        self.role = role
        self.group_id = group_id
        self.status = status
        self.password_hash = password_hash
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_user() -> FakeUser:
    """Return a default test user."""
    return FakeUser()


@pytest.fixture()
def fake_admin_user() -> FakeUser:
    """Return a test user with ADMIN role."""
    return FakeUser(
        id=str(uuid.uuid4()),
        email="admin@example.com",
        username="adminuser",
        nickname="Admin",
        role="ADMIN",
    )


@pytest.fixture()
def mock_db() -> AsyncMock:
    """
    An ``AsyncMock`` that stands in for ``AsyncSession``.

    Individual tests can configure ``mock_db.execute.return_value`` etc.
    to control what the "database" returns.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.delete = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture()
def mock_redis() -> AsyncMock:
    """Return the module-level mocked Redis client."""
    return _redis_mock


@pytest.fixture()
def override_deps(mock_db: AsyncMock, fake_user: FakeUser):
    """
    Override FastAPI dependencies so that:
    - ``get_db`` yields the mock session
    - ``get_current_user`` returns the fake user
    """

    async def _override_get_db():
        yield mock_db

    async def _override_get_current_user():
        return fake_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def override_deps_admin(mock_db: AsyncMock, fake_admin_user: FakeUser):
    """Same as ``override_deps`` but the current user is an admin."""

    async def _override_get_db():
        yield mock_db

    async def _override_get_current_user():
        return fake_admin_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
async def client(override_deps) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated async HTTP client (regular user)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture()
async def admin_client(override_deps_admin) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated async HTTP client (admin user)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture()
async def unauthed_client() -> AsyncGenerator[AsyncClient, None]:
    """
    HTTP client with NO dependency overrides — useful for testing
    endpoints that do their own auth (register / login).
    """
    app.dependency_overrides.clear()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
