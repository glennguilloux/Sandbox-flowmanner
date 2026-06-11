"""Unit tests for BaselineExtractor (app/services/substrate/baseline_extractor.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.substrate_models import SubstrateEventType


def _make_event(event_type: str, payload: dict | None = None):
    """Create a mock substrate event."""
    e = MagicMock()
    e.type = event_type
    e.payload = payload or {}
    return e


def _make_state(
    total_cost_usd: float = 0.05,
    started_at=None,
    last_event_at=None,
    completed_tasks: list | None = None,
):
    """Create a mock replay state."""
    state = MagicMock()
    state.total_cost_usd = total_cost_usd
    state.started_at = started_at or datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    state.last_event_at = last_event_at or datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC)
    state.completed_tasks = set(completed_tasks or ["task_1", "task_2"])
    state.failed_tasks = set()
    return state


class TestBaselineExtractorInit:
    def test_init_uses_defaults(self):
        from app.services.substrate.baseline_extractor import BaselineExtractor

        with (
            patch("app.services.substrate.baseline_extractor.get_event_log") as mock_el,
            patch("app.services.substrate.baseline_extractor.get_replay_engine") as mock_re,
        ):
            mock_el.return_value = MagicMock()
            mock_re.return_value = MagicMock()
            extractor = BaselineExtractor()
            assert extractor._event_log is mock_el.return_value
            assert extractor._replay_engine is mock_re.return_value


class TestExtractFromRun:
    @pytest.mark.asyncio
    async def test_extract_returns_five_behavior_types(self):
        from app.services.substrate.baseline_extractor import BaselineExtractor

        extractor = BaselineExtractor()
        extractor._replay_engine = MagicMock()
        extractor._event_log = MagicMock()

        extractor._replay_engine.rebuild_state = AsyncMock(return_value=_make_state())
        extractor._event_log.get_events = AsyncMock(return_value=[])

        db = AsyncMock()
        behaviors = await extractor.extract_from_run(db, "run-1")

        types = [b["type"] for b in behaviors]
        assert "cost_ceiling" in types
        assert "latency" in types
        assert "task_completion" in types
        assert "no_circuit_breaker" in types

    @pytest.mark.asyncio
    async def test_extract_with_tool_events_generates_tool_sequence(self):
        from app.services.substrate.baseline_extractor import BaselineExtractor

        extractor = BaselineExtractor()
        extractor._replay_engine = MagicMock()
        extractor._event_log = MagicMock()

        extractor._replay_engine.rebuild_state = AsyncMock(return_value=_make_state())
        extractor._event_log.get_events = AsyncMock(
            return_value=[
                _make_event(SubstrateEventType.TOOL_CALL, {"tool_name": "web_search"}),
                _make_event(SubstrateEventType.TOOL_CALL, {"tool_name": "code_executor"}),
                _make_event(SubstrateEventType.TOOL_CALL, {"tool_name": "web_search"}),
            ]
        )

        db = AsyncMock()
        behaviors = await extractor.extract_from_run(db, "run-1")

        tool_seq = [b for b in behaviors if b["type"] == "tool_sequence"]
        assert len(tool_seq) == 1
        assert tool_seq[0]["expected_tools"] == ["web_search", "code_executor"]
        assert tool_seq[0]["max_calls_per_tool"]["web_search"] == 3  # 2 + 1 headroom
        assert tool_seq[0]["max_calls_per_tool"]["code_executor"] == 2

    @pytest.mark.asyncio
    async def test_extract_no_tools_omits_tool_sequence(self):
        from app.services.substrate.baseline_extractor import BaselineExtractor

        extractor = BaselineExtractor()
        extractor._replay_engine = MagicMock()
        extractor._event_log = MagicMock()

        extractor._replay_engine.rebuild_state = AsyncMock(return_value=_make_state())
        # Only non-tool events
        extractor._event_log.get_events = AsyncMock(
            return_value=[
                _make_event(SubstrateEventType.MISSION_STARTED, {}),
            ]
        )

        db = AsyncMock()
        behaviors = await extractor.extract_from_run(db, "run-1")

        types = [b["type"] for b in behaviors]
        assert "tool_sequence" not in types

    @pytest.mark.asyncio
    async def test_cost_ceiling_uses_headroom_multiplier(self):
        from app.services.substrate.baseline_extractor import BaselineExtractor

        extractor = BaselineExtractor()
        extractor._replay_engine = MagicMock()
        extractor._event_log = MagicMock()

        extractor._replay_engine.rebuild_state = AsyncMock(return_value=_make_state(total_cost_usd=0.10))
        extractor._event_log.get_events = AsyncMock(return_value=[])

        db = AsyncMock()
        behaviors = await extractor.extract_from_run(db, "run-1", cost_headroom=2.0)

        cost = [b for b in behaviors if b["type"] == "cost_ceiling"][0]
        assert cost["max_cost_usd"] == 0.20  # 0.10 * 2.0

    @pytest.mark.asyncio
    async def test_latency_ceiling_uses_headroom_multiplier(self):
        from datetime import timedelta

        from app.services.substrate.baseline_extractor import BaselineExtractor

        extractor = BaselineExtractor()
        extractor._replay_engine = MagicMock()
        extractor._event_log = MagicMock()

        state = _make_state()
        state.started_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        state.last_event_at = state.started_at + timedelta(seconds=60)
        extractor._replay_engine.rebuild_state = AsyncMock(return_value=state)
        extractor._event_log.get_events = AsyncMock(return_value=[])

        db = AsyncMock()
        behaviors = await extractor.extract_from_run(db, "run-1", latency_headroom=3.0)

        latency = [b for b in behaviors if b["type"] == "latency"][0]
        assert latency["max_duration_seconds"] == 180  # 60 * 3.0

    @pytest.mark.asyncio
    async def test_latency_defaults_to_300_when_no_timestamps(self):
        from app.services.substrate.baseline_extractor import BaselineExtractor

        extractor = BaselineExtractor()
        extractor._replay_engine = MagicMock()
        extractor._event_log = MagicMock()

        state = _make_state()
        state.started_at = None
        state.last_event_at = None
        extractor._replay_engine.rebuild_state = AsyncMock(return_value=state)
        extractor._event_log.get_events = AsyncMock(return_value=[])

        db = AsyncMock()
        behaviors = await extractor.extract_from_run(db, "run-1")

        latency = [b for b in behaviors if b["type"] == "latency"][0]
        assert latency["max_duration_seconds"] == 300

    @pytest.mark.asyncio
    async def test_task_completion_reflects_completed_count(self):
        from app.services.substrate.baseline_extractor import BaselineExtractor

        extractor = BaselineExtractor()
        extractor._replay_engine = MagicMock()
        extractor._event_log = MagicMock()

        extractor._replay_engine.rebuild_state = AsyncMock(return_value=_make_state(completed_tasks=["a", "b", "c"]))
        extractor._event_log.get_events = AsyncMock(return_value=[])

        db = AsyncMock()
        behaviors = await extractor.extract_from_run(db, "run-1")

        tc = [b for b in behaviors if b["type"] == "task_completion"][0]
        assert tc["min_tasks_completed"] == 3
        assert tc["max_tasks_failed"] == 0

    @pytest.mark.asyncio
    async def test_no_circuit_breaker_always_present(self):
        from app.services.substrate.baseline_extractor import BaselineExtractor

        extractor = BaselineExtractor()
        extractor._replay_engine = MagicMock()
        extractor._event_log = MagicMock()

        extractor._replay_engine.rebuild_state = AsyncMock(return_value=_make_state())
        extractor._event_log.get_events = AsyncMock(return_value=[])

        db = AsyncMock()
        behaviors = await extractor.extract_from_run(db, "run-1")

        types = [b["type"] for b in behaviors]
        assert "no_circuit_breaker" in types


class TestGetBaselineExtractor:
    def test_returns_singleton(self):
        import app.services.substrate.baseline_extractor as mod
        from app.services.substrate.baseline_extractor import get_baseline_extractor

        original = mod._extractor
        try:
            mod._extractor = None  # reset singleton
            with (
                patch("app.services.substrate.baseline_extractor.get_event_log"),
                patch("app.services.substrate.baseline_extractor.get_replay_engine"),
            ):
                e1 = get_baseline_extractor()
                e2 = get_baseline_extractor()
                assert e1 is e2
        finally:
            mod._extractor = original  # restore to avoid leaking state
