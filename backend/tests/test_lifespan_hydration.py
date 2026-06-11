"""Tests for the Postgres-native hydration functions in lifespan.py (Phase 1.4).

Validates:
- _resolve_handler_ref() resolves dotted paths correctly
- _hydrate_tools_from_db() reads from tools_catalog and populates ToolRegistry
- _hydrate_capabilities_from_db() reads from capabilities_catalog and populates CapabilityRegistry
- Fallback behavior when DB tables are empty
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


# ── _resolve_handler_ref tests ─────────────────────────────────────────


class TestResolveHandlerRef:
    """Test the handler_ref resolution helper."""

    def test_resolve_valid_class(self):
        from app.lifespan import _resolve_handler_ref

        result = _resolve_handler_ref("app.tools.base.BaseTool")
        assert result is not None
        assert result.__name__ == "BaseTool"

    def test_resolve_valid_function(self):
        from app.lifespan import _resolve_handler_ref

        result = _resolve_handler_ref("app.tools.base.get_tool_registry")
        assert result is not None
        assert callable(result)

    def test_resolve_invalid_module(self):
        from app.lifespan import _resolve_handler_ref

        result = _resolve_handler_ref("app.nonexistent_module.Foo")
        assert result is None

    def test_resolve_invalid_attr(self):
        from app.lifespan import _resolve_handler_ref

        result = _resolve_handler_ref("app.tools.base.NonexistentClass")
        assert result is None

    def test_resolve_malformed_path(self):
        from app.lifespan import _resolve_handler_ref

        result = _resolve_handler_ref("no_dots_here")
        assert result is None

    def test_resolve_empty_string(self):
        from app.lifespan import _resolve_handler_ref

        result = _resolve_handler_ref("")
        assert result is None


# ── _hydrate_tools_from_db tests ──────────────────────────────────────


class TestHydrateToolsFromDB:
    """Test tool hydration from tools_catalog."""

    @pytest.mark.asyncio
    async def test_returns_false_when_table_empty(self):
        """When tools_catalog is empty, should return False (trigger fallback)."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=mock_factory):
            from app.lifespan import _hydrate_tools_from_db

            result = await _hydrate_tools_from_db()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_tools_exist(self):
        """When tools_catalog has rows, should return True (hydration succeeded)."""
        mock_tool = MagicMock()
        mock_tool.slug = "test_tool"
        mock_tool.handler_ref = "app.tools.base.BaseTool"
        mock_tool.enabled = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_tool]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.database.AsyncSessionLocal", return_value=mock_factory),
            patch("app.lifespan._resolve_handler_ref") as mock_resolve,
            patch("app.tools.base.get_tool_registry") as mock_registry,
        ):
            mock_resolve.return_value = MagicMock  # A class that can be instantiated
            mock_registry.return_value = MagicMock()

            from app.lifespan import _hydrate_tools_from_db

            result = await _hydrate_tools_from_db()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        """When DB connection fails, should return False (trigger fallback)."""
        with patch("app.database.AsyncSessionLocal", side_effect=Exception("DB down")):
            from app.lifespan import _hydrate_tools_from_db

            result = await _hydrate_tools_from_db()

        assert result is False


# ── _hydrate_capabilities_from_db tests ────────────────────────────────


class TestHydrateCapabilitiesFromDB:
    """Test capability hydration from capabilities_catalog."""

    @pytest.mark.asyncio
    async def test_returns_false_when_table_empty(self):
        """When capabilities_catalog is empty, should return False."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=mock_factory):
            from app.lifespan import _hydrate_capabilities_from_db

            result = await _hydrate_capabilities_from_db()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_capabilities_exist(self):
        """When capabilities_catalog has rows, should return True."""
        mock_cap = MagicMock()
        mock_cap.slug = "test_cap"
        mock_cap.name = "Test Cap"
        mock_cap.description = "A test capability"
        mock_cap.category = "general"
        mock_cap.handler_ref = None
        mock_cap.input_schema = {}
        mock_cap.output_schema = {}
        mock_cap.rate_limit = None
        mock_cap.timeout_seconds = 30
        mock_cap.metadata_ = {}
        mock_cap.enabled = True

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_cap]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.database.AsyncSessionLocal", return_value=mock_factory),
            patch("app.services.nexus.capability_registry.get_capability_registry") as mock_registry,
        ):
            mock_registry.return_value = MagicMock()

            from app.lifespan import _hydrate_capabilities_from_db

            result = await _hydrate_capabilities_from_db()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self):
        """When DB connection fails, should return False."""
        with patch("app.database.AsyncSessionLocal", side_effect=Exception("DB down")):
            from app.lifespan import _hydrate_capabilities_from_db

            result = await _hydrate_capabilities_from_db()

        assert result is False


# ── Integration: lifespan startup sequence ─────────────────────────────


class TestLifespanHydrationSequence:
    """Verify the lifespan startup uses hydration with fallback."""

    def test_lifespan_function_exists(self):
        from app.lifespan import lifespan

        assert callable(lifespan)

    def test_hydration_functions_importable(self):
        from app.lifespan import (
            _hydrate_capabilities_from_db,
            _hydrate_tools_from_db,
            _resolve_handler_ref,
        )

        assert callable(_hydrate_tools_from_db)
        assert callable(_hydrate_capabilities_from_db)
        assert callable(_resolve_handler_ref)

    def test_fallback_functions_still_exist(self):
        """Old registration functions must still exist for fallback."""
        from app.lifespan import (
            _init_tool_discovery,
            _register_agent_capabilities,
            _register_core_tools,
            _seed_agent_templates,
            _seed_marketplace,
        )

        assert callable(_register_core_tools)
        assert callable(_register_agent_capabilities)
        assert callable(_seed_agent_templates)
        assert callable(_seed_marketplace)
        assert callable(_init_tool_discovery)
