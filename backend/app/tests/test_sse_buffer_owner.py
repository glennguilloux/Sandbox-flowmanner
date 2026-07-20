# ─────────────────────────────────────────────────────────────────────
# Regression tests for the Phase-1 SSE replay owner-binding (plan §7).
#
# Proves a leaked/guessed stream id cannot replay another
# user's buffered SSE tokens (CWE-639 / IDOR).  The buffer is
# owner-bound at create time; replay_from_buffer rejects a
# cross-user caller.  Uses an in-memory fakeredis so it needs no
# real Redis.
#
# Run from the backend worktree:
#     PYTHONPATH=. uv run pytest app/tests/test_sse_buffer_owner.py -q
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

import pytest

from app.services import sse_buffer
from app.services.sse_buffer import get_stream_buffer, replay_from_buffer


@pytest.fixture
def fake_redis(monkeypatch):
    """Point the buffer's Redis factory at an in-memory fakeredis."""
    import fakeredis.aioredis

    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(sse_buffer, "_get_stream_redis", lambda: server)
    return server


@pytest.mark.asyncio
async def test_owner_bound_replay_rejects_cross_user(fake_redis):
    # User A opens a stream (owner-bound at create time).
    async def _inner():
        yield 'data: {"type": "token", "content": "secret"}\n\n'

    frames = [f async for f in get_stream_buffer(_inner(), thread_id="t1", user_id="userA")]
    # First frame is stream_start carrying the stream_id.
    assert frames[0].startswith("event: stream_start")
    import json

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
    import json

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
    import json

    stream_id = json.loads(frames[0].split("data: ", 1)[1])["stream_id"]
    events = await replay_from_buffer(stream_id, "0")
    assert events is not None
    assert any("legacy" in e for e in events)
