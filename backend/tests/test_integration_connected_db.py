"""
Integration tests for GET /api/integrations/connected — full stack, real database.

Unlike test_integration_connected_api.py (which mocks the DB session), these tests
use the real PostgreSQL database to catch SQLAlchemy query issues, model mismatches,
and column-level problems that mocks can hide.

Requirements:
- PostgreSQL must be running (Docker: workflow-postgres container)
- The app's DATABASE_URL uses Docker hostname "workflow-postgres" — these tests
  override it to "localhost" since they run on the host, not inside a container
- Test data is created and cleaned up within each test

Usage:
    pytest tests/test_integration_connected_db.py -v
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.main_fastapi import app
from app.models.phase4_models import IntegrationConnection
from app.models.user import User
from app.services.integration_bridge import (
    _INTEGRATION_CAPABILITIES,
    _NON_OAUTH_CONFIGS,
)

pytestmark = pytest.mark.integration

# ── Override DATABASE_URL to use localhost ─────────────────────────────────
# The app's settings use Docker hostname "workflow-postgres", but tests run on
# the host.  Swap in "localhost" while keeping the same credentials + db name.

_TEST_DATABASE_URL = settings.DATABASE_URL.replace("workflow-postgres", "localhost")

# NullPool: each async session gets a fresh connection, avoiding asyncpg
# "another operation is in progress" errors from connection reuse across tests.
_test_engine = create_async_engine(_TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


# ── Engine lifecycle ───────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _manage_engine():
    """Dispose the test engine after all tests finish."""
    yield
    await _test_engine.dispose()


# ── Clear non-OAuth env vars between tests ────────────────────────────────
# The endpoint checks LINEAR_API_KEY / DISCORD_BOT_TOKEN globally,
# so without this, every test sees +1 extra entry if they're set in .env.


@pytest.fixture(autouse=True)
def _clear_non_oauth_env(monkeypatch):
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setattr(settings, "LINEAR_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "DISCORD_BOT_TOKEN", "", raising=False)


# ── Skip if database isn't reachable ───────────────────────────────────────


@pytest.fixture(scope="session")
def _check_database():
    """Skip the entire test module if the database isn't reachable."""
    # Use a dedicated event loop to avoid interfering with pytest-asyncio's loop
    loop = asyncio.new_event_loop()
    try:

        async def _ping():
            async with TestSessionLocal() as s:
                await s.execute(text("SELECT 1"))

        loop.run_until_complete(_ping())
    except Exception as e:
        pytest.skip(f"Database not reachable: {e}")
    finally:
        loop.close()


# ── Unique test user ID ────────────────────────────────────────────────────


def _unique_test_id() -> int:
    """Return a unique user ID unlikely to collide with real users."""
    return uuid.uuid4().int % 900_000 + 100_000


# ── Test user + session fixture (single fixture, single session) ───────────


@pytest_asyncio.fixture
async def test_user_and_session():
    """Create a test user in the real DB and yield (user, session) for seeding.

    Cleanup: deletes all IntegrationConnections for this user, then the user.
    """
    user_id = _unique_test_id()
    email = f"test-{user_id}@test-integration-connected.flowmanner.example"

    async with TestSessionLocal() as session:
        user = User(
            id=user_id,
            email=email,
            username=f"test_connected_{user_id}",
            full_name=f"Test Connected User {user_id}",
            hashed_password="test-hash-not-real",
            is_active=True,
            is_admin=False,
            role="free",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        yield user, session

    # Cleanup: delete all connections + the user (separate session)
    async with TestSessionLocal() as cleanup_session:
        await cleanup_session.execute(
            text("DELETE FROM integration_connections WHERE user_id = :uid"),
            {"uid": user_id},
        )
        await cleanup_session.execute(
            text("DELETE FROM users WHERE id = :uid"),
            {"uid": user_id},
        )
        await cleanup_session.commit()


# ── TestClient that uses real DB (localhost) but mocked auth ──────────────


@pytest.fixture
def real_db_client(test_user_and_session):
    """TestClient with DB overridden to use localhost; only auth is faked."""
    test_user, _ = test_user_and_session

    async def override_get_db():
        async with TestSessionLocal() as session:
            yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


# ── Seed helpers ───────────────────────────────────────────────────────────


async def _seed_connection(
    session: AsyncSession,
    *,
    connection_id: str,
    user_id: int,
    slug: str,
    account_name: str | None = None,
    account_id: str | None = None,
    is_active: bool = True,
    access_token: str | None = "encrypted-fake-token",
) -> IntegrationConnection:
    conn = IntegrationConnection(
        id=connection_id,
        user_id=user_id,
        integration_slug=slug,
        account_name=account_name,
        account_id=account_id,
        is_active=is_active,
        encrypted_access_token=access_token,
        created_at=datetime.now(timezone.utc),
    )
    session.add(conn)
    await session.commit()
    await session.refresh(conn)
    return conn


# ── Tests ──────────────────────────────────────────────────────────────────


class TestRealDBEmpty:
    """User with no connections — no OAuth and no non-OAuth env vars."""

    def test_no_connections_returns_empty(self, real_db_client):
        response = real_db_client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] == []
        assert data["total"] == 0


class TestRealDBSingleOAuth:
    """Single OAuth connection seeded in the real DB."""

    @pytest.mark.asyncio
    async def test_slack_connection_returns_correct_structure(
        self, test_user_and_session, real_db_client
    ):
        test_user, session = test_user_and_session
        conn_id = str(uuid.uuid4())
        await _seed_connection(
            session,
            connection_id=conn_id,
            user_id=test_user.id,
            slug="slack",
            account_name="Test Slack Workspace",
            account_id="T99999",
        )

        response = real_db_client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        entry = data["connected"][0]
        assert entry["slug"] == "slack"
        assert entry["name"] == "Slack"
        assert entry["account_name"] == "Test Slack Workspace"
        assert entry["account_id"] == "T99999"
        assert entry["auth_type"] == "oauth2"
        expected_actions = len(_INTEGRATION_CAPABILITIES.get("slack", []))
        assert entry["action_count"] == expected_actions
        assert len(entry["actions"]) == expected_actions

    @pytest.mark.asyncio
    async def test_github_connection_includes_expected_actions(
        self, test_user_and_session, real_db_client
    ):
        test_user, session = test_user_and_session
        conn_id = str(uuid.uuid4())
        await _seed_connection(
            session,
            connection_id=conn_id,
            user_id=test_user.id,
            slug="github",
            account_name="test-org",
        )

        response = real_db_client.get("/api/integrations/connected")

        assert response.status_code == 200
        entry = response.json()["connected"][0]
        action_ids = {a["id"] for a in entry["actions"]}
        assert "create_issue" in action_ids, f"Missing create_issue in {action_ids}"
        assert "create_pr" in action_ids, f"Missing create_pr in {action_ids}"
        assert "search_code" in action_ids, f"Missing search_code in {action_ids}"

    @pytest.mark.asyncio
    async def test_multiple_oauth_connections(
        self, test_user_and_session, real_db_client
    ):
        test_user, session = test_user_and_session
        slack_id = str(uuid.uuid4())
        github_id = str(uuid.uuid4())
        await _seed_connection(
            session,
            connection_id=slack_id,
            user_id=test_user.id,
            slug="slack",
            account_name="Slack WS",
        )
        await _seed_connection(
            session,
            connection_id=github_id,
            user_id=test_user.id,
            slug="github",
            account_name="GH Org",
        )

        response = real_db_client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        slugs = {e["slug"] for e in data["connected"]}
        assert slugs == {"slack", "github"}


class TestRealDBFiltering:
    """Inactive connections should not appear."""

    @pytest.mark.asyncio
    async def test_inactive_connection_is_excluded(
        self, test_user_and_session, real_db_client
    ):
        test_user, session = test_user_and_session
        active_id = str(uuid.uuid4())
        inactive_id = str(uuid.uuid4())

        await _seed_connection(
            session,
            connection_id=active_id,
            user_id=test_user.id,
            slug="slack",
            account_name="Active Slack",
            is_active=True,
        )
        await _seed_connection(
            session,
            connection_id=inactive_id,
            user_id=test_user.id,
            slug="github",
            account_name="Inactive GitHub",
            is_active=False,
        )

        response = real_db_client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["connected"][0]["slug"] == "slack"
        assert data["connected"][0]["account_name"] == "Active Slack"


class TestRealDBNonOAuth:
    """Non-OAuth integrations via env vars (Linear, Discord)."""

    @pytest.mark.asyncio
    async def test_linear_appears_when_api_key_set(
        self, monkeypatch, test_user_and_session, real_db_client
    ):
        monkeypatch.setenv("LINEAR_API_KEY", "real-test-linear-key-integration")
        monkeypatch.setattr(
            settings, "LINEAR_API_KEY", "real-test-linear-key-integration"
        )

        response = real_db_client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        slugs = [e["slug"] for e in data["connected"]]
        assert "linear" in slugs, f"linear missing from {slugs}"
        linear = [e for e in data["connected"] if e["slug"] == "linear"][0]
        assert linear["auth_type"] == "api_key"
        assert linear["account_name"] == _NON_OAUTH_CONFIGS["linear"]["name"]
        assert linear["account_id"] is None
        expected = len(_INTEGRATION_CAPABILITIES.get("linear", []))
        assert linear["action_count"] == expected
        assert len(linear["actions"]) == expected

    @pytest.mark.asyncio
    async def test_discord_appears_when_bot_token_set(
        self, monkeypatch, test_user_and_session, real_db_client
    ):
        monkeypatch.setenv(
            "DISCORD_BOT_TOKEN", "real-test-discord-token-integration"
        )
        monkeypatch.setattr(
            settings, "DISCORD_BOT_TOKEN", "real-test-discord-token-integration"
        )

        response = real_db_client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        slugs = [e["slug"] for e in data["connected"]]
        assert "discord" in slugs, f"discord missing from {slugs}"
        discord = [e for e in data["connected"] if e["slug"] == "discord"][0]
        assert discord["auth_type"] == "bearer_token"
        assert discord["account_id"] is None

    @pytest.mark.asyncio
    async def test_linear_and_oauth_together(
        self, monkeypatch, test_user_and_session, real_db_client
    ):
        test_user, session = test_user_and_session
        monkeypatch.setenv("LINEAR_API_KEY", "real-test-linear-key-mixed")
        monkeypatch.setattr(settings, "LINEAR_API_KEY", "real-test-linear-key-mixed")

        slack_id = str(uuid.uuid4())
        await _seed_connection(
            session,
            connection_id=slack_id,
            user_id=test_user.id,
            slug="slack",
            account_name="Mixed Slack",
        )

        response = real_db_client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        slugs = {e["slug"] for e in data["connected"]}
        assert "slack" in slugs
        assert "linear" in slugs
        assert data["total"] == 2


class TestRealDBUnknownSlug:
    """Integration slugs not in _INTEGRATION_CAPABILITIES get zero actions."""

    @pytest.mark.asyncio
    async def test_unknown_slug_has_empty_actions(
        self, test_user_and_session, real_db_client
    ):
        test_user, session = test_user_and_session
        conn_id = str(uuid.uuid4())
        await _seed_connection(
            session,
            connection_id=conn_id,
            user_id=test_user.id,
            slug="nonexistent-service-xyz",
            account_name="Ghost Service",
        )

        response = real_db_client.get("/api/integrations/connected")

        assert response.status_code == 200
        entry = response.json()["connected"][0]
        assert entry["slug"] == "nonexistent-service-xyz"
        assert entry["actions"] == []
        assert entry["action_count"] == 0


class TestRealDBAuth:
    """Unauthenticated requests must be blocked."""

    def test_no_auth_returns_403(self):
        # get_db is NOT overridden here because get_current_user rejects
        # unauthenticated requests before FastAPI resolves get_db.
        client = TestClient(app)
        response = client.get("/api/integrations/connected")
        assert response.status_code in (401, 403)
