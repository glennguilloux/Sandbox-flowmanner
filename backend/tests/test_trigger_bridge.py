"""Unit tests for TriggerBridge (app/services/substrate/trigger_bridge.py)."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.substrate.trigger_bridge import (
    FALLBACK_TICK_SECONDS,
    TriggerBridge,
    get_trigger_bridge,
    notify_trigger_due,
    start_trigger_bridge,
    stop_trigger_bridge,
)


class TestTriggerBridgeInit:
    def test_init_default_state(self):
        bridge = TriggerBridge()
        assert bridge._task is None
        assert bridge._running is False
        assert bridge._tick_count == 0
        assert bridge._last_tick_time == 0.0

    def test_fallback_tick_seconds_is_2(self):
        assert FALLBACK_TICK_SECONDS == 2


class TestTriggerBridgeStartStop:
    @pytest.mark.asyncio
    async def test_start_sets_running_and_creates_task(self):
        bridge = TriggerBridge()
        with patch.object(bridge, "_run", new_callable=AsyncMock):
            await bridge.start()
            assert bridge._running is True
            assert bridge._task is not None
            bridge._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bridge._task

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self):
        bridge = TriggerBridge()
        with patch.object(bridge, "_run", new_callable=AsyncMock):
            await bridge.start()
            task1 = bridge._task
            await bridge.start()  # second call should be no-op
            assert bridge._task is task1
            bridge._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bridge._task

    @pytest.mark.asyncio
    async def test_stop_clears_task(self):
        bridge = TriggerBridge()
        with patch.object(bridge, "_run", new_callable=AsyncMock):
            await bridge.start()
            await bridge.stop()
            assert bridge._task is None
            assert bridge._running is False

    @pytest.mark.asyncio
    async def test_stop_is_safe_when_not_started(self):
        bridge = TriggerBridge()
        await bridge.stop()  # Should not raise
        assert bridge._task is None


class TestTriggerBridgeStats:
    def test_stats_initial(self):
        bridge = TriggerBridge()
        stats = bridge.stats
        assert stats["ticks_processed"] == 0
        assert stats["last_tick"] == 0.0
        assert stats["running"] is False

    def test_stats_after_running(self):
        bridge = TriggerBridge()
        bridge._tick_count = 5
        bridge._last_tick_time = 123.45
        bridge._running = True
        stats = bridge.stats
        assert stats["ticks_processed"] == 5
        assert stats["last_tick"] == 123.45
        assert stats["running"] is True


class TestPollOnce:
    @pytest.mark.asyncio
    async def test_poll_once_increments_tick_count(self):
        bridge = TriggerBridge()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_process = AsyncMock(return_value=0)
        # process_cron_triggers is imported locally inside _poll_once
        # from app.services.trigger_service which requires croniter (not installed).
        # Inject a mock module into sys.modules so the local import resolves.
        mock_ts_module = MagicMock()
        mock_ts_module.process_cron_triggers = mock_process
        with (
            patch(
                "app.services.substrate.trigger_bridge.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch.dict("sys.modules", {"app.services.trigger_service": mock_ts_module}),
        ):
            await bridge._poll_once()

        assert bridge._tick_count == 1
        assert bridge._last_tick_time > 0

    @pytest.mark.asyncio
    async def test_poll_once_commits_after_triggers(self):
        bridge = TriggerBridge()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_process = AsyncMock(return_value=2)
        mock_ts_module = MagicMock()
        mock_ts_module.process_cron_triggers = mock_process
        with (
            patch(
                "app.services.substrate.trigger_bridge.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch.dict("sys.modules", {"app.services.trigger_service": mock_ts_module}),
        ):
            await bridge._poll_once()

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_poll_once_handles_exception_gracefully(self):
        bridge = TriggerBridge()

        with patch(
            "app.services.substrate.trigger_bridge.AsyncSessionLocal",
            side_effect=RuntimeError("db down"),
        ):
            # Should not raise
            await bridge._poll_once()

        assert bridge._tick_count == 1


class TestNotifyTriggerDue:
    @pytest.mark.asyncio
    async def test_notify_is_noop_placeholder(self):
        # Should not raise
        await notify_trigger_due()
        await notify_trigger_due(next_fire_at=None)
        from datetime import datetime

        await notify_trigger_due(next_fire_at=datetime.now())


class TestGetTriggerBridge:
    def test_returns_singleton(self):
        import app.services.substrate.trigger_bridge as mod

        # Reset singleton
        original = mod._bridge
        mod._bridge = None
        try:
            b1 = get_trigger_bridge()
            b2 = get_trigger_bridge()
            assert b1 is b2
            assert isinstance(b1, TriggerBridge)
        finally:
            mod._bridge = original


class TestStartStopLifecycle:
    @pytest.mark.asyncio
    async def test_start_trigger_bridge_starts_bridge(self):
        import app.services.substrate.trigger_bridge as mod

        original = mod._bridge
        mod._bridge = None
        try:
            bridge = get_trigger_bridge()
            with patch.object(bridge, "_run", new_callable=AsyncMock):
                await start_trigger_bridge()
                assert bridge._running is True
                await bridge.stop()
        finally:
            mod._bridge = original

    @pytest.mark.asyncio
    async def test_stop_trigger_bridge_stops_bridge(self):
        import app.services.substrate.trigger_bridge as mod

        original = mod._bridge
        mod._bridge = None
        try:
            bridge = get_trigger_bridge()
            with patch.object(bridge, "_run", new_callable=AsyncMock):
                await bridge.start()
                await stop_trigger_bridge()
                assert bridge._task is None
        finally:
            mod._bridge = original

    @pytest.mark.asyncio
    async def test_stop_trigger_bridge_safe_when_none(self):
        import app.services.substrate.trigger_bridge as mod

        original = mod._bridge
        mod._bridge = None
        try:
            await stop_trigger_bridge()  # Should not raise
        finally:
            mod._bridge = original
