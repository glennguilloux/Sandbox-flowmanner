"""
Tool Handler Registry
Manages all available tool handlers
"""

import logging
from typing import Any

from .base_handler import BaseToolHandler

logger = logging.getLogger(__name__)


class ToolHandlerRegistry:
    """
    Registry for managing tool handlers

    Responsibilities:
    - Register tool handlers
    - Provide handler instances
    - Manage handler lifecycle
    - Cache handler instances
    """

    def __init__(self):
        self._handlers = {}
        self._handler_classes = {}
        self.logger = logging.getLogger(__name__)

    def register_handler(self, tool_id: str, handler_class):
        """
        Register a tool handler class

        Args:
            tool_id: Unique tool identifier
            handler_class: Handler class to register
        """
        if not issubclass(handler_class, BaseToolHandler):
            raise ValueError(f"Handler must inherit from BaseToolHandler: {handler_class}")

        self._handler_classes[tool_id] = handler_class
        self.logger.info(f"Registered handler for tool: {tool_id}")

    def get_handler(self, tool_id: str, **config) -> BaseToolHandler | None:
        """
        Get handler instance for tool

        Args:
            tool_id: Tool identifier
            **config: Handler configuration

        Returns:
            Handler instance or None if not found
        """
        # Check cache first
        if tool_id in self._handlers:
            return self._handlers[tool_id]

        # Create new instance
        if tool_id in self._handler_classes:
            handler_class = self._handler_classes[tool_id]
            handler = handler_class(**config)
            self._handlers[tool_id] = handler
            return handler

        self.logger.warning(f"No handler registered for tool: {tool_id}")
        return None

    def list_handlers(self, **config) -> dict[str, Any]:
        """
        List all registered handlers with their schemas

        Args:
            **config: Configuration for handler instantiation

        Returns:
            Dictionary of tool schemas
        """
        schemas = {}

        for tool_id in self._handler_classes:
            # Create temporary instance to get schema
            try:
                # Get handler-specific configuration
                handler_config = {}
                if tool_id == "execute_n8n_workflow":
                    handler_config = {
                        "n8n_base_url": config.get("n8n_base_url"),
                        "api_key": config.get("n8n_api_key"),
                    }
                elif tool_id == "execute_comfyui_workflow":
                    handler_config = {
                        "comfyui_base_url": config.get("comfyui_base_url"),
                        "client_id": config.get("comfyui_client_id", "workflow-agent"),
                    }

                handler = self.get_handler(tool_id, **handler_config)
                if handler:
                    schemas[tool_id] = handler.get_tool_schema()
            except Exception as e:
                self.logger.error(f"Failed to get schema for {tool_id}: {e}")

        return schemas

    async def close_all(self):
        """Close all handler sessions"""
        for handler in self._handlers.values():
            try:
                if hasattr(handler, "close"):
                    await handler.close()
            except Exception as e:
                self.logger.error(f"Error closing handler {handler.tool_id}: {e}")

        self._handlers.clear()
        self.logger.info("All handlers closed")


# Global registry instance
_registry = None


def get_tool_handler_registry() -> ToolHandlerRegistry:
    """Get global tool handler registry"""
    global _registry
    if _registry is None:
        _registry = ToolHandlerRegistry()
    return _registry
