"""Tests for app.services.sse_buffer — Task 1.2b server-side.

Tests the SSE buffer logic using mocked Redis.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.sse_buffer import (
    _BUFFER_TTL,
    append_to_buffer,
    get_stream_buffer,
    replay_from_buffer,
)


class TestBufferConstants:
    def test_ttl_is_5_minutes(self):
        assert _BUFFER_TTL == 300


class TestAppendToBuffer:
    @pytest.mark.asyncio
    async def test_append_calls_redis(self):
        # append_to_buffer no longer assigns seq (owned by _next_seq); it just
        # rpush's the already-stamped frame and refreshes the events TTL.
        mock_rds = AsyncMock()
        mock_rds.rpush = AsyncMock()
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            await append_to_buffer("test-stream", "data: hello\n\n")

        mock_rds.incr.assert_not_called()
        mock_rds.rpush.assert_called_once_with("chat:stream:test-stream:events", "data: hello\n\n")
        mock_rds.expire.assert_called_once_with("chat:stream:test-stream:events", _BUFFER_TTL)

    @pytest.mark.asyncio
    async def test_append_noop_when_redis_unavailable(self):
        with patch("app.services.sse_buffer._get_stream_redis", return_value=None):
            # Should not raise
            await append_to_buffer("test-stream", "data: hello\n\n")


class TestReplayFromBuffer:
    @pytest.mark.asyncio
    async def test_replay_returns_none_when_buffer_gone(self):
        mock_rds = AsyncMock()
        mock_rds.exists = AsyncMock(return_value=0)
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await replay_from_buffer("test-stream", since_seq=0)

        assert result is None

    @pytest.mark.asyncio
    async def test_replay_returns_events_after_seq(self):
        mock_rds = AsyncMock()
        mock_rds.exists = AsyncMock(return_value=1)
        mock_rds.llen = AsyncMock(return_value=3)
        # Realistic buffered frames: JSON dicts (as produced in production,
        # already seq-stamped by get_stream_buffer; replay re-stamps defensively).
        mock_rds.lrange = AsyncMock(
            return_value=[
                'data: {"type": "token", "content": "b"}\n\n',
                'data: {"type": "complete"}\n\n',
            ]
        )
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await replay_from_buffer("test-stream", since_seq=1)

        # replay stamps seq onto each replayed frame (since_seq=1 → frames 2,3)
        assert result == [
            'data: {"type": "token", "content": "b", "seq": 2}\n\n',
            'data: {"type": "complete", "seq": 3}\n\n',
        ]
        mock_rds.lrange.assert_called_once_with("chat:stream:test-stream:events", 1, -1)

    @pytest.mark.asyncio
    async def test_replay_noop_when_redis_unavailable(self):
        with patch("app.services.sse_buffer._get_stream_redis", return_value=None):
            result = await replay_from_buffer("test-stream", since_seq=0)
        assert result is None


class TestGetStreamBuffer:
    @pytest.mark.asyncio
    async def test_emits_stream_start_first(self):
        async def mock_gen():
            yield 'data: {"type": "token", "content": "hi"}\n\n'
            yield 'data: {"type": "complete"}\n\n'

        mock_rds = AsyncMock()
        mock_rds.incr = AsyncMock(side_effect=[1, 2, 3])  # seq per event
        mock_rds.rpush = AsyncMock()
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            chunks = [chunk async for chunk in get_stream_buffer(mock_gen())]

        # First chunk should be stream_start, carrying seq 1
        assert chunks[0].startswith("event: stream_start")
        start_data = json.loads(chunks[0].split("data: ")[1].strip())
        assert "stream_id" in start_data
        assert len(start_data["stream_id"]) == 36  # UUID
        assert start_data["seq"] == 1

        # Remaining chunks should be the original events, each stamped with a
        # monotonic seq so a reconnecting client can resume precisely.
        t1 = json.loads(chunks[1].split("data: ")[1].strip())
        assert t1["type"] == "token"
        assert t1["content"] == "hi"
        assert t1["seq"] == 2
        c1 = json.loads(chunks[2].split("data: ")[1].strip())
        assert c1["type"] == "complete"
        assert c1["seq"] == 3

        # Total: 3 events buffered (stream_start + 2 from gen)
        assert mock_rds.rpush.call_count == 3


class TestSeqStamping:
    """Task 1.2b fix: stamped seq lets a reconnect resume without redelivery."""

    @pytest.mark.asyncio
    async def test_live_events_carry_monotonic_seq(self):
        async def mock_gen():
            yield 'data: {"type": "token", "content": "a"}\n\n'
            yield 'data: {"type": "token", "content": "b"}\n\n'
            yield 'data: {"type": "token", "content": "c"}\n\n'

        mock_rds = AsyncMock()
        mock_rds.incr = AsyncMock(side_effect=[1, 2, 3, 4])  # seq per event
        mock_rds.rpush = AsyncMock()
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            chunks = [chunk async for chunk in get_stream_buffer(mock_gen())]

        seqs = [json.loads(c.split("data: ")[1])["seq"] for c in chunks]
        # stream_start=1, then tokens 2,3,4 — strictly monotonic
        assert seqs == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_replay_after_midstream_drop_does_not_redeliver(self):
        """A client that consumed seq 1..3 then drops should, on reconnect
        with since_seq=3, only receive seq 4+ (never already-rendered tokens)."""
        mock_rds = AsyncMock()
        mock_rds.exists = AsyncMock(return_value=1)
        # Buffer holds: stream_start(1) + tokens 2,3,4,5 (5 events total)
        buffered = [
            'event: stream_start\ndata: {"stream_id": "s", "seq": 1}\n\n',
            'data: {"type": "token", "content": "a", "seq": 2}\n\n',
            'data: {"type": "token", "content": "b", "seq": 3}\n\n',
            'data: {"type": "token", "content": "c", "seq": 4}\n\n',
            'data: {"type": "token", "content": "d", "seq": 5}\n\n',
        ]
        mock_rds.llen = AsyncMock(return_value=len(buffered))
        # Client consumed up to seq 3, reconnects with since=3
        mock_rds.lrange = AsyncMock(return_value=buffered[3:])  # index >= 3
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            replayed = await replay_from_buffer("s", since_seq=3)

        assert replayed is not None
        replayed_seqs = [json.loads(e.split("data: ")[1])["seq"] for e in replayed]
        # Only seq 4 and 5 delivered — seq 1..3 (already rendered) are skipped
        assert replayed_seqs == [4, 5]
        # Make sure no redelivered token content re-appears
        rendered = {json.loads(e.split("data: ")[1]).get("content") for e in replayed}
        assert rendered == {"c", "d"}


class TestSSEStreamWrapperEmitsNoDuplicateStreamStart:
    """Comment 1: the v2 _sse_stream() wrapper must NOT emit its own
    stream_start frame. The canonical single stream_start comes from
    get_stream_buffer() in sse_buffer.py."""

    @pytest.mark.asyncio
    async def test_wrapper_yields_only_inner_chunks_and_done(self):
        from app.api.v2.chat import _sse_stream

        async def fake_inner():
            yield json.dumps({"type": "token", "content": "a"})
            yield json.dumps({"type": "token", "content": "b"})

        frames = [f async for f in _sse_stream(fake_inner())]

        # Exactly the two token frames + the [DONE] terminator.
        assert frames == [
            'data: {"type": "token", "content": "a"}\n\n',
            'data: {"type": "token", "content": "b"}\n\n',
            "data: [DONE]\n\n",
        ]
        # No stream_start frame of any kind.
        assert not any("stream_start" in f for f in frames)

    @pytest.mark.asyncio
    async def test_buffer_emits_single_stream_start(self):
        """The canonical stream_start (event: stream_start) is emitted once
        by get_stream_buffer — and only once — for the whole stream."""

        async def fake_inner():
            yield json.dumps({"type": "token", "content": "a"})

        mock_rds = AsyncMock()
        mock_rds.rpush = AsyncMock()
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()
        mock_rds.incr = AsyncMock(return_value=1)  # seq is JSON-serialized; must be int, not a MagicMock

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            captured = [frame async for frame in get_stream_buffer(fake_inner())]

        start_frames = [f for f in captured if "stream_start" in f]
        assert len(start_frames) == 1
        assert start_frames[0].startswith("event: stream_start")
