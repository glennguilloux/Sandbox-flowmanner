"""
Telegram Connector

Provides integration with Telegram Bot API for:
- Bot info (get_me)
- Messages (send text, photo, document, edit, delete, forward)
- Chat info (get, get member)
- Pin (pin message)
- Webhook (set)
- Updates (poll)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import (
    AuthType,
    BaseConnector,
    ConnectorConfig,
    ConnectorResponse,
    RateLimitConfig,
)

if TYPE_CHECKING:
    from app.services.telegram.telegram_client import TelegramClient

logger = logging.getLogger(__name__)


class TelegramConnector(BaseConnector):
    """Telegram messaging connector."""

    CONNECTOR_TYPE = "telegram"

    TELEGRAM_RATE_LIMIT = RateLimitConfig(
        requests_per_second=1.0,
        requests_per_minute=30,
        requests_per_hour=1800,
        burst_size=5,
    )

    ACTIONS = [
        "get_me",
        "send_message",
        "send_photo",
        "send_document",
        "edit_message",
        "delete_message",
        "forward_message",
        "get_chat",
        "get_chat_member",
        "pin_message",
        "set_webhook",
        "get_updates",
    ]

    def __init__(self, config: ConnectorConfig):
        config.base_url = config.base_url or "https://api.telegram.org"
        config.auth_type = config.auth_type or AuthType.API_KEY
        config.rate_limit = config.rate_limit or self.TELEGRAM_RATE_LIMIT
        super().__init__(config)
        self._client: TelegramClient | None = None

    @property
    def connector_type(self) -> str:
        return self.CONNECTOR_TYPE

    @property
    def available_actions(self) -> list[str]:
        return self.ACTIONS

    async def _validate_credentials(self) -> bool:
        try:
            from app.config import settings
            from app.services.telegram.telegram_client import TelegramClient

            bot_token = self.config.auth_config.get("bot_token", "") or settings.TELEGRAM_BOT_TOKEN
            if not bot_token:
                logger.debug("Telegram credentials not configured — skipping validation")
                return True
            self._client = TelegramClient(bot_token=bot_token)
            me = await self._client.get_me()
            return bool(me.get("id"))
        except Exception as e:
            logger.warning("Telegram credential validation failed: %s", e)
            return False

    async def execute_action(self, action: str, params: dict[str, Any]) -> ConnectorResponse:
        handlers = {
            "get_me": self._get_me,
            "send_message": self._send_message,
            "send_photo": self._send_photo,
            "send_document": self._send_document,
            "edit_message": self._edit_message,
            "delete_message": self._delete_message,
            "forward_message": self._forward_message,
            "get_chat": self._get_chat,
            "get_chat_member": self._get_chat_member,
            "pin_message": self._pin_message,
            "set_webhook": self._set_webhook,
            "get_updates": self._get_updates,
        }
        handler = handlers.get(action)
        if not handler:
            return ConnectorResponse(success=False, error=f"Unknown action: {action}", status_code=400)
        try:
            return await handler(params)
        except Exception as e:
            logger.error("Telegram action %s failed: %s", action, e)
            return ConnectorResponse(success=False, error=str(e), status_code=500)

    async def _get_me(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        result = await self._client.get_me()
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _send_message(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        chat_id = params.get("chat_id")
        text = params.get("text")
        if not chat_id or not text:
            return ConnectorResponse(success=False, error="Missing: chat_id and text", status_code=400)
        result = await self._client.send_message(
            chat_id,
            text,
            parse_mode=params.get("parse_mode"),
            reply_to_message_id=params.get("reply_to_message_id"),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _send_photo(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        chat_id = params.get("chat_id")
        photo = params.get("photo")
        if not chat_id or not photo:
            return ConnectorResponse(success=False, error="Missing: chat_id and photo", status_code=400)
        result = await self._client.send_photo(chat_id, photo, caption=params.get("caption"))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _send_document(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        chat_id = params.get("chat_id")
        document = params.get("document")
        if not chat_id or not document:
            return ConnectorResponse(success=False, error="Missing: chat_id and document", status_code=400)
        result = await self._client.send_document(chat_id, document, caption=params.get("caption"))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _edit_message(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        chat_id = params.get("chat_id")
        message_id = params.get("message_id")
        text = params.get("text")
        if not chat_id or message_id is None or not text:
            return ConnectorResponse(success=False, error="Missing: chat_id, message_id, and text", status_code=400)
        result = await self._client.edit_message(chat_id, message_id, text)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _delete_message(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        chat_id = params.get("chat_id")
        message_id = params.get("message_id")
        if not chat_id or message_id is None:
            return ConnectorResponse(success=False, error="Missing: chat_id and message_id", status_code=400)
        result = await self._client.delete_message(chat_id, message_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _forward_message(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        chat_id = params.get("chat_id")
        from_chat_id = params.get("from_chat_id")
        message_id = params.get("message_id")
        if not chat_id or not from_chat_id or message_id is None:
            return ConnectorResponse(
                success=False, error="Missing: chat_id, from_chat_id, and message_id", status_code=400
            )
        result = await self._client.forward_message(chat_id, from_chat_id, message_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_chat(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        chat_id = params.get("chat_id")
        if not chat_id:
            return ConnectorResponse(success=False, error="Missing: chat_id", status_code=400)
        result = await self._client.get_chat(chat_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_chat_member(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        chat_id = params.get("chat_id")
        user_id = params.get("user_id")
        if not chat_id or not user_id:
            return ConnectorResponse(success=False, error="Missing: chat_id and user_id", status_code=400)
        result = await self._client.get_chat_member(chat_id, user_id)
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _pin_message(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        chat_id = params.get("chat_id")
        message_id = params.get("message_id")
        if not chat_id or message_id is None:
            return ConnectorResponse(success=False, error="Missing: chat_id and message_id", status_code=400)
        result = await self._client.pin_message(
            chat_id, message_id, disable_notification=params.get("disable_notification", False)
        )
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _set_webhook(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        url = params.get("url")
        if not url:
            return ConnectorResponse(success=False, error="Missing: url", status_code=400)
        result = await self._client.set_webhook(url, secret_token=params.get("secret_token"))
        return ConnectorResponse(success=True, data=result, status_code=200)

    async def _get_updates(self, params: dict[str, Any]) -> ConnectorResponse:
        assert self._client is not None, "TelegramClient not initialized — call connect() first"
        result = await self._client.get_updates(
            offset=params.get("offset"),
            limit=params.get("limit", 100),
            timeout=params.get("timeout", 0),
        )
        return ConnectorResponse(success=True, data=result, status_code=200)
