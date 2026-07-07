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
    """Append an SSE event to the Redis buffer.

    The monotonic ``seq`` is assigned upstream (in ``get_stream_buffer`` via
    ``_next_seq``) and baked into ``event_data``'s JSON payload — do NOT
    incr the seq key here, or seq would advance twice per event.
    """
    rds = await _get_stream_redis()
    if rds is None:
        return
    try:
        events_key = f"chat:stream:{stream_id}:events"

        await rds.rpush(events_key, event_data)
        await rds.expire(events_key, _BUFFER_TTL)
    except Exception as exc:
        logger.debug("sse_buffer_append_failed stream_id=%s error=%s", stream_id, exc)
    finally:
        await rds.aclose()


def _stamp_seq(sse_event: str, seq: int) -> str:
    """Inject the monotonic ``seq`` into the JSON payload of an SSE event.

    Accepts an SSE frame (e.g. ``data: {json}\\n\\n`` or
    ``event: stream_start\\ndata: {json}\\n\\n``), parses the ``data:`` JSON,
    sets ``seq`` on it, and returns the re-serialized frame. Non-JSON or
    ``[DONE]`` frames are returned unchanged so downstream parsers still work.
    """
    nl = sse_event.find("\n")
    head = sse_event[:nl] if nl != -1 else sse_event
    if not head.startswith("data: "):
        return sse_event
    payload = head[len("data: ") :].strip()
    if not payload or payload == "[DONE]":
        return sse_event
    try:
        obj = json.loads(payload)
    except (ValueError, TypeError):
        return sse_event
    if not isinstance(obj, dict):
        return sse_event
    obj["seq"] = seq
    tail = sse_event[nl:] if nl != -1 else "\n\n"
    return f"data: {json.dumps(obj)}{tail}"


async def replay_from_buffer(stream_id: str, since_seq: int) -> list[str] | None:
    """Replay SSE events with seq > since_seq.

    Returns None if buffer is gone (TTL expired or never existed) — caller
    returns 404 so the client falls back to the message API.
    Returns an empty list if there are no new events.

    Each returned SSE frame carries a ``seq`` field on its JSON payload, so a
    reconnecting client can advance its cursor precisely and never redelivers
    already-rendered tokens.
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

        total = await rds.llen(events_key)
        if total == 0:
            return []

        # Each append increments seq, so event at index i has seq = i + 1.
        # We want events with seq > since_seq, i.e. index >= since_seq.
        raw_events = await rds.lrange(events_key, since_seq, -1)
        # Re-stamp seq defensively (buffer stores already-stamped frames, but
        # this guarantees the cursor contract for the client).
        return [_stamp_seq(e, since_seq + i + 1) for i, e in enumerate(raw_events)]
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
    then buffers and yields every event from the inner generator, stamping a
    monotonic ``seq`` onto each event's JSON payload. The seq lets the client
    resume precisely after a reconnect (see ``replay_from_buffer``).

    Usage in the route handler::

        return StreamingResponse(
            get_stream_buffer(_sse_stream(stream_message_to_llm(...))),
            media_type="text/event-stream",
        )
    """
    stream_id = str(uuid.uuid4())

    # Emit stream_start as the first event (seq 1)
    seq = await _next_seq(stream_id)
    stream_start_obj = {"stream_id": stream_id, "seq": seq}
    stream_start_sse = f"event: stream_start\ndata: {json.dumps(stream_start_obj)}\n\n"
    await append_to_buffer(stream_id, stream_start_sse)
    yield stream_start_sse

    async for chunk in inner_gen:
        seq = await _next_seq(stream_id)
        stamped = _stamp_seq(chunk, seq)
        # Buffer the stamped frame so replay keeps the same seq values
        await append_to_buffer(stream_id, stamped)
        yield stamped


async def _next_seq(stream_id: str) -> int:
    """Return the next monotonic seq for a stream (1-based)."""
    rds = await _get_stream_redis()
    if rds is None:
        # No redis: fall back to a local per-call counter via the module cache
        return _local_seq_cache.get(stream_id, 0) + 1
    try:
        seq = await rds.incr(f"chat:stream:{stream_id}:seq")
        await rds.expire(f"chat:stream:{stream_id}:seq", _BUFFER_TTL)
        return seq
    except Exception as exc:
        logger.debug("sse_buffer_seq_failed stream_id=%s error=%s", stream_id, exc)
        return _local_seq_cache.get(stream_id, 0) + 1
    finally:
        await rds.aclose()


_local_seq_cache: dict[str, int] = {}
