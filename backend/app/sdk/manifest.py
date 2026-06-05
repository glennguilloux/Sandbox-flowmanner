"""Plugin Manifest — Pydantic model for flowmanner-plugin.yaml.

Every plugin must include a manifest that declares its name, version,
permissions, node types, and configuration schema.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class NodeTypeInput(BaseModel):
    """Schema for a single input port on a plugin node type."""

    type: str = Field(..., description="JSON Schema type: string, integer, number, boolean, object, array")
    required: bool = Field(default=False, description="Whether this input is required")
    description: str | None = None
    default: Any = None


class NodeTypeOutput(BaseModel):
    """Schema for a single output port on a plugin node type."""

    type: str = Field(..., description="JSON Schema type")
    description: str | None = None


class PluginNodeType(BaseModel):
    """Declares a custom node type provided by a plugin."""

    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(..., min_length=1, max_length=128)
    category: str = Field(default="custom", description="Node category: transform, data, integration, custom")
    description: str | None = None
    icon: str | None = Field(default=None, description="Lucide icon name or emoji")
    color: str | None = Field(default=None, description="Hex color for node in graph editor")
    inputs: dict[str, NodeTypeInput] = Field(default_factory=dict)
    outputs: dict[str, NodeTypeOutput] = Field(default_factory=dict)


class PluginManifest(BaseModel):
    """Manifest for a FlowManner plugin (flowmanner-plugin.yaml).

    This model validates the plugin manifest file and is used for:
    - Plugin registration and loading
    - Marketplace listing metadata
    - Security review (permission declarations)
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9-]*$",
        description="Unique plugin identifier (lowercase, hyphens allowed)",
    )
    version: str = Field(
        ...,
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version (e.g., 1.0.0)",
    )
    description: str = Field(default="", max_length=500)
    author: str = Field(default="", max_length=200)
    permissions: list[str] = Field(
        default_factory=list,
        description="Required permissions: network, filesystem, subprocess, env_read, env_write",
    )
    node_types: list[PluginNodeType] = Field(
        default_factory=list,
        description="Custom node types this plugin provides",
    )
    config: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Plugin-level configuration schema (key → JSON Schema)",
    )
    entry_point: str = Field(
        default="plugin",
        description="Python module path for the plugin class (relative to plugin root)",
    )
    min_platform_version: str | None = Field(
        default=None,
        description="Minimum FlowManner platform version required",
    )

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v: list[str]) -> list[str]:
        allowed = {"network", "filesystem", "subprocess", "env_read", "env_write"}
        for p in v:
            if p not in allowed:
                raise ValueError(
                    f"Unknown permission '{p}'. Allowed: {sorted(allowed)}"
                )
        return v

    @field_validator("node_types")
    @classmethod
    def validate_node_type_ids_unique(cls, v: list[PluginNodeType]) -> list[PluginNodeType]:
        seen: set[str] = set()
        for nt in v:
            if nt.id in seen:
                raise ValueError(f"Duplicate node_type id: '{nt.id}'")
            seen.add(nt.id)
        return v
