"""Tests for the Slack integration adapter (all 4 actions with mocked httpx)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.adapters.slack import (
    SlackAdapter,
    _parse_slack_response,
    _slack_error_message,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def adapter():
    return SlackAdapter()


@pytest.fixture
def connection():
    """Mock UserOAuthConnection that returns a fake access token."""
    conn = MagicMock()
    conn.provider = "slack"
    conn.get_access_token.return_value = "xoxb-test-token"
    conn.get_refresh_token.return_value = None
    return conn


# ── Response parser tests ─────────────────────────────────────────────────────


class TestSlackResponseParser:
    def test_success(self):
        resp = MagicMock()
        resp.json.return_value = {
            "ok": True,
            "channel": "C123",
            "ts": "1234567890.0001",
        }
        result = _parse_slack_response(resp)
        assert result["success"] is True
        assert result["response"]["ok"] is True
        assert result["response"]["channel"] == "C123"

    def test_error_channel_not_found(self):
        resp = MagicMock()
        resp.json.return_value = {"ok": False, "error": "channel_not_found"}
        result = _parse_slack_response(resp)
        assert result["success"] is False
        assert result["error_code"] == "channel_not_found"
        assert "Channel not found" in result["error"]

    def test_token_expired(self):
        resp = MagicMock()
        resp.json.return_value = {"ok": False, "error": "token_expired"}
        result = _parse_slack_response(resp)
        assert result["success"] is False
        assert result["error"] == "token_expired"

    def test_not_authed(self):
        resp = MagicMock()
        resp.json.return_value = {"ok": False, "error": "not_authed"}
        result = _parse_slack_response(resp)
        assert result["success"] is False
        assert result["error"] == "token_expired"

    def test_non_json_response(self):
        resp = MagicMock()
        resp.json.side_effect = ValueError("not json")
        resp.status_code = 502
        result = _parse_slack_response(resp)
        assert result["success"] is False
        assert "non-JSON" in result["error"]


class TestSlackErrorMessages:
    def test_known_errors(self):
        assert "Channel not found" in _slack_error_message("channel_not_found")
        assert "not a member" in _slack_error_message("not_in_channel")
        assert "too long" in _slack_error_message("msg_too_long")
        assert "Rate limited" in _slack_error_message("rate_limited")

    def test_unknown_error(self):
        msg = _slack_error_message("some_unknown_code")
        assert "Slack API error" in msg
        assert "some_unknown_code" in msg


# ── SlackAdapter action tests (mocked httpx) ──────────────────────────────────


class TestSlackAdapter:
    @pytest.mark.asyncio
    async def test_provider_mismatch(self, adapter, connection):
        connection.provider = "github"
        result = await adapter.execute("send_message", {}, connection)
        assert result["success"] is False
        assert "Provider mismatch" in result["error"]

    @pytest.mark.asyncio
    async def test_no_access_token(self, adapter, connection):
        connection.get_access_token.return_value = ""
        result = await adapter.execute("send_message", {}, connection)
        assert result["success"] is False
        assert "No access token" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_action(self, adapter, connection):
        result = await adapter.execute("unknown_action", {}, connection)
        assert result["success"] is False
        assert "Unknown Slack action" in result["error"]


# ── Action: send_message ─────────────────────────────────────────────────────


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "channel": "C123", "ts": "123.456"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "send_message",
                {"channel": "#general", "text": "Hello, world!"},
                connection,
            )

        assert result["success"] is True
        assert result["response"]["channel"] == "C123"

    @pytest.mark.asyncio
    async def test_missing_channel(self, adapter, connection):
        result = await adapter.execute("send_message", {"text": "Hello"}, connection)
        assert result["success"] is False
        assert "channel" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_text(self, adapter, connection):
        result = await adapter.execute("send_message", {"channel": "#general"}, connection)
        assert result["success"] is False
        assert "text" in result["error"]

    @pytest.mark.asyncio
    async def test_with_thread_ts(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "ts": "123.456"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "send_message",
                {"channel": "#general", "text": "Reply", "thread_ts": "123.000"},
                connection,
            )

        assert result["success"] is True
        call_args = mock_post.call_args
        body = call_args[1]["json"]
        assert body["thread_ts"] == "123.000"

    @pytest.mark.asyncio
    async def test_api_error_handled(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "channel_not_found"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "send_message",
                {"channel": "#nonexistent", "text": "Hi"},
                connection,
            )

        assert result["success"] is False
        assert result["error_code"] == "channel_not_found"


# ── Action: search_messages ───────────────────────────────────────────────────


class TestSearchMessages:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "messages": {"matches": [{"text": "found it", "channel": {"name": "general"}}]},
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            result = await adapter.execute(
                "search_messages",
                {"query": "important meeting"},
                connection,
            )

        assert result["success"] is True
        assert result["response"]["ok"] is True

    @pytest.mark.asyncio
    async def test_missing_query(self, adapter, connection):
        result = await adapter.execute("search_messages", {}, connection)
        assert result["success"] is False
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_with_limit(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "messages": {"matches": []}}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            await adapter.execute(
                "search_messages",
                {"query": "test", "limit": 50},
                connection,
            )

        call_args = mock_get.call_args
        assert call_args[1]["params"]["count"] == 50

    @pytest.mark.asyncio
    async def test_limit_capped_at_100(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "messages": {"matches": []}}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            await adapter.execute(
                "search_messages",
                {"query": "test", "limit": 500},
                connection,
            )

        call_args = mock_get.call_args
        assert call_args[1]["params"]["count"] == 100


# ── Action: list_channels ─────────────────────────────────────────────────────


class TestListChannels:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "channels": [
                {"id": "C1", "name": "general"},
                {"id": "C2", "name": "random"},
            ],
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            result = await adapter.execute("list_channels", {}, connection)

        assert result["success"] is True
        assert result["response"]["ok"] is True

    @pytest.mark.asyncio
    async def test_with_cursor(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "channels": []}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            await adapter.execute(
                "list_channels",
                {"cursor": "dXNlcjpVMDIx"},
                connection,
            )

        call_args = mock_get.call_args
        assert call_args[1]["params"]["cursor"] == "dXNlcjpVMDIx"

    @pytest.mark.asyncio
    async def test_limit_capped_at_200(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "channels": []}

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            await adapter.execute(
                "list_channels",
                {"limit": 1000},
                connection,
            )

        call_args = mock_get.call_args
        assert call_args[1]["params"]["limit"] == 200


# ── Action: create_channel ────────────────────────────────────────────────────


class TestCreateChannel:
    @pytest.mark.asyncio
    async def test_success(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "channel": {"id": "C123", "name": "new-project"},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "create_channel",
                {"name": "new-project"},
                connection,
            )

        assert result["success"] is True
        assert result["response"]["channel"]["name"] == "new-project"

    @pytest.mark.asyncio
    async def test_missing_name(self, adapter, connection):
        result = await adapter.execute("create_channel", {}, connection)
        assert result["success"] is False
        assert "name" in result["error"]

    @pytest.mark.asyncio
    async def test_private_channel(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ok": True,
            "channel": {"id": "C456", "name": "secret", "is_private": True},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            await adapter.execute(
                "create_channel",
                {"name": "secret", "is_private": True},
                connection,
            )

        call_args = mock_post.call_args
        body = call_args[1]["json"]
        assert body["is_private"] is True

    @pytest.mark.asyncio
    async def test_api_error_handled(self, adapter, connection):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "name_taken"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "create_channel",
                {"name": "existing-channel"},
                connection,
            )

        assert result["success"] is False
        assert result["error_code"] == "name_taken"


# ── Token refresh ─────────────────────────────────────────────────────────────


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_refresh_not_available(self, adapter, connection):
        connection.get_refresh_token.return_value = None
        token = await adapter._refresh_token(connection)
        assert token is None

    @pytest.mark.asyncio
    async def test_send_message_token_expired_no_refresh(self, adapter, connection):
        """When token is expired and no refresh token, returns error."""
        connection.get_refresh_token.return_value = None
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "token_expired"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp
            result = await adapter.execute(
                "send_message",
                {"channel": "#general", "text": "Hello"},
                connection,
            )

        # Without a refresh token, we should get the token expired error
        assert result["success"] is False
        assert result["error"] == "token_expired"
