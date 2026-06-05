"""Redis cache-aside service for high-read mission views.

Cache keys are user-scoped to prevent cross-user stale reads.
Invalidation happens on any mutation (create/update/delete/execute/abort/
pause/resume/retry) by deleting the relevant cache keys.

TTLs are configurable via settings: MISSION_CACHE_LIST_TTL, MISSION_CACHE_GET_TTL,
MISSION_CACHE_ACTIVE_TTL.
"""

from __future__ import annotations

import json

import structlog

from app.config import settings

# Lazy import to avoid test failures when redis is mocked
AsyncRedis = None

logger = structlog.get_logger(__name__)

_redis: AsyncRedis | None = None
_redis_available: bool | None = None


async def _get_redis():
    global _redis, _redis_available, AsyncRedis
    if _redis_available is False:
        return None
    if _redis is None:
        try:
            from redis.asyncio import Redis as _AsyncRedis
            AsyncRedis = _AsyncRedis
            _redis = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
            await _redis.ping()
            _redis_available = True
        except Exception:
            _redis_available = False
            logger.warning("mission_cache_redis_unavailable")
            return None
    return _redis


# ── Cache keys ────────────────────────────────────────────────────────────────


def _list_key(user_id: int, page: int, per_page: int, workspace_id: str | None = None) -> str:
    ws_part = f":ws:{workspace_id}" if workspace_id else ""
    return f"mission:list:{user_id}{ws_part}:p{page}:pp{per_page}"


def _get_key(user_id: int, mission_id: str) -> str:
    return f"mission:get:{user_id}:{mission_id}"


def _active_key(user_id: int, workspace_id: str | None = None) -> str:
    ws_part = f":ws:{workspace_id}" if workspace_id else ""
    return f"mission:active:{user_id}{ws_part}"


def _tasks_key(user_id: int, mission_id: str) -> str:
    return f"mission:tasks:{user_id}:{mission_id}"


def _logs_key(user_id: int, mission_id: str) -> str:
    return f"mission:logs:{user_id}:{mission_id}"


def _status_key(user_id: int, mission_id: str) -> str:
    return f"mission:status:{user_id}:{mission_id}"


def _improvements_key(user_id: int, mission_id: str) -> str:
    return f"mission:improvements:{user_id}:{mission_id}"


# ── Public API ────────────────────────────────────────────────────────────────


async def cache_get(user_id: int, mission_id: str) -> dict | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(_get_key(user_id, mission_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set(user_id: int, mission_id: str, data: dict, ttl: int | None = None) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        ttl = ttl or settings.MISSION_CACHE_GET_TTL
        await r.setex(_get_key(user_id, mission_id), ttl, json.dumps(data))
    except Exception:
        logger.debug("mission_cache_set_failed", mission_id=mission_id)


async def cache_list(user_id: int, page: int, per_page: int, workspace_id: str | None = None) -> dict | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(_list_key(user_id, page, per_page, workspace_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set_list(user_id: int, page: int, per_page: int, data: dict, workspace_id: str | None = None) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.setex(_list_key(user_id, page, per_page, workspace_id), settings.MISSION_CACHE_LIST_TTL, json.dumps(data))
    except Exception as e:
        logger.debug("mission_cache_set_list_failed", user_id=user_id, error=str(e))


async def cache_active(user_id: int, workspace_id: str | None = None) -> dict | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(_active_key(user_id, workspace_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set_active(user_id: int, data: dict, workspace_id: str | None = None) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.setex(_active_key(user_id, workspace_id), settings.MISSION_CACHE_ACTIVE_TTL, json.dumps(data))
    except Exception as e:
        logger.debug("mission_cache_set_active_failed", user_id=user_id, error=str(e))


# ── Tasks cache ────────────────────────────────────────────────────────────────


async def cache_get_tasks(user_id: int, mission_id: str) -> dict | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(_tasks_key(user_id, mission_id))
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.debug("mission_cache_get_tasks_failed", mission_id=mission_id, error=str(e))
        return None


async def cache_set_tasks(user_id: int, mission_id: str, data: dict, ttl: int | None = None) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        ttl = ttl or settings.MISSION_CACHE_GET_TTL
        await r.setex(_tasks_key(user_id, mission_id), ttl, json.dumps(data))
    except Exception as e:
        logger.debug("mission_cache_set_tasks_failed", mission_id=mission_id, error=str(e))


# ── Logs cache ─────────────────────────────────────────────────────────────────


async def cache_get_logs(user_id: int, mission_id: str) -> dict | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(_logs_key(user_id, mission_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set_logs(user_id: int, mission_id: str, data: dict, ttl: int | None = None) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        ttl = ttl or settings.MISSION_CACHE_GET_TTL
        await r.setex(_logs_key(user_id, mission_id), ttl, json.dumps(data))
    except Exception as e:
        logger.debug("mission_cache_set_logs_failed", mission_id=mission_id, error=str(e))


# ── Status cache ───────────────────────────────────────────────────────────────


async def cache_get_status(user_id: int, mission_id: str) -> dict | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(_status_key(user_id, mission_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set_status(user_id: int, mission_id: str, data: dict, ttl: int | None = None) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        ttl = ttl or settings.MISSION_CACHE_ACTIVE_TTL
        await r.setex(_status_key(user_id, mission_id), ttl, json.dumps(data))
    except Exception as e:
        logger.debug("mission_cache_set_status_failed", mission_id=mission_id, error=str(e))


# ── Improvements cache ────────────────────────────────────────────────────────


async def cache_get_improvements(user_id: int, mission_id: str) -> dict | None:
    r = await _get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(_improvements_key(user_id, mission_id))
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def cache_set_improvements(user_id: int, mission_id: str, data: dict, ttl: int | None = None) -> None:
    r = await _get_redis()
    if r is None:
        return
    try:
        ttl = ttl or settings.MISSION_CACHE_GET_TTL
        await r.setex(_improvements_key(user_id, mission_id), ttl, json.dumps(data))
    except Exception as e:
        logger.debug("mission_cache_set_improvements_failed", mission_id=mission_id, error=str(e))


# ── Invalidation (called after mutations) ─────────────────────────────────────


async def invalidate_user_caches(user_id: int) -> None:
    """Invalidate all cached mission views for a user after any mutation."""
    r = await _get_redis()
    if r is None:
        return
    try:
        pattern = f"mission:list:{user_id}:*"
        cursor = 0
        while True:
            cursor, keys = await r.scan(cursor, match=pattern, count=100)
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break
        # Delete both workspace-scoped and non-scoped active caches
        await r.delete(_active_key(user_id))
        active_ws_pattern = f"mission:active:{user_id}:ws:*"
        ws_cursor = 0
        while True:
            ws_cursor, ws_keys = await r.scan(ws_cursor, match=active_ws_pattern, count=100)
            if ws_keys:
                await r.delete(*ws_keys)
            if ws_cursor == 0:
                break
    except Exception:
        logger.debug("mission_cache_invalidation_failed", user_id=user_id)


async def invalidate_mission_cache(user_id: int, mission_id: str) -> None:
    """Invalidate all cached views for a single mission (get, tasks, logs, status)."""
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.delete(
            _get_key(user_id, mission_id),
            _tasks_key(user_id, mission_id),
            _logs_key(user_id, mission_id),
            _status_key(user_id, mission_id),
            _improvements_key(user_id, mission_id),
            _active_key(user_id),  # no-workspace variant
        )
    except Exception as e:
        logger.debug("mission_cache_invalidate_failed", mission_id=mission_id, error=str(e))
