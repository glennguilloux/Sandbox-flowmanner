"""PluginConfig — typed configuration for plugin settings.

Plugins can define config schemas in their manifest and use this class
to validate and access config values at runtime.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PluginConfig(BaseModel):
    """Base configuration model for plugin settings.

    Plugin authors can subclass this to define typed config:

        class MyPluginConfig(PluginConfig):
            timeout_seconds: int = Field(default=30, ge=1, le=120)
            max_retries: int = Field(default=3, ge=0, le=10)
            api_endpoint: str = "https://api.example.com"
    """

    model_config = {"extra": "allow"}  # Plugins can add custom fields

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginConfig:
        """Create a config instance from a raw dict."""
        return cls(**data)

    def to_manifest_schema(self) -> dict[str, dict[str, Any]]:
        """Export config as manifest-compatible schema format.

        Returns a dict mapping field names to JSON Schema descriptors
        suitable for the plugin manifest's ``config`` section.
        """
        schema: dict[str, dict[str, Any]] = {}
        for field_name, field_info in self.model_fields.items():
            field_schema: dict[str, Any] = {}
            # Map Python types to JSON Schema types
            ann = field_info.annotation
            if ann is int:
                field_schema["type"] = "integer"
            elif ann is float:
                field_schema["type"] = "number"
            elif ann is bool:
                field_schema["type"] = "boolean"
            elif ann is str:
                field_schema["type"] = "string"
            elif ann is list:
                field_schema["type"] = "array"
            elif ann is dict:
                field_schema["type"] = "object"
            else:
                field_schema["type"] = "string"

            if field_info.default is not None and field_info.default is not ...:
                field_schema["default"] = field_info.default

            field_schema["description"] = field_info.description or ""
            schema[field_name] = field_schema
        return schema
