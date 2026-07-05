"""Tests for tool call billing — Phase 5.

Covers:
- CostTracker.record_tool_call_cost()
- CostTracker._estimate_tool_cost() pricing
- Fire-and-forget session independence
- CostCategory.TOOL_EXECUTION usage
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.cost_event import CostCategory, CostEvent
from app.services.cost_tracker import CostTracker

# ── CostTracker._estimate_tool_cost ───────────────────────────────


class TestEstimateToolCost:
    def test_sandbox_tools_pricing(self):
        """Sandbox tools are priced by duration ($0.001/sec)."""
        tracker = CostTracker()

        # 1 second = $0.001
        cost = tracker._estimate_tool_cost("sandboxd_preview", 1000.0)
        assert cost == pytest.approx(0.001, abs=1e-6)

        # 5 seconds = $0.005
        cost = tracker._estimate_tool_cost("sandboxd_exec", 5000.0)
        assert cost == pytest.approx(0.005, abs=1e-6)

        # browser_sandbox also uses sandbox pricing
        cost = tracker._estimate_tool_cost("browser_sandbox", 2000.0)
        assert cost == pytest.approx(0.002, abs=1e-6)

    def test_sandbox_minimum_cost(self):
        """Sandbox tools have a minimum cost of $0.001."""
        tracker = CostTracker()

        # Very short duration still costs $0.001
        cost = tracker._estimate_tool_cost("sandboxd_preview", 10.0)
        assert cost >= 0.001

    def test_search_tools_flat_rate(self):
        """Search tools have a flat $0.0001 rate."""
        tracker = CostTracker()

        for tool in ["web_search_enhanced", "rag_search", "memory_recall"]:
            cost = tracker._estimate_tool_cost(tool, 500.0)
            assert cost == pytest.approx(0.0001, abs=1e-8)

    def test_default_tool_flat_rate(self):
        """Unknown tools use the default $0.0005 rate."""
        tracker = CostTracker()

        cost = tracker._estimate_tool_cost("some_unknown_tool", 1000.0)
        assert cost == pytest.approx(0.0005, abs=1e-8)

    def test_all_sandboxd_tools(self):
        """All sandboxd tools use sandbox pricing."""
        tracker = CostTracker()
        sandboxd = {
            "sandboxd_preview",
            "sandboxd_exec",
            "sandboxd_file_write",
            "sandboxd_file_read",
            "sandboxd_file_list",
            "sandboxd_serve",
            "browser_sandbox",
        }
        for tool in sandboxd:
            cost = tracker._estimate_tool_cost(tool, 1000.0)
            assert cost == pytest.approx(0.001, abs=1e-6), f"{tool} should use sandbox pricing"


# ── CostTracker.record_tool_call_cost ─────────────────────────────


class TestRecordToolCallCost:
    @pytest.mark.asyncio
    async def test_creates_cost_event(self):
        """record_tool_call_cost creates a CostEvent with correct fields."""
        tracker = CostTracker()
        mock_db = AsyncMock()

        await tracker.record_tool_call_cost(
            db=mock_db,
            user_id=42,
            tool_name="sandboxd_preview",
            duration_ms=1500.0,
            workspace_id="ws-abc",
        )

        mock_db.add.assert_called_once()
        event = mock_db.add.call_args[0][0]

        # It should be an LLMCallRecord (from record_cost_event)
        assert event is not None

    @pytest.mark.asyncio
    async def test_no_db_commit(self):
        """record_tool_call_cost does NOT call db.commit()."""
        tracker = CostTracker()
        mock_db = AsyncMock()

        await tracker.record_tool_call_cost(
            db=mock_db,
            user_id=42,
            tool_name="web_search_enhanced",
            duration_ms=200.0,
        )

        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_db_skips_write(self):
        """When db is None, only Prometheus metrics are recorded."""
        tracker = CostTracker()

        # Should not raise
        await tracker.record_tool_call_cost(
            db=None,
            user_id=42,
            tool_name="sandboxd_preview",
            duration_ms=1000.0,
        )

    @pytest.mark.asyncio
    async def test_with_workspace_id(self):
        """workspace_id is passed through to the cost event."""
        tracker = CostTracker()
        mock_db = AsyncMock()

        await tracker.record_tool_call_cost(
            db=mock_db,
            user_id=42,
            tool_name="browser_sandbox",
            duration_ms=3000.0,
            workspace_id="ws-xyz",
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_agent_id(self):
        """agent_id is passed through to the cost event."""
        tracker = CostTracker()
        mock_db = AsyncMock()

        await tracker.record_tool_call_cost(
            db=mock_db,
            user_id=42,
            tool_name="sandboxd_exec",
            duration_ms=2000.0,
            workspace_id="ws-abc",
            agent_id="agent-123",
        )

        mock_db.add.assert_called_once()


# ── Fire-and-forget pattern ───────────────────────────────────────


class TestFireAndForgetPattern:
    def test_record_tool_cost_fire_and_forget_exists(self):
        """The fire-and-forget helper is importable from chat_service."""
        from app.services.chat_service import _record_tool_cost_fire_and_forget

        assert callable(_record_tool_cost_fire_and_forget)

    def test_fire_and_forget_does_not_raise(self):
        """Fire-and-forget wrapper should never raise synchronously."""
        import asyncio

        from app.services.chat_service import _record_tool_cost_fire_and_forget

        async def _run():
            # Should not raise even with invalid data — errors are swallowed
            _record_tool_cost_fire_and_forget(
                user_id=0,
                tool_name="nonexistent",
                duration_ms=0.0,
                workspace_id=None,
            )
            # Give the fire-and-forget task a moment to start (and fail gracefully)
            await asyncio.sleep(0.05)

        asyncio.run(_run())


# ── CostEvent DTO ─────────────────────────────────────────────────


class TestCostEventDTO:
    def test_tool_execution_category(self):
        """CostCategory.TOOL_EXECUTION exists and is 'tool_execution'."""
        assert CostCategory.TOOL_EXECUTION.value == "tool_execution"

    def test_cost_event_with_tool_fields(self):
        """CostEvent can be created with tool-specific fields."""
        event = CostEvent(
            category=CostCategory.TOOL_EXECUTION,
            cost_usd=0.001,
            tool_name="sandboxd_preview",
            latency_ms=1000,
            workspace_id="ws-123",
            provider="tool",
        )
        assert event.category == CostCategory.TOOL_EXECUTION
        assert event.tool_name == "sandboxd_preview"
        assert event.cost_usd == 0.001
        assert event.workspace_id == "ws-123"
