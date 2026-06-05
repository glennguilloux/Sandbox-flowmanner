"""Account lockout and brute-force protection service."""

import logging
import time
from collections import defaultdict
from threading import Lock

import redis

from app.config import settings

logger = logging.getLogger(__name__)


class InMemoryAttemptTracker:
    """In-memory tracker for failed login attempts."""

    MAX_KEYS = 10000

    def __init__(self):
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lockouts: dict[str, float] = {}
        self._lock = Lock()

    def _cleanup(self, key: str, window: int) -> None:
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
            # Evict oldest keys if over cap
            total_keys = len(self._attempts) + len(self._lockouts)
            if total_keys > self.MAX_KEYS:
                # Remove oldest lockouts first
                if self._lockouts:
                    oldest = sorted(self._lockouts.items(), key=lambda x: x[1])[
                        : total_keys - self.MAX_KEYS
                    ]
                    for k, _ in oldest:
                        self._lockouts.pop(k, None)
                # Then oldest attempts if still over
                if len(self._attempts) + len(self._lockouts) > self.MAX_KEYS:
                    sorted_keys = sorted(
                        self._attempts.keys(),
                        key=lambda k: self._attempts[k][-1] if self._attempts[k] else 0,
                    )
                    for old_key in sorted_keys[
                        : len(self._attempts) + len(self._lockouts) - self.MAX_KEYS
                    ]:
                        self._attempts.pop(old_key, None)

    def record_attempt(
        self, key: str, max_attempts: int = 5, window: int = 900
    ) -> dict:
        """Record a failed login attempt.

        Returns dict with:
            - locked: bool — whether the account is now locked
            - attempts_remaining: int — attempts before lockout
            - lockout_seconds: int — remaining lockout time (0 if not locked)
            - progressive_delay_ms: int — suggested delay before next attempt
        """
        self._cleanup(key, window)
        with self._lock:
            # Check if already locked
            if key in self._lockouts:
                lockout_end = self._lockouts[key]
                remaining = int(lockout_end - time.monotonic())
                if remaining > 0:
                    return {
                        "locked": True,
                        "attempts_remaining": 0,
                        "lockout_seconds": remaining,
                        "progressive_delay_ms": 0,
                    }
                else:
                    del self._lockouts[key]

            self._attempts[key].append(time.monotonic())
            count = len(self._attempts[key])
            remaining = max(0, max_attempts - count)

            if count >= max_attempts:
                # Lock out for 15 minutes
                lockout_duration = 900
                self._lockouts[key] = time.monotonic() + lockout_duration
                return {
                    "locked": True,
                    "attempts_remaining": 0,
                    "lockout_seconds": lockout_duration,
                    "progressive_delay_ms": 0,
                }

            # Progressive delay: 1s, 2s, 4s, 8s...
            progressive_delay = min(2 ** (count - 1), 16) * 1000

            return {
                "locked": False,
                "attempts_remaining": remaining,
                "lockout_seconds": 0,
                "progressive_delay_ms": progressive_delay,
            }

    def reset(self, key: str) -> None:
        """Reset attempts after successful login."""
        with self._lock:
            self._attempts.pop(key, None)
            self._lockouts.pop(key, None)


class RedisAttemptTracker:
    """Redis-backed attempt tracker for distributed deployments."""

    def __init__(self, redis_url: str):
        self._redis = redis.from_url(redis_url, decode_responses=True)

    def record_attempt(
        self, key: str, max_attempts: int = 5, window: int = 900
    ) -> dict:
        redis_key = f"login_attempts:{key}"
        lockout_key = f"login_lockout:{key}"

        # Check lockout
        lockout_ttl = self._redis.ttl(lockout_key)
        if lockout_ttl > 0:
            return {
                "locked": True,
                "attempts_remaining": 0,
                "lockout_seconds": lockout_ttl,
                "progressive_delay_ms": 0,
            }

        # Increment attempt counter
        pipe = self._redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window)
        results = pipe.execute()
        count = results[0]

        remaining = max(0, max_attempts - count)

        if count >= max_attempts:
            self._redis.setex(lockout_key, 900, "1")
            self._redis.delete(redis_key)
            return {
                "locked": True,
                "attempts_remaining": 0,
                "lockout_seconds": 900,
                "progressive_delay_ms": 0,
            }

        progressive_delay = min(2 ** (count - 1), 16) * 1000

        return {
            "locked": False,
            "attempts_remaining": remaining,
            "lockout_seconds": 0,
            "progressive_delay_ms": progressive_delay,
        }

    def reset(self, key: str) -> None:
        self._redis.delete(f"login_attempts:{key}", f"login_lockout:{key}")


# Global tracker instance
_tracker: InMemoryAttemptTracker | RedisAttemptTracker | None = None


def get_tracker() -> InMemoryAttemptTracker | RedisAttemptTracker:
    """Get or create the global attempt tracker."""
    global _tracker
    if _tracker is None:
        try:
            _tracker = RedisAttemptTracker(settings.REDIS_URL)
            logger.info("Account lockout tracker initialized with Redis backend")
        except Exception as e:
            logger.warning(
                f"Redis unavailable for lockout tracker, using in-memory: {e}"
            )
            _tracker = InMemoryAttemptTracker()
    return _tracker


def record_failed_login(identifier: str) -> dict:
    """Record a failed login attempt. Returns lockout status."""
    return get_tracker().record_attempt(identifier)


def reset_login_attempts(identifier: str) -> None:
    """Reset failed login attempts after successful login."""
    get_tracker().reset(identifier)
