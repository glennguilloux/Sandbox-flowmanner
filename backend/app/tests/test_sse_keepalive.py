"""Tests for the SSE timer-driven keepalive (Task 2b.2).

Verifies the ``_sse_keepalive_timer`` coroutine emits ``: ping`` comments on a
fixed cadence independent of LLM token cadence, and that the merge wrapper
interleaves pings during idle gaps.
"""

import asyncio
import contextlib

import pytest

from app.services.chat_service import (
    _SSE_KEEPALIVE_INTERVAL,
    _SSE_KEEPALIVE_PING,
    _sse_keepalive_merge,
    _sse_keepalive_timer,
)


class TestSseKeepaliveTimer:
    async def test_emits_ping_after_one_interval(self):
        """The timer should queue a ping roughly every interval."""
        queue: asyncio.Queue = asyncio.Queue()
        stop = asyncio.Event()
        task = asyncio.ensure_future(_sse_keepalive_timer(queue, stop))

        # Wait just over one interval, then stop.
        await asyncio.sleep(_SSE_KEEPALIVE_INTERVAL + 0.3)
        stop.set()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)

        assert queue.qsize() >= 1
        assert queue.get_nowait() == _SSE_KEEPALIVE_PING

    async def test_no_ping_before_interval(self):
        """Within the interval, no ping should be queued yet."""
        queue: asyncio.Queue = asyncio.Queue()
        stop = asyncio.Event()
        task = asyncio.ensure_future(_sse_keepalive_timer(queue, stop))

        await asyncio.sleep(_SSE_KEEPALIVE_INTERVAL * 0.4)
        assert queue.empty()

        stop.set()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)

    async def test_stops_when_event_set_immediately(self):
        """If stop_event is set before the first interval, no ping is emitted."""
        queue: asyncio.Queue = asyncio.Queue()
        stop = asyncio.Event()
        stop.set()
        await _sse_keepalive_timer(queue, stop)
        assert queue.empty()

    async def test_uses_configured_interval(self):
        """The interval constant should be 15 seconds (Task 2b.2 spec)."""
        assert _SSE_KEEPALIVE_INTERVAL == 15


class TestSseKeepaliveMerge:
    async def test_ping_emitted_during_idle_body(self):
        """When the LLM body is idle > interval, the merge yields timer pings."""

        async def slow_body():
            yield '{"type": "token", "content": "a"}'
            # Simulate a long tool round with no yields.
            await asyncio.sleep(_SSE_KEEPALIVE_INTERVAL + 0.5)
            yield '{"type": "token", "content": "b"}'

        queue: asyncio.Queue = asyncio.Queue()
        stop = asyncio.Event()
        # Timer starts only after the first body event, mirroring production
        # (the real stream spawns the timer before iterating but the first
        # token arrives promptly, so no ping can leak into the startup gap).
        collected = []
        got_first = False
        timer = None
        async for event in _sse_keepalive_merge(slow_body(), queue, stop):
            if not got_first:
                got_first = True
                timer = asyncio.ensure_future(_sse_keepalive_timer(queue, stop))
            collected.append(event)

        stop.set()
        if timer is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(timer, timeout=2.0)

        # The two real tokens plus at least one ping in the idle gap.
        assert collected[0] == '{"type": "token", "content": "a"}'
        assert collected[-1] == '{"type": "token", "content": "b"}'
        pings = [e for e in collected if e == _SSE_KEEPALIVE_PING]
        assert len(pings) >= 1

    async def test_real_activity_resets_clock(self):
        """Frequent body activity keeps the queue drained, so no pings surface."""

        async def fast_body():
            # Emit the first token immediately, then a stream of frequent
            # tokens (every 3s, well under the 15s interval) so the timer
            # never gets a full idle interval to fire a ping.
            yield '{"type": "token", "content": "0"}'
            for i in range(1, 5):
                await asyncio.sleep(_SSE_KEEPALIVE_INTERVAL * 0.2)
                yield f'{{"type": "token", "content": "{i}"}}'

        queue: asyncio.Queue = asyncio.Queue()
        stop = asyncio.Event()
        # Timer starts only after the first body event (production parity):
        # the startup gap before the first token must not accumulate a ping.
        collected = []
        got_first = False
        timer = None
        async for event in _sse_keepalive_merge(fast_body(), queue, stop):
            if not got_first:
                got_first = True
                timer = asyncio.ensure_future(_sse_keepalive_timer(queue, stop))
            collected.append(event)

        stop.set()
        if timer is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(timer, timeout=2.0)

        # Frequent body activity keeps the queue drained, so no pings surface.
        assert _SSE_KEEPALIVE_PING not in collected
        assert len(collected) == 5
