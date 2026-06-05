"""Base classes for FlowManner plugins.

Plugin authors subclass :class:`BaseNodeHandler` for each custom node type,
then bundle them into a :class:`BasePlugin` subclass.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from app.sdk.context import PluginContext

logger = logging.getLogger(__name__)


class BaseNodeHandler(ABC):
    """Abstract base for a plugin-provided node type handler.

    Plugin authors must set ``node_type_id`` and implement :meth:`execute`.

    Example::

        class JsonTransformHandler(BaseNodeHandler):
            node_type_id = "json_transform"

            async def execute(self, context: PluginContext) -> dict:
                data = context.get_input("data")
                return {"result": transform(data)}
    """

    node_type_id: ClassVar[str]
    """Unique identifier matching the manifest's ``node_types[].id``."""

    @abstractmethod
    async def execute(self, context: PluginContext) -> dict[str, Any]:
        """Execute this node.

        Args:
            context: Provides inputs, config, logger, and workspace state.

        Returns:
            A dict of output values keyed by output port name.
            On failure, raise a :class:`PluginError` subclass.
        """

    async def validate(self, context: PluginContext) -> list[str]:
        """Optional pre-execution validation.

        Override to check required inputs, config values, etc.

        Returns:
            List of human-readable error strings. Empty means valid.
        """
        return []


class BasePlugin(ABC):
    """Bundle of one or more node handlers that form a plugin.

    Example::

        class JsonTransformPlugin(BasePlugin):
            name = "json-transform"
            version = "1.0.0"
            handlers = [JsonTransformHandler]
    """

    name: ClassVar[str]
    """Plugin identifier — must match manifest ``name``."""

    version: ClassVar[str]
    """Semantic version — must match manifest ``version``."""

    handlers: ClassVar[list[type[BaseNodeHandler]]]
    """List of handler classes this plugin provides."""

    def get_handler(self, node_type_id: str) -> BaseNodeHandler | None:
        """Return an instantiated handler for the given node type, or None."""
        for handler_cls in self.handlers:
            if handler_cls.node_type_id == node_type_id:
                return handler_cls()
        return None

    def node_type_ids(self) -> list[str]:
        """Return all node type IDs provided by this plugin."""
        return [h.node_type_id for h in self.handlers]
