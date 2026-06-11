"""
Integration Tool Handlers — BaseToolHandler subclasses for integration discovery & execution.

Registered with the ToolHandlerRegistry so the LangGraph agent can call
list_integrations and execute_integration at runtime.
"""

from __future__ import annotations

from typing import Any

from .base_handler import BaseToolHandler


class ListIntegrationsHandler(BaseToolHandler):
    """Handler that discovers which integrations the current user has connected."""

    def __init__(self):
        super().__init__("list_integrations", "List Integrations")

    async def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, str | None]:
        # No required parameters — user_id comes from context
        return True, None

    async def execute(self, parameters: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        user_context = (context or {}).get("user_context", {})
        user_id = user_context.get("user_id")
        if not user_id:
            return {"success": False, "error": "User ID required"}

        from app.tools.integration import ListIntegrationsTool

        tool = ListIntegrationsTool()
        input_data = {
            "context": {"user_id": user_id},
        }
        result = await tool.execute(input_data)

        if result.success:
            return {
                "success": True,
                "data": result.result,
            }
        return {
            "success": False,
            "error": result.error,
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "description": (
                "List all integrations the current user has connected "
                "(Slack, GitHub, Google, Notion, Linear, Discord) along "
                "with available actions for each."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
            "requires_approval": False,
            "category": "integration",
        }

    async def close(self):
        pass


class ExecuteIntegrationHandler(BaseToolHandler):
    """Handler that calls an action on a user's connected integration."""

    def __init__(self):
        super().__init__("execute_integration", "Execute Integration Action")

    async def validate_parameters(self, parameters: dict[str, Any]) -> tuple[bool, str | None]:
        if "slug" not in parameters:
            return False, "Missing required field: slug"
        if "action" not in parameters:
            return False, "Missing required field: action"
        return True, None

    async def execute(self, parameters: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        user_context = (context or {}).get("user_context", {})
        user_id = user_context.get("user_id")
        if not user_id:
            return {"success": False, "error": "User ID required"}

        from app.tools.integration import ExecuteIntegrationTool

        tool = ExecuteIntegrationTool()
        input_data = {
            "slug": parameters.get("slug"),
            "action": parameters.get("action"),
            "params": parameters.get("params", {}),
            "context": {"user_id": user_id},
        }
        result = await tool.execute(input_data)

        if result.success:
            return {
                "success": True,
                "data": result.result,
            }
        return {
            "success": False,
            "error": result.error,
        }

    def get_tool_schema(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "description": (
                "Call an action on a user's connected integration. "
                "Use list_integrations first to discover available slugs and actions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Integration slug: slack, github, google, notion, linear, discord",
                    },
                    "action": {
                        "type": "string",
                        "description": "Action to call (e.g., send_message, create_issue, gmail_send)",
                    },
                    "params": {
                        "type": "object",
                        "description": "Parameters for the action",
                    },
                },
                "required": ["slug", "action"],
            },
            "requires_approval": True,
            "category": "integration",
        }

    async def close(self):
        pass
