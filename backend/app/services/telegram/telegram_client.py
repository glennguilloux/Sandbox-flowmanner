"""
Telegram Bot API Client

Async client for Telegram Bot API.
Auth: Bot token embedded in URL path (not a header).

API Base: https://api.telegram.org/bot<TOKEN>
Quirk: Token is in the URL path, not a header.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramAPIError(Exception):
    """Telegram API error."""

    pass


class TelegramClient:
    """Async REST client for Telegram Bot API."""

    def __init__(
        self,
        bot_token: str,
        base_url: str = TELEGRAM_API_BASE,
    ):
        self.bot_token = bot_token
        self.base_url = f"{base_url}/bot{bot_token}"
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        api_method: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an API request."""
        url = f"{self.base_url}/{api_method}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=self._headers, params=params)
            else:
                resp = await client.post(url, headers=self._headers, json=json or params)
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After", "?")
                raise TelegramAPIError(f"Telegram rate limited: {api_method} — retry after {retry_after}s")
            if resp.status_code >= 400:
                raise TelegramAPIError(f"Telegram API {api_method} failed: {resp.status_code} {resp.text[:300]}")
            result = resp.json()
            if not result.get("ok"):
                raise TelegramAPIError(f"Telegram API error: {result.get('description', 'Unknown error')}")
            return result.get("result", result)

    # ── Bot Info ─────────────────────────────────────────────────

    async def get_me(self) -> dict[str, Any]:
        """GET /getMe — Get bot info (credential validation)."""
        return await self._request("GET", "getMe")

    # ── Messages ─────────────────────────────────────────────────

    async def send_message(
        self, chat_id: str | int, text: str, parse_mode: str | None = None, reply_to_message_id: int | None = None
    ) -> dict[str, Any]:
        """POST /sendMessage — Send a text message."""
        data: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        return await self._request("POST", "sendMessage", json=data)

    async def send_photo(self, chat_id: str | int, photo: str, caption: str | None = None) -> dict[str, Any]:
        """POST /sendPhoto — Send a photo (URL or file_id)."""
        data: dict[str, Any] = {"chat_id": chat_id, "photo": photo}
        if caption:
            data["caption"] = caption
        return await self._request("POST", "sendPhoto", json=data)

    async def send_document(self, chat_id: str | int, document: str, caption: str | None = None) -> dict[str, Any]:
        """POST /sendDocument — Send a document/file."""
        data: dict[str, Any] = {"chat_id": chat_id, "document": document}
        if caption:
            data["caption"] = caption
        return await self._request("POST", "sendDocument", json=data)

    async def edit_message(self, chat_id: str | int, message_id: int, text: str) -> dict[str, Any]:
        """POST /editMessageText — Edit a previously sent message."""
        return await self._request(
            "POST", "editMessageText", json={"chat_id": chat_id, "message_id": message_id, "text": text}
        )

    async def delete_message(self, chat_id: str | int, message_id: int) -> dict[str, Any]:
        """POST /deleteMessage — Delete a message."""
        return await self._request("POST", "deleteMessage", json={"chat_id": chat_id, "message_id": message_id})

    async def forward_message(self, chat_id: str | int, from_chat_id: str | int, message_id: int) -> dict[str, Any]:
        """POST /forwardMessage — Forward a message to another chat."""
        return await self._request(
            "POST", "forwardMessage", json={"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id}
        )

    # ── Chat Info ────────────────────────────────────────────────

    async def get_chat(self, chat_id: str | int) -> dict[str, Any]:
        """POST /getChat — Get chat info."""
        return await self._request("POST", "getChat", json={"chat_id": chat_id})

    async def get_chat_member(self, chat_id: str | int, user_id: int) -> dict[str, Any]:
        """POST /getChatMember — Get info about a chat member."""
        return await self._request("POST", "getChatMember", json={"chat_id": chat_id, "user_id": user_id})

    # ── Pin ──────────────────────────────────────────────────────

    async def pin_message(
        self, chat_id: str | int, message_id: int, disable_notification: bool = False
    ) -> dict[str, Any]:
        """POST /pinChatMessage — Pin a message in a chat."""
        return await self._request(
            "POST",
            "pinChatMessage",
            json={"chat_id": chat_id, "message_id": message_id, "disable_notification": disable_notification},
        )

    # ── Webhook ──────────────────────────────────────────────────

    async def set_webhook(self, url: str, secret_token: str | None = None) -> dict[str, Any]:
        """POST /setWebhook — Configure webhook URL for bot updates."""
        data: dict[str, Any] = {"url": url}
        if secret_token:
            data["secret_token"] = secret_token
        return await self._request("POST", "setWebhook", json=data)

    # ── Updates (polling) ────────────────────────────────────────

    async def get_updates(self, offset: int | None = None, limit: int = 100, timeout: int = 0) -> list[dict[str, Any]]:
        """GET /getUpdates — Poll for updates (alternative to webhook)."""
        params: dict[str, Any] = {"limit": limit, "timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        result = await self._request("GET", "getUpdates", params=params)
        return result if isinstance(result, list) else []
