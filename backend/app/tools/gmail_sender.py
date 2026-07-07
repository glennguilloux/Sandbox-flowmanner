"""
Communication Tools — Gmail Sender.

gmail_sender → Draft and send formatted emails directly from connected
    Gmail accounts via the Gmail API.
"""

from __future__ import annotations

import base64
import logging
import os
from email.mime.text import MIMEText
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

GMAIL_SERVICE_ACCOUNT_FILE = os.getenv("GMAIL_SERVICE_ACCOUNT_FILE", "")
GMAIL_DELEGATED_ACCOUNT = os.getenv("GMAIL_DELEGATED_ACCOUNT", "")
GMAIL_TIMEOUT = int(os.getenv("GMAIL_TIMEOUT", "30"))

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


# ── Input ─────────────────────────────────────────────────────────────

GMAIL_ACTIONS = ("send",)


class GmailSenderInput(ToolInput):
    action: str = Field(
        "send",
        description="Action to perform: 'send'",
    )
    to: list[str] = Field(
        ...,
        description="Recipient email addresses",
    )
    subject: str = Field(
        ...,
        description="Email subject line",
    )
    body: str = Field(
        ...,
        description="Email body content (plain text or HTML)",
    )
    is_html: bool = Field(
        False,
        description="Set True if body is HTML formatted",
    )
    cc: list[str] | None = Field(
        None,
        description="CC recipient email addresses",
    )
    bcc: list[str] | None = Field(
        None,
        description="BCC recipient email addresses",
    )
    sender: str | None = Field(
        None,
        description="Sender email address (defaults to GMAIL_DELEGATED_ACCOUNT)",
    )
    attachments: list[dict[str, str]] | None = Field(
        None,
        description="List of attachments with 'filename', 'content' (base64), 'mime_type'",
    )
    reply_to: str | None = Field(
        None,
        description="Reply-To header email address",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class GmailSenderTool(BaseTool):
    """Send formatted emails via Gmail API."""

    def __init__(self):
        metadata = ToolMetadata(
            visibility="hidden",
            tool_id="gmail_sender",
            name="Gmail Sender",
            description=(
                "Draft and send formatted emails directly from connected "
                "Gmail accounts via the Gmail API. Supports plain text and "
                "HTML bodies, CC/BCC recipients. Requires Gmail API "
                "credentials (service account or API key)."
            ),
            category="communication",
            input_schema=GmailSenderInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string"},
                    "thread_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
            tags=["email", "gmail", "communication", "messaging", "send"],
            requires_auth=True,
            timeout_seconds=GMAIL_TIMEOUT + 15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = GmailSenderInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        if validated.action not in GMAIL_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(GMAIL_ACTIONS)}",
            )

        if not GMAIL_SERVICE_ACCOUNT_FILE or not GMAIL_DELEGATED_ACCOUNT:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=("Gmail not configured. Set GMAIL_SERVICE_ACCOUNT_FILE and GMAIL_DELEGATED_ACCOUNT."),
            )

        if is_placeholder(GMAIL_SERVICE_ACCOUNT_FILE) or is_placeholder(GMAIL_DELEGATED_ACCOUNT):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "Gmail credentials contain a placeholder. "
                    "Replace placeholder in .env with real GMAIL_SERVICE_ACCOUNT_FILE "
                    "(path to service account JSON) and GMAIL_DELEGATED_ACCOUNT "
                    "(email for domain-wide delegation from https://console.cloud.google.com)."
                ),
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("Gmail API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Gmail API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("gmail_sender failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(self, validated: GmailSenderInput) -> dict[str, Any]:
        if validated.action == "send":
            return await self._send_email(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── Auth helpers ─────────────────────────────────────────────

    async def _get_access_token(self) -> str:
        """Get an OAuth2 access token for Gmail API via service account."""
        if not GMAIL_SERVICE_ACCOUNT_FILE or not GMAIL_DELEGATED_ACCOUNT:
            raise ValueError("Gmail not configured. Set GMAIL_SERVICE_ACCOUNT_FILE and GMAIL_DELEGATED_ACCOUNT.")

        import json

        from google.auth.transport.requests import Request
        from google.oauth2.service_account import Credentials

        with open(GMAIL_SERVICE_ACCOUNT_FILE) as f:
            creds_dict = json.load(f)

        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=GMAIL_SCOPES,
            subject=GMAIL_DELEGATED_ACCOUNT,
        )

        # Run the blocking google-auth refresh in a thread
        import asyncio

        await asyncio.to_thread(credentials.refresh, Request())
        return credentials.token

    # ── Email builder ────────────────────────────────────────────

    def _build_mime_message(self, validated: GmailSenderInput) -> str:
        """Build a MIME email message and return base64url-encoded string."""
        if validated.is_html:
            msg = MIMEText(validated.body, "html", "utf-8")
        else:
            msg = MIMEText(validated.body, "plain", "utf-8")

        msg["To"] = ", ".join(validated.to)
        msg["Subject"] = validated.subject
        sender = validated.sender or GMAIL_DELEGATED_ACCOUNT
        msg["From"] = sender
        if validated.cc:
            msg["Cc"] = ", ".join(validated.cc)
        if validated.bcc:
            msg["Bcc"] = ", ".join(validated.bcc)
        if validated.reply_to:
            msg["Reply-To"] = validated.reply_to

        raw_bytes = msg.as_bytes()
        return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

    # ── Action handlers ──────────────────────────────────────────

    async def _send_email(self, validated: GmailSenderInput) -> dict[str, Any]:
        """Send an email via the Gmail API."""
        sender = validated.sender or GMAIL_DELEGATED_ACCOUNT
        if not sender:
            return {"error": "No sender address. Set sender or GMAIL_DELEGATED_ACCOUNT."}

        token = await self._get_access_token()
        raw_base64 = self._build_mime_message(validated)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"raw": raw_base64}

        async with httpx.AsyncClient(timeout=GMAIL_TIMEOUT) as client:
            resp = await client.post(
                f"{GMAIL_API_BASE}/users/me/messages/send",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "action": "send",
            "message_id": data.get("id", ""),
            "thread_id": data.get("threadId", ""),
            "label_ids": data.get("labelIds", []),
            "status": "sent",
            "to": ", ".join(validated.to),
            "subject": validated.subject,
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(GmailSenderTool())
