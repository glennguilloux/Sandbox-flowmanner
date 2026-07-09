"""
Unit tests for IntegrationBridge.

Tests the bridge between OAuth tokens and Nexus capabilities:
- get_integration_bridge singleton
- register/unregister capabilities for users
- execute_integration_action with mocked connectors
- connector lifecycle (connect → execute → disconnect)
- token refresh logic
- register_all_active_connections startup flow
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.integration_bridge import (
    _INTEGRATION_CAPABILITIES,
    IntegrationBridge,
    get_integration_bridge,
)

# ── Helpers ────────────────────────────────────────────────────────────


def _mock_db_session(connections=None):
    """Create a mock AsyncSession that returns IntegrationConnection-like objects."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.flush = AsyncMock()

    # Build the scalar chain for query results
    mock_result = MagicMock()
    if isinstance(connections, list):
        mock_result.scalars.return_value.all.return_value = connections
    else:
        mock_result.scalar_one_or_none.return_value = connections
    session.execute.return_value = mock_result

    return session


def _make_connection_row(user_id=33, slug="google", is_active=True, token="encrypted-token"):
    """Create a mock IntegrationConnection row."""
    conn = MagicMock()
    conn.user_id = user_id
    conn.integration_slug = slug
    conn.is_active = is_active
    conn.encrypted_access_token = token
    conn.encrypted_refresh_token = None
    conn.expires_at = None
    return conn


def _mock_connector_response(success=True, data=None, error=None, status_code=200):
    """Create a mock ConnectorResponse."""
    from app.services.connectors.base import ConnectorResponse

    return ConnectorResponse(
        success=success,
        data=data,
        error=error,
        status_code=status_code,
    )


# ── Singleton ─────────────────────────────────────────────────────────


def test_get_integration_bridge_singleton():
    """get_integration_bridge returns the same instance."""
    b1 = get_integration_bridge()
    b2 = get_integration_bridge()
    assert b1 is b2


def test_integration_bridge_init():
    """Bridge starts with empty registrations."""
    bridge = IntegrationBridge()
    assert len(bridge._active_registrations) == 0


# ── Registration Key ──────────────────────────────────────────────────


def test_registration_key():
    """_registration_key formats correctly."""
    bridge = IntegrationBridge()
    key = bridge._registration_key(user_id=42, slug="github")
    assert key == "42:github"


# ── Capability Definitions ───────────────────────────────────────────


def test_capability_defs_exist_for_all_integrations():
    """All six integrations (slack, github, google, notion, linear, discord) have capability defs."""
    assert "slack" in _INTEGRATION_CAPABILITIES
    assert "github" in _INTEGRATION_CAPABILITIES
    assert "google" in _INTEGRATION_CAPABILITIES
    assert "notion" in _INTEGRATION_CAPABILITIES
    assert "linear" in _INTEGRATION_CAPABILITIES
    assert "discord" in _INTEGRATION_CAPABILITIES

    assert len(_INTEGRATION_CAPABILITIES["slack"]) >= 3
    assert len(_INTEGRATION_CAPABILITIES["github"]) >= 5
    assert len(_INTEGRATION_CAPABILITIES["google"]) >= 8
    assert len(_INTEGRATION_CAPABILITIES["notion"]) >= 6
    assert len(_INTEGRATION_CAPABILITIES["linear"]) >= 6
    assert len(_INTEGRATION_CAPABILITIES["discord"]) >= 8


def test_github_capability_actions():
    """GitHub capabilities include expected actions."""
    gh_caps = _INTEGRATION_CAPABILITIES["github"]
    action_ids = {c["id"] for c in gh_caps}
    assert "create_issue" in action_ids
    assert "create_pr" in action_ids
    assert "search_code" in action_ids
    assert "list_repos" in action_ids


def test_google_capability_actions():
    """Google capabilities include Drive, Gmail, and Calendar actions."""
    goog_caps = _INTEGRATION_CAPABILITIES["google"]
    action_ids = {c["id"] for c in goog_caps}
    assert "gmail_send" in action_ids
    assert "drive_list_files" in action_ids
    assert "calendar_create_event" in action_ids
    assert "calendar_list_events" in action_ids


def test_linear_capability_actions():
    """Linear capabilities include issue management and team actions."""
    lin_caps = _INTEGRATION_CAPABILITIES["linear"]
    action_ids = {c["id"] for c in lin_caps}
    assert "create_issue" in action_ids
    assert "update_issue" in action_ids
    assert "get_issue" in action_ids
    assert "list_issues" in action_ids
    assert "search_issues" in action_ids
    assert "add_comment" in action_ids
    assert "list_teams" in action_ids


def test_discord_capability_actions():
    """Discord capabilities include messaging, channels, guilds, and reactions."""
    dsc_caps = _INTEGRATION_CAPABILITIES["discord"]
    action_ids = {c["id"] for c in dsc_caps}
    assert "send_message" in action_ids
    assert "list_channels" in action_ids
    assert "list_guilds" in action_ids
    assert "get_user" in action_ids
    assert "create_dm" in action_ids
    assert "add_reaction" in action_ids
    assert "create_channel" in action_ids


# ── register_capabilities_for_user ─────────────────────────────────────


@pytest.mark.asyncio
async def test_register_capabilities_success():
    """Register capabilities for a user's integration."""
    bridge = IntegrationBridge()

    with patch("app.services.nexus.capability_registry.get_capability_registry") as mock_get_registry:
        mock_registry = MagicMock()
        mock_registry.register = MagicMock()
        mock_get_registry.return_value = mock_registry

        ids = await bridge.register_capabilities_for_user(user_id=1, slug="github")

    assert len(ids) > 0
    assert mock_registry.register.call_count == len(ids)
    # Verify the registration was tracked
    key = bridge._registration_key(1, "github")
    assert key in bridge._active_registrations


@pytest.mark.asyncio
async def test_register_capabilities_unknown_slug():
    """Registering an unknown slug returns empty list."""
    bridge = IntegrationBridge()
    ids = await bridge.register_capabilities_for_user(user_id=1, slug="unknown-service")
    assert ids == []


@pytest.mark.asyncio
async def test_register_capabilities_registry_unavailable():
    """Gracefully handles missing capability registry."""
    bridge = IntegrationBridge()

    with patch(
        "app.services.nexus.capability_registry.get_capability_registry",
        side_effect=ImportError("No registry"),
    ):
        ids = await bridge.register_capabilities_for_user(user_id=1, slug="github")

    # Should not crash
    assert ids == []


# ── unregister_capabilities_for_user ────────────────────────────────────


@pytest.mark.asyncio
async def test_unregister_capabilities_success():
    """Unregister capabilities for a user's integration."""
    bridge = IntegrationBridge()

    # First register
    with patch("app.services.nexus.capability_registry.get_capability_registry") as mock_get_registry:
        mock_registry = MagicMock()
        mock_registry.register = MagicMock()
        mock_registry.unregister = MagicMock(return_value=True)
        mock_get_registry.return_value = mock_registry

        await bridge.register_capabilities_for_user(user_id=1, slug="github")

        # Now unregister
        count = await bridge.unregister_capabilities_for_user(user_id=1, slug="github")

    assert count > 0
    assert mock_registry.unregister.call_count == count
    # Registration should be removed
    key = bridge._registration_key(1, "github")
    assert key not in bridge._active_registrations


@pytest.mark.asyncio
async def test_unregister_capabilities_no_registration():
    """Unregister when nothing was registered returns 0."""
    bridge = IntegrationBridge()
    count = await bridge.unregister_capabilities_for_user(user_id=99, slug="github")
    assert count == 0


@pytest.mark.asyncio
async def test_unregister_capabilities_registry_unavailable():
    """Unregister gracefully handles missing registry."""
    bridge = IntegrationBridge()

    # Manually set up a registration without going through the registry
    bridge._active_registrations["1:github"] = MagicMock(capability_ids=["integration:github:create_issue"])

    with patch(
        "app.services.nexus.capability_registry.get_capability_registry",
        side_effect=ImportError("No registry"),
    ):
        count = await bridge.unregister_capabilities_for_user(user_id=1, slug="github")

    assert count == 0


# ── execute_integration_action ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_integration_action_success():
    """Execute an integration action via the bridge."""
    bridge = IntegrationBridge()

    # Mock the connector
    mock_connector = AsyncMock()
    mock_connector.connect = AsyncMock(return_value=True)
    mock_connector.disconnect = AsyncMock()
    mock_connector.execute_action = AsyncMock(
        return_value=_mock_connector_response(success=True, data={"id": "msg-1"}, status_code=200)
    )

    mock_connector_class = MagicMock(return_value=mock_connector)
    mock_connector_manager = MagicMock()
    mock_connector_manager.get_connector_class = MagicMock(return_value=mock_connector_class)

    conn_row = _make_connection_row(slug="google")

    with (
        patch(
            "app.database.AsyncSessionLocal",
            return_value=_FakeAsyncSessionLocal(_mock_db_session(conn_row)),
        ),
        patch(
            "app.services.connectors.ConnectorManager",
            return_value=mock_connector_manager,
        ),
        patch(
            "app.services.integration_bridge.decrypt_token",
            return_value="ya29.decrypted-token",
        ),
    ):
        result = await bridge.execute_integration_action(
            user_id=33,
            slug="google",
            action="gmail_send",
            params={"to": "x@x.com", "subject": "Hi", "body": "Hello"},
        )

    assert result.success is True
    assert result.data["id"] == "msg-1"
    mock_connector.connect.assert_called_once()
    mock_connector.disconnect.assert_called_once()
    mock_connector.execute_action.assert_called_once()


@pytest.mark.asyncio
async def test_execute_integration_action_no_connection():
    """Execute fails when user has no connection."""
    bridge = IntegrationBridge()

    with patch(
        "app.database.AsyncSessionLocal",
        return_value=_FakeAsyncSessionLocal(_mock_db_session(None)),
    ):
        result = await bridge.execute_integration_action(
            user_id=99,
            slug="google",
            action="gmail_send",
            params={},
        )

    assert result.success is False
    assert result.status_code == 401
    assert "No active" in (result.error or "")


@pytest.mark.asyncio
async def test_execute_integration_action_connector_fails():
    """Execute returns connector error when action fails."""
    bridge = IntegrationBridge()

    mock_connector = AsyncMock()
    mock_connector.connect = AsyncMock(return_value=True)
    mock_connector.disconnect = AsyncMock()
    mock_connector.execute_action = AsyncMock(
        return_value=_mock_connector_response(success=False, error="API error: rate limited", status_code=429)
    )

    mock_connector_class = MagicMock(return_value=mock_connector)
    mock_connector_manager = MagicMock()
    mock_connector_manager.get_connector_class = MagicMock(return_value=mock_connector_class)

    conn_row = _make_connection_row(slug="github")

    with (
        patch(
            "app.database.AsyncSessionLocal",
            return_value=_FakeAsyncSessionLocal(_mock_db_session(conn_row)),
        ),
        patch(
            "app.services.connectors.ConnectorManager",
            return_value=mock_connector_manager,
        ),
        patch(
            "app.services.integration_bridge.decrypt_token",
            return_value="ghp.decrypted",
        ),
    ):
        result = await bridge.execute_integration_action(
            user_id=33,
            slug="github",
            action="create_issue",
            params={"owner": "o", "repo": "r", "title": "Bug"},
        )

    assert result.success is False
    assert result.status_code == 429
    # Still disconnect even on error
    mock_connector.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_execute_always_disconnects():
    """Connector is disconnected even if execute_action raises."""
    bridge = IntegrationBridge()

    mock_connector = AsyncMock()
    mock_connector.connect = AsyncMock(return_value=True)
    mock_connector.disconnect = AsyncMock()

    # Make execute_action raise an unexpected exception
    mock_connector.execute_action = AsyncMock(side_effect=RuntimeError("Unexpected failure"))

    mock_connector_class = MagicMock(return_value=mock_connector)
    mock_connector_manager = MagicMock()
    mock_connector_manager.get_connector_class = MagicMock(return_value=mock_connector_class)

    conn_row = _make_connection_row(slug="google")

    with (
        patch(
            "app.database.AsyncSessionLocal",
            return_value=_FakeAsyncSessionLocal(_mock_db_session(conn_row)),
        ),
        patch(
            "app.services.connectors.ConnectorManager",
            return_value=mock_connector_manager,
        ),
        patch(
            "app.services.integration_bridge.decrypt_token",
            return_value="ya29.token",
        ),
        contextlib.suppress(RuntimeError),
    ):
        await bridge.execute_integration_action(
            user_id=33,
            slug="google",
            action="gmail_send",
            params={"to": "x@x.com", "subject": "Hi", "body": "Hello"},
        )

    # Disconnect is always called in the finally block
    mock_connector.disconnect.assert_called_once()


# ── get_connector_for_user ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_connector_for_user_returns_connector():
    """get_connector_for_user creates a connected connector."""
    bridge = IntegrationBridge()

    conn_row = _make_connection_row(slug="google")

    mock_connector = AsyncMock()
    mock_connector.connect = AsyncMock(return_value=True)

    mock_cls = MagicMock(return_value=mock_connector)
    mock_manager = MagicMock()
    mock_manager.get_connector_class = MagicMock(return_value=mock_cls)

    with (
        patch(
            "app.database.AsyncSessionLocal",
            return_value=_FakeAsyncSessionLocal(_mock_db_session(conn_row)),
        ),
        patch(
            "app.services.connectors.ConnectorManager",
            return_value=mock_manager,
        ),
        patch(
            "app.services.integration_bridge.decrypt_token",
            return_value="ya29.decrypted",
        ),
    ):
        connector = await bridge.get_connector_for_user(user_id=33, slug="google")

    assert connector is not None
    mock_connector.connect.assert_called_once()


@pytest.mark.asyncio
async def test_get_connector_for_user_no_token():
    """Returns None when no active connection exists."""
    bridge = IntegrationBridge()

    # Connection with no token
    conn_row = _make_connection_row(token="")

    with patch(
        "app.database.AsyncSessionLocal",
        return_value=_FakeAsyncSessionLocal(_mock_db_session(conn_row)),
    ):
        connector = await bridge.get_connector_for_user(user_id=33, slug="google")

    assert connector is None


@pytest.mark.asyncio
async def test_get_connector_for_user_decrypt_fails():
    """Returns None when token decryption fails."""
    bridge = IntegrationBridge()

    conn_row = _make_connection_row()

    with (
        patch(
            "app.database.AsyncSessionLocal",
            return_value=_FakeAsyncSessionLocal(_mock_db_session(conn_row)),
        ),
        patch(
            "app.services.integration_bridge.decrypt_token",
            side_effect=ValueError("Bad encryption"),
        ),
    ):
        connector = await bridge.get_connector_for_user(user_id=33, slug="google")

    assert connector is None


@pytest.mark.asyncio
async def test_get_connector_for_linear_skips_oauth():
    """Linear connector uses API key — skips DB token lookup entirely."""
    bridge = IntegrationBridge()

    mock_connector = AsyncMock()
    mock_connector.connect = AsyncMock(return_value=True)

    mock_cls = MagicMock(return_value=mock_connector)
    mock_manager = MagicMock()
    mock_manager.get_connector_class = MagicMock(return_value=mock_cls)

    with patch(
        "app.services.connectors.ConnectorManager",
        return_value=mock_manager,
    ):
        connector = await bridge.get_connector_for_user(user_id=33, slug="linear")

    assert connector is not None
    mock_connector.connect.assert_called_once()
    # Verify the config uses API_KEY auth type
    call_args = mock_cls.call_args[0]
    assert call_args[0].auth_type.value == "api_key"
    assert call_args[0].name == "linear-workspace"


@pytest.mark.asyncio
async def test_get_connector_for_discord_skips_oauth():
    """Discord connector uses bot token — skips DB token lookup entirely."""
    bridge = IntegrationBridge()

    mock_connector = AsyncMock()
    mock_connector.connect = AsyncMock(return_value=True)

    mock_cls = MagicMock(return_value=mock_connector)
    mock_manager = MagicMock()
    mock_manager.get_connector_class = MagicMock(return_value=mock_cls)

    with patch(
        "app.services.connectors.ConnectorManager",
        return_value=mock_manager,
    ):
        connector = await bridge.get_connector_for_user(user_id=33, slug="discord")

    assert connector is not None
    mock_connector.connect.assert_called_once()
    # Verify the config uses BEARER_TOKEN auth type
    call_args = mock_cls.call_args[0]
    assert call_args[0].auth_type.value == "bearer_token"
    assert call_args[0].name == "discord-bot"


# ── Token Refresh ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_google_token_success(monkeypatch):
    """_refresh_google_token exchanges a refresh token."""
    # The bridge short-circuits when Google OAuth env vars are absent; the
    # test must set them itself rather than depending on the host env so it
    # is hermetic in CI.
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")

    bridge = IntegrationBridge()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "ya29.new-token",
            "expires_in": 3599,
            "token_type": "Bearer",
        }

        async def _post(url, data=None):
            return mock_resp

        mock_client.post = _post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await bridge._refresh_google_token("refresh-token-123")

    assert result is not None
    assert result["access_token"] == "ya29.new-token"
    assert result["expires_in"] == 3599


@pytest.mark.asyncio
async def test_refresh_google_token_fails(monkeypatch):
    """_refresh_google_token returns None on HTTP failure."""
    # Same hermetic env-var setup as the success test: without these the
    # bridge short-circuits to None before the mocked httpx is ever called,
    # making the HTTP-failure path untestable.
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")

    bridge = IntegrationBridge()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "invalid_grant"

        async def _post(url, data=None):
            return mock_resp

        mock_client.post = _post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await bridge._refresh_google_token("bad-token")

    assert result is None


# ── register_all_active_connections ────────────────────────────────────


@pytest.mark.asyncio
async def test_register_all_active_connections():
    """Startup re-registration scans all active connections."""
    bridge = IntegrationBridge()

    conns = [
        _make_connection_row(user_id=1, slug="slack"),
        _make_connection_row(user_id=2, slug="github"),
    ]

    with (
        patch(
            "app.database.AsyncSessionLocal",
            return_value=_FakeAsyncSessionLocal(_mock_db_session(conns)),
        ),
        patch("app.services.nexus.capability_registry.get_capability_registry") as mock_get_registry,
    ):
        mock_registry = MagicMock()
        mock_registry.register = MagicMock()
        mock_get_registry.return_value = mock_registry

        total = await bridge.register_all_active_connections()

    assert total > 0
    # Both users should have registrations
    assert bridge._registration_key(1, "slack") in bridge._active_registrations
    assert bridge._registration_key(2, "github") in bridge._active_registrations


@pytest.mark.asyncio
async def test_register_all_empty():
    """No connections means 0 capabilities registered."""
    bridge = IntegrationBridge()

    with patch(
        "app.database.AsyncSessionLocal",
        return_value=_FakeAsyncSessionLocal(_mock_db_session([])),
    ):
        total = await bridge.register_all_active_connections()

    assert total == 0


@pytest.mark.asyncio
async def test_register_all_handles_errors_per_connection():
    """Failure on one connection doesn't prevent others from registering."""
    bridge = IntegrationBridge()

    good_conn = _make_connection_row(user_id=1, slug="slack")
    bad_conn = _make_connection_row(user_id=2, slug="github")

    with (
        patch(
            "app.database.AsyncSessionLocal",
            return_value=_FakeAsyncSessionLocal(_mock_db_session([good_conn, bad_conn])),
        ),
        patch.object(
            bridge,
            "register_capabilities_for_user",
            new_callable=AsyncMock,
        ) as mock_register,
    ):
        # First call succeeds, second fails
        mock_register.side_effect = [
            ["integration:slack:send_message", "integration:slack:list_channels"],
            Exception("DB error"),
        ]

        total = await bridge.register_all_active_connections()

    # Should still report the successful registrations
    assert total == 2
    assert mock_register.call_count == 2


# ── AsyncSessionLocal Mock ─────────────────────────────────────────────


class _FakeAsyncSessionLocal:
    """Fake that mimics AsyncSessionLocal() as an async context manager."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass
