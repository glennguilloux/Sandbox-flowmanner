"""Example plugin: JSON Transform — demonstrates the FlowManner Plugin SDK.

Transforms JSON data between workflow nodes using configurable field mappings.

To install:
    1. Place this directory under plugins/ or pack with: python -m app.sdk.cli pack .
    2. Install via API: POST /plugins with the .fmp file
"""

from __future__ import annotations

import json
from typing import Any

from app.sdk import BaseNodeHandler, BasePlugin, PluginContext


class JsonTransformHandler(BaseNodeHandler):
    """Transforms JSON data using a field mapping expression.

    Inputs:
        data: The input data object.
        mapping: A dict mapping output field names to input field paths.

    Outputs:
        result: The transformed data object.
    """

    node_type_id = "json_transform"

    async def validate(self, context: PluginContext) -> list[str]:
        errors: list[str] = []
        if context.get_input("data") is None:
            errors.append("Required input 'data' is missing")
        mapping = context.get_input("mapping")
        if mapping is None:
            errors.append("Required input 'mapping' is missing")
        elif not isinstance(mapping, dict):
            errors.append("'mapping' must be a dict")
        return errors

    async def execute(self, context: PluginContext) -> dict[str, Any]:
        data = context.require_input("data")
        mapping = context.require_input("mapping")

        result: dict[str, Any] = {}
        for output_field, input_path in mapping.items():
            result[output_field] = self._resolve_path(data, str(input_path))

        context.set_output("result", result)
        context.logger.info("Transformed %d fields", len(result))
        return result

    @staticmethod
    def _resolve_path(obj: Any, path: str) -> Any:
        """Resolve a dot-separated path like 'user.profile.name'."""
        current = obj
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current


class JsonTransformPlugin(BasePlugin):
    """JSON Transform plugin for FlowManner workflows."""

    name = "json-transform"
    version = "1.0.0"
    handlers = [JsonTransformHandler]
