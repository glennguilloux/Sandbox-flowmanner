"""
API & SaaS Integration Tools — Slack Communicator.

slack_communicator → Read channels, send messages, and wait for human-in-the-loop approvals.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


class SlackCommunicatorInput(ToolInput):
    action: str = Field(
        ...,
        description="Action: 'send_message', 'list_channels', 'list_users', 'post_reply', 'add_reaction'",
    )
    channel: str | None = Field(
        None, description="Channel name or ID (e.g., '#general' or 'C01234567')"
    )
    message: str | None = Field(None, description="Message text to send")
    thread_ts: str | None = Field(None, description="Thread timestamp for replies")
    emoji: str | None = Field(None, description="Emoji name for reactions (without colons)")
    message_ts: str | None = Field(None, description="Message timestamp for reactions")
    limit: int = Field(100, ge=1, le=1000, description="Max results for list actions")
    bot_token: str | None = Field(
        None, description="Slack bot token (uses SLACK_BOT_TOKEN env var if omitted)"
    )


class SlackCommunicatorTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="slack_communicator",
            name="Slack Communicator",
            description="Read channels, send messages, and wait for human-in-the-loop approvals",
            category="api-integrations",
            input_schema=SlackCommunicatorInput.schema_extra(),
            tags=["slack", "messaging", "communication", "integration"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = SlackCommunicatorInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        token = validated.bot_token or os.getenv("SLACK_BOT_TOKEN", "")
        if not token:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No Slack token. Set SLACK_BOT_TOKEN env var or pass bot_token.",
            )

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        action = validated.action.lower().strip()

        try:
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                if action == "send_message":
                    return await self._send_message(client, validated)
                elif action == "list_channels":
                    return await self._list_channels(client, validated)
                elif action == "list_users":
                    return await self._list_users(client, validated)
                elif action == "post_reply":
                    return await self._post_reply(client, validated)
                elif action == "add_reaction":
                    return await self._add_reaction(client, validated)
                else:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=f"Unknown action: {action}",
                    )
        except Exception as e:
            logger.exception("slack_communicator failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    async def _send_message(self, client: httpx.AsyncClient, v) -> ToolResult:
        if not v.channel or not v.message:
            return ToolResult.error_result(tool_id=self.tool_id, error="channel and message are required")
        payload: dict[str, Any] = {"channel": v.channel, "text": v.message}
        if v.thread_ts:
            payload["thread_ts"] = v.thread_ts
        r = await client.post("https://slack.com/api/chat.postMessage", json=payload)
        data = r.json()
        if not data.get("ok"):
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Slack error: {data.get('error')}")
        return ToolResult.success_result(tool_id=self.tool_id, result={
            "action": "send_message", "channel": v.channel,
            "ts": data.get("ts"), "message": v.message,
        })

    async def _list_channels(self, client: httpx.AsyncClient, v) -> ToolResult:
        r = await client.get("https://slack.com/api/conversations.list", params={"limit": v.limit})
        data = r.json()
        if not data.get("ok"):
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Slack error: {data.get('error')}")
        channels = [{"id": c["id"], "name": c["name"], "is_private": c.get("is_private", False)}
                     for c in data.get("channels", [])]
        return ToolResult.success_result(tool_id=self.tool_id, result={
            "action": "list_channels", "count": len(channels), "channels": channels,
        })

    async def _list_users(self, client: httpx.AsyncClient, v) -> ToolResult:
        r = await client.get("https://slack.com/api/users.list", params={"limit": v.limit})
        data = r.json()
        if not data.get("ok"):
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Slack error: {data.get('error')}")
        users = [{"id": u["id"], "name": u.get("real_name", u.get("name", "")), "email": u.get("profile", {}).get("email", "")}
                  for u in data.get("members", [])]
        return ToolResult.success_result(tool_id=self.tool_id, result={
            "action": "list_users", "count": len(users), "users": users,
        })

    async def _post_reply(self, client: httpx.AsyncClient, v) -> ToolResult:
        if not v.channel or not v.message or not v.thread_ts:
            return ToolResult.error_result(tool_id=self.tool_id, error="channel, message, and thread_ts are required")
        r = await client.post("https://slack.com/api/chat.postMessage", json={
            "channel": v.channel, "text": v.message, "thread_ts": v.thread_ts,
        })
        data = r.json()
        if not data.get("ok"):
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Slack error: {data.get('error')}")
        return ToolResult.success_result(tool_id=self.tool_id, result={
            "action": "post_reply", "channel": v.channel, "thread_ts": v.thread_ts, "ts": data.get("ts"),
        })

    async def _add_reaction(self, client: httpx.AsyncClient, v) -> ToolResult:
        if not v.channel or not v.emoji or not v.message_ts:
            return ToolResult.error_result(tool_id=self.tool_id, error="channel, emoji, and message_ts are required")
        r = await client.post("https://slack.com/api/reactions.add", json={
            "channel": v.channel, "name": v.emoji, "timestamp": v.message_ts,
        })
        data = r.json()
        if not data.get("ok"):
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Slack error: {data.get('error')}")
        return ToolResult.success_result(tool_id=self.tool_id, result={
            "action": "add_reaction", "channel": v.channel, "emoji": v.emoji, "ok": True,
        })


register_tool(SlackCommunicatorTool())
