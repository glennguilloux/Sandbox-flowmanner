"""Tests for app.services.sse_buffer — Redis Streams implementation.

Tests the SSE buffer logic using mocked Redis (XADD/XRANGE instead of
RPUSH/LRANGE/INCR).
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.sse_buffer import (
    _BUFFER_TTL,
    _MAXLEN,
    append_to_buffer,
    get_stream_buffer,
    replay_from_buffer,
)


class TestBufferConstants:
    def test_ttl_is_5_minutes(self):
        assert _BUFFER_TTL == 300

    def test_maxlen_is_set(self):
        assert _MAXLEN == 1000


class TestAppendToBuffer:
    @pytest.mark.asyncio
    async def test_append_calls_xadd(self):
        mock_rds = AsyncMock()
        mock_rds.xadd = AsyncMock(return_value="1720451234567-0")
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await append_to_buffer("test-stream", "data: hello\n\n")

        assert result == "1720451234567-0"
        mock_rds.xadd.assert_called_once_with(
            "chat:stream:test-stream:events",
            {"event": "data: hello\n\n"},
            maxlen=_MAXLEN,
            approximate=True,
        )
        mock_rds.expire.assert_called_once_with("chat:stream:test-stream:events", _BUFFER_TTL)

    @pytest.mark.asyncio
    async def test_append_returns_none_when_redis_unavailable(self):
        with patch("app.services.sse_buffer._get_stream_redis", return_value=None):
            result = await append_to_buffer("test-stream", "data: hello\n\n")
        assert result is None

    @pytest.mark.asyncio
    async def test_append_returns_none_on_redis_error(self):
        mock_rds = AsyncMock()
        mock_rds.xadd = AsyncMock(side_effect=Exception("connection refused"))
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await append_to_buffer("test-stream", "data: hello\n\n")
        assert result is None


class TestReplayFromBuffer:
    @pytest.mark.asyncio
    async def test_replay_returns_none_when_buffer_gone(self):
        mock_rds = AsyncMock()
        mock_rds.exists = AsyncMock(return_value=0)
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await replay_from_buffer("test-stream", since_seq="0")

        assert result is None

    @pytest.mark.asyncio
    async def test_replay_returns_events_after_seq(self):
        mock_rds = AsyncMock()
        mock_rds.exists = AsyncMock(return_value=1)
        # xrange for gap check (oldest entry)
        # xrange for actual replay (entries after since)
        mock_rds.xrange = AsyncMock(
            side_effect=[
                # First call: oldest entry check
                [("1720451234567-0", {"event": 'event: stream_start\ndata: {"stream_id": "s"}\n\n'})],
                # Second call: entries after since
                [
                    ("1720451234567-2", {"event": 'data: {"type": "token", "content": "b"}\n\n'}),
                    ("1720451234567-3", {"event": 'data: {"type": "complete"}\n\n'}),
                ],
            ]
        )
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await replay_from_buffer("test-stream", since_seq="1720451234567-1")

        assert result is not None
        assert len(result) == 2
        # Verify seq is stamped as the stream entry ID
        first = json.loads(result[0].split("data: ")[1].strip())
        assert first["seq"] == "1720451234567-2"
        assert first["content"] == "b"
        second = json.loads(result[1].split("data: ")[1].strip())
        assert second["seq"] == "1720451234567-3"
        assert second["type"] == "complete"
        # Verify xrange called with exclusive start
        mock_rds.xrange.assert_any_call("chat:stream:test-stream:events", "(1720451234567-1", "+")

    @pytest.mark.asyncio
    async def test_replay_returns_all_when_since_is_zero(self):
        mock_rds = AsyncMock()
        mock_rds.exists = AsyncMock(return_value=1)
        mock_rds.xrange = AsyncMock(
            return_value=[
                ("1720451234567-0", {"event": 'data: {"type": "token", "content": "a"}\n\n'}),
                ("1720451234567-1", {"event": 'data: {"type": "token", "content": "b"}\n\n'}),
            ]
        )
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await replay_from_buffer("test-stream", since_seq="0")

        assert result is not None
        assert len(result) == 2
        # Verify xrange called with "-" (inclusive start)
        mock_rds.xrange.assert_called_once_with("chat:stream:test-stream:events", "-", "+")

    @pytest.mark.asyncio
    async def test_replay_resync_when_gap_expired(self):
        """If since_seq predates the oldest entry, return a resync event."""
        mock_rds = AsyncMock()
        mock_rds.exists = AsyncMock(return_value=1)
        mock_rds.xrange = AsyncMock(
            return_value=[
                ("1720451239999-0", {"event": 'data: {"type": "token"}\n\n'}),
            ]
        )
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await replay_from_buffer("test-stream", since_seq="1720451234000-0")

        assert result is not None
        assert len(result) == 1
        assert "resync" in result[0]

    @pytest.mark.asyncio
    async def test_replay_returns_none_when_redis_unavailable(self):
        with patch("app.services.sse_buffer._get_stream_redis", return_value=None):
            result = await replay_from_buffer("test-stream", since_seq="0")
        assert result is None

    @pytest.mark.asyncio
    async def test_replay_returns_none_on_redis_error(self):
        mock_rds = AsyncMock()
        mock_rds.exists = AsyncMock(side_effect=Exception("connection refused"))
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await replay_from_buffer("test-stream", since_seq="0")
        assert result is None


class TestGetStreamBuffer:
    @pytest.mark.asyncio
    async def test_emits_stream_start_first(self):
        async def mock_gen():
            yield 'data: {"type": "token", "content": "hi"}\n\n'
            yield 'data: {"type": "complete"}\n\n'

        mock_rds = AsyncMock()
        mock_rds.xadd = AsyncMock(side_effect=["1720451234567-0", "1720451234567-1", "1720451234567-2"])
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            chunks = [chunk async for chunk in get_stream_buffer(mock_gen())]

        # First chunk should be stream_start with stream_id and seq
        assert chunks[0].startswith("event: stream_start")
        start_data = json.loads(chunks[0].split("data: ")[1].strip())
        assert "stream_id" in start_data
        assert len(start_data["stream_id"]) == 36  # UUID
        assert start_data["seq"] == "1720451234567-0"

        # Remaining chunks stamped with stream entry IDs
        t1 = json.loads(chunks[1].split("data: ")[1].strip())
        assert t1["type"] == "token"
        assert t1["content"] == "hi"
        assert t1["seq"] == "1720451234567-1"

        c1 = json.loads(chunks[2].split("data: ")[1].strip())
        assert c1["type"] == "complete"
        assert c1["seq"] == "1720451234567-2"

        # Total: 3 events buffered (stream_start + 2 from gen)
        assert mock_rds.xadd.call_count == 3

    @pytest.mark.asyncio
    async def test_degrades_when_redis_unavailable(self):
        """When Redis is down, events still yield with seq='0'."""

        async def mock_gen():
            yield 'data: {"type": "token", "content": "hi"}\n\n'

        with patch("app.services.sse_buffer._get_stream_redis", return_value=None):
            chunks = [chunk async for chunk in get_stream_buffer(mock_gen())]

        assert len(chunks) == 2
        # stream_start with seq "0"
        start_data = json.loads(chunks[0].split("data: ")[1].strip())
        assert start_data["seq"] == "0"
        # token with seq "0"
        token_data = json.loads(chunks[1].split("data: ")[1].strip())
        assert token_data["seq"] == "0"


class TestSeqStamping:
    """Seq stamping uses native Redis Stream entry IDs (strings)."""

    @pytest.mark.asyncio
    async def test_live_events_carry_stream_ids(self):
        async def mock_gen():
            yield 'data: {"type": "token", "content": "a"}\n\n'
            yield 'data: {"type": "token", "content": "b"}\n\n'
            yield 'data: {"type": "token", "content": "c"}\n\n'

        mock_rds = AsyncMock()
        mock_rds.xadd = AsyncMock(
            side_effect=[
                "1720451234567-0",  # stream_start
                "1720451234567-1",  # token a
                "1720451234567-2",  # token b
                "1720451234567-3",  # token c
            ]
        )
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            chunks = [chunk async for chunk in get_stream_buffer(mock_gen())]

        seqs = [json.loads(c.split("data: ")[1])["seq"] for c in chunks]
        # stream_start + 3 tokens — strictly monotonic stream IDs
        assert seqs == [
            "1720451234567-0",
            "1720451234567-1",
            "1720451234567-2",
            "1720451234567-3",
        ]

    @pytest.mark.asyncio
    async def test_replay_does_not_redeliver(self):
        """A client that consumed up to seq 1720451234567-2 then drops
        should, on reconnect with since=1720451234567-2, only receive
        seq 1720451234567-3+ (never already-rendered tokens)."""
        mock_rds = AsyncMock()
        mock_rds.exists = AsyncMock(return_value=1)
        mock_rds.xrange = AsyncMock(
            side_effect=[
                # Gap check: oldest entry
                [("1720451234567-0", {"event": 'event: stream_start\ndata: {"stream_id": "s"}\n\n'})],
                # Replay: entries after since
                [
                    (
                        "1720451234567-3",
                        {"event": 'data: {"type": "token", "content": "c", "seq": "1720451234567-3"}\n\n'},
                    ),
                    (
                        "1720451234567-4",
                        {"event": 'data: {"type": "token", "content": "d", "seq": "1720451234567-4"}\n\n'},
                    ),
                ],
            ]
        )
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            replayed = await replay_from_buffer("s", since_seq="1720451234567-2")

        assert replayed is not None
        replayed_seqs = [json.loads(e.split("data: ")[1])["seq"] for e in replayed]
        # Only seq 3 and 4 delivered
        assert replayed_seqs == ["1720451234567-3", "1720451234567-4"]
        rendered = {json.loads(e.split("data: ")[1]).get("content") for e in replayed}
        assert rendered == {"c", "d"}


class TestSSEStreamWrapperEmitsNoDuplicateStreamStart:
    """The v2 _sse_stream() wrapper must NOT emit its own stream_start frame.
    The canonical single stream_start comes from get_stream_buffer()."""

    @pytest.mark.asyncio
    async def test_wrapper_yields_only_inner_chunks_and_done(self):
        from app.api.v2.chat import _sse_stream

        async def fake_inner():
            yield json.dumps({"type": "token", "content": "a"})
            yield json.dumps({"type": "token", "content": "b"})

        frames = [f async for f in _sse_stream(fake_inner())]

        assert frames == [
            'data: {"type": "token", "content": "a"}\n\n',
            'data: {"type": "token", "content": "b"}\n\n',
            "data: [DONE]\n\n",
        ]
        assert not any("stream_start" in f for f in frames)

    @pytest.mark.asyncio
    async def test_buffer_emits_single_stream_start(self):
        """The canonical stream_start (event: stream_start) is emitted once
        by get_stream_buffer — and only once — for the whole stream."""

        async def fake_inner():
            yield json.dumps({"type": "token", "content": "a"})

        mock_rds = AsyncMock()
        mock_rds.xadd = AsyncMock(return_value="1720451234567-0")
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            captured = [frame async for frame in get_stream_buffer(fake_inner())]

        start_frames = [f for f in captured if "stream_start" in f]
        assert len(start_frames) == 1
        assert start_frames[0].startswith("event: stream_start")
