"""Circuit breaker pattern for external dependency protection.

States:
  CLOSED  — normal operation, requests pass through
  OPEN    — dependency is failing, requests are rejected immediately
  HALF_OPEN — recovery probe, limited requests allowed to test recovery

Usage:
    breaker = get_circuit_breaker("deepseek")
    async with breaker.protect():
        result = await call_deepseek_api()
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from prometheus_client import Gauge

logger = logging.getLogger(__name__)

# Module-level gauges (created once, shared across all CircuitBreaker instances)
_CB_STATE_GAUGE = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["dependency"],
)
_CB_FAILURE_GAUGE = Gauge(
    "circuit_breaker_failures",
    "Recent failure count in window",
    ["dependency"],
)


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    window_seconds: float = 60.0
    name: str = "default"


@dataclass
class _FailureRecord:
    timestamp: float


class CircuitBreaker:
    """State-machine circuit breaker with Prometheus metrics."""

    def __init__(self, config: CircuitConfig):
        self.config = config
        self._state = CircuitState.CLOSED
        self._failures: list[float] = []
        self._last_state_change = time.monotonic()
        self._half_open_calls = 0
        self._half_open_successes = 0
        self._lock = asyncio.Lock()

        # Initialize gauge label for this dependency
        _CB_STATE_GAUGE.labels(dependency=config.name).set(0)

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def name(self) -> str:
        return self.config.name

    def _prune_old_failures(self) -> None:
        cutoff = time.monotonic() - self.config.window_seconds
        self._failures = [f for f in self._failures if f > cutoff]

    def _failure_count(self) -> int:
        self._prune_old_failures()
        return len(self._failures)

    def _should_trip(self) -> bool:
        return self._failure_count() >= self.config.failure_threshold

    def _should_attempt_reset(self) -> bool:
        return (
            time.monotonic() - self._last_state_change
        ) >= self.config.recovery_timeout

    async def _transition(self, new_state: CircuitState) -> None:
        old = self._state
        self._state = new_state
        self._last_state_change = time.monotonic()

        state_value = {"closed": 0, "open": 1, "half_open": 2}[new_state.value]
        _CB_STATE_GAUGE.labels(dependency=self.config.name).set(state_value)

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._half_open_successes = 0

        logger.info(
            "Circuit breaker [%s] %s → %s (failures=%d)",
            self.config.name,
            old.value,
            new_state.value,
            self._failure_count(),
        )

        # Fire alert on state change (non-blocking)
        try:
            from app.services.alerting import send_circuit_alert

            asyncio.get_event_loop().create_task(
                send_circuit_alert(
                    dependency=self.config.name,
                    old_state=old.value,
                    new_state=new_state.value,
                    failure_count=self._failure_count(),
                )
            )
        except Exception:
            logger.debug("circuit_alert_failed", exc_info=True)

    def record_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.config.half_open_max_calls:
                asyncio.get_event_loop().create_task(
                    self._transition(CircuitState.CLOSED)
                )
                self._failures.clear()

    def record_failure(self) -> None:
        self._failures.append(time.monotonic())
        _CB_FAILURE_GAUGE.labels(dependency=self.config.name).set(self._failure_count())

        if self._state == CircuitState.HALF_OPEN or (
            self._state == CircuitState.CLOSED and self._should_trip()
        ):
            asyncio.get_event_loop().create_task(self._transition(CircuitState.OPEN))

    @asynccontextmanager
    async def protect(self):
        """Context manager that enforces circuit breaker logic.

        Raises CircuitOpenError if the circuit is open.
        Records success/failure automatically.
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    await self._transition(CircuitState.HALF_OPEN)
                else:
                    raise CircuitOpenError(
                        f"Circuit [{self.config.name}] is OPEN — "
                        f"rejecting request (retry in {self.config.recovery_timeout}s)"
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitOpenError(
                        f"Circuit [{self.config.name}] is HALF_OPEN — "
                        f"max probe calls reached"
                    )
                self._half_open_calls += 1

        try:
            yield self
            self.record_success()
        except CircuitOpenError:
            raise
        except Exception:
            self.record_failure()
            raise

    def get_status(self) -> dict[str, Any]:
        return {
            "name": self.config.name,
            "state": self._state.value,
            "failure_count": self._failure_count(),
            "failure_threshold": self.config.failure_threshold,
            "recovery_timeout": self.config.recovery_timeout,
            "seconds_since_state_change": round(
                time.monotonic() - self._last_state_change, 1
            ),
        }


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open and rejecting requests."""


# --- Registry ---

_breakers: dict[str, CircuitBreaker] = {}
_initialized = False


def _init_default_breakers() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    configs = [
        CircuitConfig(
            name="deepseek",
            failure_threshold=5,
            recovery_timeout=30.0,
            window_seconds=30.0,
            half_open_max_calls=2,
        ),
        CircuitConfig(
            name="llamacpp",
            failure_threshold=3,
            recovery_timeout=60.0,
            window_seconds=60.0,
            half_open_max_calls=2,
        ),
        CircuitConfig(
            name="redis",
            failure_threshold=10,
            recovery_timeout=10.0,
            window_seconds=10.0,
            half_open_max_calls=3,
        ),
        CircuitConfig(
            name="qdrant",
            failure_threshold=5,
            recovery_timeout=30.0,
            window_seconds=30.0,
            half_open_max_calls=2,
        ),
    ]

    for cfg in configs:
        _breakers[cfg.name] = CircuitBreaker(cfg)
        logger.info(
            "Circuit breaker [%s] initialized: threshold=%d, recovery=%ds",
            cfg.name,
            cfg.failure_threshold,
            int(cfg.recovery_timeout),
        )


def get_circuit_breaker(name: str) -> CircuitBreaker:
    _init_default_breakers()
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(CircuitConfig(name=name))
    return _breakers[name]


def get_all_breakers() -> dict[str, CircuitBreaker]:
    _init_default_breakers()
    return dict(_breakers)
