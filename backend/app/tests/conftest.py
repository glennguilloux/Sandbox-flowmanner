import os
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

# 1. Set ALL env vars BEFORE any imports
os.environ["OPENAI_API_KEY"] = "***"
os.environ["LANGFUSE_PUBLIC_KEY"] = "test-public-key"
os.environ["LANGFUSE_SECRET_KEY"] = "test-secret-key"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-123"
os.environ["AES_ENCRYPTION_KEY"] = "test-aes-key-16-char"
os.environ["APP_ENV"] = "test"
os.environ["LANGFUSE_ENABLED"] = "false"
os.environ["USE_NEW_READS"] = "0"

# 1b. Remove shell env overrides of config defaults
# Single source of truth: ``tests._env_guard.pop_config_overrides``.
# See that module for the full rationale and the canonical list of
# popped env vars. Both this conftest and ``backend/tests/conftest.py``
# call ``pop_config_overrides()`` to keep the guard logic in one place.
import socket as _socket

_real_db_url = os.environ.get("DATABASE_URL")

from app.testing._env_guard import pop_config_overrides

pop_config_overrides()

# If running inside Docker with a reachable PostgreSQL, restore DATABASE_URL
# so that _pg.py integration tests can connect to the real database.
try:
    with _socket.create_connection(("workflow-postgres", 5432), timeout=2):
        if _real_db_url:
            os.environ["DATABASE_URL"] = _real_db_url
except (OSError, TimeoutError):
    pass  # Not in Docker — _pg.py tests will be auto-skipped

# 2. Mock redis globally BEFORE any imports that use it
#    This ensures auth_rate_limiter falls back to InMemoryRateLimiter
#    NOTE: Redis.from_url must NOT raise at module-import time (dashboard_service.py
#    calls it at module level). Instead it returns a mock that fails on actual usage.
mock_redis = MagicMock()
mock_redis.from_url = MagicMock(return_value=MagicMock())
mock_redis.ConnectionError = ConnectionError
# Support lazy imports like "from redis.asyncio import Redis"
mock_redis.asyncio = MagicMock()
mock_redis.asyncio.Redis = MagicMock()
mock_redis.asyncio.Redis.from_url = MagicMock(return_value=MagicMock())
sys.modules["redis"] = mock_redis
sys.modules["redis.asyncio"] = mock_redis.asyncio

# 2b. Mock portalocker globally so portalocker/redis.py is never evaluated.
#     portalocker/redis.py subclasses redis.client.PubSubWorkerThread and uses it
#     in a type annotation (typing.Optional[PubSubWorkerThread]).  Since redis is
#     mocked above, that inheritance produces a MagicMock which then blows up
#     typing.ForwardRef with SyntaxError: "Forward reference must be an expression".
mock_portalocker = MagicMock()
sys.modules["portalocker"] = mock_portalocker
sys.modules["portalocker.redis"] = mock_portalocker.redis
sys.modules["portalocker.utils"] = mock_portalocker.utils

# 3. Mock stripe globally so partner.py can be imported without stripe installed
mock_stripe = MagicMock()
mock_stripe.Transfer = MagicMock()
sys.modules["stripe"] = mock_stripe

# 4. Mock lifespan BEFORE importing app
import app.lifespan as lifespan_module


@asynccontextmanager
async def mock_lifespan(app_instance):
    yield


# Replace lifespan in module (affects subsequent import of main_fastapi)
lifespan_module.lifespan = mock_lifespan

# 5. Disable production secret validation
lifespan_module._validate_production_secrets = lambda: None

# 6. Patch GlobalRateLimitMiddleware to be a no-op BEFORE app import
#    This prevents tests from getting 429 rate-limited
import app.api.middleware.rate_limit as rl_module

_original_dispatch = rl_module.GlobalRateLimitMiddleware.dispatch


async def _noop_dispatch(self, request, call_next):
    """Pass-through dispatch — rate limiting disabled for tests."""
    return await call_next(request)


rl_module.GlobalRateLimitMiddleware.dispatch = _noop_dispatch

# 7. Now import FastAPI app (uses mocked lifespan, rate limiter, redis, stripe)
# 8. Test fixtures
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.database import get_db_session
from app.main_fastapi import app


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    # CRITICAL: session.execute must return a plain MagicMock, NOT an AsyncMock.
    # If execute returns an AsyncMock, then .scalar_one_or_none() on its result
    # returns a coroutine (AsyncMock methods are async by default), which escapes
    # as the return value of any "await session.execute()" → breaks testing.
    # We use an AsyncMock with return_value=MagicMock() so tests CAN set
    # execute.side_effect = [result1, result2] to control per-query results.
    execute_mock = AsyncMock()
    execute_mock.return_value = MagicMock()
    session.execute = execute_mock
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def db_session(mock_db_session):
    """Alias for tests that request ``db_session`` instead of ``mock_db_session``."""
    return mock_db_session


@pytest.fixture
def sample_user():
    """Standard test user as SimpleNamespace (supports attribute access)."""
    return SimpleNamespace(
        id=1,
        email="test@example.com",
        username="testuser",
        is_active=True,
        role="user",
        is_admin=False,
        is_superuser=False,
        tenant_id=1,
        is_partner_admin=False,
        partner_id=None,
    )


@pytest.fixture
def test_client(mock_db_session):
    async def override_get_db():
        yield mock_db_session

    async def override_get_db_session():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_db_session, None)
