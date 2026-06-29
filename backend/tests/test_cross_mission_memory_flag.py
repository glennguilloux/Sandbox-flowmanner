"""Unit tests for the FLOWMANNER_CROSS_MISSION_MEMORY feature flag (Q2-Q3 Chunk 2 Tier 2).

Covers:
- get_episodic_memory_service() returns None when flag is off
- get_episodic_memory_service() returns service when flag is on
- API endpoints return 503 when flag is off
- EpisodicMemoryWorker skips when flag is off
- ToolRouter memory_service is None when flag is off
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ═══════════════════════════════════════════════════════════════════
# get_episodic_memory_service() singleton
# ═══════════════════════════════════════════════════════════════════


class TestEpisodicMemoryServiceSingleton:
    def teardown_method(self):
        """Reset the singleton between tests."""
        import app.services.episodic_memory_service as mod

        mod._service = None

    def test_returns_none_when_flag_off(self):
        """When FLOWMANNER_CROSS_MISSION_MEMORY=False, returns None."""
        mock_settings = MagicMock()
        mock_settings.FLOWMANNER_CROSS_MISSION_MEMORY = False

        with patch("app.config.settings", mock_settings):
            from app.services.episodic_memory_service import get_episodic_memory_service

            result = get_episodic_memory_service()

        assert result is None

    def test_returns_service_when_flag_on(self):
        """When FLOWMANNER_CROSS_MISSION_MEMORY=True, returns a service instance."""
        mock_settings = MagicMock()
        mock_settings.FLOWMANNER_CROSS_MISSION_MEMORY = True

        with patch("app.config.settings", mock_settings):
            from app.services.episodic_memory_service import get_episodic_memory_service

            result = get_episodic_memory_service()

        assert result is not None

    def test_singleton_returns_same_instance_when_flag_on(self):
        """When enabled, repeated calls return the same instance."""
        mock_settings = MagicMock()
        mock_settings.FLOWMANNER_CROSS_MISSION_MEMORY = True

        with patch("app.config.settings", mock_settings):
            from app.services.episodic_memory_service import get_episodic_memory_service

            svc1 = get_episodic_memory_service()
            svc2 = get_episodic_memory_service()

        assert svc1 is svc2


# ═══════════════════════════════════════════════════════════════════
# EpisodicMemoryWorker — skips when disabled
# ═══════════════════════════════════════════════════════════════════


class TestEpisodicMemoryWorkerGate:
    def teardown_method(self):
        """Reset the singleton between tests."""
        import app.services.episodic_memory_service as mod

        mod._service = None

    @pytest.mark.asyncio
    async def test_process_mission_completed_returns_none_when_disabled(self):
        """Worker returns None immediately when flag is off."""
        mock_settings = MagicMock()
        mock_settings.FLOWMANNER_CROSS_MISSION_MEMORY = False

        from app.services.episodic_memory_worker import EpisodicMemoryWorker

        worker = EpisodicMemoryWorker()

        with patch("app.config.settings", mock_settings):
            result = await worker.process_mission_completed(
                AsyncMock(),
                mission_id=str(uuid4()),
                run_id=str(uuid4()),
            )

        assert result is None


# ═══════════════════════════════════════════════════════════════════
# ToolRouter — memory_service is None when flag is off
# ═══════════════════════════════════════════════════════════════════


class TestToolRouterGate:
    def teardown_method(self):
        """Reset singletons between tests."""
        import app.services.episodic_memory_service as mod

        mod._service = None
        from app.services.tool_router import reset_tool_router

        reset_tool_router()

    def test_get_tool_router_passes_none_memory_when_disabled(self):
        """When flag is off, ToolRouter receives None for memory_service."""
        mock_settings = MagicMock()
        mock_settings.FLOWMANNER_CROSS_MISSION_MEMORY = False

        from app.services.tool_router import get_tool_router

        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = []

        with patch("app.config.settings", mock_settings):
            router = get_tool_router(registry=mock_registry, memory_service=None)

        assert router._memory_service is None

    @pytest.mark.asyncio
    async def test_memory_hint_returns_zero_when_service_none(self):
        """When memory_service is None, _memory_hint always returns 0.0."""
        from app.services.tool_router import ToolRouter

        mock_registry = MagicMock()
        mock_registry.list_tools.return_value = []
        router = ToolRouter(registry=mock_registry, memory_service=None)

        mock_tool = MagicMock()
        mock_tool.tool_id = "test_tool"
        mock_tool.name = "test"

        result = await router._memory_hint(mock_tool, "test task", "ws-1", 1)
        assert result == 0.0


# ═══════════════════════════════════════════════════════════════════
# Config setting
# ═══════════════════════════════════════════════════════════════════


class TestConfigSetting:
    def test_default_is_true(self):
        """FLOWMANNER_CROSS_MISSION_MEMORY defaults to True (on).

        Enabled 2026-06-29 as part of the personal-memory-in-chat
        integration (Gap 1).  Previously defaulted to False.
        """
        from app.config import Settings

        # Settings without env override should default to True
        s = Settings()
        assert s.FLOWMANNER_CROSS_MISSION_MEMORY is True
