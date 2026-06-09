"""
Unit tests for DiscordConnector.

Tests all 20 Discord actions (messaging, channels, guilds, users, reactions,
channel management, invites, typing, crosspost) using mocked aiohttp HTTP
responses since BaseConnector uses aiohttp internally.
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
from app.services.connectors.discord_connector import DiscordConnector

# ── Helpers ────────────────────────────────────────────────────────────


def _make_mock_response(
    status: int, body: dict | list | str, headers: dict | None = None
):
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
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def request(self, method: str, url: str, **kwargs):
        key = f"{method}:{url}"
        resp = self._response_map.get(key, self._response_map.get("default"))
        if resp is None:
            resp = _make_mock_response(
                404, {"code": 10003, "message": "Unknown Channel"}
            )

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
        name="test-discord",
        connector_type="discord",
        auth_type=AuthType.BEARER_TOKEN,
        auth_config=auth_config or {"token": "bot-token-abc123"},
    )


# ── Constructor / Defaults ────────────────────────────────────────────


def test_constructor_defaults():
    """Verify default config values are set correctly."""
    config = _make_config()
    connector = DiscordConnector(config)

    assert connector.connector_type == "discord"
    assert "send_message" in connector.available_actions
    assert "list_guilds" in connector.available_actions
    assert "create_channel" in connector.available_actions
    assert "crosspost_message" in connector.available_actions


def test_init_falls_back_to_settings_token():
    """When auth_config has no token, reads DISCORD_BOT_TOKEN from settings."""
    from app.services.connectors.base import AuthType, ConnectorConfig

    with patch(
        "app.services.connectors.discord_connector.settings.DISCORD_BOT_TOKEN",
        "settings-bot-token",
    ):
        config = ConnectorConfig(
            name="test-discord",
            connector_type="discord",
            auth_type=AuthType.BEARER_TOKEN,
            auth_config={},
        )
        connector = DiscordConnector(config)

    assert connector.config.auth_config["token"] == "settings-bot-token"


def test_init_keeps_explicit_token_over_settings():
    """Explicit token in auth_config overrides settings."""
    with patch(
        "app.services.connectors.discord_connector.settings.DISCORD_BOT_TOKEN",
        "settings-bot-token",
    ):
        config = _make_config(auth_config={"token": "explicit-token"})
        connector = DiscordConnector(config)

    assert connector.config.auth_config["token"] == "explicit-token"


def test_init_sets_bot_prefix():
    """Discord bot tokens always use 'Bot' prefix, not 'Bearer'."""
    config = _make_config()
    connector = DiscordConnector(config)

    assert connector.config.auth_config["token_prefix"] == "Bot"


def test_available_actions_count():
    """Discord connector has 20 actions."""
    connector = DiscordConnector(_make_config())
    assert len(connector.available_actions) == 20


@pytest.mark.asyncio
async def test_unknown_action_returns_error():
    """Non-existent action returns error."""
    fake = _FakeSession(
        {"default": _make_mock_response(200, {"id": "bot1", "username": "MyBot"})}
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        result = await connector.execute_action("nonexistent_action", {})

    assert result.success is False
    assert result.status_code == 400
    assert "Unknown action" in (result.error or "")


# ── Credential Validation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_credentials_success():
    """connect() succeeds with valid bot token."""
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200,
                {"id": "123456789", "username": "MyBot", "discriminator": "0"},
            )
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        ok = await connector.connect()

    assert ok is True
    assert connector._bot_user_id == "123456789"


@pytest.mark.asyncio
async def test_validate_credentials_failure():
    """connect() returns False on 401 Unauthorized."""
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                401, {"code": 0, "message": "401: Unauthorized"}
            )
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        ok = await connector.connect()

    assert ok is False


# ── Messaging Actions ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_message_success():
    """Send a message to a channel."""
    msg = {
        "id": "msg1",
        "channel_id": "123",
        "content": "Hello world",
        "author": {"id": "bot1", "username": "MyBot"},
    }
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1", "username": "MyBot"}
            ),
            "POST:https://discord.com/api/v10/channels/123/messages": _make_mock_response(
                200, msg
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "send_message", {"channel_id": "123", "content": "Hello world"}
        )

    assert result.success is True
    assert result.data["content"] == "Hello world"
    assert result.data["channel_id"] == "123"


@pytest.mark.asyncio
async def test_send_message_missing_channel():
    """Missing channel_id returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"id": "bot1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("send_message", {"content": "Hello"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_send_message_with_embeds():
    """Send a rich embed message."""
    embed = {
        "title": "Announcement",
        "description": "Something important",
        "color": 0xFF0000,
    }
    msg = {"id": "msg2", "content": "", "embeds": [embed]}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "POST:https://discord.com/api/v10/channels/456/messages": _make_mock_response(
                200, msg
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "send_message", {"channel_id": "456", "embeds": [embed]}
        )

    assert result.success is True
    assert result.data["embeds"][0]["title"] == "Announcement"


@pytest.mark.asyncio
async def test_edit_message():
    """Edit an existing message."""
    edited = {
        "id": "msg1",
        "content": "Updated content",
        "edited_timestamp": "2026-06-01T10:00:00Z",
    }
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "PATCH:https://discord.com/api/v10/channels/123/messages/msg1": _make_mock_response(
                200, edited
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "edit_message",
            {"channel_id": "123", "message_id": "msg1", "content": "Updated content"},
        )

    assert result.success is True
    assert result.data["content"] == "Updated content"


@pytest.mark.asyncio
async def test_edit_message_missing_params():
    """Missing channel_id or message_id returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"id": "bot1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("edit_message", {"message_id": "msg1"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_delete_message():
    """Delete a message (returns 204 No Content)."""
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "DELETE:https://discord.com/api/v10/channels/123/messages/msg1": _make_mock_response(
                204, {}
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "delete_message", {"channel_id": "123", "message_id": "msg1"}
        )

    assert result.success is True


# ── Channel Actions ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_channel_messages():
    """Get messages from a channel."""
    messages = [
        {"id": "m1", "content": "First", "author": {"id": "u1"}},
        {"id": "m2", "content": "Second", "author": {"id": "u2"}},
    ]
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "GET:https://discord.com/api/v10/channels/123/messages": _make_mock_response(
                200, messages
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "get_channel_messages", {"channel_id": "123"}
        )

    assert result.success is True
    assert len(result.data) == 2
    assert result.data[0]["content"] == "First"


@pytest.mark.asyncio
async def test_get_channel_messages_missing_channel():
    """Missing channel_id returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"id": "bot1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_channel_messages", {})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_get_channel():
    """Get channel info."""
    ch = {"id": "123", "name": "general", "type": 0, "guild_id": "g1"}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "GET:https://discord.com/api/v10/channels/123": _make_mock_response(
                200, ch
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_channel", {"channel_id": "123"})

    assert result.success is True
    assert result.data["name"] == "general"


@pytest.mark.asyncio
async def test_list_channels():
    """List channels in a guild."""
    channels = [
        {"id": "c1", "name": "general", "type": 0},
        {"id": "c2", "name": "random", "type": 0},
    ]
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "GET:https://discord.com/api/v10/guilds/g1/channels": _make_mock_response(
                200, channels
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("list_channels", {"guild_id": "g1"})

    assert result.success is True
    assert len(result.data) == 2
    assert result.data[0]["name"] == "general"


# ── Guild Actions ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_guilds():
    """List guilds the bot is in."""
    guilds = [
        {"id": "g1", "name": "My Server", "owner": True},
        {"id": "g2", "name": "Other Server", "owner": False},
    ]
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "GET:https://discord.com/api/v10/users/@me/guilds": _make_mock_response(
                200, guilds
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("list_guilds", {})

    assert result.success is True
    assert len(result.data) == 2
    assert result.data[0]["name"] == "My Server"


@pytest.mark.asyncio
async def test_get_guild():
    """Get guild info."""
    guild = {"id": "g1", "name": "My Server", "owner_id": "u1", "member_count": 42}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "GET:https://discord.com/api/v10/guilds/g1": _make_mock_response(
                200, guild
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_guild", {"guild_id": "g1"})

    assert result.success is True
    assert result.data["name"] == "My Server"
    assert result.data["member_count"] == 42


@pytest.mark.asyncio
async def test_get_guild_missing_id():
    """Missing guild_id returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"id": "bot1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_guild", {})

    assert result.success is False
    assert result.status_code == 400


# ── User Actions ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user():
    """Get user by ID."""
    user = {"id": "u42", "username": "carol", "discriminator": "1234", "avatar": "abc"}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "GET:https://discord.com/api/v10/users/u42": _make_mock_response(200, user),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_user", {"user_id": "u42"})

    assert result.success is True
    assert result.data["username"] == "carol"


@pytest.mark.asyncio
async def test_create_dm():
    """Create a DM channel with a user."""
    dm_ch = {"id": "dm1", "type": 1, "recipients": [{"id": "u42", "username": "carol"}]}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "POST:https://discord.com/api/v10/users/@me/channels": _make_mock_response(
                200, dm_ch
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("create_dm", {"recipient_id": "u42"})

    assert result.success is True
    assert result.data["id"] == "dm1"
    assert result.data["type"] == 1


@pytest.mark.asyncio
async def test_create_dm_missing_recipient():
    """Missing recipient_id returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"id": "bot1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("create_dm", {})

    assert result.success is False
    assert result.status_code == 400


# ── Reaction Actions ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_reaction():
    """Add a reaction to a message (returns 204)."""
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "PUT:https://discord.com/api/v10/channels/123/messages/msg1/reactions/%F0%9F%91%8D/@me": _make_mock_response(
                204, {}
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "add_reaction", {"channel_id": "123", "message_id": "msg1", "emoji": "👍"}
        )

    assert result.success is True


@pytest.mark.asyncio
async def test_add_reaction_missing_params():
    """Missing params for reaction returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"id": "bot1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "add_reaction", {"channel_id": "123", "message_id": "msg1"}
        )

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_delete_reaction():
    """Remove a reaction from a message."""
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "DELETE:https://discord.com/api/v10/channels/123/messages/msg1/reactions/%F0%9F%91%8D/@me": _make_mock_response(
                204, {}
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "delete_reaction",
            {"channel_id": "123", "message_id": "msg1", "emoji": "👍"},
        )

    assert result.success is True


@pytest.mark.asyncio
async def test_get_reactions():
    """Get reactions for a message."""
    users = [{"id": "u1", "username": "alice"}, {"id": "u2", "username": "bob"}]
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "GET:https://discord.com/api/v10/channels/123/messages/msg1/reactions/%F0%9F%91%8D": _make_mock_response(
                200, users
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "get_reactions", {"channel_id": "123", "message_id": "msg1", "emoji": "👍"}
        )

    assert result.success is True
    assert len(result.data) == 2


# ── Channel Management ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_channel():
    """Create a new text channel in a guild."""
    ch = {"id": "c3", "name": "new-channel", "type": 0, "guild_id": "g1"}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "POST:https://discord.com/api/v10/guilds/g1/channels": _make_mock_response(
                200, ch
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "create_channel", {"guild_id": "g1", "name": "new-channel", "type": 0}
        )

    assert result.success is True
    assert result.data["name"] == "new-channel"


@pytest.mark.asyncio
async def test_create_channel_missing_params():
    """Missing guild_id or name returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"id": "bot1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("create_channel", {"guild_id": "g1"})

    assert result.success is False
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_delete_channel():
    """Delete a channel (returns 200 with channel object)."""
    ch = {"id": "c3", "name": "to-delete", "type": 0}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "DELETE:https://discord.com/api/v10/channels/c3": _make_mock_response(
                200, ch
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("delete_channel", {"channel_id": "c3"})

    assert result.success is True


@pytest.mark.asyncio
async def test_modify_channel():
    """Modify channel name and topic."""
    updated = {"id": "c1", "name": "renamed", "topic": "New topic"}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "PATCH:https://discord.com/api/v10/channels/c1": _make_mock_response(
                200, updated
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "modify_channel",
            {"channel_id": "c1", "name": "renamed", "topic": "New topic"},
        )

    assert result.success is True
    assert result.data["name"] == "renamed"


# ── Invites ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_invite():
    """Create an invite for a channel."""
    invite = {"code": "abc123", "channel": {"id": "c1", "name": "general"}}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "POST:https://discord.com/api/v10/channels/c1/invites": _make_mock_response(
                200, invite
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "create_invite", {"channel_id": "c1", "max_age": 3600, "max_uses": 10}
        )

    assert result.success is True
    assert result.data["code"] == "abc123"


@pytest.mark.asyncio
async def test_get_invites():
    """Get invites for a channel."""
    invites = [{"code": "abc", "uses": 5}, {"code": "def", "uses": 0}]
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "GET:https://discord.com/api/v10/channels/c1/invites": _make_mock_response(
                200, invites
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("get_invites", {"channel_id": "c1"})

    assert result.success is True
    assert len(result.data) == 2


# ── Typing Indicator ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_typing():
    """Trigger typing indicator (returns 204)."""
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "POST:https://discord.com/api/v10/channels/123/typing": _make_mock_response(
                204, {}
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action("trigger_typing", {"channel_id": "123"})

    assert result.success is True


# ── Crosspost ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_crosspost_message():
    """Crosspost an announcement message."""
    crossposted = {"id": "msg2", "content": "Announcement", "flags": 2}
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot1"}
            ),
            "POST:https://discord.com/api/v10/channels/123/messages/msg1/crosspost": _make_mock_response(
                200, crossposted
            ),
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "crosspost_message", {"channel_id": "123", "message_id": "msg1"}
        )

    assert result.success is True
    assert result.data["flags"] == 2


@pytest.mark.asyncio
async def test_crosspost_message_missing_params():
    """Missing channel_id or message_id returns 400."""
    fake = _FakeSession({"default": _make_mock_response(200, {"id": "bot1"})})

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        await connector.connect()
        result = await connector.execute_action(
            "crosspost_message", {"channel_id": "123"}
        )

    assert result.success is False
    assert result.status_code == 400


# ── get_stats ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_stats():
    """get_stats returns connector info including Discord-specific fields."""
    fake = _FakeSession(
        {
            "GET:https://discord.com/api/v10/users/@me": _make_mock_response(
                200, {"id": "bot123", "application_id": "app456"}
            )
        }
    )

    with patch("aiohttp.ClientSession", return_value=fake):
        connector = DiscordConnector(_make_config())
        # connect() sets bot_user_id and application_id
        await connector.connect()

    stats = connector.get_stats()
    assert stats["name"] == "test-discord"
    assert stats["type"] == "discord"
    assert stats["bot_user_id"] == "bot123"
    assert stats["application_id"] == "app456"
