"""
Slack Connector

Provides integration with Slack API for:
- Sending messages to channels
- Reading channel messages
- Managing channels
- User interactions
"""

import logging
from typing import Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


class SlackConnector(BaseConnector):
    """
    Slack API connector for messaging and channel operations.

    Supports:
    - Sending messages to channels/users
    - Reading channel history
    - Listing channels
    - User info lookup
    """

    CONNECTOR_TYPE = "slack"

    # Slack API rate limits
    SLACK_RATE_LIMIT = RateLimitConfig(
        requests_per_second=1.0,  # Conservative for tier 1
        requests_per_minute=60,
        requests_per_hour=3600,
        burst_size=5,
    )

    ACTIONS = [
        "send_message",
        "send_ephemeral",
        "update_message",
        "delete_message",
        "get_channel_history",
        "list_channels",
        "list_users",
        "get_user_info",
        "create_channel",
        "archive_channel",
        "add_reaction",
        "remove_reaction",
        "upload_file",
        "open_im",
    ]

    def __init__(self, config: ConnectorConfig):
        # Set Slack-specific defaults
        config.base_url = config.base_url or "https://slack.com/api"
        config.auth_type = config.auth_type or AuthType.BEARER_TOKEN
        config.rate_limit = config.rate_limit or self.SLACK_RATE_LIMIT

        super().__init__(config)
        self._team_id: str | None = None
        self._bot_user_id: str | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        """Validate Slack bot token by calling auth.test"""
        response = await self._execute_request("GET", "auth.test")

        if response.success and response.data:
            self._team_id = response.data.get("team_id")
            self._bot_user_id = response.data.get("user_id")
            return response.data.get("ok", False)

        return False

    async def _slack_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> ConnectorResponse:
        """Execute a Slack API request and translate ok=false to success=False.

        Slack always returns HTTP 200, even for errors. The actual success
        is encoded in the JSON body's "ok" field. This wrapper translates
        Slack's convention into ConnectorResponse.success so callers don't
        mistake a Slack error for a successful operation.
        """
        response = await self._execute_with_retry(method, endpoint, **kwargs)

        if (
            response.success
            and isinstance(response.data, dict)
            and response.data.get("ok") is False
        ):
            return ConnectorResponse(
                success=False,
                data=response.data,
                error=response.data.get("error", "Unknown Slack error"),
                status_code=response.status_code,
            )

        return response

    async def execute_action(
        self, action: str, params: dict[str, Any]
    ) -> ConnectorResponse:
        """Execute a Slack action"""

        action_handlers = {
            "send_message": self._send_message,
            "send_ephemeral": self._send_ephemeral,
            "update_message": self._update_message,
            "delete_message": self._delete_message,
            "get_channel_history": self._get_channel_history,
            "list_channels": self._list_channels,
            "list_users": self._list_users,
            "get_user_info": self._get_user_info,
            "create_channel": self._create_channel,
            "archive_channel": self._archive_channel,
            "add_reaction": self._add_reaction,
            "remove_reaction": self._remove_reaction,
            "upload_file": self._upload_file,
            "open_im": self._open_im,
        }

        handler = action_handlers.get(action)
        if not handler:
            return ConnectorResponse(
                success=False, error=f"Unknown action: {action}", status_code=400
            )

        return await handler(params)

    async def _send_message(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send a message to a channel or user"""
        channel = params.get("channel")
        text = params.get("text")

        if not channel or not text:
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel and text",
                status_code=400,
            )

        payload = {
            "channel": channel,
            "text": text,
        }

        # Optional parameters
        if params.get("blocks"):
            payload["blocks"] = params["blocks"]
        if params.get("attachments"):
            payload["attachments"] = params["attachments"]
        if params.get("thread_ts"):
            payload["thread_ts"] = params["thread_ts"]
        if params.get("reply_broadcast"):
            payload["reply_broadcast"] = params["reply_broadcast"]
        if params.get("parse"):
            payload["parse"] = params["parse"]
        if params.get("link_names"):
            payload["link_names"] = params["link_names"]
        if params.get("unfurl_links"):
            payload["unfurl_links"] = params["unfurl_links"]
        if params.get("unfurl_media"):
            payload["unfurl_media"] = params["unfurl_media"]

        return await self._slack_request("POST", "chat.postMessage", json_data=payload)

    async def _send_ephemeral(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send an ephemeral message visible only to a user"""
        channel = params.get("channel")
        user = params.get("user")
        text = params.get("text")

        if not all([channel, user, text]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel, user, and text",
                status_code=400,
            )

        payload = {
            "channel": channel,
            "user": user,
            "text": text,
        }

        if params.get("blocks"):
            payload["blocks"] = params["blocks"]
        if params.get("attachments"):
            payload["attachments"] = params["attachments"]

        return await self._slack_request(
            "POST", "chat.postEphemeral", json_data=payload
        )

    async def _update_message(self, params: dict[str, Any]) -> ConnectorResponse:
        """Update an existing message"""
        channel = params.get("channel")
        ts = params.get("ts")

        if not channel or not ts:
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel and ts",
                status_code=400,
            )

        payload = {
            "channel": channel,
            "ts": ts,
        }

        if params.get("text"):
            payload["text"] = params["text"]
        if params.get("blocks"):
            payload["blocks"] = params["blocks"]
        if params.get("attachments"):
            payload["attachments"] = params["attachments"]

        return await self._slack_request("POST", "chat.update", json_data=payload)

    async def _delete_message(self, params: dict[str, Any]) -> ConnectorResponse:
        """Delete a message"""
        channel = params.get("channel")
        ts = params.get("ts")

        if not channel or not ts:
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel and ts",
                status_code=400,
            )

        return await self._slack_request(
            "POST", "chat.delete", json_data={"channel": channel, "ts": ts}
        )

    async def _get_channel_history(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get messages from a channel"""
        channel = params.get("channel")

        if not channel:
            return ConnectorResponse(
                success=False, error="Missing required param: channel", status_code=400
            )

        query_params = {"channel": channel}

        if params.get("latest"):
            query_params["latest"] = params["latest"]
        if params.get("oldest"):
            query_params["oldest"] = params["oldest"]
        if params.get("inclusive"):
            query_params["inclusive"] = params["inclusive"]
        if params.get("limit"):
            query_params["limit"] = params["limit"]
        else:
            query_params["limit"] = 100

        return await self._slack_request(
            "GET", "conversations.history", params=query_params
        )

    async def _list_channels(self, params: dict[str, Any]) -> ConnectorResponse:
        """List all channels"""
        query_params = {}

        if params.get("types"):
            query_params["types"] = params["types"]
        else:
            query_params["types"] = "public_channel,private_channel"
        if params.get("exclude_archived"):
            query_params["exclude_archived"] = params["exclude_archived"]
        if params.get("limit"):
            query_params["limit"] = params["limit"]
        if params.get("cursor"):
            query_params["cursor"] = params["cursor"]

        return await self._slack_request(
            "GET", "conversations.list", params=query_params
        )

    async def _list_users(self, params: dict[str, Any]) -> ConnectorResponse:
        """List all users in the workspace"""
        query_params = {}

        if params.get("limit"):
            query_params["limit"] = params["limit"]
        if params.get("cursor"):
            query_params["cursor"] = params["cursor"]
        if params.get("include_locale"):
            query_params["include_locale"] = params["include_locale"]

        return await self._slack_request("GET", "users.list", params=query_params)

    async def _get_user_info(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get info about a user"""
        user = params.get("user")

        if not user:
            return ConnectorResponse(
                success=False, error="Missing required param: user", status_code=400
            )

        return await self._slack_request("GET", "users.info", params={"user": user})

    async def _create_channel(self, params: dict[str, Any]) -> ConnectorResponse:
        """Create a new channel"""
        name = params.get("name")

        if not name:
            return ConnectorResponse(
                success=False, error="Missing required param: name", status_code=400
            )

        payload = {"name": name}

        if params.get("is_private"):
            payload["is_private"] = params["is_private"]
        if params.get("team_id"):
            payload["team_id"] = params["team_id"]

        return await self._slack_request(
            "POST", "conversations.create", json_data=payload
        )

    async def _archive_channel(self, params: dict[str, Any]) -> ConnectorResponse:
        """Archive a channel"""
        channel = params.get("channel")

        if not channel:
            return ConnectorResponse(
                success=False, error="Missing required param: channel", status_code=400
            )

        return await self._slack_request(
            "POST", "conversations.archive", json_data={"channel": channel}
        )

    async def _add_reaction(self, params: dict[str, Any]) -> ConnectorResponse:
        """Add a reaction to a message"""
        channel = params.get("channel")
        ts = params.get("ts")
        name = params.get("name")

        if not all([channel, ts, name]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel, ts, and name",
                status_code=400,
            )

        return await self._slack_request(
            "POST",
            "reactions.add",
            json_data={"channel": channel, "timestamp": ts, "name": name},
        )

    async def _remove_reaction(self, params: dict[str, Any]) -> ConnectorResponse:
        """Remove a reaction from a message"""
        channel = params.get("channel")
        ts = params.get("ts")
        name = params.get("name")

        if not all([channel, ts, name]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel, ts, and name",
                status_code=400,
            )

        return await self._slack_request(
            "POST",
            "reactions.remove",
            json_data={"channel": channel, "timestamp": ts, "name": name},
        )

    async def _upload_file(self, params: dict[str, Any]) -> ConnectorResponse:
        """Upload a file to Slack"""
        # Note: File upload requires multipart/form-data
        # This is a simplified implementation
        channel = params.get("channels") or params.get("channel")

        if not channel:
            return ConnectorResponse(
                success=False,
                error="Missing required param: channel(s)",
                status_code=400,
            )

        # For file uploads, we need to handle differently
        # This would require aiohttp multipart upload
        return ConnectorResponse(
            success=False,
            error="File upload requires multipart handling - use direct API call",
            status_code=501,
        )

    async def _open_im(self, params: dict[str, Any]) -> ConnectorResponse:
        """Open a direct message channel with a user"""
        users = params.get("users")

        if not users:
            return ConnectorResponse(
                success=False, error="Missing required param: users", status_code=400
            )

        return await self._slack_request(
            "POST", "conversations.open", json_data={"users": users}
        )

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics including Slack-specific info"""
        stats = super().get_stats()
        stats.update({"team_id": self._team_id, "bot_user_id": self._bot_user_id})
        return stats
