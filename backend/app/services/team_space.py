"""Collaborative Team Space — Redis-backed shared state for multi-agent teams.

Spaces are ephemeral (24h TTL) and use Redis sorted sets for
time-ordered messages and sets for membership tracking.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_TTL_SECONDS = 86400  # 24 hours
_KEY_PREFIX = "team_space:"


# ── Result types ──────────────────────────────────────────────────────


@dataclass
class SpaceMessage:
    agent_id: str
    content: str
    timestamp: float


@dataclass
class SpaceInfo:
    space_id: str
    members: list[str] = field(default_factory=list)
    messages: list[SpaceMessage] = field(default_factory=list)
    created_at: str = ""


# ── Redis helpers ─────────────────────────────────────────────────────


async def _get_redis():
    """Return an async Redis client, or ``None`` if unavailable."""
    try:
        from redis.asyncio import Redis

        from app.config import settings

        client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        return client
    except Exception:
        return None


def _msg_key(space_id: str) -> str:
    return f"{_KEY_PREFIX}{space_id}:messages"


def _members_key(space_id: str) -> str:
    return f"{_KEY_PREFIX}{space_id}:members"


def _meta_key(space_id: str) -> str:
    return f"{_KEY_PREFIX}{space_id}:meta"


async def _touch_ttl(redis, space_id: str) -> None:
    """Refresh TTL on all keys for *space_id*."""
    for suffix in ("messages", "members", "meta"):
        await redis.expire(f"{_KEY_PREFIX}{space_id}:{suffix}", _TTL_SECONDS)


# ── Public API ────────────────────────────────────────────────────────


async def create_space(space_id: str) -> SpaceInfo:
    """Create a new team space.  Returns the space info."""
    redis = await _get_redis()
    if redis is None:
        raise RuntimeError("Redis unavailable for team space operations")
    try:
        now = time.time()
        meta = {"created_at": now, "space_id": space_id}
        await redis.hset(_meta_key(space_id), mapping={"data": json.dumps(meta)})
        await redis.expire(_meta_key(space_id), _TTL_SECONDS)
        await redis.expire(_members_key(space_id), _TTL_SECONDS)
        await redis.expire(_msg_key(space_id), _TTL_SECONDS)
        return SpaceInfo(space_id=space_id, created_at=str(now))
    finally:
        await redis.aclose()


async def join_space(space_id: str, agent_id: str) -> SpaceInfo:
    """Add *agent_id* to the space's member set."""
    redis = await _get_redis()
    if redis is None:
        raise RuntimeError("Redis unavailable for team space operations")
    try:
        await redis.sadd(_members_key(space_id), agent_id)
        await _touch_ttl(redis, space_id)
        info = await _read_space(redis, space_id)
        return info
    finally:
        await redis.aclose()


async def post_message(space_id: str, agent_id: str, content: str) -> SpaceInfo:
    """Append a message to the space."""
    redis = await _get_redis()
    if redis is None:
        raise RuntimeError("Redis unavailable for team space operations")
    try:
        now = time.time()
        msg = json.dumps({"agent_id": agent_id, "content": content, "timestamp": now})
        await redis.zadd(_msg_key(space_id), {msg: now})
        await _touch_ttl(redis, space_id)
        info = await _read_space(redis, space_id)
        return info
    finally:
        await redis.aclose()


async def read_messages(space_id: str, since: float | None = None) -> SpaceInfo:
    """Return all messages (optionally since *since* epoch seconds)."""
    redis = await _get_redis()
    if redis is None:
        raise RuntimeError("Redis unavailable for team space operations")
    try:
        return await _read_space(redis, space_id, since=since)
    finally:
        await redis.aclose()


async def leave_space(space_id: str, agent_id: str) -> SpaceInfo:
    """Remove *agent_id* from the space's member set."""
    redis = await _get_redis()
    if redis is None:
        raise RuntimeError("Redis unavailable for team space operations")
    try:
        await redis.srem(_members_key(space_id), agent_id)
        await _touch_ttl(redis, space_id)
        info = await _read_space(redis, space_id)
        return info
    finally:
        await redis.aclose()


# ── Internal reader ───────────────────────────────────────────────────


async def _read_space(redis, space_id: str, *, since: float | None = None) -> SpaceInfo:
    """Build a SpaceInfo snapshot from Redis."""
    members = list(await redis.smembers(_members_key(space_id)))

    min_score = since if since is not None else "-inf"
    raw_messages = await redis.zrangebyscore(_msg_key(space_id), min_score, "+inf", withscores=True)
    messages: list[SpaceMessage] = []
    for raw, score in raw_messages:
        try:
            parsed = json.loads(raw)
            messages.append(
                SpaceMessage(
                    agent_id=parsed.get("agent_id", ""),
                    content=parsed.get("content", ""),
                    timestamp=parsed.get("timestamp", score),
                )
            )
        except (json.JSONDecodeError, TypeError):
            continue

    # Fetch created_at from meta
    meta_raw = await redis.hget(_meta_key(space_id), "data")
    created_at = ""
    if meta_raw:
        try:
            meta = json.loads(meta_raw)
            created_at = str(meta.get("created_at", ""))
        except (json.JSONDecodeError, TypeError):
            pass

    return SpaceInfo(
        space_id=space_id,
        members=members,
        messages=messages,
        created_at=created_at,
    )
