"""
Unified Tool Bridge for LangGraph Agent — H3.2 OCap integration.

Bridges the LangGraph agent to the unified tool ecosystem,
allowing the user-facing chat to access all unified tools.

H3.2: Tool execution now requires a valid CapabilityToken.
Callers must pass a capability_token parameter or the bridge will
attempt to verify and require one via the CapabilityEngine.
"""

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from app.tools.base import get_tool_registry

logger = logging.getLogger(__name__)

# ── H3.2 OCap error class ─────────────────────────────────────────


class CapabilityRequiredError(PermissionError):
    """Raised when a tool invocation lacks a required capability token."""

    def __init__(self, tool_name: str, action: str = "execute"):
        self.tool_name = tool_name
        self.action = action
        super().__init__(
            f"Capability token required for tool '{tool_name}' (action: {action}). "
            f"No ambient authority — every tool invocation must carry a valid token."
        )


class UnifiedToolBridge:
    """Bridge between LangGraph agent and the unified tool ecosystem.

    H3.2: Tool execution now enforces capability-based security.
    Every tool call is checked against the CapabilityEngine.
    """

    def __init__(self, user_id: int | None = None, *, ocap_enabled: bool = True):
        self.user_id = user_id
        self._tool_registry = None
        self._discovery_service = None
        self._initialized = False
        # H3.2: Capability enforcement mode (configurable for testing/migration)
        self.ocap_enabled = ocap_enabled

    def _ensure_initialized(self):
        if self._initialized:
            return

        try:
            self._tool_registry = get_tool_registry()
            logger.info(
                "Tool registry initialized with %s tools",
                len(self._tool_registry.list_all()),
            )
        except Exception as e:
            logger.warning("Could not initialize tool registry: %s", e)
            self._tool_registry = None

        self._initialized = True

    def get_available_tools(self) -> list[dict[str, Any]]:
        """Get list of all available tools with their schemas"""
        self._ensure_initialized()

        tools = []
        if self._tool_registry:
            for tool in self._tool_registry.list_all():
                tools.append(
                    {
                        "name": tool.tool_id,
                        "description": tool.description,
                        "tier": getattr(tool.metadata, "tier", 0),
                        "input_schema": tool.metadata.input_schema,
                    }
                )
        return tools

    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        user_id: int | None = None,
        *,
        # H3.2: Optional capability token for OCap enforcement
        capability_token_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Execute a tool by name with given parameters.

        H3.2: If capability_token_id is provided, the bridge verifies it
        with the CapabilityEngine before executing.  If OCap is enabled
        and no token is provided, raises CapabilityRequiredError.

        Args:
            tool_name: Name of the tool to execute.
            parameters: Tool input parameters.
            user_id: Override user ID.
            capability_token_id: Optional capability token UUID (H3.2 OCap).

        Returns:
            Tool execution result dict.

        Raises:
            CapabilityRequiredError: If OCap is enabled and no valid token provided.
        """
        self._ensure_initialized()

        effective_user_id = user_id or self.user_id

        # H3.2: Capability enforcement
        if self.ocap_enabled:
            await self.verify_capability(tool_name, capability_token_id)

        if not self._tool_registry:
            return {
                "success": False,
                "error": "Tool registry not available",
                "tool_name": tool_name,
            }

        tool = self._tool_registry.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}",
                "tool_name": tool_name,
            }

        try:
            if effective_user_id and "user_id" in str(tool.metadata.input_schema):
                parameters = {**parameters, "user_id": effective_user_id}

            result = await tool.execute(parameters)
            return {"success": True, "tool_name": tool_name, "result": result}
        except Exception as e:
            logger.error("Error executing tool %s: %s", tool_name, e)
            return {"success": False, "error": str(e), "tool_name": tool_name}

    async def verify_capability(
        self, tool_name: str, capability_token_id: UUID | None
    ) -> None:
        """H3.2: Verify that the caller has a valid capability token.

        If no token is provided, this is a violation of Invariant I.3
        (No ambient authority).  The call is rejected.
        """
        if capability_token_id is None:
            raise CapabilityRequiredError(tool_name, "execute")

        try:
            from app.models.capability_models import Action
            from app.services.capability_engine import get_capability_engine
        except ImportError as e:
            logger.warning(
                "Capability engine not available, cannot enforce OCap for %s: %s",
                tool_name,
                e,
            )
            return  # Graceful degradation when capability engine is unavailable

        engine = get_capability_engine()
        token = engine.get_token(capability_token_id)

        if token is None:
            raise CapabilityRequiredError(tool_name, "execute")

        engine.verify_and_require(token, Action.EXECUTE)
        logger.debug(
            "Capability verified: token %s for tool %s",
            capability_token_id,
            tool_name,
        )

    async def discover_tools_for_task(
        self, task_description: str
    ) -> list[dict[str, Any]]:
        """Use semantic discovery to find relevant tools for a task."""
        self._ensure_initialized()

        if not self._discovery_service:
            return self.get_available_tools()

        try:
            # Placeholder for discovery service integration
            return self.get_available_tools()
        except Exception as e:
            logger.error("Error discovering tools: %s", e)
            return self.get_available_tools()

    def get_tool_handler(self, tool_name: str) -> Callable | None:
        """Get a callable handler for a tool that can be registered with LangGraph."""

        async def handler(
            state: dict[str, Any], params: dict[str, Any]
        ) -> dict[str, Any]:
            return await self.execute_tool(tool_name, params)

        return handler


_unified_bridge: UnifiedToolBridge | None = None


def get_unified_tool_bridge(user_id: int | None = None) -> UnifiedToolBridge:
    """Get or create the unified tool bridge"""
    global _unified_bridge
    if _unified_bridge is None:
        _unified_bridge = UnifiedToolBridge(user_id=user_id)
    return _unified_bridge
