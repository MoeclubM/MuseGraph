"""
Shared pytest fixtures for MuseMemory server-py test suite.

All database and Redis interactions are mocked so tests run
without any real infrastructure.
"""

from __future__ import annotations

import uuid
from types import ModuleType
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Patch heavy / side-effect-laden modules BEFORE importing the application.
# This prevents real connections to PostgreSQL, Redis, storage backend, Memory, etc.
# ---------------------------------------------------------------------------

# 1. Patch storage so ensure_bucket() is a no-op
_storage_mock = MagicMock()
_storage_mock.ensure_bucket = MagicMock()
_storage_module = SimpleNamespace(
    ensure_bucket=_storage_mock.ensure_bucket,
    upload_file=MagicMock(return_value="mock-file"),
)

# 2. Patch redis module-level client
_redis_mock = AsyncMock()
_redis_mock.get = AsyncMock(return_value=None)
_redis_mock.set = AsyncMock()
_redis_mock.delete = AsyncMock()
_redis_asyncio_module = ModuleType("redis.asyncio")
_redis_asyncio_module.from_url = MagicMock(return_value=_redis_mock)
_redis_module = ModuleType("redis")
_redis_module.asyncio = _redis_asyncio_module

# NOTE: install the mocks permanently instead of using ``patch.dict`` as a
# context manager. ``patch.dict`` restores ``sys.modules`` to its pre-import
# state on exit, which evicts every module imported transitively by
# ``app.main`` (all ``app.*`` modules, ``dulwich``, ...). Test files would then
# re-import fresh copies, so monkeypatches against the new instances never
# reached the route handlers (stale ``settings``) and cross-instance
# ``isinstance`` checks failed inside dulwich.
import sys  # noqa: E402

sys.modules["redis"] = _redis_module
sys.modules["redis.asyncio"] = _redis_asyncio_module
sys.modules["app.storage"] = _storage_module  # type: ignore[assignment]

from app.database import get_db  # noqa: E402
from app.dependencies import get_current_user  # noqa: E402
from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Fake user object that mimics the SQLAlchemy User model
# ---------------------------------------------------------------------------

TEST_USER_ID = str(uuid.uuid4())
TEST_USER_EMAIL = "test@example.com"


class FakeUser:
    """Lightweight stand-in for ``app.models.user.User``."""

    def __init__(
        self,
        *,
        id: str = TEST_USER_ID,
        email: str = TEST_USER_EMAIL,
        nickname: str = "Test User",
        avatar: str | None = None,
        balance: Decimal = Decimal("100.0000"),
        is_admin: bool = False,
        group_id: str | None = None,
        status: str = "ACTIVE",
        password_hash: str = "hashed",
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.id = id
        self.email = email
        self.nickname = nickname
        self.avatar = avatar
        self.balance = balance
        self.is_admin = is_admin
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
    """Return a test user with admin permission."""
    return FakeUser(
        id=str(uuid.uuid4()),
        email="admin@example.com",
        nickname="Admin",
        is_admin=True,
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


def patch_app_route_globals(monkeypatch: pytest.MonkeyPatch, module_name: str, values: dict[str, object]) -> None:
    for route in iter_app_routes():
        endpoint = getattr(route, "endpoint", None)
        globals_ = getattr(endpoint, "__globals__", {})
        if not isinstance(globals_, dict) or globals_.get("__name__") != module_name:
            continue
        for name, value in values.items():
            if name in globals_:
                monkeypatch.setitem(globals_, name, value)


def iter_app_routes_with_paths():
    pending = [(route, "") for route in app.routes]
    while pending:
        route, parent_prefix = pending.pop(0)
        route_path = str(getattr(route, "path", "") or "")
        yield route, f"{parent_prefix.rstrip('/')}/{route_path.lstrip('/')}" if route_path else parent_prefix
        included_router = getattr(route, "original_router", None)
        include_context = getattr(route, "include_context", None)
        include_prefix = str(getattr(include_context, "prefix", "") or "")
        nested_prefix = f"{parent_prefix.rstrip('/')}/{include_prefix.lstrip('/')}" if include_prefix else parent_prefix
        pending.extend((nested, nested_prefix) for nested in getattr(included_router, "routes", ()))
        pending.extend((nested, parent_prefix) for nested in getattr(route, "routes", ()))


def iter_app_routes():
    for route, _path in iter_app_routes_with_paths():
        yield route


def get_app_endpoint(path: str, method: str):
    method_upper = method.upper()
    for route, route_path in iter_app_routes_with_paths():
        if route_path == path and method_upper in set(getattr(route, "methods", ())):
            return route.endpoint
    raise RuntimeError(f"Route not found: {method_upper} {path}")


def get_endpoint_globals(endpoint_name: str) -> dict:
    for route in iter_app_routes():
        endpoint = getattr(route, "endpoint", None)
        if getattr(route, "name", "") == endpoint_name and endpoint is not None:
            return endpoint.__globals__
    raise RuntimeError(f"Endpoint {endpoint_name!r} not found")


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
