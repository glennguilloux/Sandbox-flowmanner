"""
Communication Tools — Telegram Bot.

telegram_bot → Send messages and documents to Telegram chats and
    channels via the Telegram Bot API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import (
    BaseTool,
    ToolInput,
    ToolMetadata,
    ToolResult,
    is_placeholder,
    register_tool,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_DEFAULT_CHAT_ID = os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "")
TELEGRAM_TIMEOUT = int(os.getenv("TELEGRAM_TIMEOUT", "30"))


def _telegram_api_base(token: str | None = None) -> str:
    """Get the Telegram Bot API base URL."""
    t = token or TELEGRAM_BOT_TOKEN
    return f"https://api.telegram.org/bot{t}"


# ── Input ─────────────────────────────────────────────────────────────

TELEGRAM_ACTIONS = (
    "send_message",
    "send_photo",
    "send_document",
    "get_updates",
    "get_chat_info",
)


class TelegramBotInput(ToolInput):
    action: str = Field(
        ...,
        description=f"Action to perform: {', '.join(TELEGRAM_ACTIONS)}",
    )
    chat_id: str = Field(
        ...,
        description="Target chat/channel ID or @username",
    )
    message: str | None = Field(
        None,
        description="Message text (for send_message), max 4096 chars",
    )
    parse_mode: str | None = Field(
        "HTML",
        description="Parse mode: 'HTML', 'MarkdownV2', or None for plain text",
    )
    photo_url: str | None = Field(
        None,
        description="URL of photo to send (for send_photo)",
    )
    photo_caption: str | None = Field(
        None,
        description="Caption for photo (for send_photo)",
    )
    document_url: str | None = Field(
        None,
        description="URL of document to send (for send_document)",
    )
    document_caption: str | None = Field(
        None,
        description="Caption for document (for send_document)",
    )
    document_filename: str | None = Field(
        None,
        description="Display filename for the document",
    )
    attachment_url: str | None = Field(
        None,
        description="Generic file URL to send (auto-detects type: photo, document, video, audio)",
    )
    attachment_type: str | None = Field(
        None,
        description="Attachment type hint: 'photo', 'document', 'video', 'audio'",
    )
    disable_notification: bool = Field(
        False,
        description="Send message silently without notification",
    )
    reply_to_message_id: int | None = Field(
        None,
        description="ID of message to reply to",
    )
    inline_keyboard: list | None = Field(
        None,
        description="List of button rows for inline keyboard markup",
    )
    limit: int = Field(
        10,
        ge=1,
        le=100,
        description="Maximum number of updates to fetch (for get_updates)",
    )
    offset: int | None = Field(
        None,
        description="Update ID offset for pagination (for get_updates)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class TelegramBotTool(BaseTool):
    """Send messages and documents to Telegram via the Bot API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="telegram_bot",
            name="Telegram Bot",
            description=(
                "Send messages, photos, and documents to Telegram chats "
                "and channels via the Telegram Bot API. Supports HTML and "
                "MarkdownV2 formatting, silent delivery, and chat updates. "
                "Requires TELEGRAM_BOT_TOKEN env var."
            ),
            category="communication",
            input_schema=TelegramBotInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "integer"},
                    "chat": {"type": "object"},
                    "status": {"type": "string"},
                },
            },
            tags=[
                "telegram",
                "bot",
                "messaging",
                "chat",
                "communication",
                "notifications",
            ],
            requires_auth=True,
            timeout_seconds=TELEGRAM_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TelegramBotInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if validated.action not in TELEGRAM_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(TELEGRAM_ACTIONS)}",
            )

        if not TELEGRAM_BOT_TOKEN:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Telegram not configured. Set TELEGRAM_BOT_TOKEN.",
            )

        if is_placeholder(TELEGRAM_BOT_TOKEN):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "TELEGRAM_BOT_TOKEN is a placeholder. "
                    "Replace placeholder in .env with a real Telegram bot token "
                    "(from @BotFather on Telegram)."
                ),
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Telegram API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Telegram API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("telegram_bot failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: TelegramBotInput) -> dict[str, Any]:
        if validated.action == "send_message":
            return await self._send_message(validated)
        elif validated.action == "send_photo":
            return await self._send_photo(validated)
        elif validated.action == "send_document":
            return await self._send_document(validated)
        elif validated.action == "get_updates":
            return await self._get_updates(validated)
        elif validated.action == "get_chat_info":
            return await self._get_chat_info(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── Helpers ──────────────────────────────────────────────────

    def _resolve_chat_id(self, validated: TelegramBotInput) -> str:
        """Resolve chat_id (now required — no fallback needed)."""
        return validated.chat_id

    async def _call_api(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Call a Telegram Bot API method."""
        url = f"{_telegram_api_base()}/{method}"
        async with httpx.AsyncClient(timeout=TELEGRAM_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if not data.get("ok", False):
            return {"error": data.get("description", "Unknown API error")}
        return data.get("result", {})

    def _format_result(self, action: str, result: dict) -> dict[str, Any]:
        """Format a standard Telegram API result."""
        chat = result.get("chat", {})
        return {
            "action": action,
            "message_id": result.get("message_id"),
            "chat": {
                "id": chat.get("id"),
                "type": chat.get("type"),
                "title": chat.get("title", ""),
                "username": chat.get("username", ""),
            },
            "date": result.get("date"),
            "status": "sent",
        }

    # ── Action handlers ──────────────────────────────────────────

    async def _send_message(self, validated: TelegramBotInput) -> dict[str, Any]:
        """Send a text message to a Telegram chat."""
        if not validated.message:
            return {"error": "message is required for send_message"}

        payload: dict[str, Any] = {
            "chat_id": validated.chat_id,
            "text": validated.message,
            "disable_notification": validated.disable_notification,
        }
        if validated.parse_mode and validated.parse_mode != "None":
            payload["parse_mode"] = validated.parse_mode
        if validated.reply_to_message_id:
            payload["reply_to_message_id"] = validated.reply_to_message_id
        if validated.inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": validated.inline_keyboard}

        result = await self._call_api("sendMessage", payload)
        if "error" in result:
            return result
        return self._format_result("send_message", result)

    async def _send_photo(self, validated: TelegramBotInput) -> dict[str, Any]:
        """Send a photo to a Telegram chat."""
        if not validated.photo_url:
            return {"error": "photo_url is required for send_photo"}

        chat_id = self._resolve_chat_id(validated)
        if not chat_id:
            return {"error": "No chat_id. Set chat_id or TELEGRAM_DEFAULT_CHAT_ID."}

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "photo": validated.photo_url,
            "disable_notification": validated.disable_notification,
        }
        if validated.photo_caption:
            payload["caption"] = validated.photo_caption
        if validated.parse_mode:
            payload["parse_mode"] = validated.parse_mode

        result = await self._call_api("sendPhoto", payload)
        if "error" in result:
            return result
        return self._format_result("send_photo", result)

    async def _send_document(self, validated: TelegramBotInput) -> dict[str, Any]:
        """Send a document to a Telegram chat."""
        if not validated.document_url:
            return {"error": "document_url is required for send_document"}

        chat_id = self._resolve_chat_id(validated)
        if not chat_id:
            return {"error": "No chat_id. Set chat_id or TELEGRAM_DEFAULT_CHAT_ID."}

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "document": validated.document_url,
            "disable_notification": validated.disable_notification,
        }
        if validated.document_caption:
            payload["caption"] = validated.document_caption
        if validated.parse_mode:
            payload["parse_mode"] = validated.parse_mode
        if validated.document_filename:
            payload["filename"] = validated.document_filename

        result = await self._call_api("sendDocument", payload)
        if "error" in result:
            return result
        return self._format_result("send_document", result)

    async def _get_updates(self, validated: TelegramBotInput) -> dict[str, Any]:
        """Fetch recent updates from the bot."""
        payload: dict[str, Any] = {
            "limit": validated.limit,
            "timeout": 0,
        }
        if validated.offset is not None:
            payload["offset"] = validated.offset

        result = await self._call_api("getUpdates", payload)
        if "error" in result:
            return result
        updates: list[Any] = result if isinstance(result, list) else []
        return {
            "action": "get_updates",
            "update_count": len(updates),
            "updates": updates[: validated.limit],
        }

    async def _get_chat_info(self, validated: TelegramBotInput) -> dict[str, Any]:
        """Get information about a chat."""
        chat_id = self._resolve_chat_id(validated)
        if not chat_id:
            return {"error": "No chat_id. Set chat_id or TELEGRAM_DEFAULT_CHAT_ID."}

        result = await self._call_api("getChat", {"chat_id": chat_id})
        if "error" in result:
            return result

        return {
            "action": "get_chat_info",
            "chat": {
                "id": result.get("id"),
                "type": result.get("type"),
                "title": result.get("title", ""),
                "username": result.get("username", ""),
                "description": result.get("description", ""),
                "invite_link": result.get("invite_link", ""),
                "member_count": result.get("member_count"),
            },
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(TelegramBotTool())
