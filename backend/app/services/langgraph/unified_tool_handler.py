#!/usr/bin/env python3
"""
Unified Tool Handler for LangGraph Agent

This handler bridges LangGraph tool calls to the 30-tool ecosystem.
It can be registered as a catch-all handler for any unified tool.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class UnifiedToolHandler:
    """
    Handler for executing unified tools from LangGraph agent.

    This allows the user-facing chat to access all 30 tools through
    the LangGraph agent's tool execution pipeline.
    """

    def __init__(self, user_id: int | None = None):
        self.user_id = user_id
        self._bridge = None

    @property
    def bridge(self):
        """Lazy load the unified tool bridge"""
        if self._bridge is None:
            from app.services.unified_tool_bridge import get_unified_tool_bridge

            self._bridge = get_unified_tool_bridge(user_id=self.user_id)
        return self._bridge

    async def execute(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a unified tool.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool input parameters
            state: Optional LangGraph state for context

        Returns:
            Tool execution result
        """
        # Extract user_id from state if available
        user_id = self.user_id
        if state and "user_id" in state:
            user_id = state.get("user_id")

        return await self.bridge.execute_tool(tool_name=tool_name, parameters=parameters, user_id=user_id)

    def get_tool_schemas(self) -> list:
        """
        Get JSON schemas for all available tools.

        This can be used to register tools with the LangGraph agent.
        """
        tools = self.bridge.get_available_tools()
        schemas = []

        for tool in tools:
            schema = {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            }
            schemas.append(schema)

        return schemas


def get_unified_tool_handler(user_id: int | None = None) -> UnifiedToolHandler:
    """Factory function to create unified tool handler"""
    return UnifiedToolHandler(user_id=user_id)
