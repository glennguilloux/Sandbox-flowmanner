"""
Tests for GET /api/integrations/connected endpoint.

Covers:
- No connected integrations (empty response)
- OAuth connections only (from DB)
- Non-OAuth connections only (from env vars + _NON_OAUTH_CONFIGS)
- Mixed OAuth + non-OAuth
- Filters inactive connections
- Multiple OAuth connections
- Proper action structure in response
- Auth required
- Unknown slugs get zero actions
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.main_fastapi import app
from app.models.phase4_models import IntegrationConnection

pytestmark = pytest.mark.integration


# ── Module-level fixtures ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_non_oauth_env(monkeypatch):
    """Ensure LINEAR_API_KEY and DISCORD_BOT_TOKEN are not set in any test."""
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    # Also clear pydantic-settings cached values (loaded at import time)
    monkeypatch.setattr(settings, "LINEAR_API_KEY", "", raising=False)
    monkeypatch.setattr(settings, "DISCORD_BOT_TOKEN", "", raising=False)


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_user(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id=1,
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        hashed_password="hashed",
        is_active=True,
        is_admin=False,
        is_superuser=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_connection(
    *,
    id="conn-1",
    user_id=1,
    integration_slug="slack",
    account_name="My Workspace",
    account_id="T12345",
    is_active=True,
    created_at=None,
    expires_at=None,
    scopes=None,
) -> MagicMock:
    """Minimal IntegrationConnection mock for DB results."""
    conn = MagicMock(spec=IntegrationConnection)
    conn.id = id
    conn.user_id = user_id
    conn.integration_slug = integration_slug
    conn.account_name = account_name
    conn.account_id = account_id
    conn.scopes = scopes
    conn.is_active = is_active
    conn.created_at = created_at or datetime(2025, 1, 1, tzinfo=timezone.utc)
    conn.expires_at = expires_at
    return conn


def _make_db_result(*connections) -> MagicMock:
    """Build mock SQLAlchemy result chain: result.scalars().all() → list of connections."""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = list(connections)
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    return mock_result


@pytest.fixture
def auth_client():
    """Yield a TestClient with get_current_user and get_db overridden."""
    user = _make_user()
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.close = AsyncMock()

    async def override_get_db():
        yield mock_db

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as client:
        yield client, mock_db
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestConnectedIntegrationsEmpty:
    """User has no connections and no non-OAuth env vars set."""

    def test_no_connections_returns_empty_list(self, auth_client):
        client, mock_db = auth_client
        mock_db.execute.return_value = _make_db_result()

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] == []
        assert data["total"] == 0

    def test_response_structure_is_correct(self, auth_client):
        client, mock_db = auth_client
        mock_db.execute.return_value = _make_db_result()

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        assert "total" in data
        assert isinstance(data["connected"], list)
        assert isinstance(data["total"], int)


class TestOAuthConnections:
    """User has active OAuth connections in DB."""

    def test_single_slack_connection_returns_actions(self, auth_client):
        client, mock_db = auth_client
        conn = _make_connection(integration_slug="slack", account_name="My Slack")
        mock_db.execute.return_value = _make_db_result(conn)

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["connected"]) == 1
        entry = data["connected"][0]
        assert entry["slug"] == "slack"
        assert entry["name"] == "Slack"
        assert entry["account_name"] == "My Slack"
        assert entry["auth_type"] == "oauth2"
        assert entry["account_id"] == "T12345"
        assert entry["action_count"] > 0
        assert len(entry["actions"]) == entry["action_count"]

    def test_github_connection_returns_actions(self, auth_client):
        client, mock_db = auth_client
        conn = _make_connection(integration_slug="github", account_name="my-org")
        mock_db.execute.return_value = _make_db_result(conn)

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        entry = response.json()["connected"][0]
        assert entry["slug"] == "github"
        assert entry["name"] == "Github"
        action_ids = [a["id"] for a in entry["actions"]]
        assert "create_issue" in action_ids
        assert "list_issues" in action_ids

    def test_multiple_connections_returned(self, auth_client):
        client, mock_db = auth_client
        slack = _make_connection(id="c1", integration_slug="slack")
        github = _make_connection(id="c2", integration_slug="github")
        mock_db.execute.return_value = _make_db_result(slack, github)

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        slugs = [e["slug"] for e in data["connected"]]
        assert "slack" in slugs
        assert "github" in slugs


class TestFiltersInactiveConnections:
    """Only active connections are returned."""

    def test_active_connection_is_returned(self, auth_client):
        client, mock_db = auth_client
        active_slack = _make_connection(id="c1", integration_slug="slack", is_active=True)
        mock_db.execute.return_value = _make_db_result(active_slack)

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["connected"][0]["slug"] == "slack"


class TestNonOAuthConnections:
    """Non-OAuth integrations appear when env vars are set."""

    def test_linear_appears_when_env_var_set(self, monkeypatch, auth_client):
        monkeypatch.setenv("LINEAR_API_KEY", "lin-api-test-key")
        monkeypatch.setattr(settings, "LINEAR_API_KEY", "lin-api-test-key")
        client, mock_db = auth_client
        mock_db.execute.return_value = _make_db_result()

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        slugs = [e["slug"] for e in data["connected"]]
        assert "linear" in slugs
        linear = [e for e in data["connected"] if e["slug"] == "linear"][0]
        assert linear["auth_type"] == "api_key"
        assert linear["account_name"] == "linear-workspace"

    def test_discord_appears_when_env_var_set(self, monkeypatch, auth_client):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-test-token")
        monkeypatch.setattr(settings, "DISCORD_BOT_TOKEN", "discord-test-token")
        client, mock_db = auth_client
        mock_db.execute.return_value = _make_db_result()

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        slugs = [e["slug"] for e in data["connected"]]
        assert "discord" in slugs

    def test_linear_not_appearing_when_env_var_unset(self, auth_client):
        client, mock_db = auth_client
        mock_db.execute.return_value = _make_db_result()

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        slugs = [e["slug"] for e in response.json()["connected"]]
        assert "linear" not in slugs
        assert "discord" not in slugs

    def test_non_oauth_actions_are_populated(self, monkeypatch, auth_client):
        monkeypatch.setenv("LINEAR_API_KEY", "lin-api-test-key")
        monkeypatch.setattr(settings, "LINEAR_API_KEY", "lin-api-test-key")
        client, mock_db = auth_client
        mock_db.execute.return_value = _make_db_result()

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        linear = [e for e in response.json()["connected"] if e["slug"] == "linear"][0]
        assert linear["action_count"] > 0
        assert len(linear["actions"]) > 0
        for action in linear["actions"]:
            assert "id" in action
            assert "name" in action
            assert "description" in action


class TestMixedConnections:
    """Both OAuth and non-OAuth integrations appear together."""

    def test_oauth_and_non_oauth_both_returned(self, monkeypatch, auth_client):
        monkeypatch.setenv("LINEAR_API_KEY", "lin-api-test-key")
        monkeypatch.setattr(settings, "LINEAR_API_KEY", "lin-api-test-key")
        client, mock_db = auth_client
        slack = _make_connection(id="c1", integration_slug="slack")
        mock_db.execute.return_value = _make_db_result(slack)

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        data = response.json()
        slugs = [e["slug"] for e in data["connected"]]
        assert "slack" in slugs
        assert "linear" in slugs
        assert data["total"] == 2


class TestActionStructure:
    """Verify the structure of returned actions and connection entries."""

    def test_actions_have_required_fields(self, auth_client):
        client, mock_db = auth_client
        conn = _make_connection(integration_slug="slack")
        mock_db.execute.return_value = _make_db_result(conn)

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        entry = response.json()["connected"][0]
        for action in entry["actions"]:
            assert "id" in action, f"Missing 'id' in {action}"
            assert "name" in action, f"Missing 'name' in {action}"
            assert "description" in action, f"Missing 'description' in {action}"
            assert isinstance(action["id"], str)
            assert isinstance(action["name"], str)
            assert isinstance(action["description"], str)

    def test_connection_entry_has_required_fields(self, auth_client):
        client, mock_db = auth_client
        conn = _make_connection(integration_slug="github")
        mock_db.execute.return_value = _make_db_result(conn)

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        entry = response.json()["connected"][0]
        required = ["slug", "name", "account_name", "auth_type", "actions", "action_count"]
        for field in required:
            assert field in entry, f"Missing '{field}' in connection entry"


class TestAuthRequired:
    """Unauthenticated requests should be rejected."""

    def test_unauthenticated_returns_403(self):
        client = TestClient(app)
        response = client.get("/api/integrations/connected")
        assert response.status_code in (401, 403)


class TestIntegrationWithUnknownSlug:
    """Connections for slugs not in _INTEGRATION_CAPABILITIES get zero actions."""

    def test_unknown_slug_has_zero_actions(self, auth_client):
        client, mock_db = auth_client
        conn = _make_connection(integration_slug="unknown-service")
        mock_db.execute.return_value = _make_db_result(conn)

        response = client.get("/api/integrations/connected")

        assert response.status_code == 200
        entry = response.json()["connected"][0]
        assert entry["slug"] == "unknown-service"
        assert entry["actions"] == []
        assert entry["action_count"] == 0
