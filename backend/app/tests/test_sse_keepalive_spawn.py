"""Isolated unit test for ``_sse_keepalive_spawn`` (Task t_239e7e62).

Tests the spawn unit in isolation with a mocked ``BackgroundTaskManager``:
it must hand the timer coroutine to the manager's ``spawn`` with the correct
label, and the coroutine must be exactly ``_sse_keepalive_timer``.

Kept independent of the full ``stream_message_to_llm`` body and of any live
LLM / DB, so it runs fast and hermetically.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services.chat_service import (
    _SSE_KEEPALIVE_INTERVAL,
    _SSE_KEEPALIVE_PING,
    _sse_keepalive_spawn,
    _sse_keepalive_timer,
)


class TestSseKeepaliveSpawn:
    def test_spawn_calls_manager_with_timer_coro_and_label(self):
        """The unit must delegate to BackgroundTaskManager.spawn with the
        timer coroutine and the ``sse_keepalive`` label, returning the
        fire-and-forget task handle."""
        fake_task = MagicMock(spec=asyncio.Task)
        mock_manager = MagicMock()
        mock_manager.spawn.return_value = fake_task

        queue: asyncio.Queue = asyncio.Queue()
        stop = asyncio.Event()

        with patch("app.services.chat_service.background_task_manager", mock_manager):
            returned = _sse_keepalive_spawn(queue, stop)

        mock_manager.spawn.assert_called_once()
        args, kwargs = mock_manager.spawn.call_args
        assert kwargs.get("label") == "sse_keepalive"
        assert len(args) == 1
        assert asyncio.iscoroutine(args[0])
        assert returned is fake_task

    def test_spawned_coro_is_timer(self):
        """The coroutine handed to spawn must be ``_sse_keepalive_timer``
        (so the keepalive is timer-driven, not yield-gated)."""
        mock_manager = MagicMock()
        queue: asyncio.Queue = asyncio.Queue()
        stop = asyncio.Event()

        with patch("app.services.chat_service.background_task_manager", mock_manager):
            _sse_keepalive_spawn(queue, stop)

        coro = mock_manager.spawn.call_args.args[0]
        assert asyncio.iscoroutine(coro)
        # Identity of the wrapped coroutine function.
        assert coro.cr_code.co_name == "_sse_keepalive_timer"
        coro.close()

    async def test_spawned_timer_fires_ping_on_cadence(self):
        """End-to-end within the test: driving the spawned timer task (via the
        real manager) emits ``: ping`` every interval, independent of any token
        stream."""
        import contextlib

        queue: asyncio.Queue = asyncio.Queue()
        stop = asyncio.Event()
        task = _sse_keepalive_spawn(queue, stop)

        try:
            # Wait just over one interval; the timer must have fired by then.
            await asyncio.sleep(_SSE_KEEPALIVE_INTERVAL + 0.3)
        finally:
            stop.set()
            task.cancel()
            # The timer may exit via cancellation OR via the stop event (normal
            # completion) — either is valid, so tolerate both.
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2.0)

        assert queue.qsize() >= 1
        assert queue.get_nowait() == _SSE_KEEPALIVE_PING
