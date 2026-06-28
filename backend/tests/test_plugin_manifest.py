"""Tests for PluginManifest validation — Trick 11 (Codex Plugins Adoption Plan).

Validates:
- extra="forbid" rejects unknown top-level keys
- @model_validator rejects Codex-style prohibited fields (mcpServers, hooks, skills, apps)
- Existing valid manifests continue to parse
- Minimal manifests with only required fields parse correctly
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.sdk.manifest import PluginManifest


class TestPluginManifestExtraForbid:
    """extra='forbid' rejects unknown top-level keys."""

    def test_valid_manifest_passes(self) -> None:
        """A manifest with only declared fields parses cleanly."""
        m = PluginManifest(name="test-plugin", version="1.0.0")
        assert m.name == "test-plugin"
        assert m.version == "1.0.0"
        assert m.description == ""
        assert m.permissions == []
        assert m.node_types == []

    def test_valid_manifest_with_all_fields(self) -> None:
        """A manifest using all declared fields parses cleanly."""
        m = PluginManifest(
            name="json-transform",
            version="1.0.0",
            description="Transforms JSON data",
            author="FlowManner Team",
            permissions=["network"],
            node_types=[
                {
                    "id": "json_transform",
                    "label": "JSON Transform",
                    "category": "transform",
                }
            ],
            config={"timeout_seconds": {"type": "integer", "default": 30}},
            entry_point="plugin",
            min_platform_version="1.0.0",
        )
        assert m.name == "json-transform"
        assert len(m.node_types) == 1
        assert m.node_types[0].id == "json_transform"

    def test_unknown_field_rejected(self) -> None:
        """An unknown top-level field is rejected by extra='forbid'."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            PluginManifest(name="test", version="1.0.0", unknownField="oops")  # type: ignore[call-arg]

    def test_multiple_unknown_fields_rejected(self) -> None:
        """Multiple unknown top-level fields are all rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            PluginManifest(
                name="test",
                version="1.0.0",
                foo="bar",
                baz="qux",
            )  # type: ignore[call-arg]


class TestPluginManifestProhibitedFields:
    """@model_validator rejects Codex-style prohibited fields."""

    def test_mcpservers_rejected(self) -> None:
        """mcpServers field is explicitly prohibited."""
        with pytest.raises(ValidationError, match="Prohibited fields"):
            PluginManifest(name="test", version="1.0.0", mcpServers={})  # type: ignore[call-arg]

    def test_hooks_rejected(self) -> None:
        """hooks field is explicitly prohibited."""
        with pytest.raises(ValidationError, match="Prohibited fields"):
            PluginManifest(name="test", version="1.0.0", hooks={})  # type: ignore[call-arg]

    def test_skills_rejected(self) -> None:
        """skills field is explicitly prohibited."""
        with pytest.raises(ValidationError, match="Prohibited fields"):
            PluginManifest(name="test", version="1.0.0", skills=[])  # type: ignore[call-arg]

    def test_apps_rejected(self) -> None:
        """apps field is explicitly prohibited."""
        with pytest.raises(ValidationError, match="Prohibited fields"):
            PluginManifest(name="test", version="1.0.0", apps={})  # type: ignore[call-arg]

    def test_multiple_prohibited_fields_rejected(self) -> None:
        """Multiple prohibited fields are reported together."""
        with pytest.raises(ValidationError, match="Prohibited fields"):
            PluginManifest(
                name="test",
                version="1.0.0",
                mcpServers={},
                hooks={},
            )  # type: ignore[call-arg]

    def test_prohibited_field_error_message_includes_field_names(self) -> None:
        """Error message lists the prohibited field names for actionable feedback."""
        with pytest.raises(ValidationError, match="mcpServers"):
            PluginManifest(name="test", version="1.0.0", mcpServers={})  # type: ignore[call-arg]


class TestPluginManifestMinimal:
    """Minimal manifests with only required fields parse correctly."""

    def test_name_and_version_only(self) -> None:
        """Only name and version are required; everything else defaults."""
        m = PluginManifest(name="my-plugin", version="0.1.0")
        assert m.name == "my-plugin"
        assert m.version == "0.1.0"
        assert m.description == ""
        assert m.author == ""
        assert m.permissions == []
        assert m.node_types == []
        assert m.config == {}
        assert m.entry_point == "plugin"
        assert m.min_platform_version is None

    def test_invalid_name_rejected(self) -> None:
        """Name must match ^[a-z][a-z0-9-]*$."""
        with pytest.raises(ValidationError):
            PluginManifest(name="Invalid_Name", version="1.0.0")

    def test_invalid_version_rejected(self) -> None:
        """Version must match ^\\d+\\.\\d+\\.\\d+$."""
        with pytest.raises(ValidationError):
            PluginManifest(name="test", version="1.0")

    def test_invalid_permission_rejected(self) -> None:
        """Unknown permissions are rejected."""
        with pytest.raises(ValidationError, match="Unknown permission"):
            PluginManifest(name="test", version="1.0.0", permissions=["admin"])

    def test_example_manifest_roundtrip(self) -> None:
        """The shipped example manifest must still parse after extra='forbid' is added."""
        from pathlib import Path

        import yaml

        example = Path(__file__).resolve().parent.parent / "app" / "sdk" / "examples" / "flowmanner-plugin.yaml"
        data = yaml.safe_load(example.read_text())
        m = PluginManifest(**data)
        assert m.name == "json-transform"
        assert m.version == "1.0.0"
        assert len(m.node_types) == 1
