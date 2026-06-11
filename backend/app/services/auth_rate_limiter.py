"""Rate limiting for authentication endpoints using Redis or in-memory fallback."""

import logging
import time
from collections import defaultdict
from threading import Lock

import redis

from app.config import settings

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Fallback in-memory rate limiter when Redis is unavailable."""

    MAX_KEYS = 10000

    def __init__(self):
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def _cleanup(self, key: str, window: int) -> None:
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            self._windows[key] = [t for t in self._windows[key] if t > cutoff]
            # Evict oldest keys if over cap
            if len(self._windows) > self.MAX_KEYS:
                sorted_keys = sorted(
                    self._windows.keys(),
                    key=lambda k: self._windows[k][-1] if self._windows[k] else 0,
                )
                for old_key in sorted_keys[: len(self._windows) - self.MAX_KEYS]:
                    del self._windows[old_key]

    def check(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        """Check if request is allowed. Returns (allowed, remaining, retry_after)."""
        self._cleanup(key, window_seconds)
        with self._lock:
            current = len(self._windows[key])
            if current >= max_requests:
                oldest = self._windows[key][0]
                retry_after = int(oldest + window_seconds - time.monotonic()) + 1
                return False, 0, max(retry_after, 1)
            self._windows[key].append(time.monotonic())
            remaining = max_requests - current - 1
            return True, remaining, 0


class RedisRateLimiter:
    """Redis-backed rate limiter using sliding window."""

    def __init__(self, redis_url: str):
        self._redis = redis.from_url(redis_url, decode_responses=True)

    def check(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        """Check if request is allowed. Returns (allowed, remaining, retry_after)."""
        now = time.monotonic()
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - window_seconds)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds + 1)
        results = pipe.execute()
        count = results[2]

        if count > max_requests:
            oldest = self._redis.zrange(key, 0, 0, withscores=True)
            retry_after = int(oldest[0][1] + window_seconds - now) + 1
            return False, 0, max(retry_after, 1)

        remaining = max_requests - count
        return True, remaining, 0


# Global rate limiter instance
_rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter | RedisRateLimiter:
    """Get or create the global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        try:
            _rate_limiter = RedisRateLimiter(settings.REDIS_URL)
            logger.info("Rate limiter initialized with Redis backend")
        except Exception as e:
            logger.warning("Redis unavailable for rate limiter, using in-memory: %s", e)
            _rate_limiter = InMemoryRateLimiter()
    return _rate_limiter


def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
    """Check rate limit for a given key. Returns (allowed, remaining, retry_after)."""
    return get_rate_limiter().check(key, max_requests, window_seconds)


# Rate limit configurations for auth endpoints
RATE_LIMITS = {
    "login": {"max_requests": 5, "window_seconds": 60},  # 5 per minute
    "register": {"max_requests": 3, "window_seconds": 3600},  # 3 per hour
    "2fa_verify": {"max_requests": 5, "window_seconds": 60},  # 5 per minute
    "social_token": {"max_requests": 5, "window_seconds": 60},  # 5 per minute
    "default": {"max_requests": 100, "window_seconds": 60},  # 100 per minute
}
