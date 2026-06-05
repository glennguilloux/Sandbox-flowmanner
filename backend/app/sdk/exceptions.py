"""Plugin SDK Exceptions.

All exceptions raised by plugin code or the plugin runtime.
"""

from __future__ import annotations


class PluginError(Exception):
    """Base exception for all plugin errors."""

    def __init__(self, message: str, plugin_name: str | None = None):
        self.plugin_name = plugin_name
        super().__init__(message)


class PermissionDenied(PluginError):
    """Raised when a plugin attempts an action outside its declared permissions."""

    def __init__(self, permission: str, plugin_name: str | None = None):
        self.permission = permission
        super().__init__(
            f"Permission denied: '{permission}' not in plugin manifest permissions",
            plugin_name=plugin_name,
        )


class ExecutionTimeout(PluginError):
    """Raised when a plugin node exceeds its configured timeout."""

    def __init__(self, timeout_seconds: float, plugin_name: str | None = None):
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Execution timed out after {timeout_seconds}s",
            plugin_name=plugin_name,
        )


class SchemaValidationError(PluginError):
    """Raised when plugin input/output fails schema validation."""

    def __init__(self, errors: list[str], plugin_name: str | None = None):
        self.errors = errors
        super().__init__(
            f"Schema validation failed: {'; '.join(errors)}",
            plugin_name=plugin_name,
        )


class ManifestError(PluginError):
    """Raised when a plugin manifest is invalid or missing required fields."""

    pass


class PluginLoadError(PluginError):
    """Raised when a plugin fails to load (import error, missing handler, etc.)."""

    pass
