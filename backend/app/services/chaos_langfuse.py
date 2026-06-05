"""
Chaos Engineering for Langfuse Integration

When CHAOS_LANGFUSE_FAIL=true, randomly injects failures into Langfuse SDK calls
to verify that LLM responses remain unaffected.

Guarantees tested:
1. LLM latency stays bounded when Langfuse is failing
2. No request fails due to Langfuse errors
3. Circuit breaker transitions correctly (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
4. % successful LLM responses while Langfuse is failing ~ 100%
"""

import logging
import random
import threading

logger = logging.getLogger(__name__)


class ChaosMode:
    """Injects controlled failures into Langfuse SDK calls."""

    def __init__(
        self,
        enabled: bool = False,
        fail_rate: float = 0.7,
        delay_rate: float = 0.2,
        timeout_rate: float = 0.1,
    ):
        self.enabled = enabled
        self.fail_rate = fail_rate  # % of calls that fail entirely
        self.delay_rate = delay_rate  # % of calls that get delayed 2-5s
        self.timeout_rate = timeout_rate  # % of calls that hang for >10s
        self._call_count = 0
        self._failure_count = 0
        self._delay_count = 0
        self._timeout_count = 0
        self._lock = threading.Lock()

    def should_inject_failure(self) -> bool:
        """Determine if this call should fail."""
        if not self.enabled:
            return False

        with self._lock:
            self._call_count += 1

        roll = random.random()
        if roll < self.fail_rate:
            with self._lock:
                self._failure_count += 1
            return True
        return False

    def should_inject_delay(self) -> float | None:
        """Determine if this call should be delayed. Returns delay seconds or None."""
        if not self.enabled:
            return None

        roll = random.random()
        if roll < self.delay_rate:
            delay = random.uniform(2.0, 5.0)
            with self._lock:
                self._delay_count += 1
            return delay
        return None

    def should_inject_timeout(self) -> bool:
        """Determine if this call should hang (simulating timeout)."""
        if not self.enabled:
            return False

        roll = random.random()
        if roll < self.timeout_rate:
            with self._lock:
                self._timeout_count += 1
            return True
        return False

    def get_stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "total_calls": self._call_count,
            "failures_injected": self._failure_count,
            "delays_injected": self._delay_count,
            "timeouts_injected": self._timeout_count,
        }


# Singleton
_chaos: ChaosMode | None = None


def get_chaos() -> ChaosMode:
    global _chaos
    if _chaos is None:
        import os

        enabled = os.environ.get("CHAOS_LANGFUSE_FAIL", "false").lower() in (
            "true",
            "1",
            "yes",
        )
        if not enabled:
            try:
                from app.config import settings

                enabled = getattr(settings, "CHAOS_LANGFUSE_FAIL", False)
            except Exception:
                logger.debug("chaos_settings_read_failed", exc_info=True)
        _chaos = ChaosMode(enabled=enabled)
    return _chaos


def toggle_chaos(enabled: bool) -> dict:
    """Enable or disable chaos mode at runtime without restart."""
    chaos = get_chaos()
    chaos.enabled = enabled
    return {"chaos_enabled": chaos.enabled, **chaos.get_stats()}
