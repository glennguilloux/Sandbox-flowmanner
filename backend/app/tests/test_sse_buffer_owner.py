# ─────────────────────────────────────────────────────────────────────
# Regression tests for the Phase-1 SSE replay owner-binding (plan §7).
#
# Proves a leaked/guessed stream id cannot replay another
# user's buffered SSE tokens (CWE-639 / IDOR).  The buffer is
# owner-bound at create time; replay_from_buffer rejects a
# cross-user caller.
#
# Uses an in-process async fake that implements the small Redis-Streams
# surface sse_buffer.py actually calls (XADD / XRANGE / HSET / HGETALL /
# EXPIRE / EXISTS / ACLOSE).  No real Redis and no external dependency
# required, so the regression runs in any environment.
#
# Run from the backend worktree:
#     PYTHONPATH=. python -m pytest app/tests/test_sse_buffer_owner.py -q
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import pytest

from app.services import sse_buffer
from app.services.sse_buffer import get_stream_buffer, replay_from_buffer


class _FakeStream:
    """A single Redis Stream (one key) with monotonic entry IDs."""

    def __init__(self) -> None:
        self._entries: list[tuple[str, dict[str, str]]] = []

    def xadd(self, fields: dict[str, str]) -> str:
        ts = int(time.time() * 1000)
        seq = len(self._entries)
        entry_id = f"{ts}-{seq}"
        self._entries.append((entry_id, dict(fields)))
        return entry_id

    def xrange(self, start: str, stop: str, count: int | None = None) -> list[tuple[str, dict[str, str]]]:
        # start may be "-", "+", "(<id>" (exclusive), or an exact id.
        # stop is typically "+".
        out: list[tuple[str, dict[str, str]]] = []
        for entry_id, fields in self._entries:
            if start == "-":
                include = True
            elif start.startswith("("):
                include = entry_id > start[1:]
            else:
                include = entry_id >= start
            if stop == "+":
                pass
            else:
                include = include and entry_id <= stop
            if include:
                out.append((entry_id, fields))
        if count is not None:
            out = out[:count]
        return out


class FakeRedis:
    """Minimal async stand-in for the Redis client sse_buffer.py uses."""

    def __init__(self, decode_responses: bool = True) -> None:
        self._streams: dict[str, _FakeStream] = {}
        self._hashes: dict[str, dict[str, str]] = {}
        self._ttls: dict[str, int] = {}

    async def xadd(self, key: str, fields: dict[str, str], **_: Any) -> str:
        stream = self._streams.setdefault(key, _FakeStream())
        return stream.xadd(fields)

    async def xrange(
        self, key: str, start: str, stop: str, count: int | None = None
    ) -> list[tuple[str, dict[str, str]]]:
        stream = self._streams.get(key)
        if stream is None:
            return []
        return stream.xrange(start, stop, count=count)

    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        self._hashes.setdefault(key, {}).update(mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self._hashes.get(key, {}))

    async def exists(self, key: str) -> bool:
        return key in self._streams or key in self._hashes

    async def expire(self, key: str, ttl: int) -> None:
        self._ttls[key] = ttl

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_redis(monkeypatch):
    """Point the buffer's Redis factory at an in-process FakeRedis."""
    server = FakeRedis(decode_responses=True)

    async def _fake_factory():
        return server

    monkeypatch.setattr(sse_buffer, "_get_stream_redis", _fake_factory)
    return server


@pytest.mark.asyncio
async def test_owner_bound_replay_rejects_cross_user(fake_redis):
    # User A opens a stream (owner-bound at create time).
    async def _inner():
        yield 'data: {"type": "token", "content": "secret"}\n\n'

    frames = [f async for f in get_stream_buffer(_inner(), thread_id="t1", user_id="userA")]
    # First frame is stream_start carrying the stream_id.
    assert frames[0].startswith("event: stream_start")
    start = json.loads(frames[0].split("data: ", 1)[1])
    stream_id = start["stream_id"]

    # User A (owner) replays → gets the buffered frame.
    a_events = await replay_from_buffer(stream_id, "0", user_id="userA")
    assert a_events is not None
    assert any("secret" in e for e in a_events)

    # User B (different user) replays the SAME stream id → rejected.
    b_events = await replay_from_buffer(stream_id, "0", user_id="userB")
    assert b_events is None


@pytest.mark.asyncio
async def test_anonymous_replay_with_owner_bound_is_rejected(fake_redis):
    async def _inner():
        yield 'data: {"type": "token", "content": "x"}\n\n'

    frames = [f async for f in get_stream_buffer(_inner(), thread_id="t1", user_id="userA")]
    stream_id = json.loads(frames[0].split("data: ", 1)[1])["stream_id"]

    # An anonymous (None) caller must not read an owner-bound buffer.
    anon = await replay_from_buffer(stream_id, "0", user_id=None)
    assert anon is None


@pytest.mark.asyncio
async def test_unbound_buffer_allows_legacy_replay(fake_redis):
    # A buffer created WITHOUT owner binding (thread_id=None) replays
    # for anyone, preserving legacy behavior where no owner was set.
    async def _inner():
        yield 'data: {"type": "token", "content": "legacy"}\n\n'

    frames = [f async for f in get_stream_buffer(_inner())]
    stream_id = json.loads(frames[0].split("data: ", 1)[1])["stream_id"]
    events = await replay_from_buffer(stream_id, "0")
    assert events is not None
    assert any("legacy" in e for e in events)
