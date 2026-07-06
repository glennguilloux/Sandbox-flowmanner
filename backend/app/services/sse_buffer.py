from __future__ import annotations

"""SSE Redis event buffer for stream replay.

Task 1.2b of the Chat Wiring Sprint (Round 2).  Provides:
  - ``append_to_buffer`` — store each SSE event with a monotonic seq
  - ``replay_from_buffer`` — replay events after a given seq
  - ``get_stream_buffer`` — wrapper generator that buffers + yields SSE events

The buffer is keyed by ``chat:stream:{stream_id}`` with a 5-minute TTL
(sliding window — refreshed on every append).  The replay endpoint reads
from this buffer when a client reconnects with ``Last-Event-ID``.
"""

import json
import logging
import os
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

_BUFFER_TTL = 300  # 5 minutes


async def _get_stream_redis():
    """Return an async Redis client for the stream buffer, or None."""
    try:
        from redis.asyncio import from_url

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return from_url(url, decode_responses=True)
    except Exception:
        return None


async def append_to_buffer(stream_id: str, event_data: str) -> None:
    """Append an SSE event to the Redis buffer with a monotonic seq."""
    rds = await _get_stream_redis()
    if rds is None:
        return
    try:
        seq_key = f"chat:stream:{stream_id}:seq"
        events_key = f"chat:stream:{stream_id}:events"

        await rds.incr(seq_key)
        await rds.rpush(events_key, event_data)
        await rds.expire(seq_key, _BUFFER_TTL)
        await rds.expire(events_key, _BUFFER_TTL)
    except Exception as exc:
        logger.debug("sse_buffer_append_failed stream_id=%s error=%s", stream_id, exc)
    finally:
        await rds.aclose()


async def replay_from_buffer(stream_id: str, since_seq: int) -> list[str] | None:
    """Replay SSE events with seq > since_seq.

    Returns None if buffer is gone (TTL expired or never existed) — caller
    returns 404 so the client falls back to the message API.
    Returns an empty list if there are no new events.
    """
    rds = await _get_stream_redis()
    if rds is None:
        return None
    try:
        events_key = f"chat:stream:{stream_id}:events"
        seq_key = f"chat:stream:{stream_id}:seq"

        exists = await rds.exists(events_key)
        if not exists:
            return None

        # Get the total count so we can skip events <= since_seq
        total = await rds.llen(events_key)
        if total == 0:
            return []

        # Fetch all events; filter by position (since_seq maps to index)
        # Each append increments seq, so event at index i has seq = i+1
        # We want events with seq > since_seq, i.e. index >= since_seq
        raw_events = await rds.lrange(events_key, since_seq, -1)
        return raw_events
    except Exception as exc:
        logger.debug("sse_buffer_replay_failed stream_id=%s error=%s", stream_id, exc)
        return None
    finally:
        await rds.aclose()


async def get_stream_buffer(
    inner_gen: AsyncGenerator,
) -> AsyncGenerator:
    """Wrapper generator that buffers each yielded SSE event to Redis.

    Emits a ``stream_start`` event as the first event with the stream_id,
    then buffers and yields every event from the inner generator.

    Usage in the route handler::

        return StreamingResponse(
            get_stream_buffer(_sse_stream(stream_message_to_llm(...))),
            media_type="text/event-stream",
        )
    """
    stream_id = str(uuid.uuid4())

    # Emit stream_start as the first event
    stream_start_data = json.dumps({"stream_id": stream_id})
    stream_start_sse = f"event: stream_start\ndata: {stream_start_data}\n\n"
    await append_to_buffer(stream_id, stream_start_sse)
    yield stream_start_sse

    async for chunk in inner_gen:
        # Buffer each SSE-formatted chunk
        await append_to_buffer(stream_id, chunk)
        yield chunk
