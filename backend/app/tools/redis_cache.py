"""
Shared Redis cache connection for tools.

Provides a lazy, singleton Redis connection with graceful fallback.
Multiple tools share one connection pool — safe for async use.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Redis connection (shared singleton) ──────────────────────────

_redis: Any | None = None
_redis_available: bool | None = None
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def get_redis():
    """Lazy Redis connection with graceful fallback (shared across tools).

    Returns an ``redis.asyncio.Redis`` client or ``None`` if Redis is
    unavailable.  All callers share one connection pool.
    """
    global _redis, _redis_available
    if _redis_available is False:
        return None
    if _redis is None:
        try:
            import redis.asyncio as redis_asyncio

            _redis = redis_asyncio.from_url(REDIS_URL, decode_responses=True)
            _redis_available = True
        except Exception:
            logger.warning("Redis unavailable; cache disabled for tools")
            _redis_available = False
            return None
    return _redis
