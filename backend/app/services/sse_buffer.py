from __future__ import annotations

"""SSE Redis event buffer for stream replay — backed by Redis Streams.

Replaces the earlier List + INCR design with ``XADD`` / ``XRANGE`` to
eliminate the dual-source seq bug (separate ``_next_seq`` counter vs.
list-index inference in ``replay_from_buffer``).

Redis Streams give us:
  - Atomic monotonic entry IDs (no separate counter)
  - Exact-range resume via ``XRANGE id (since +``
  - Approximate ``MAXLEN`` trimming for memory bounding

The ``seq`` in SSE payloads is now the native stream entry ID (a string
like ``"1720451234567-0"``).  The client uses this as an opaque cursor.
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
_MAXLEN = 1000  # approximate max entries per stream


async def _get_stream_redis():
    """Return an async Redis client for the stream buffer, or None."""
    try:
        from redis.asyncio import from_url

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        return from_url(url, decode_responses=True)
    except Exception:
        return None


async def append_to_buffer(stream_id: str, event_data: str) -> str | None:
    """Append an SSE event to the Redis Stream buffer.

    Returns the native stream entry ID (e.g. ``"1720451234567-0"``),
    or ``None`` if Redis is unavailable.
    """
    rds = await _get_stream_redis()
    if rds is None:
        return None
    try:
        events_key = f"chat:stream:{stream_id}:events"
        seq = await rds.xadd(events_key, {"event": event_data}, maxlen=_MAXLEN, approximate=True)
        await rds.expire(events_key, _BUFFER_TTL)
        return seq
    except Exception as exc:
        logger.debug("sse_buffer_append_failed stream_id=%s error=%s", stream_id, exc)
        return None
    finally:
        await rds.aclose()


def _stamp_seq(sse_event: str, seq: str) -> str:
    """Inject the stream entry ``seq`` (string) into the JSON payload of an SSE event.

    Handles both single-line (``data: {json}``) and multi-line
    (``event: foo\\ndata: {json}``) SSE frames by scanning all lines
    for the ``data:`` payload.  Non-JSON or ``[DONE]`` frames are
    returned unchanged.
    """
    lines = sse_event.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("data: "):
            payload = line[len("data: ") :].strip()
            if not payload or payload == "[DONE]":
                return sse_event
            try:
                obj = json.loads(payload)
            except (ValueError, TypeError):
                return sse_event
            if not isinstance(obj, dict):
                return sse_event
            obj["seq"] = seq
            lines[i] = f"data: {json.dumps(obj)}"
            return "\n".join(lines)
    return sse_event


def _parse_stream_id(entry_id: str) -> tuple[int, int]:
    """Parse a Redis Stream entry ID ``'<ms>-<seq>'`` into a comparable tuple."""
    try:
        ts, seq = entry_id.split("-")
        return int(ts), int(seq)
    except (ValueError, AttributeError):
        return (0, 0)


async def replay_from_buffer(
    stream_id: str,
    since_seq: str,
    user_id: str | None = None,
) -> list[str] | None:
    """Replay SSE events with entry ID > since_seq.

    Returns None if buffer is gone (TTL expired or never existed) — caller
    returns 404 so the client falls back to the message API.
    Returns an empty list if there are no new events.

    If ``since_seq`` predates the oldest retained entry (gap expired),
    returns a single ``resync`` event so the client can do a full refetch.

    Each returned SSE frame carries a ``seq`` field on its JSON payload (the
    native Redis Stream entry ID), so a reconnecting client can advance its
    cursor precisely.

    Owner-binding (Phase-1 security, plan §7): when ``user_id`` is
    supplied and the buffer was owner-bound at create time, the stored
    owner record must match or we return None (caller → 404). This
    closes the v1 ``/streams/{id}/replay`` IDOR: a leaked/guessed
    stream id can no longer replay another user's tokens.
    """
    rds = await _get_stream_redis()
    if rds is None:
        return None
    try:
        events_key = f"chat:stream:{stream_id}:events"
        exists = await rds.exists(events_key)
        if not exists:
            return None

        # Owner check: reject cross-user (and anonymous) replay of a
        # bound buffer (fail-closed).  Unbound buffers (no owner
        # record) fall through to legacy replay behavior.
        owner_key = f"chat:stream:{stream_id}:owner"
        owner = await rds.hgetall(owner_key)
        if owner and (user_id is None or str(owner.get("user_id")) != str(user_id)):
            logger.debug("sse_buffer_replay_owner_mismatch stream_id=%s", stream_id)
            return None

        since_str = str(since_seq)

        # Check if requested resume point predates our oldest retained entry
        if since_str not in ("0", ""):
            oldest = await rds.xrange(events_key, "-", "+", count=1)
            if oldest:
                oldest_id = oldest[0][0]
                if _parse_stream_id(since_str) < _parse_stream_id(oldest_id):
                    return ["event: resync\ndata: {}\n\n"]

        # XRANGE with exclusive start: "(since" means strictly after
        start = f"({since_str}" if since_str not in ("0", "") else "-"
        raw_entries = await rds.xrange(events_key, start, "+")
        return [_stamp_seq(ev_data["event"], entry_id) for entry_id, ev_data in raw_entries]
    except Exception as exc:
        logger.debug("sse_buffer_replay_failed stream_id=%s error=%s", stream_id, exc)
        return None
    finally:
        await rds.aclose()


async def get_stream_buffer(
    inner_gen: AsyncGenerator,
    thread_id: str | None = None,
    user_id: str | None = None,
) -> AsyncGenerator:
    """Wrapper generator that buffers each yielded SSE event to a Redis Stream.

    Emits a ``stream_start`` event as the first event with the stream_id,
    then buffers and yields every event from the inner generator, stamping
    the native Redis Stream entry ID (``seq``) onto each event's JSON payload.

    When Redis is unavailable, degrades to no-resume mode (seq = "0").

    Owner-binding (Phase-1 security, plan §7): when ``thread_id`` and
    ``user_id`` are supplied, the buffer also persists a small owner
    record (``chat:stream:{stream_id}:owner``) so a leaked/guessed
    stream id cannot replay another user's tokens — ``replay_from_buffer``
    enforces the match before returning buffered frames. This closes the
    v1 ``/streams/{id}/replay`` IDOR even though v2 owns
    replay under auth.

    Usage in the route handler::

        return StreamingResponse(
            get_stream_buffer(
                _sse_stream(stream_message_to_llm(...)),
                thread_id=str(thread_id),
                user_id=str(user.id),
            ),
            media_type="text/event-stream",
        )
    """
    stream_id = str(uuid.uuid4())
    # Owner-bind the buffer when we have the caller's identity.
    if thread_id is not None and user_id is not None:
        try:
            rds_owner = await _get_stream_redis()
            if rds_owner is not None:
                owner_key = f"chat:stream:{stream_id}:owner"
                await rds_owner.hset(
                    owner_key,
                    mapping={"thread_id": str(thread_id), "user_id": str(user_id)},
                )
                await rds_owner.expire(owner_key, _BUFFER_TTL)
        except Exception as exc:
            logger.debug("sse_buffer_owner_bind_failed stream_id=%s error=%s", stream_id, exc)
    # Emit stream_start as the first event
    stream_start_obj = {"stream_id": stream_id}
    if thread_id is not None:
        stream_start_obj["thread_id"] = str(thread_id)
        stream_start_obj["user_id"] = str(user_id) if user_id is not None else None
    stream_start_sse = f"event: stream_start\ndata: {json.dumps(stream_start_obj)}\n\n"
    seq = await append_to_buffer(stream_id, stream_start_sse)
    yield _stamp_seq(stream_start_sse, seq or "0")

    async for chunk in inner_gen:
        seq = await append_to_buffer(stream_id, chunk)
        yield _stamp_seq(chunk, seq or "0")
