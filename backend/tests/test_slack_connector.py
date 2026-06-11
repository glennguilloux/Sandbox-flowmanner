"""
Unit tests for SlackConnector.

Tests the 14 actions (messaging, channels, users, reactions, files) using
mocked aiohttp HTTP responses since BaseConnector uses aiohttp internally.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponse

from app.services.connectors.base import (
    AuthType,
    ConnectorConfig,
    ConnectorResponse,
)
from app.services.connectors.slack_connector import SlackConnector

# ── Helpers ────────────────────────────────────────────────────────────


def _make_mock_response(status: int, body: dict | list | str, headers: dict | None = None):
    """Create a mock aiohttp ClientResponse."""
    resp = MagicMock(spec=ClientResponse)
    resp.status = status
    resp.headers = headers or {}
    resp.ok = 200 <= status < 300

    async def _json():
        if isinstance(body, (dict, list)):
            return body
        return json.loads(body)

    async def _text():
        return body if isinstance(body, str) else json.dumps(body)

    resp.json = _json
    resp.text = _text
    return resp


class _FakeSession:
    """Fake aiohttp.ClientSession that returns controlled responses."""

    def __init__(self, response_map: dict[str, MagicMock] | None = None):
        self._response_map = response_map or {}
        self._last_request = None
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def request(self, method: str, url: str, **kwargs):
        self._last_request = (method, url, kwargs)
        key = f"{method}:{url}"
        resp = self._response_map.get(key, self._response_map.get("default"))
        if resp is None:
            resp = _make_mock_response(404, {"ok": False, "error": "not_found"})

        class _Ctx:
            async def __aenter__(self):
                return resp

            async def __aexit__(self, *args):
                pass

        return _Ctx()

    async def close(self):
        self.closed = True


def _make_config(auth_config: dict | None = None) -> ConnectorConfig:
    return ConnectorConfig(
        name="test-slack",
        connector_type="slack",
        auth_type=AuthType.BEARER_TOKEN,
        auth_config=auth_config or {"token": "xoxb-test-token"},
    )


# ── Constructor / Defaults ────────────────────────────────────────────


def test_constructor_defaults():
    """Verify default config values are set correctly."""
    config = _make_config()
    connector = SlackConnector(config)

    assert connector.connector_type == "slack"
    assert "send_message" in connector.available_actions
    assert "list_channels" in connector.available_actions
    assert "add_reaction" in connector.available_actions
    assert "open_im" in connector.available_actions


def test_available_actions_count():
    """Slack connector has 14 actions."""
    connector = SlackConnector(_make_config())
    assert len(connector.available_actions) == 14


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    """Non-existent action returns error."""
    connector = SlackConnector(_make_config())
    result = await connector.execute_action("nonexistent_action", {})
    assert result.success is False
    assert result.status_code == 400
    assert "Unknown action" in (result.error or "")


# ── Messaging Actions ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_message_success():
    """Send a message to a channel."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/chat.postMessage": _make_mock_response(
                200,
                {
                    "ok": True,
                    "channel": "C123",
                    "ts": "1234567890.0001",
                    "message": {"text": "Hello"},
                },
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("send_message", {"channel": "C123", "text": "Hello world"})

    assert result.success is True
    assert result.data["ok"] is True
    assert result.data["channel"] == "C123"


@pytest.mark.asyncio
async def test_send_message_with_optional_params():
    """Send a message with threads, blocks, and attachments."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/chat.postMessage": _make_mock_response(
                200,
                {"ok": True, "channel": "C123", "ts": "1234567890.0002"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action(
            "send_message",
            {
                "channel": "C123",
                "text": "Thread reply",
                "thread_ts": "1234567890.0001",
                "reply_broadcast": True,
                "parse": "full",
                "link_names": True,
                "unfurl_links": True,
                "unfurl_media": False,
            },
        )

    assert result.success is True
    assert result.data["ok"] is True


@pytest.mark.asyncio
async def test_send_message_missing_params():
    """Missing channel or text returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("send_message", {"channel": "C123"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_send_ephemeral():
    """Send an ephemeral message to a user in a channel."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/chat.postEphemeral": _make_mock_response(
                200,
                {"ok": True, "message_ts": "1234567890.0003"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action(
            "send_ephemeral",
            {"channel": "C123", "user": "U42", "text": "Only you can see this"},
        )

    assert result.success is True
    assert result.data["ok"] is True


@pytest.mark.asyncio
async def test_send_ephemeral_missing_params():
    """Missing required params for ephemeral returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("send_ephemeral", {"channel": "C123", "user": "U1"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_update_message():
    """Update an existing message."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/chat.update": _make_mock_response(
                200,
                {
                    "ok": True,
                    "channel": "C123",
                    "ts": "1234567890.0001",
                    "text": "Updated",
                },
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action(
            "update_message",
            {"channel": "C123", "ts": "1234567890.0001", "text": "Updated text"},
        )

    assert result.success is True
    assert result.data["ok"] is True


@pytest.mark.asyncio
async def test_update_message_missing_params():
    """Missing channel or ts returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("update_message", {"channel": "C123"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_delete_message():
    """Delete a message."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/chat.delete": _make_mock_response(
                200,
                {"ok": True, "channel": "C123", "ts": "1234567890.0001"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("delete_message", {"channel": "C123", "ts": "1234567890.0001"})

    assert result.success is True
    assert result.data["ok"] is True


# ── Channel Actions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_channel_history():
    """Get messages from a channel."""
    messages = [
        {"type": "message", "user": "U1", "text": "Hello", "ts": "1"},
        {"type": "message", "user": "U2", "text": "World", "ts": "2"},
    ]
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "GET:https://slack.com/api/conversations.history": _make_mock_response(
                200,
                {"ok": True, "messages": messages, "has_more": False},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("get_channel_history", {"channel": "C123"})

    assert result.success is True
    assert len(result.data["messages"]) == 2
    assert result.data["messages"][0]["text"] == "Hello"


@pytest.mark.asyncio
async def test_get_channel_history_missing_channel():
    """Missing channel param returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_channel_history", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_list_channels():
    """List all channels in the workspace."""
    channels = [
        {"id": "C1", "name": "general"},
        {"id": "C2", "name": "random"},
    ]
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "GET:https://slack.com/api/conversations.list": _make_mock_response(
                200,
                {"ok": True, "channels": channels},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("list_channels", {})

    assert result.success is True
    assert len(result.data["channels"]) == 2
    assert result.data["channels"][0]["name"] == "general"


@pytest.mark.asyncio
async def test_create_channel():
    """Create a new channel."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/conversations.create": _make_mock_response(
                200,
                {"ok": True, "channel": {"id": "C3", "name": "new-channel"}},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("create_channel", {"name": "new-channel", "is_private": True})

    assert result.success is True
    assert result.data["channel"]["name"] == "new-channel"


@pytest.mark.asyncio
async def test_create_channel_missing_name():
    """Missing name param returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("create_channel", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_archive_channel():
    """Archive a channel."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/conversations.archive": _make_mock_response(
                200,
                {"ok": True},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("archive_channel", {"channel": "C123"})

    assert result.success is True
    assert result.data["ok"] is True


# ── User Actions ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_users():
    """List all users in the workspace."""
    users = [
        {"id": "U1", "name": "alice", "real_name": "Alice"},
        {"id": "U2", "name": "bob", "real_name": "Bob"},
    ]
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "GET:https://slack.com/api/users.list": _make_mock_response(
                200,
                {"ok": True, "members": users},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("list_users", {})

    assert result.success is True
    assert len(result.data["members"]) == 2


@pytest.mark.asyncio
async def test_get_user_info():
    """Get info about a specific user."""
    user = {"id": "U42", "name": "carol", "real_name": "Carol"}
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "GET:https://slack.com/api/users.info": _make_mock_response(
                200,
                {"ok": True, "user": user},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("get_user_info", {"user": "U42"})

    assert result.success is True
    assert result.data["user"]["real_name"] == "Carol"


@pytest.mark.asyncio
async def test_get_user_info_missing_user():
    """Missing user param returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_user_info", {})

    assert result.success is False
    assert result.status_code == 400


# ── Reaction Actions ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_reaction():
    """Add a reaction to a message."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/reactions.add": _make_mock_response(
                200,
                {"ok": True},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action(
            "add_reaction",
            {"channel": "C123", "ts": "1234567890.0001", "name": "thumbsup"},
        )

    assert result.success is True
    assert result.data["ok"] is True


@pytest.mark.asyncio
async def test_add_reaction_missing_params():
    """Missing required params for reaction returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("add_reaction", {"channel": "C123", "ts": "1"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_remove_reaction():
    """Remove a reaction from a message."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/reactions.remove": _make_mock_response(
                200,
                {"ok": True},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action(
            "remove_reaction",
            {"channel": "C123", "ts": "1234567890.0001", "name": "thumbsup"},
        )

    assert result.success is True
    assert result.data["ok"] is True


# ── Slack API Error Responses (HTTP 200, {"ok": false}) ───────────────


@pytest.mark.asyncio
async def test_send_message_to_nonexistent_channel():
    """Slack returns ok=false when posting to a non-existent channel."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/chat.postMessage": _make_mock_response(
                200,
                {"ok": False, "error": "channel_not_found"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("send_message", {"channel": "C_NOPE", "text": "Hello"})

    assert result.success is False  # Slack ok=false translated to success=False
    assert result.data["ok"] is False
    assert result.data["error"] == "channel_not_found"


@pytest.mark.asyncio
async def test_get_channel_history_not_in_channel():
    """Slack returns ok=false when bot is not in the channel."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "GET:https://slack.com/api/conversations.history": _make_mock_response(
                200,
                {"ok": False, "error": "not_in_channel"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("get_channel_history", {"channel": "C_SECRET"})

    assert result.success is False  # Slack not_in_channel translated to success=False
    assert result.data["ok"] is False
    assert "not_in_channel" in result.data["error"]


@pytest.mark.asyncio
async def test_get_user_info_not_found():
    """Slack returns ok=false when user does not exist."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "GET:https://slack.com/api/users.info": _make_mock_response(
                200,
                {"ok": False, "error": "user_not_found"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("get_user_info", {"user": "U_BOGUS"})

    assert result.success is False  # Slack user_not_found translated to success=False
    assert result.data["ok"] is False
    assert result.data["error"] == "user_not_found"


@pytest.mark.asyncio
async def test_add_reaction_already_exists():
    """Slack returns ok=false when reaction already exists."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/reactions.add": _make_mock_response(
                200,
                {"ok": False, "error": "already_reacted"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action(
            "add_reaction",
            {"channel": "C123", "ts": "1234567890.0001", "name": "thumbsup"},
        )

    assert result.success is False  # Slack already_reacted translated to success=False
    assert result.data["ok"] is False
    assert result.data["error"] == "already_reacted"


@pytest.mark.asyncio
async def test_create_channel_name_taken():
    """Slack returns ok=false when channel name is already taken."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/conversations.create": _make_mock_response(
                200,
                {"ok": False, "error": "name_taken"},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("create_channel", {"name": "general"})

    assert result.success is False  # Slack name_taken translated to success=False
    assert result.data["ok"] is False
    assert result.data["error"] == "name_taken"


# ── File Upload (not implemented via connector) ───────────────────────


@pytest.mark.asyncio
async def test_upload_file_returns_501():
    """File upload returns 501 as multipart is not implemented."""
    fake = _FakeSession({"default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("upload_file", {"channel": "C123", "file": "content"})

    assert result.success is False
    assert result.status_code == 501
    assert "multipart" in (result.error or "").lower()


# ── Direct Message ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_open_im():
    """Open a direct message channel with a user."""
    fake = _FakeSession(
        {
            "default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"}),
            "POST:https://slack.com/api/conversations.open": _make_mock_response(
                200,
                {"ok": True, "channel": {"id": "D123"}},
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()

        result = await connector.execute_action("open_im", {"users": "U42"})

    assert result.success is True
    assert result.data["channel"]["id"] == "D123"


@pytest.mark.asyncio
async def test_open_im_missing_users():
    """Missing users param returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"ok": True, "team_id": "T1", "user_id": "U1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("open_im", {})

    assert result.success is False
    assert result.status_code == 400


# ── Auth Failure ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_connect_with_invalid_token():
    """Connector connect() fails when auth.test returns error."""
    fake = _FakeSession(
        {"GET:https://slack.com/api/auth.test": _make_mock_response(200, {"ok": False, "error": "invalid_auth"})}
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = SlackConnector(_make_config())
        ok = await connector.connect()

    assert ok is False


# ── get_stats ─────────────────────────────────────────────────────────


def test_get_stats():
    """get_stats returns connector info including Slack-specific fields."""
    connector = SlackConnector(_make_config())
    stats = connector.get_stats()

    assert stats["name"] == "test-slack"
    assert stats["type"] == "slack"
    assert "team_id" in stats
    assert "bot_user_id" in stats
