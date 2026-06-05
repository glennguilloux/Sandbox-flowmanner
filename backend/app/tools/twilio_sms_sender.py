"""
Communication Tools — Twilio SMS Sender.

twilio_sms_sender → Dispatch SMS text messages for urgent alerts or
    marketing via the Twilio REST API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, is_placeholder, register_tool

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
TWILIO_TIMEOUT = int(os.getenv("TWILIO_TIMEOUT", "30"))

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


# ── Input ─────────────────────────────────────────────────────────────

TWILIO_ACTIONS = ("send_sms",)


class TwilioSmsSenderInput(ToolInput):
    action: str = Field(
        "send_sms",
        description="Action to perform: 'send_sms'",
    )
    to: str = Field(
        ...,
        description="Destination phone number in E.164 format (e.g., '+14155551234')",
    )
    body: str = Field(
        ...,
        description="SMS message body content",
    )
    from_number: str | None = Field(
        None,
        description=f"Sender phone number in E.164 format (defaults to TWILIO_FROM_NUMBER env var)",
    )
    status_callback_url: str | None = Field(
        None,
        description="URL to receive delivery status webhook callbacks",
    )
    media_urls: list[str] | None = Field(
        None,
        description="List of media URLs to attach (max 10 URLs)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class TwilioSmsSenderTool(BaseTool):
    """Send SMS messages via the Twilio REST API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="twilio_sms_sender",
            name="Twilio SMS Sender",
            description=(
                "Dispatch SMS text messages for urgent alerts or marketing "
                "via the Twilio REST API. Supports delivery status callbacks. "
                "Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and "
                "TWILIO_FROM_NUMBER env vars."
            ),
            category="communication",
            input_schema=TwilioSmsSenderInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "message_sid": {"type": "string"},
                    "status": {"type": "string"},
                    "to": {"type": "string"},
                },
            },
            tags=["sms", "twilio", "text", "messaging", "communication", "alerts"],
            requires_auth=True,
            timeout_seconds=TWILIO_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = TwilioSmsSenderInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in TWILIO_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(TWILIO_ACTIONS)}",
            )

        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Twilio not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.",
            )

        if is_placeholder(TWILIO_ACCOUNT_SID) or is_placeholder(TWILIO_AUTH_TOKEN):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "Twilio credentials contain a placeholder. "
                    "Replace placeholder in .env with real TWILIO_ACCOUNT_SID and "
                    "TWILIO_AUTH_TOKEN values "
                    "(from https://console.twilio.com → Account Info)."
                ),
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Twilio API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Twilio API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("twilio_sms_sender failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(
        self, validated: TwilioSmsSenderInput
    ) -> dict[str, Any]:
        if validated.action == "send_sms":
            return await self._send_sms(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── Action handlers ──────────────────────────────────────────

    async def _send_sms(self, validated: TwilioSmsSenderInput) -> dict[str, Any]:
        """Send an SMS message via the Twilio API."""
        from_number = validated.from_number or TWILIO_FROM_NUMBER
        if not from_number:
            return {"error": "No sender number. Set from_number or TWILIO_FROM_NUMBER."}

        url = (
            f"{TWILIO_API_BASE}/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        )

        # Twilio uses form-encoded POST with Basic auth
        form_data = {
            "To": validated.to,
            "From": from_number,
            "Body": validated.body,
        }
        if validated.status_callback_url:
            form_data["StatusCallback"] = validated.status_callback_url
        if validated.media_urls:
            for i, media_url in enumerate(validated.media_urls[:10]):
                form_data[f"MediaUrl{i}"] = media_url

        auth = httpx.BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        async with httpx.AsyncClient(timeout=TWILIO_TIMEOUT) as client:
            resp = await client.post(url, data=form_data, auth=auth)
            resp.raise_for_status()
            data = resp.json()

        return {
            "action": "send_sms",
            "message_sid": data.get("sid", ""),
            "status": data.get("status", "queued"),
            "to": data.get("to", validated.to),
            "from": data.get("from", from_number),
            "direction": data.get("direction", ""),
            "num_segments": int(data.get("num_segments", 1)),
            "price": data.get("price", ""),
            "date_created": data.get("date_created", ""),
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(TwilioSmsSenderTool())
