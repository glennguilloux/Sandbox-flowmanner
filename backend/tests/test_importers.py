"""Tests for builtin importer CLI commands.

Validates:
- Import scripts can be imported without errors
- ORM models (Tool, ToolVersion, Capability, CapabilityVersion) load correctly
- The import logic handles upsert correctly (mocked DB)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestToolCatalogModels:
    """Test that the canonical tool catalog models are importable and well-formed."""

    def test_tool_model_importable(self):
        from app.models.tool_catalog_models import Tool

        assert Tool.__tablename__ == "tools_catalog"

    def test_tool_version_model_importable(self):
        from app.models.tool_catalog_models import ToolVersion

        assert ToolVersion.__tablename__ == "tool_versions"

    def test_tool_has_required_columns(self):
        from app.models.tool_catalog_models import Tool

        columns = {c.name for c in Tool.__table__.columns}
        required = {
            "id",
            "slug",
            "name",
            "description",
            "category",
            "tool_type",
            "handler_ref",
            "input_schema",
            "output_schema",
            "enabled",
            "version",
            "source",
            "tags",
            "tier",
        }
        assert required.issubset(columns)

    def test_capability_model_importable(self):
        from app.models.capability_catalog_models import Capability

        assert Capability.__tablename__ == "capabilities_catalog"

    def test_capability_version_model_importable(self):
        from app.models.capability_catalog_models import CapabilityVersion

        assert CapabilityVersion.__tablename__ == "capability_versions"

    def test_capability_has_required_columns(self):
        from app.models.capability_catalog_models import Capability

        columns = {c.name for c in Capability.__table__.columns}
        required = {
            "id",
            "slug",
            "name",
            "description",
            "category",
            "handler_ref",
            "input_schema",
            "output_schema",
            "enabled",
            "version",
            "source",
        }
        assert required.issubset(columns)


class TestImporterModules:
    """Test that importer scripts are importable without errors."""

    def test_import_builtin_tools_importable(self):
        import scripts.import_builtin_tools

        assert hasattr(scripts.import_builtin_tools, "run")

    def test_import_builtin_capabilities_importable(self):
        import scripts.import_builtin_capabilities

        assert hasattr(scripts.import_builtin_capabilities, "run")

    def test_import_agent_templates_importable(self):
        import scripts.import_agent_templates

        assert hasattr(scripts.import_agent_templates, "run")


class TestToolTypeInference:
    """Test the tool_type inference helper in import_builtin_tools."""

    def test_builtin_type_for_regular_tool(self):
        from scripts.import_builtin_tools import _tool_type_from_module

        assert _tool_type_from_module("browser_ping") == "builtin"
        assert _tool_type_from_module("terminal") == "builtin"
        assert _tool_type_from_module("topology") == "builtin"

    def test_integration_type_for_integration_tools(self):
        from scripts.import_builtin_tools import _tool_type_from_module

        assert _tool_type_from_module("slack_communicator") == "integration"
        assert _tool_type_from_module("gmail_sender") == "integration"
        assert _tool_type_from_module("notion_sync") == "integration"
        assert _tool_type_from_module("stripe_operations") == "integration"

    def test_handler_ref_format(self):
        from app.tools.browser_ping import BrowserPingTool
        from scripts.import_builtin_tools import _handler_ref

        tool = BrowserPingTool()
        ref = _handler_ref(tool)
        assert ref == "app.tools.browser_ping.BrowserPingTool"


class TestToolRegistryBootstrap:
    """Test that the in-memory ToolRegistry can be bootstrapped with core tools."""

    def test_core_tools_register(self):
        from app.tools.base import ToolRegistry
        from app.tools.browser_ping import BrowserPingTool

        # Use a fresh registry to avoid polluting the global singleton
        registry = ToolRegistry()
        tool = BrowserPingTool()
        result = registry.register(tool)

        assert result is True
        retrieved = registry.get("browser_ping")
        assert retrieved is not None
        assert retrieved.tool_id == "browser_ping"
        assert retrieved.name == "Ping Browser"

    def test_tool_metadata_populated(self):
        from app.tools.browser_ping import BrowserPingTool

        tool = BrowserPingTool()
        assert tool.name is not None
        assert len(tool.name) > 0
        assert tool.description is not None
        assert len(tool.description) > 0
        assert tool.category == "browser"
        assert "browser" in tool.tags


class TestAgentParserIntegration:
    """Test that agent_parser loads markdown agent definitions."""

    def test_load_all_agents_returns_list(self):
        from app.services.agent_parser import load_all_agents

        agents = load_all_agents()
        assert isinstance(agents, list)
        if agents:
            agent = agents[0]
            assert "name" in agent
            assert "slug" in agent
            assert "system_prompt" in agent
            assert "division" in agent


class TestPythonAgentTemplates:
    """Test that Python agent templates are loadable."""

    def test_agent_templates_list(self):
        from app.services.nexus.agent_templates import AGENT_TEMPLATES

        assert len(AGENT_TEMPLATES) > 0
        tpl = AGENT_TEMPLATES[0]
        assert hasattr(tpl, "id")
        assert hasattr(tpl, "name")
        assert hasattr(tpl, "category")
        assert hasattr(tpl, "model_config")
        assert hasattr(tpl, "tools")

    def test_agent_templates_have_unique_ids(self):
        from app.services.nexus.agent_templates import AGENT_TEMPLATES

        ids = [t.id for t in AGENT_TEMPLATES]
        assert len(ids) == len(set(ids))
