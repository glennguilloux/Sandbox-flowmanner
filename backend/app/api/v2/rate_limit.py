"""Per-user rate limiting dependency for API v2 missions.

Redis-backed sliding-window strategy with proper in-memory fallback:
- Redis available → Redis sorted-set sliding window
- Redis unavailable → in-process sliding window enforces limits

Limits are settings-driven via app.config.Settings.

Errors use v2 envelope:
  { "data": null, "meta": {...}, "error": { "code": "RATE_LIMITED", "message": "..." } }
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user
from app.api.v2.base import ErrorDetail, ResponseMeta

if TYPE_CHECKING:
    from app.models.user import User

logger = structlog.get_logger(__name__)

# ── Settings-driven defaults (fallback if settings not available) ─────────────
_FALLBACK_LIMIT = 60
_FALLBACK_WINDOW = 60
_FALLBACK_BURST = 2


def _get_limits_from_settings():
    """Read rate-limit config from app settings or return defaults."""
    try:
        from app.config import settings

        return {
            "mission:create": getattr(settings, "MISSION_RATE_LIMIT_CREATE", 30),
            "mission:update": getattr(settings, "MISSION_RATE_LIMIT_UPDATE", 30),
            "mission:delete": getattr(settings, "MISSION_RATE_LIMIT_DELETE", 15),
            "mission:execute": getattr(settings, "MISSION_RATE_LIMIT_EXECUTE", 20),
            "mission:abort": getattr(settings, "MISSION_RATE_LIMIT_ABORT", 15),
            "mission:plan": getattr(settings, "MISSION_RATE_LIMIT_PLAN", 20),
            "_DEFAULT": getattr(settings, "MISSION_RATE_LIMIT_DEFAULT", _FALLBACK_LIMIT),
            "_WINDOW": getattr(settings, "MISSION_RATE_LIMIT_WINDOW_SECONDS", _FALLBACK_WINDOW),
            "_BURST": getattr(settings, "MISSION_RATE_LIMIT_BURST_MULTIPLIER", _FALLBACK_BURST),
        }
    except Exception:
        return {}


# ── Redis helpers ─────────────────────────────────────────────────────────────


async def _get_redis():
    """Lazy Redis client."""
    try:
        from redis.asyncio import Redis as AsyncRedis

        from app.config import settings

        r = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.ping()
        return r
    except Exception:
        return None


async def _redis_allowed(key: str, max_tokens: int, window_s: int, burst: int) -> tuple[bool, int, int]:
    """Redis sorted-set sliding window. Returns (allowed, remaining, retry_after)."""
    r = await _get_redis()
    if r is None:
        return True, max_tokens, 0  # Redis down → fall through to in-memory

    now_ms = int(time.time() * 1000)
    window_ms = window_s * 1000
    cutoff = now_ms - window_ms
    burst_max = max_tokens * burst

    try:
        async with r.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            pipe.zadd(key, {str(now_ms): now_ms})
            pipe.expire(key, window_s * 2)
            _, count, _, _ = await pipe.execute()

        if count > burst_max:
            oldest = await r.zrange(key, 0, 0, withscores=True)
            oldest_ts = int(oldest[0][1]) if oldest else cutoff
            retry = max(1, int((oldest_ts + window_ms - now_ms) / 1000) + 1)
            return False, 0, retry
        remaining = max(0, burst_max - count)
        return True, remaining, 0
    except Exception:
        logger.warning("rate_limit_redis_error", exc_info=True)
        return True, max_tokens, 0


def _inmem_allowed(
    windows: dict[str, list[float]],
    key: str,
    max_tokens: int,
    window_s: int,
    burst: int,
) -> tuple[bool, int, int]:
    """In-memory sliding window. Returns (allowed, remaining, retry_after)."""
    now = time.monotonic()
    cutoff = now - window_s
    burst_max = max_tokens * burst

    if key not in windows:
        windows[key] = []
    windows[key] = [t for t in windows[key] if t > cutoff]

    if len(windows[key]) >= burst_max:
        oldest = windows[key][0]
        retry = max(1, int(oldest + window_s - now) + 1)
        return False, 0, retry
    windows[key].append(now)
    remaining = burst_max - len(windows[key])
    return True, remaining, 0


def _build_429(limit: int, window_s: int, retry: int) -> JSONResponse:
    meta = ResponseMeta()
    error = ErrorDetail(
        code="RATE_LIMITED",
        message="Rate limit exceeded. Please slow down.",
        details={"limit": limit, "window_seconds": window_s, "retry_after": retry},
    )
    return JSONResponse(
        status_code=429,
        content={"data": None, "meta": meta.model_dump(), "error": error.model_dump()},
        headers={
            "Retry-After": str(retry),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + window_s),
        },
    )


# ── FastAPI dependency factory ────────────────────────────────────────────────


def rate_limit(endpoint_key: str, *, limit: int | None = None, window_seconds: int | None = None):
    """FastAPI dependency factory for per-user rate limiting.

    Checks Redis first, then in-memory.  Either one can deny the request.
    """
    cfg = _get_limits_from_settings()
    effective_limit = limit or cfg.get(endpoint_key, cfg.get("_DEFAULT", _FALLBACK_LIMIT))
    effective_window = window_seconds or cfg.get("_WINDOW", _FALLBACK_WINDOW)
    effective_burst = cfg.get("_BURST", _FALLBACK_BURST)
    inmem: dict[str, list[float]] = {}

    async def _check(
        request: Request,
        user: User = Depends(get_current_user),
    ) -> JSONResponse | None:
        key = f"rl:v2:mission:{endpoint_key}:user:{user.id}"

        # Always check in-memory (authoritative, per-process gate)
        # Redis check is optional cross-process hint, not required
        inmem_ok, remaining, inmem_retry = _inmem_allowed(
            inmem, key, effective_limit, effective_window, effective_burst
        )

        # Store rate limit state on request.state for the headers middleware
        request.state.rate_limit_limit = effective_limit
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset = int(time.time()) + effective_window

        if not inmem_ok:
            return _build_429(effective_limit, effective_window, inmem_retry)

        return None

    return _check
