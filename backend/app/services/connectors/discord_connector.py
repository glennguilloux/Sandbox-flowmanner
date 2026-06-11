"""
Discord Connector

Provides integration with Discord API for:
- Sending messages to channels
- Reading channel messages
- Managing channels and guilds
- User interactions
"""

import logging
from typing import Any

from app.config import settings

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

logger = logging.getLogger(__name__)


class DiscordConnector(BaseConnector):
    """
    Discord API connector for messaging and channel operations.

    Supports:
    - Sending messages to channels
    - Reading channel messages
    - Managing channels
    - Guild information
    - User management
    """

    CONNECTOR_TYPE = "discord"

    # Discord API rate limits
    DISCORD_RATE_LIMIT = RateLimitConfig(
        requests_per_second=10.0,  # Global rate limit
        requests_per_minute=600,
        requests_per_hour=36000,
        burst_size=50,
    )

    ACTIONS = [
        "send_message",
        "edit_message",
        "delete_message",
        "get_channel_messages",
        "get_channel",
        "list_channels",
        "list_guilds",
        "get_guild",
        "get_user",
        "create_dm",
        "add_reaction",
        "delete_reaction",
        "get_reactions",
        "create_channel",
        "delete_channel",
        "modify_channel",
        "create_invite",
        "get_invites",
        "trigger_typing",
        "crosspost_message",
    ]

    def __init__(self, config: ConnectorConfig):
        # Set Discord-specific defaults
        config.base_url = config.base_url or "https://discord.com/api/v10"
        config.auth_type = config.auth_type or AuthType.BEARER_TOKEN
        config.rate_limit = config.rate_limit or self.DISCORD_RATE_LIMIT

        # Discord bot tokens use "Bot" prefix, not "Bearer"
        config.auth_config.setdefault("token_prefix", "Bot")

        # Use the bot token from settings if not provided in auth_config
        if not config.auth_config.get("token"):
            token = settings.DISCORD_BOT_TOKEN
            if token:
                config.auth_config["token"] = token

        super().__init__(config)
        self._application_id: str | None = None
        self._bot_user_id: str | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        """Validate Discord bot token by getting current user info"""
        response = await self._execute_request("GET", "users/@me")

        if response.success and response.data:
            self._bot_user_id = response.data.get("id")
            self._application_id = response.data.get("application_id")
            return True

        return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        """Execute a Discord action"""

        action_handlers = {
            "send_message": self._send_message,
            "edit_message": self._edit_message,
            "delete_message": self._delete_message,
            "get_channel_messages": self._get_channel_messages,
            "get_channel": self._get_channel,
            "list_channels": self._list_channels,
            "list_guilds": self._list_guilds,
            "get_guild": self._get_guild,
            "get_user": self._get_user,
            "create_dm": self._create_dm,
            "add_reaction": self._add_reaction,
            "delete_reaction": self._delete_reaction,
            "get_reactions": self._get_reactions,
            "create_channel": self._create_channel,
            "delete_channel": self._delete_channel,
            "modify_channel": self._modify_channel,
            "create_invite": self._create_invite,
            "get_invites": self._get_invites,
            "trigger_typing": self._trigger_typing,
            "crosspost_message": self._crosspost_message,
        }

        handler = action_handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)

        return await handler(params)

    async def _send_message(self, params: dict[str, Any]) -> ConnectorResponse:
        """Send a message to a channel"""
        channel_id = params.get("channel_id")
        content = params.get("content")

        if not channel_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: channel_id",
                status_code=400,
            )

        payload = {}

        if content:
            payload["content"] = content
        if params.get("embeds"):
            payload["embeds"] = params["embeds"]
        if params.get("embed"):
            payload["embed"] = params["embed"]
        if params.get("components"):
            payload["components"] = params["components"]
        if params.get("tts"):
            payload["tts"] = params["tts"]
        if params.get("allowed_mentions"):
            payload["allowed_mentions"] = params["allowed_mentions"]
        if params.get("message_reference"):
            payload["message_reference"] = params["message_reference"]
        if params.get("sticker_ids"):
            payload["sticker_ids"] = params["sticker_ids"]
        if params.get("flags"):
            payload["flags"] = params["flags"]

        if not payload:
            return ConnectorResponse(
                success=False,
                error="Message must have content, embeds, or components",
                status_code=400,
            )

        return await self._execute_with_retry("POST", f"channels/{channel_id}/messages", json_data=payload)

    async def _edit_message(self, params: dict[str, Any]) -> ConnectorResponse:
        """Edit an existing message"""
        channel_id = params.get("channel_id")
        message_id = params.get("message_id")

        if not channel_id or not message_id:
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel_id and message_id",
                status_code=400,
            )

        payload = {}

        if params.get("content"):
            payload["content"] = params["content"]
        if params.get("embeds"):
            payload["embeds"] = params["embeds"]
        if params.get("components"):
            payload["components"] = params["components"]
        if params.get("flags"):
            payload["flags"] = params["flags"]

        return await self._execute_with_retry(
            "PATCH", f"channels/{channel_id}/messages/{message_id}", json_data=payload
        )

    async def _delete_message(self, params: dict[str, Any]) -> ConnectorResponse:
        """Delete a message"""
        channel_id = params.get("channel_id")
        message_id = params.get("message_id")

        if not channel_id or not message_id:
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel_id and message_id",
                status_code=400,
            )

        return await self._execute_with_retry("DELETE", f"channels/{channel_id}/messages/{message_id}")

    async def _get_channel_messages(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get messages from a channel"""
        channel_id = params.get("channel_id")

        if not channel_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: channel_id",
                status_code=400,
            )

        query_params = {}

        if params.get("around"):
            query_params["around"] = params["around"]
        if params.get("before"):
            query_params["before"] = params["before"]
        if params.get("after"):
            query_params["after"] = params["after"]
        if params.get("limit"):
            query_params["limit"] = min(params["limit"], 100)
        else:
            query_params["limit"] = 50

        return await self._execute_with_retry("GET", f"channels/{channel_id}/messages", params=query_params)

    async def _get_channel(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get channel information"""
        channel_id = params.get("channel_id")

        if not channel_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: channel_id",
                status_code=400,
            )

        return await self._execute_with_retry("GET", f"channels/{channel_id}")

    async def _list_channels(self, params: dict[str, Any]) -> ConnectorResponse:
        """List channels in a guild"""
        guild_id = params.get("guild_id")

        if not guild_id:
            return ConnectorResponse(success=False, error="Missing required param: guild_id", status_code=400)

        return await self._execute_with_retry("GET", f"guilds/{guild_id}/channels")

    async def _list_guilds(self, params: dict[str, Any]) -> ConnectorResponse:
        """List guilds the bot is in"""
        query_params = {}

        if params.get("before"):
            query_params["before"] = params["before"]
        if params.get("after"):
            query_params["after"] = params["after"]
        if params.get("limit"):
            query_params["limit"] = min(params["limit"], 200)

        return await self._execute_with_retry("GET", "users/@me/guilds", params=query_params)

    async def _get_guild(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get guild information"""
        guild_id = params.get("guild_id")

        if not guild_id:
            return ConnectorResponse(success=False, error="Missing required param: guild_id", status_code=400)

        return await self._execute_with_retry("GET", f"guilds/{guild_id}")

    async def _get_user(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get user information"""
        user_id = params.get("user_id", "@me")

        return await self._execute_with_retry("GET", f"users/{user_id}")

    async def _create_dm(self, params: dict[str, Any]) -> ConnectorResponse:
        """Create a DM channel with a user"""
        recipient_id = params.get("recipient_id")

        if not recipient_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: recipient_id",
                status_code=400,
            )

        return await self._execute_with_retry("POST", "users/@me/channels", json_data={"recipient_id": recipient_id})

    async def _add_reaction(self, params: dict[str, Any]) -> ConnectorResponse:
        """Add a reaction to a message"""
        channel_id = params.get("channel_id")
        message_id = params.get("message_id")
        emoji = params.get("emoji")

        if not all([channel_id, message_id, emoji]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel_id, message_id, and emoji",
                status_code=400,
            )

        # URL encode the emoji
        import urllib.parse

        encoded_emoji = urllib.parse.quote(emoji)

        return await self._execute_with_retry(
            "PUT",
            f"channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me",
        )

    async def _delete_reaction(self, params: dict[str, Any]) -> ConnectorResponse:
        """Delete a reaction from a message"""
        channel_id = params.get("channel_id")
        message_id = params.get("message_id")
        emoji = params.get("emoji")
        user_id = params.get("user_id", "@me")

        if not all([channel_id, message_id, emoji]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel_id, message_id, and emoji",
                status_code=400,
            )

        import urllib.parse

        encoded_emoji = urllib.parse.quote(emoji)

        return await self._execute_with_retry(
            "DELETE",
            f"channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/{user_id}",
        )

    async def _get_reactions(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get reactions for a message"""
        channel_id = params.get("channel_id")
        message_id = params.get("message_id")
        emoji = params.get("emoji")

        if not all([channel_id, message_id, emoji]):
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel_id, message_id, and emoji",
                status_code=400,
            )

        import urllib.parse

        encoded_emoji = urllib.parse.quote(emoji)

        query_params = {}
        if params.get("after"):
            query_params["after"] = params["after"]
        if params.get("limit"):
            query_params["limit"] = min(params["limit"], 100)

        return await self._execute_with_retry(
            "GET",
            f"channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}",
            params=query_params,
        )

    async def _create_channel(self, params: dict[str, Any]) -> ConnectorResponse:
        """Create a channel in a guild"""
        guild_id = params.get("guild_id")
        name = params.get("name")

        if not guild_id or not name:
            return ConnectorResponse(
                success=False,
                error="Missing required params: guild_id and name",
                status_code=400,
            )

        payload = {"name": name}

        if params.get("type"):
            payload["type"] = params["type"]  # 0=text, 2=voice, 4=category
        if params.get("topic"):
            payload["topic"] = params["topic"]
        if params.get("bitrate"):
            payload["bitrate"] = params["bitrate"]
        if params.get("user_limit"):
            payload["user_limit"] = params["user_limit"]
        if params.get("rate_limit_per_user"):
            payload["rate_limit_per_user"] = params["rate_limit_per_user"]
        if params.get("position"):
            payload["position"] = params["position"]
        if params.get("permission_overwrites"):
            payload["permission_overwrites"] = params["permission_overwrites"]
        if params.get("parent_id"):
            payload["parent_id"] = params["parent_id"]
        if params.get("nsfw"):
            payload["nsfw"] = params["nsfw"]

        return await self._execute_with_retry("POST", f"guilds/{guild_id}/channels", json_data=payload)

    async def _delete_channel(self, params: dict[str, Any]) -> ConnectorResponse:
        """Delete a channel"""
        channel_id = params.get("channel_id")

        if not channel_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: channel_id",
                status_code=400,
            )

        return await self._execute_with_retry("DELETE", f"channels/{channel_id}")

    async def _modify_channel(self, params: dict[str, Any]) -> ConnectorResponse:
        """Modify a channel"""
        channel_id = params.get("channel_id")

        if not channel_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: channel_id",
                status_code=400,
            )

        payload = {}

        if params.get("name"):
            payload["name"] = params["name"]
        if params.get("type"):
            payload["type"] = params["type"]
        if params.get("position"):
            payload["position"] = params["position"]
        if params.get("topic"):
            payload["topic"] = params["topic"]
        if params.get("nsfw"):
            payload["nsfw"] = params["nsfw"]
        if params.get("rate_limit_per_user"):
            payload["rate_limit_per_user"] = params["rate_limit_per_user"]
        if params.get("bitrate"):
            payload["bitrate"] = params["bitrate"]
        if params.get("user_limit"):
            payload["user_limit"] = params["user_limit"]
        if params.get("permission_overwrites"):
            payload["permission_overwrites"] = params["permission_overwrites"]
        if params.get("parent_id"):
            payload["parent_id"] = params["parent_id"]

        return await self._execute_with_retry("PATCH", f"channels/{channel_id}", json_data=payload)

    async def _create_invite(self, params: dict[str, Any]) -> ConnectorResponse:
        """Create an invite for a channel"""
        channel_id = params.get("channel_id")

        if not channel_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: channel_id",
                status_code=400,
            )

        payload = {}

        if params.get("max_age"):
            payload["max_age"] = params["max_age"]
        if params.get("max_uses"):
            payload["max_uses"] = params["max_uses"]
        if params.get("temporary"):
            payload["temporary"] = params["temporary"]
        if params.get("unique"):
            payload["unique"] = params["unique"]
        if params.get("target_type"):
            payload["target_type"] = params["target_type"]
        if params.get("target_user_id"):
            payload["target_user_id"] = params["target_user_id"]
        if params.get("target_application_id"):
            payload["target_application_id"] = params["target_application_id"]

        return await self._execute_with_retry("POST", f"channels/{channel_id}/invites", json_data=payload)

    async def _get_invites(self, params: dict[str, Any]) -> ConnectorResponse:
        """Get invites for a channel"""
        channel_id = params.get("channel_id")

        if not channel_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: channel_id",
                status_code=400,
            )

        return await self._execute_with_retry("GET", f"channels/{channel_id}/invites")

    async def _trigger_typing(self, params: dict[str, Any]) -> ConnectorResponse:
        """Trigger typing indicator in a channel"""
        channel_id = params.get("channel_id")

        if not channel_id:
            return ConnectorResponse(
                success=False,
                error="Missing required param: channel_id",
                status_code=400,
            )

        return await self._execute_with_retry("POST", f"channels/{channel_id}/typing")

    async def _crosspost_message(self, params: dict[str, Any]) -> ConnectorResponse:
        """Crosspost a message to following channels"""
        channel_id = params.get("channel_id")
        message_id = params.get("message_id")

        if not channel_id or not message_id:
            return ConnectorResponse(
                success=False,
                error="Missing required params: channel_id and message_id",
                status_code=400,
            )

        return await self._execute_with_retry("POST", f"channels/{channel_id}/messages/{message_id}/crosspost")

    def get_stats(self) -> dict[str, Any]:
        """Get connector statistics including Discord-specific info"""
        stats = super().get_stats()
        stats.update({"bot_user_id": self._bot_user_id, "application_id": self._application_id})
        return stats
