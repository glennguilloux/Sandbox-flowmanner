"""Slack integration adapter — 4 actions using the Slack Web API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.integrations.adapters.base import BaseIntegrationAdapter
from app.models.integration_models import UserOAuthApp, UserOAuthConnection

logger = logging.getLogger(__name__)

# Base URL for the Slack Web API
SLACK_API_BASE = "https://slack.com/api"


class SlackAdapter(BaseIntegrationAdapter):
    """Adapter for Slack actions using stored OAuth bot tokens.

    Actions:
        - ``send_message``: Post a message to a channel.
        - ``search_messages``: Search messages in a workspace.
        - ``list_channels``: List channels in the workspace.
        - ``create_channel``: Create a new channel.
    """

    provider = "slack"

    # ── Action dispatch ────────────────────────────────────────────────────

    async def _execute_action(
        self,
        action: str,
        params: dict[str, Any],
        access_token: str,
    ) -> dict[str, Any]:
        match action:
            case "send_message":
                return await self._send_message(params, access_token)
            case "search_messages":
                return await self._search_messages(params, access_token)
            case "list_channels":
                return await self._list_channels(params, access_token)
            case "create_channel":
                return await self._create_channel(params, access_token)
            case _:
                return {
                    "success": False,
                    "error": f"Unknown Slack action: {action}",
                }

    # ── Action: send_message ───────────────────────────────────────────────

    async def _send_message(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Post a message to a Slack channel.

        Required params: ``channel``, ``text``
        Optional params: ``thread_ts``
        """
        channel = params.get("channel")
        text = params.get("text")

        if not channel:
            return {"success": False, "error": "Missing required param: channel"}
        if not text:
            return {"success": False, "error": "Missing required param: text"}

        body: dict = {
            "channel": channel,
            "text": text,
        }
        if params.get("thread_ts"):
            body["thread_ts"] = params["thread_ts"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                json=body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            return _parse_slack_response(resp)

    # ── Action: search_messages ────────────────────────────────────────────

    async def _search_messages(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Search messages in the Slack workspace.

        Required params: ``query``
        Optional params: ``limit`` (default 20, max 100)
        """
        query = params.get("query")
        if not query:
            return {"success": False, "error": "Missing required param: query"}

        limit = min(int(params.get("limit", 20)), 100)

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SLACK_API_BASE}/search.messages",
                params={"query": query, "count": limit},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return _parse_slack_response(resp)

    # ── Action: list_channels ──────────────────────────────────────────────

    async def _list_channels(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """List public channels in the workspace.

        Optional params: ``limit`` (default 100, max 200),
        ``cursor`` (for pagination).
        """
        limit = min(int(params.get("limit", 100)), 200)
        cursor = params.get("cursor")

        query_params: dict = {"limit": limit}
        if cursor:
            query_params["cursor"] = cursor

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{SLACK_API_BASE}/conversations.list",
                params=query_params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            return _parse_slack_response(resp)

    # ── Action: create_channel ─────────────────────────────────────────────

    async def _create_channel(
        self, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        """Create a new public or private channel.

        Required params: ``name``
        Optional params: ``is_private`` (bool, default False)
        """
        name = params.get("name")
        if not name:
            return {"success": False, "error": "Missing required param: name"}

        body: dict = {"name": name}
        if params.get("is_private"):
            body["is_private"] = True

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{SLACK_API_BASE}/conversations.create",
                json=body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            return _parse_slack_response(resp)

    # ── Token refresh ──────────────────────────────────────────────────────

    async def _refresh_token(
        self, connection: UserOAuthConnection
    ) -> str | None:
        """Attempt to refresh the Slack OAuth token.

        Slack supports token refresh via ``oauth.v2.access`` with
        grant_type=refresh_token.
        """
        refresh_token = connection.get_refresh_token()
        if not refresh_token:
            logger.warning("No refresh token available for Slack connection %s", connection.id)
            return None

        try:
            # Get client credentials from the associated app
            from sqlalchemy import select

            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(UserOAuthApp).where(
                        UserOAuthApp.id == connection.app_id,
                        UserOAuthApp.is_active == True,
                    )
                )
                app = result.scalars().first()
                if not app:
                    return None

                client_id = app.get_client_id()
                client_secret = app.get_client_secret()

                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        "https://slack.com/api/oauth.v2.access",
                        data={
                            "client_id": client_id,
                            "client_secret": client_secret,
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token,
                        },
                    )

                    if resp.status_code >= 400:
                        return None

                    data = resp.json()
                    if not data.get("ok"):
                        return None

                    new_access = data.get("access_token")
                    if new_access:
                        from app.integrations.oauth import encrypt_token
                        # Merge the connection into this session so changes persist
                        db_conn = await db.merge(connection)
                        db_conn.encrypted_access_token = encrypt_token(new_access)
                        if data.get("refresh_token"):
                            db_conn.encrypted_refresh_token = encrypt_token(
                                data["refresh_token"]
                            )
                        await db.commit()
                        return new_access

        except Exception as e:
            logger.error("Slack token refresh failed: %s", e)

        return None


# ── Response parser ───────────────────────────────────────────────────────────


def _parse_slack_response(resp: httpx.Response) -> dict[str, Any]:
    """Parse a Slack API response and return a structured result.

    Slack always returns HTTP 200 — the ``ok`` field in the JSON body
    indicates success or failure.
    """
    try:
        data = resp.json()
    except Exception:
        return {
            "success": False,
            "error": f"Slack returned non-JSON response (HTTP {resp.status_code})",
        }

    if not isinstance(data, dict):
        return {"success": False, "error": f"Unexpected Slack response type: {type(data).__name__}"}

    if data.get("ok"):
        return {
            "success": True,
            "response": data,
        }

    # Slack error — extract a clear error message
    error_code = data.get("error", "unknown_error")
    error_detail = _slack_error_message(error_code)

    # Detect token-related errors
    if error_code in ("token_expired", "not_authed", "invalid_auth"):
        return {"success": False, "error": "token_expired", "error_detail": error_detail}

    return {
        "success": False,
        "error": error_detail,
        "error_code": error_code,
    }


def _slack_error_message(error: str) -> str:
    """Map Slack error codes to human-readable messages."""
    messages = {
        "not_authed": "No authentication token provided",
        "invalid_auth": "Invalid authentication token",
        "token_expired": "Authentication token has expired",
        "account_inactive": "Authentication token is for a deleted user or workspace",
        "channel_not_found": "Channel not found",
        "not_in_channel": "Bot is not a member of the channel",
        "is_archived": "Channel has been archived",
        "msg_too_long": "Message text is too long",
        "no_text": "No message text provided",
        "rate_limited": "Rate limited — try again later",
        "missing_scope": "Missing required OAuth scope",
        "invalid_arguments": "Invalid arguments provided",
        "invalid_arg_name": "Invalid argument name",
        "invalid_charset": "Invalid character encoding",
        "invalid_form_data": "Invalid form data",
        "invalid_post_type": "Invalid POST type",
        "missing_post_type": "Missing POST type",
        "team_added_to_org": "Team has been added to an org",
        "request_timeout": "Request timed out",
        "fatal_error": "Fatal error occurred",
    }
    return messages.get(error, f"Slack API error: {error}")
