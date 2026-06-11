"""
Integration Tools — Agent-callable tools for discovering and calling connected integrations.

list_integrations   → shows what integrations the current user has connected plus available actions
execute_integration → calls a specific integration action through the IntegrationBridge

These bridge the LangGraph agent to the Nexus capability system so the agent
can reason about and use a user's connected services (Slack, GitHub, Google,
Notion, Linear, Discord).
"""

from __future__ import annotations

import logging

from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)


# ── list_integrations ──────────────────────────────────────────────


class ListIntegrationsInput(ToolInput):
    """No required input — user_id is read from the agent context."""


class ListIntegrationsTool(BaseTool):
    """Discover what integrations the current user has connected."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="list_integrations",
            name="List Integrations",
            description=(
                "List all integrations the current user has connected, along with the "
                "available actions for each one. Use this to discover what external "
                "services (Slack, GitHub, Google, Notion, Linear, Discord) are available "
                "before calling execute_integration."
            ),
            category="integration",
            input_schema=ListIntegrationsInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "connected": {
                        "type": "array",
                        "description": "List of connected integrations",
                    },
                    "total": {"type": "integer"},
                },
            },
            tags=["integration", "discovery"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ListIntegrationsInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        # Extract user_id from agent context
        context = input_data.get("context", {})
        user_id = context.get("user_id") if isinstance(context, dict) else None

        if not user_id:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No user_id in agent context — cannot list integrations",
            )

        try:
            from sqlalchemy import select

            from app.database import AsyncSessionLocal
            from app.models.phase4_models import IntegrationConnection
            from app.services.integration_bridge import (
                _INTEGRATION_CAPABILITIES,
                _NON_OAUTH_CONFIGS,
            )

            connected: list[dict] = []

            # ── 1. Query active OAuth connections from DB ──────────
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(IntegrationConnection).where(
                        IntegrationConnection.user_id == user_id,
                        IntegrationConnection.is_active.is_(True),
                    )
                )
                connections = result.scalars().all()

                for conn in connections:
                    slug = conn.integration_slug
                    caps = _INTEGRATION_CAPABILITIES.get(slug, [])
                    connected.append(
                        {
                            "slug": slug,
                            "name": slug.title(),
                            "account_name": conn.account_name,
                            "account_id": conn.account_id,
                            "auth_type": "oauth2",
                            "actions": [
                                {
                                    "id": c["id"],
                                    "name": c["name"],
                                    "description": c["description"],
                                    "params": c.get("params", {}),
                                }
                                for c in caps
                            ],
                            "action_count": len(caps),
                        }
                    )

            # ── 2. Report non-OAuth integrations (API key / bot token) ──
            # Each _NON_OAUTH_CONFIGS entry maps to a settings attr that holds
            # the credential. Add a slug→setting mapping when adding new entries.
            from app.config import settings

            _NON_OAUTH_SETTINGS: dict[str, str] = {
                "linear": "LINEAR_API_KEY",
                "discord": "DISCORD_BOT_TOKEN",
            }

            for slug, cfg in _NON_OAUTH_CONFIGS.items():
                setting_key = _NON_OAUTH_SETTINGS.get(slug)
                if setting_key and getattr(settings, setting_key, ""):
                    # Only report if the credential is configured
                    caps = _INTEGRATION_CAPABILITIES.get(slug, [])
                    connected.append(
                        {
                            "slug": slug,
                            "name": slug.title(),
                            "account_name": cfg.get("name"),
                            "account_id": None,
                            "auth_type": cfg.get("auth_type"),
                            "actions": [
                                {
                                    "id": c["id"],
                                    "name": c["name"],
                                    "description": c["description"],
                                    "params": c.get("params", {}),
                                }
                                for c in caps
                            ],
                            "action_count": len(caps),
                        }
                    )

            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "connected": connected,
                    "total": len(connected),
                },
            )

        except Exception as e:
            logger.exception("list_integrations failed for user %s: %s", user_id, e)
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Failed to list integrations: {e}",
            )


# ── execute_integration ────────────────────────────────────────────


class ExecuteIntegrationInput(ToolInput):
    slug: str = Field(
        ...,
        description="Integration slug: 'slack', 'github', 'google', 'notion', 'linear', or 'discord'",
    )
    action: str = Field(
        ...,
        description="Action to call (e.g., 'send_message', 'create_issue', 'gmail_send')",
    )
    params: dict = Field(
        default_factory=dict,
        description="Parameters for the action (e.g., {'channel': 'C123', 'text': 'hello'})",
    )


class ExecuteIntegrationTool(BaseTool):
    """Execute a specific action on a user's connected integration."""

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="execute_integration",
            name="Execute Integration",
            description=(
                "Call an action on a user's connected integration. Use list_integrations "
                "first to discover available slugs and actions, then call this with "
                "the slug, action name, and required parameters."
            ),
            category="integration",
            input_schema=ExecuteIntegrationInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "data": {"type": "object"},
                    "error": {"type": "string"},
                },
            },
            tags=["integration", "action"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ExecuteIntegrationInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        # Extract user_id from agent context
        context = input_data.get("context", {})
        user_id = context.get("user_id") if isinstance(context, dict) else None

        if not user_id:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="No user_id in agent context — cannot execute integration action",
            )

        slug = validated.slug
        action = validated.action
        params = validated.params

        try:
            from app.services.integration_bridge import get_integration_bridge

            bridge = get_integration_bridge()
            result = await bridge.execute_integration_action(
                user_id=user_id,
                slug=slug,
                action=action,
                params=params,
            )

            if result.success:
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "success": True,
                        "data": result.data,
                    },
                    metadata={
                        "integration": slug,
                        "action": action,
                        "status_code": result.status_code,
                    },
                )
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"{slug}/{action} failed: {result.error}",
                    metadata={
                        "integration": slug,
                        "action": action,
                        "status_code": result.status_code,
                    },
                )

        except Exception as e:
            logger.exception(
                "execute_integration failed for user %s, %s/%s: %s",
                user_id,
                slug,
                action,
                e,
            )
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error=f"Integration execution failed: {e}",
            )


# ── Register ────────────────────────────────────────────────────────

register_tool(ListIntegrationsTool())
register_tool(ExecuteIntegrationTool())
