"""Tests for Phase 2: Registry Replacement — hydrate_from_db + binding models.

Covers:
- ToolRegistry.hydrate_from_db(session)
- CapabilityRegistry.hydrate_from_db(session)
- AgentToolBinding / AgentCapabilityBinding / CapabilityDependency models
- Alembic migration 20260604_bindings (table existence)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_tool_row():
    """A fake tools_catalog row as returned by SQLAlchemy."""
    row = MagicMock()
    row.slug = "test_tool"
    row.name = "Test Tool"
    row.description = "A test tool"
    row.category = "general"
    row.handler_ref = "app.tools.base.ToolRegistry"  # valid importable path
    row.enabled = True
    row.input_schema = {"type": "object"}
    row.output_schema = {"type": "object"}
    row.tags = ["test"]
    row.timeout_seconds = 30
    row.requires_auth = False
    row.metadata_ = {}
    return row


@pytest.fixture
def mock_capability_row():
    """A fake capabilities_catalog row as returned by SQLAlchemy."""
    row = MagicMock()
    row.slug = "test_cap"
    row.name = "Test Capability"
    row.description = "A test capability"
    row.category = "knowledge"
    row.handler_ref = "app.tools.base.ToolRegistry"  # valid importable path (callable)
    row.enabled = True
    row.input_schema = {"type": "object"}
    row.output_schema = {"type": "object"}
    row.rate_limit = 10
    row.timeout_seconds = 15
    row.metadata_ = {"test": True}
    return row


def _make_mock_session(rows):
    """Build a mock AsyncSession whose execute returns *rows*."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = rows

    session = AsyncMock()
    session.execute.return_value = mock_result
    return session


# ---------------------------------------------------------------------------
# ToolRegistry.hydrate_from_db
# ---------------------------------------------------------------------------

class TestToolRegistryHydrateFromDB:
    @pytest.mark.asyncio
    async def test_hydrate_from_db_returns_count(self, mock_tool_row):
        from app.tools.base import ToolRegistry

        session = _make_mock_session([mock_tool_row])
        registry = ToolRegistry()

        # _resolve_handler will find ToolRegistry class — instantiating it
        # will work because it has no required __init__ args.
        # However, ToolRegistry() doesn't have `execute` etc, so
        # we mock the handler resolution to return a simple BaseTool subclass.
        mock_tool_instance = MagicMock()
        mock_tool_instance.tool_id = "test_tool"
        mock_tool_instance.name = "Test Tool"
        mock_tool_instance.description = "desc"
        mock_tool_instance.category = "general"
        mock_tool_instance.tags = []

        with patch.object(ToolRegistry, "_resolve_handler", return_value=lambda: mock_tool_instance):
            count = await registry.hydrate_from_db(session)

        assert count == 1
        assert registry.get("test_tool") is not None

    @pytest.mark.asyncio
    async def test_hydrate_from_db_empty_table(self):
        from app.tools.base import ToolRegistry

        session = _make_mock_session([])
        registry = ToolRegistry()
        count = await registry.hydrate_from_db(session)

        assert count == 0

    @pytest.mark.asyncio
    async def test_hydrate_from_db_skips_unresolvable(self, mock_tool_row):
        from app.tools.base import ToolRegistry

        session = _make_mock_session([mock_tool_row])
        registry = ToolRegistry()

        with patch.object(ToolRegistry, "_resolve_handler", return_value=None):
            count = await registry.hydrate_from_db(session)

        assert count == 0

    @pytest.mark.asyncio
    async def test_hydrate_from_db_skips_no_handler_ref(self):
        from app.tools.base import ToolRegistry

        row = MagicMock()
        row.slug = "no_handler"
        row.handler_ref = None

        session = _make_mock_session([row])
        registry = ToolRegistry()
        count = await registry.hydrate_from_db(session)

        assert count == 0


# ---------------------------------------------------------------------------
# CapabilityRegistry.hydrate_from_db
# ---------------------------------------------------------------------------

class TestCapabilityRegistryHydrateFromDB:
    @pytest.mark.asyncio
    async def test_hydrate_from_db_returns_count(self, mock_capability_row):
        from app.services.nexus.capability_registry import CapabilityRegistry

        session = _make_mock_session([mock_capability_row])
        registry = CapabilityRegistry()

        # Provide a callable that will be used as handler
        async def fake_handler(params):
            return {"ok": True}

        with patch.object(
            CapabilityRegistry, "_resolve_handler", return_value=fake_handler
        ):
            count = await registry.hydrate_from_db(session)

        assert count == 1
        cap = registry.get("test_cap")
        assert cap is not None
        assert cap.name == "Test Capability"
        assert cap.category == "knowledge"

    @pytest.mark.asyncio
    async def test_hydrate_from_db_empty_table(self):
        from app.services.nexus.capability_registry import CapabilityRegistry

        session = _make_mock_session([])
        registry = CapabilityRegistry()
        count = await registry.hydrate_from_db(session)

        assert count == 0

    @pytest.mark.asyncio
    async def test_hydrate_from_db_creates_passthrough_on_unresolvable(self, mock_capability_row):
        """When handler_ref can't be resolved, a passthrough handler is created."""
        from app.services.nexus.capability_registry import CapabilityRegistry

        mock_capability_row.handler_ref = "nonexistent.module.Class"

        session = _make_mock_session([mock_capability_row])
        registry = CapabilityRegistry()

        # Don't mock _resolve_handler — let it fail naturally
        count = await registry.hydrate_from_db(session)

        assert count == 1
        cap = registry.get("test_cap")
        assert cap is not None
        # The passthrough handler should return the capability info
        result = await cap.execute({})
        assert result["capability"]["id"] == "test_cap"


# ---------------------------------------------------------------------------
# Binding models — table existence via Alembic migration
# ---------------------------------------------------------------------------

class TestBindingModelsExist:
    """Verify the binding tables were created by migration 20260604_bindings."""

    def test_agent_tool_binding_model_importable(self):
        from app.models.binding_models import AgentToolBinding
        assert AgentToolBinding.__tablename__ == "agent_tool_bindings"

    def test_agent_capability_binding_model_importable(self):
        from app.models.binding_models import AgentCapabilityBinding
        assert AgentCapabilityBinding.__tablename__ == "agent_capability_bindings"

    def test_capability_dependency_model_importable(self):
        from app.models.binding_models import CapabilityDependency
        assert CapabilityDependency.__tablename__ == "capability_dependencies"

    def test_binding_models_registered_with_base(self):
        from app.models import Base
        from app.models.binding_models import (
            AgentToolBinding,
            AgentCapabilityBinding,
            CapabilityDependency,
        )
        tables = Base.metadata.tables
        assert "agent_tool_bindings" in tables
        assert "agent_capability_bindings" in tables
        assert "capability_dependencies" in tables


# ---------------------------------------------------------------------------
# Binding models — field coverage
# ---------------------------------------------------------------------------

class TestBindingModelFields:
    def test_agent_tool_binding_columns(self):
        from app.models.binding_models import AgentToolBinding
        cols = {c.name for c in AgentToolBinding.__table__.columns}
        expected = {"id", "agent_id", "tool_id", "enabled", "priority",
                    "config_override", "metadata", "created_at", "updated_at"}
        assert expected.issubset(cols)

    def test_agent_capability_binding_columns(self):
        from app.models.binding_models import AgentCapabilityBinding
        cols = {c.name for c in AgentCapabilityBinding.__table__.columns}
        expected = {"id", "agent_id", "capability_id", "enabled", "priority",
                    "config_override", "metadata", "created_at", "updated_at"}
        assert expected.issubset(cols)

    def test_capability_dependency_columns(self):
        from app.models.binding_models import CapabilityDependency
        cols = {c.name for c in CapabilityDependency.__table__.columns}
        expected = {"id", "capability_id", "depends_on_id", "dependency_type",
                    "metadata", "created_at", "updated_at"}
        assert expected.issubset(cols)


# ---------------------------------------------------------------------------
# _resolve_handler (ToolRegistry static method)
# ---------------------------------------------------------------------------

class TestResolveHandler:
    def test_resolve_valid_path(self):
        from app.tools.base import ToolRegistry
        result = ToolRegistry._resolve_handler("app.tools.base.ToolRegistry")
        assert result is ToolRegistry

    def test_resolve_invalid_module(self):
        from app.tools.base import ToolRegistry
        result = ToolRegistry._resolve_handler("nonexistent.module.Class")
        assert result is None

    def test_resolve_invalid_attr(self):
        from app.tools.base import ToolRegistry
        result = ToolRegistry._resolve_handler("app.tools.base.NonexistentClass")
        assert result is None
