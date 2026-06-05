"""
Communication Tools — SendGrid Campaign.

sendgrid_campaign → Trigger transactional email templates and send
    emails via the SendGrid Mail Send API v3.
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

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL", "")
SENDGRID_FROM_NAME = os.getenv("SENDGRID_FROM_NAME", "")
SENDGRID_TIMEOUT = int(os.getenv("SENDGRID_TIMEOUT", "30"))

SENDGRID_API_BASE = "https://api.sendgrid.com/v3"


# ── Input ─────────────────────────────────────────────────────────────

SENDGRID_ACTIONS = ("send", "send_template")


class SendgridCampaignInput(ToolInput):
    action: str = Field(
        "send",
        description="Action: 'send' (custom email) or 'send_template' (transactional template)",
    )
    to: list[str] = Field(
        ...,
        description="Recipient email addresses",
    )
    subject: str | None = Field(
        None,
        description="Email subject line (required for 'send' action)",
    )
    body: str | None = Field(
        None,
        description="Email body content — plain text or HTML (for 'send' action)",
    )
    html: bool = Field(
        False,
        description="Set True if body is HTML formatted",
    )
    template_id: str | None = Field(
        None,
        description="SendGrid dynamic template ID (required for 'send_template' action)",
    )
    template_data: dict[str, Any] | None = Field(
        None,
        description="Dynamic template substitution data (for 'send_template')",
    )
    from_email: str | None = Field(
        None,
        description=f"Sender email address (defaults to SENDGRID_FROM_EMAIL env var)",
    )
    from_name: str | None = Field(
        None,
        description=f"Sender display name (defaults to SENDGRID_FROM_NAME env var)",
    )
    cc: str | None = Field(
        None,
        description="CC email address(es), comma-separated",
    )
    bcc: str | None = Field(
        None,
        description="BCC email address(es), comma-separated",
    )
    reply_to: str | None = Field(
        None,
        description="Reply-To email address",
    )
    attachments: list[dict[str, str]] | None = Field(
        None,
        description="List of attachments with 'filename', 'content' (base64), 'type' (MIME)",
    )
    categories: list[str] | None = Field(
        None,
        description="Analytics tracking categories for SendGrid",
    )
    send_at: int | None = Field(
        None,
        description="Unix timestamp to schedule delivery (max 72 hours in the future)",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class SendgridCampaignTool(BaseTool):
    """Send transactional emails via SendGrid v3 API."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="sendgrid_campaign",
            name="SendGrid Campaign",
            description=(
                "Trigger transactional email templates and send custom emails "
                "via the SendGrid Mail Send API v3. Supports dynamic templates, "
                "HTML/plain text, CC/BCC, attachments. "
                "Requires SENDGRID_API_KEY env var."
            ),
            category="communication",
            input_schema=SendgridCampaignInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "message": {"type": "string"},
                },
            },
            tags=["email", "sendgrid", "transactional", "templates", "campaign", "marketing"],
            requires_auth=True,
            timeout_seconds=SENDGRID_TIMEOUT + 10,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SendgridCampaignInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        if validated.action not in SENDGRID_ACTIONS:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Unknown action: '{validated.action}'. Use: {', '.join(SENDGRID_ACTIONS)}",
            )

        if not SENDGRID_API_KEY:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="SendGrid not configured. Set SENDGRID_API_KEY.",
            )

        if is_placeholder(SENDGRID_API_KEY):
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=(
                    "SENDGRID_API_KEY is a placeholder. "
                    "Replace placeholder in .env with a real SendGrid API key "
                    "(from https://app.sendgrid.com/settings/api_keys)."
                ),
            )

        try:
            result = await self._execute_action(validated)
            return ToolResult.success_result(tool_id=self.tool_id, result=result)
        except httpx.HTTPStatusError as e:
            logger.error("SendGrid API error: %s", e)
            detail = ""
            try:
                detail = str(e.response.json())
            except Exception:
                detail = e.response.text[:500]
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"SendGrid API error ({e.response.status_code}): {detail}",
            )
        except Exception as e:
            logger.warning("sendgrid_campaign failed: %s", e)
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── _execute_action ──────────────────────────────────────────

    async def _execute_action(
        self, validated: SendgridCampaignInput
    ) -> dict[str, Any]:
        if validated.action == "send":
            return await self._send_email(validated)
        elif validated.action == "send_template":
            return await self._send_template(validated)
        else:
            return {"error": f"Unhandled action: {validated.action}"}

    # ── Payload builders ─────────────────────────────────────────

    def _parse_recipients(self, to_addrs: list[str]) -> list[dict[str, str]]:
        """Convert list of emails into SendGrid personalization format."""
        return [
            {"email": addr.strip()}
            for addr in to_addrs
            if addr.strip()
        ]

    def _build_personalizations(
        self, validated: SendgridCampaignInput
    ) -> list[dict[str, Any]]:
        """Build the personalizations array for SendGrid v3."""
        p: dict[str, Any] = {
            "to": self._parse_recipients(validated.to),
        }
        if validated.cc:
            p["cc"] = self._parse_recipients(validated.cc)
        if validated.bcc:
            p["bcc"] = self._parse_recipients(validated.bcc)
        if validated.subject and validated.action == "send":
            p["subject"] = validated.subject
        if validated.template_data:
            p["dynamic_template_data"] = validated.template_data
        return [p]

    def _build_from(self, validated: SendgridCampaignInput) -> dict[str, str]:
        """Build the from object."""
        frm: dict[str, str] = {
            "email": validated.from_email or SENDGRID_FROM_EMAIL,
        }
        name = validated.from_name or SENDGRID_FROM_NAME
        if name:
            frm["name"] = name
        return frm

    def _build_attachments(self, validated: SendgridCampaignInput) -> list[dict]:
        """Build the attachments array."""
        if not validated.attachments:
            return []
        result = []
        for att in validated.attachments:
            result.append({
                "content": att.get("content", ""),
                "type": att.get("type", "application/octet-stream"),
                "filename": att.get("filename", "attachment"),
                "disposition": "attachment",
            })
        return result

    # ── Action handlers ──────────────────────────────────────────

    async def _send_email(self, validated: SendgridCampaignInput) -> dict[str, Any]:
        """Send a custom email via SendGrid."""
        if not validated.subject:
            return {"error": "subject is required for 'send' action"}
        if not validated.body:
            return {"error": "body is required for 'send' action"}

        content_type = "text/html" if validated.html else "text/plain"
        payload: dict[str, Any] = {
            "personalizations": self._build_personalizations(validated),
            "from": self._build_from(validated),
            "content": [{"type": content_type, "value": validated.body}],
        }

        if validated.reply_to:
            payload["reply_to"] = {"email": validated.reply_to}
        attachments = self._build_attachments(validated)
        if attachments:
            payload["attachments"] = attachments

        if validated.categories:
            payload["categories"] = validated.categories
        if validated.send_at:
            payload["send_at"] = validated.send_at

        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=SENDGRID_TIMEOUT) as client:
            resp = await client.post(
                f"{SENDGRID_API_BASE}/mail/send",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()

        return {
            "action": "send",
            "status": "accepted",
            "message": "Email queued for delivery",
            "to": ", ".join(validated.to),
            "subject": validated.subject,
        }

    async def _send_template(self, validated: SendgridCampaignInput) -> dict[str, Any]:
        """Send a transactional email using a SendGrid dynamic template."""
        if not validated.template_id:
            return {"error": "template_id is required for 'send_template' action"}

        payload: dict[str, Any] = {
            "personalizations": self._build_personalizations(validated),
            "from": self._build_from(validated),
            "template_id": validated.template_id,
        }

        if validated.reply_to:
            payload["reply_to"] = {"email": validated.reply_to}
        attachments = self._build_attachments(validated)
        if attachments:
            payload["attachments"] = attachments

        if validated.categories:
            payload["categories"] = validated.categories
        if validated.send_at:
            payload["send_at"] = validated.send_at

        headers = {
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=SENDGRID_TIMEOUT) as client:
            resp = await client.post(
                f"{SENDGRID_API_BASE}/mail/send",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()

        return {
            "action": "send_template",
            "status": "accepted",
            "message": "Template email queued for delivery",
            "template_id": validated.template_id,
            "to": ", ".join(validated.to),
        }


# ── Register ──────────────────────────────────────────────────────────

register_tool(SendgridCampaignTool())
