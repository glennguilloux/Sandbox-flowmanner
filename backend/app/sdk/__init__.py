"""FlowManner Plugin SDK — Build custom workflow node types.

Quick start::

    from app.sdk import BasePlugin, BaseNodeHandler, PluginContext

    class MyHandler(BaseNodeHandler):
        node_type_id = "my_node"

        async def execute(self, context: PluginContext) -> dict:
            data = context.get_input("data")
            return {"result": data}

    class MyPlugin(BasePlugin):
        name = "my-plugin"
        version = "1.0.0"
        handlers = [MyHandler]
"""

from app.sdk.base import BaseNodeHandler, BasePlugin
from app.sdk.config import PluginConfig
from app.sdk.context import PluginContext
from app.sdk.exceptions import (
    ExecutionTimeout,
    ManifestError,
    PermissionDenied,
    PluginError,
    PluginLoadError,
    SchemaValidationError,
)
from app.sdk.manifest import (
    NodeTypeInput,
    NodeTypeOutput,
    PluginManifest,
    PluginNodeType,
)

__all__ = [
    "BaseNodeHandler",
    "BasePlugin",
    "ExecutionTimeout",
    "ManifestError",
    "NodeTypeInput",
    "NodeTypeOutput",
    "PermissionDenied",
    "PluginConfig",
    "PluginContext",
    "PluginError",
    "PluginLoadError",
    "PluginManifest",
    "PluginNodeType",
    "SchemaValidationError",
]
