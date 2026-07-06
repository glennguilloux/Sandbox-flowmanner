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
        mock_rds = AsyncMock()
        mock_rds.incr = AsyncMock(return_value=1)
        mock_rds.rpush = AsyncMock()
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            await append_to_buffer("test-stream", "data: hello\n\n")

        mock_rds.incr.assert_called_once_with("chat:stream:test-stream:seq")
        mock_rds.rpush.assert_called_once_with("chat:stream:test-stream:events", "data: hello\n\n")
        assert mock_rds.expire.call_count == 2  # seq key + events key

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
        mock_rds.lrange = AsyncMock(return_value=["data: event2\n\n", "data: event3\n\n"])
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            result = await replay_from_buffer("test-stream", since_seq=1)

        assert result == ["data: event2\n\n", "data: event3\n\n"]
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
        mock_rds.incr = AsyncMock(return_value=1)
        mock_rds.rpush = AsyncMock()
        mock_rds.expire = AsyncMock()
        mock_rds.aclose = AsyncMock()

        with patch("app.services.sse_buffer._get_stream_redis", return_value=mock_rds):
            chunks = [chunk async for chunk in get_stream_buffer(mock_gen())]

        # First chunk should be stream_start
        assert chunks[0].startswith("event: stream_start")
        start_data = json.loads(chunks[0].split("data: ")[1].strip())
        assert "stream_id" in start_data
        assert len(start_data["stream_id"]) == 36  # UUID

        # Remaining chunks should be the original events
        assert chunks[1] == 'data: {"type": "token", "content": "hi"}\n\n'
        assert chunks[2] == 'data: {"type": "complete"}\n\n'

        # Total: 3 events buffered (stream_start + 2 from gen)
        assert mock_rds.rpush.call_count == 3
