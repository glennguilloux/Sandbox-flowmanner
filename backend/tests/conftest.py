"""Fixtures for integration tests.

Creates a minimal FastAPI app (no lifespan) with swarm, swarm protocol,
and dashboard routes assembled under the correct prefix hierarchy.

Also provides global sys.modules mocking (redis, stripe, portalocker) and
lifespan/rate-limiting patches so that tests copied from app/tests/ can
import app.main_fastapi and use TestClient(app) without real services.
"""

import os
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# 1. Set ALL env vars BEFORE any imports
# ---------------------------------------------------------------------------
os.environ["OPENAI_API_KEY"] = "***"
os.environ["LANGFUSE_PUBLIC_KEY"] = "test-public-key"
os.environ["LANGFUSE_SECRET_KEY"] = "test-secret-key"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-123"
os.environ["SECRET_KEY"] = "test-secret-key-123"
os.environ["AES_ENCRYPTION_KEY"] = "test-aes-key-16-char"
os.environ["APP_ENV"] = "test"
os.environ["LANGFUSE_ENABLED"] = "false"
os.environ["USE_NEW_READS"] = "0"

# ---------------------------------------------------------------------------
# 2. Mock redis globally BEFORE any imports that use it
# ---------------------------------------------------------------------------
mock_redis = MagicMock()
mock_redis.from_url = MagicMock(return_value=MagicMock())
mock_redis.ConnectionError = ConnectionError
mock_redis.asyncio = MagicMock()
mock_redis.asyncio.Redis = MagicMock()
mock_redis.asyncio.Redis.from_url = MagicMock(return_value=MagicMock())
sys.modules["redis"] = mock_redis
sys.modules["redis.asyncio"] = mock_redis.asyncio

# ---------------------------------------------------------------------------
# 2b. Mock portalocker globally (prevents SyntaxError from redis mock
#     leaking into portalocker/redis.py type annotations)
# ---------------------------------------------------------------------------
mock_portalocker = MagicMock()
sys.modules["portalocker"] = mock_portalocker
sys.modules["portalocker.redis"] = mock_portalocker.redis
sys.modules["portalocker.utils"] = mock_portalocker.utils

# ---------------------------------------------------------------------------
# 3. Mock stripe globally so partner.py can be imported without stripe installed
# ---------------------------------------------------------------------------
mock_stripe = MagicMock()
mock_stripe.Transfer = MagicMock()
sys.modules["stripe"] = mock_stripe

# ---------------------------------------------------------------------------
# 4. Mock lifespan BEFORE importing app
# ---------------------------------------------------------------------------
import app.lifespan as lifespan_module


@asynccontextmanager
async def mock_lifespan(app_instance):
    yield


lifespan_module.lifespan = mock_lifespan
lifespan_module._validate_production_secrets = lambda: None

# ---------------------------------------------------------------------------
# 5. Disable production secret validation & rate limiting
# ---------------------------------------------------------------------------
import app.api.middleware.rate_limit as rl_module


async def _noop_dispatch(self, request, call_next):
    """Pass-through dispatch — rate limiting disabled for tests."""
    return await call_next(request)


rl_module.GlobalRateLimitMiddleware.dispatch = _noop_dispatch

# ---------------------------------------------------------------------------
# 6. Now safe to import FastAPI app and routers
# ---------------------------------------------------------------------------
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRouter
from fastapi.testclient import TestClient

from app.main_fastapi import (
    app as _real_app,
)  # noqa: F401 — side-effect: init app with mocked services
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.swarm import router as swarm_router
from app.api.v1.swarm_protocol import router as protocol_router


# ===========================================================================
# Original fixtures (minimal app for swarm/dashboard tests)
# ===========================================================================


@pytest.fixture(scope="session")
def test_app():
    """Minimal FastAPI app — no lifespan, no external service connections.

    Assembles the same prefix hierarchy as the real app:
        /api → /swarm → [execute, list, {id}]
        /api → /swarm → /protocol → [debate, handoff, escalation]
        /api → /dashboard → [analytics, firefighting-metrics, stats]
    """
    app = FastAPI()

    api_router = APIRouter(prefix="/api")
    api_router.include_router(swarm_router)
    api_router.include_router(protocol_router, prefix="/swarm")
    api_router.include_router(dashboard_router)
    app.include_router(api_router)

    return app


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def mock_user():
    """Mock authenticated user with default attributes."""
    return MagicMock(
        id=1,
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        is_active=True,
        is_admin=True,
        is_superuser=False,
        role="admin",
        avatar_url=None,
        totp_enabled=False,
        totp_secret=None,
        totp_backup_codes=None,
        tenant_id=None,
        hashed_password="$2b$...",
        login_count=5,
        last_login_at=None,
        created_at="2026-01-01T00:00:00Z",
        onboarding_step=None,
        onboarding_completed=False,
    )


@pytest.fixture
def test_client(test_app, mock_db, mock_user):
    """TestClient with get_db and get_current_user overridden."""
    from app.api.deps import get_current_user
    from app.database import get_db

    async def override_get_db():
        yield mock_db

    async def override_get_current_user():
        return mock_user

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth v3 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db_session():
    """Alias for mock_db — used by v3 integration tests."""
    session = AsyncMock()
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
def sample_user():
    """Mock user with all v3-accessible attributes."""
    from datetime import datetime, timezone

    return MagicMock(
        id=1,
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        role="pro",
        is_admin=False,
        is_superuser=False,
        is_active=True,
        avatar_url=None,
        totp_enabled=False,
        totp_secret=None,
        totp_backup_codes=None,
        tenant_id=None,
        hashed_password="$2b$...",
        login_count=5,
        last_login_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        onboarding_step=None,
        onboarding_completed=False,
    )


@pytest.fixture(scope="session")
def v3_test_app():
    """Minimal FastAPI app with v3 routes registered."""
    from app.api.v3 import api_v3_router
    from app.api.v3.middleware import register_v3_exception_handlers

    app = FastAPI()
    register_v3_exception_handlers(app)
    app.include_router(api_v3_router)
    return app


@pytest.fixture
def v3_client(v3_test_app, mock_db_session, sample_user):
    """TestClient for v3 endpoints with dependencies overridden."""
    from app.api.deps import get_current_user
    from app.database import get_db

    async def override_get_db():
        yield mock_db_session

    async def override_get_current_user():
        return sample_user

    v3_test_app.dependency_overrides[get_db] = override_get_db
    v3_test_app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(v3_test_app) as client:
        yield client

    v3_test_app.dependency_overrides.clear()
