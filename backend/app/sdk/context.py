"""PluginContext — the execution sandbox interface for plugin handlers.

Provides typed access to inputs, config, workspace state, and logging
without exposing the full graph interpreter internals.
"""

from __future__ import annotations

import logging
from typing import Any


class PluginContext:
    """Execution context passed to :meth:`BaseNodeHandler.execute`.

    Provides a clean, typed API for reading node inputs, plugin config,
    workspace state, and writing outputs — without leaking internals.
    """

    def __init__(
        self,
        *,
        inputs: dict[str, Any],
        config: dict[str, Any] | None = None,
        node_outputs: dict[str, dict[str, Any]] | None = None,
        workspace_id: str | None = None,
        execution_id: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._inputs = dict(inputs)
        self._config = dict(config or {})
        self._node_outputs = dict(node_outputs or {})
        self._workspace_id = workspace_id
        self._execution_id = execution_id
        self._logger = logger or logging.getLogger(f"plugin.{workspace_id or 'default'}")
        self._outputs: dict[str, Any] = {}

    # ─── Inputs ───

    def get_input(self, key: str, default: Any = None) -> Any:
        """Get a node input value by key."""
        return self._inputs.get(key, default)

    def require_input(self, key: str) -> Any:
        """Get a required input or raise SchemaValidationError."""
        if key not in self._inputs:
            from app.sdk.exceptions import SchemaValidationError
            raise SchemaValidationError(
                [f"Required input '{key}' is missing"],
                plugin_name=None,
            )
        return self._inputs[key]

    @property
    def inputs(self) -> dict[str, Any]:
        """All input values (read-only snapshot)."""
        return dict(self._inputs)

    # ─── Config ───

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a plugin-level config value."""
        return self._config.get(key, default)

    @property
    def config(self) -> dict[str, Any]:
        """All config values (read-only snapshot)."""
        return dict(self._config)

    # ─── Previous node outputs ───

    def get_node_output(self, node_id: str) -> dict[str, Any] | None:
        """Get the output dict from a previously executed node."""
        return self._node_outputs.get(node_id)

    # ─── Outputs (set during execution) ───

    def set_output(self, key: str, value: Any) -> None:
        """Set an output value for this node."""
        self._outputs[key] = value

    def get_outputs(self) -> dict[str, Any]:
        """Get all outputs set during execution."""
        return dict(self._outputs)

    # ─── Metadata ───

    @property
    def workspace_id(self) -> str | None:
        return self._workspace_id

    @property
    def execution_id(self) -> str | None:
        return self._execution_id

    @property
    def logger(self) -> logging.Logger:
        """Plugin-scoped logger."""
        return self._logger
