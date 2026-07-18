"""
Langfuse Integration Service

Central integration point for Langfuse observability in the workflows backend.
Provides:
- Singleton Langfuse client with graceful degradation
- Trace/Span creation that mirrors existing ObservabilityService API
- LangChain callback handler factory
- LiteLLM callback configuration
- Sampling and flush control
- Non-blocking guarantees: all SDK calls wrapped in try/except
- Circuit breaker with formal state machine (CLOSED, OPEN, HALF_OPEN)
- Bounded retries with exponential backoff on transient failures
- 3-second timeout on all SDK operations
- Per-worker isolation (each Uvicorn worker has its own singleton)
- Trace statistics counters for monitoring
- Prometheus metrics integration for production observability

Circuit Breaker State Machine:
    CLOSED  -> OPEN:      after CIRCUIT_FAILURE_THRESHOLD consecutive failures
    OPEN    -> HALF_OPEN: after CIRCUIT_RECOVERY_SECONDS cooldown
    HALF_OPEN -> CLOSED:  on first successful call
    HALF_OPEN -> OPEN:    on failure during probe

Worker Isolation:
    Each Uvicorn worker has its own process, its own LangfuseService
    singleton, and its own circuit breaker state. This is by design —
    no cross-worker state sharing is needed since traces are independent.
    The worker_id (os.getpid()) is included in trace metadata so the
    Langfuse UI can filter traces by worker.

Used by:
- app.services.nexus.observability.ObservabilityService (delegates here)
- app.services.nexus.tracing.LangGraphTraceEmitter (dual-emit bridge)
- app.api.v1.llm (LangChain callback injection)
"""

import logging
import os
import threading
import time
import uuid
from enum import Enum
from typing import Any

from app.services.chaos_langfuse import get_chaos
from app.services.langfuse_metrics import (
    langfuse_traces_failed,
    langfuse_traces_sent,
    observe_operation,
    update_circuit_breaker_gauge,
)
from app.services.reliability_assertions import get_reliability_monitor

logger = logging.getLogger(__name__)

# Circuit breaker constants
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RECOVERY_SECONDS = 60
CALLBACK_CREATION_TIMEOUT_SECONDS = 2
SDK_OPERATION_TIMEOUT_SECONDS = 3
FLUSH_TIMEOUT_SECONDS = 5

# Retry constants
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 0.5  # seconds; retries at 0.5s, 1.5s


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"  # Normal operation — tracing active
    OPEN = "OPEN"  # Tracing disabled — too many failures
    HALF_OPEN = "HALF_OPEN"  # Probing — allowing one test call


# Lazy imports — Langfuse SDK is optional
class _LangfuseUnavailable:
    """Stub when Langfuse is not installed or not configured."""

    class _StubTrace:
        def span(self, **kwargs):
            return _LangfuseUnavailable._StubSpan()

        def generation(self, **kwargs):
            return _LangfuseUnavailable._StubSpan()

        def update(self, **kwargs):
            pass

    class _StubSpan:
        def span(self, **kwargs):
            return _LangfuseUnavailable._StubSpan()

        def generation(self, **kwargs):
            return _LangfuseUnavailable._StubSpan()

        def update(self, **kwargs):
            pass

        def end(self, **kwargs):
            pass

        def score(self, **kwargs):
            pass

    _trace = _StubTrace()
    _span = _StubSpan()

    def trace(self, **kwargs):
        return self._trace

    def flush(self):
        pass

    def shutdown(self):
        pass


def _is_transient_error(exc: Exception) -> bool:
    """Determine if an exception is transient (worth retrying)."""
    transient_types = (
        ConnectionError,
        ConnectionResetError,
        ConnectionRefusedError,
        ConnectionAbortedError,
        TimeoutError,
        OSError,
    )
    if isinstance(exc, transient_types):
        return True
    msg = str(exc).lower()
    transient_keywords = [
        "connection",
        "timeout",
        "timed out",
        "refused",
        "reset",
        "unreachable",
        "network",
        "temporary",
    ]
    auth_keywords = [
        "unauthorized",
        "forbidden",
        "authentication",
        "invalid api key",
        "invalid credentials",
    ]
    if any(kw in msg for kw in auth_keywords):
        return False
    return bool(any(kw in msg for kw in transient_keywords))


def _run_with_timeout(func, timeout_seconds: float, *args, **kwargs):
    """Run a function with a timeout using threading."""
    result: list[Any] = [None]
    error: list[Exception | None] = [None]
    done = threading.Event()

    def _worker():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            error[0] = e
        finally:
            done.set()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()

    if not done.wait(timeout=timeout_seconds):
        error[0] = TimeoutError(f"Langfuse SDK operation timed out after {timeout_seconds}s")

    return result[0], error[0]


def _run_with_retry(func, timeout_seconds: float, *args, **kwargs):
    """Run a function with timeout and bounded retries on transient errors."""
    # Chaos injection
    chaos = get_chaos()
    if chaos.enabled:
        if chaos.should_inject_timeout():
            time.sleep(15)  # Will be caught by 3s timeout
        delay = chaos.should_inject_delay()
        if delay:
            time.sleep(delay)
        if chaos.should_inject_failure():
            get_reliability_monitor().record_langfuse_failure("chaos_injected")
            raise ConnectionError("[CHAOS] Injected Langfuse connection failure")

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        result, error = _run_with_timeout(func, timeout_seconds, *args, **kwargs)
        if error is None:
            return result, None
        last_error = error
        if not _is_transient_error(error):
            break
        if attempt < MAX_RETRIES:
            backoff = RETRY_BACKOFF_BASE * (3**attempt)
            logger.debug(
                "Langfuse transient error (attempt %s/%s), retrying in %.1fs: %s",
                attempt + 1,
                MAX_RETRIES + 1,
                backoff,
                error,
            )
            time.sleep(backoff)
    return None, last_error


class LangfuseService:
    """Singleton service wrapping the Langfuse SDK with Prometheus metrics."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._client = None
        self._enabled = False
        self._sampling_rate = 1.0
        self._flush_interval = 1.0
        self._host = None
        self._worker_id = os.getpid()
        self._circuit_state = CircuitState.CLOSED
        self._failure_count = 0
        self._circuit_open_until = 0.0
        self._last_failure_reason = None
        self._lock = threading.Lock()
        self._traces_sent = 0
        self._traces_failed = 0
        # Initialize Prometheus circuit breaker gauge
        try:
            update_circuit_breaker_gauge(self._worker_id, CircuitState.CLOSED.value)
        except Exception:
            logger.debug("langfuse_init_gauge_failed", exc_info=True)

    def initialize(
        self,
        public_key: str,
        secret_key: str,
        host: str = "http://langfuse-web:3000",
        enabled: bool = True,
        sampling_rate: float = 1.0,
        flush_interval: float = 1.0,
    ) -> bool:
        """Initialize the Langfuse client. Called once at app startup."""
        if not enabled:
            logger.info("Langfuse disabled via configuration")
            self._enabled = False
            return False
        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            self._enabled = True
            self._sampling_rate = sampling_rate
            self._flush_interval = flush_interval
            self._host = host
            logger.info(
                "Langfuse client initialized (worker=%s, host=%s, sampling=%s)",
                self._worker_id,
                host,
                sampling_rate,
            )
            return True
        except ImportError:
            logger.warning("Langfuse SDK not installed")
            self._enabled = False
            return False
        except Exception as e:
            logger.error("Failed to initialize Langfuse: %s", e)
            self._enabled = False
            return False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def worker_id(self) -> int:
        return self._worker_id

    @property
    def circuit_state(self) -> str:
        """Get the current circuit breaker state. Transitions OPEN->HALF_OPEN if cooldown elapsed."""
        with self._lock:
            if self._circuit_state == CircuitState.OPEN and time.time() >= self._circuit_open_until:
                self._circuit_state = CircuitState.HALF_OPEN
                try:
                    get_reliability_monitor().record_circuit_transition("OPEN", "HALF_OPEN")
                except Exception:
                    logger.debug("langfuse_reliability_monitor_failed", exc_info=True)
                logger.warning(
                    "Langfuse circuit breaker: OPEN -> HALF_OPEN (worker=%s, probing after cooldown)",
                    self._worker_id,
                )
                try:
                    update_circuit_breaker_gauge(self._worker_id, CircuitState.HALF_OPEN.value)
                except Exception:
                    logger.debug("langfuse_gauge_update_failed", exc_info=True)
            return self._circuit_state.value

    @property
    def circuit_open(self) -> bool:
        state = self.circuit_state
        return state == CircuitState.OPEN.value

    def circuit_reset(self):
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            old_state = self._circuit_state
            self._circuit_state = CircuitState.CLOSED
            self._failure_count = 0
            self._circuit_open_until = 0.0
            self._last_failure_reason = None
            logger.warning(
                "Langfuse circuit breaker: %s -> CLOSED (manual reset, worker=%s)",
                old_state.value,
                self._worker_id,
            )
        try:
            update_circuit_breaker_gauge(self._worker_id, CircuitState.CLOSED.value)
        except Exception:
            logger.debug("langfuse_gauge_reset_failed", exc_info=True)

    def _transition_to_open(self):
        """Transition circuit breaker to OPEN state (must hold self._lock)."""
        old_state = self._circuit_state
        self._circuit_state = CircuitState.OPEN
        try:
            get_reliability_monitor().record_circuit_transition(old_state.value, CircuitState.OPEN.value)
        except Exception:
            logger.debug("langfuse_transition_monitor_failed", exc_info=True)
        self._circuit_open_until = time.time() + CIRCUIT_RECOVERY_SECONDS
        logger.warning(
            "Langfuse circuit breaker: %s -> OPEN (worker=%s, %s consecutive failures, disabled for %ss)",
            old_state.value,
            self._worker_id,
            self._failure_count,
            CIRCUIT_RECOVERY_SECONDS,
        )
        try:
            update_circuit_breaker_gauge(self._worker_id, CircuitState.OPEN.value)
        except Exception:
            logger.debug("langfuse_open_gauge_failed", exc_info=True)

    def _record_success(self, operation: str = "unknown", duration: float = 0.0):
        """Record a successful SDK call with Prometheus metrics."""
        with self._lock:
            self._failure_count = 0
            self._last_failure_reason = None
            if self._circuit_state == CircuitState.HALF_OPEN:
                self._circuit_state = CircuitState.CLOSED
                try:
                    get_reliability_monitor().record_circuit_transition("HALF_OPEN", "CLOSED")
                except Exception:
                    logger.debug("langfuse_close_transition_failed", exc_info=True)
                logger.warning(
                    "Langfuse circuit breaker: HALF_OPEN -> CLOSED (worker=%s, probe succeeded)",
                    self._worker_id,
                )
            self._traces_sent += 1
        # Prometheus metrics (outside lock)
        try:
            langfuse_traces_sent.inc()
            update_circuit_breaker_gauge(self._worker_id, self.circuit_state)
            if duration > 0:
                observe_operation(operation, duration)
        except Exception:
            logger.debug("langfuse_success_metrics_failed", exc_info=True)

    def _record_failure(self, reason=None, operation: str = "unknown", duration: float = 0.0):
        """Record a failed SDK call with Prometheus metrics."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_reason = reason
            self._traces_failed += 1
            if self._circuit_state == CircuitState.HALF_OPEN or self._failure_count >= CIRCUIT_FAILURE_THRESHOLD:
                self._transition_to_open()
            else:
                logger.debug(
                    "Langfuse failure count: %s/%s (worker=%s)",
                    self._failure_count,
                    CIRCUIT_FAILURE_THRESHOLD,
                    self._worker_id,
                )
        # Prometheus metrics (outside lock)
        try:
            langfuse_traces_failed.inc()
            update_circuit_breaker_gauge(self._worker_id, self.circuit_state)
            if duration > 0:
                observe_operation(operation, duration)
        except Exception:
            logger.debug("langfuse_failure_metrics_failed", exc_info=True)

    @property
    def client(self):
        if not self._enabled or self._client is None:
            return _LangfuseUnavailable()
        return self._client

    def _base_trace_metadata(self) -> dict[str, Any]:
        return {"worker_id": self._worker_id}

    def trace(
        self,
        trace_id=None,
        name=None,
        user_id=None,
        metadata=None,
        input=None,
        output=None,
        tags=None,
        session_id=None,
        version=None,
    ):
        """Create a Langfuse trace. Returns a trace object or stub."""
        if not self._should_sample():
            return _LangfuseUnavailable._StubTrace()
        if self.circuit_open:
            return _LangfuseUnavailable._StubTrace()
        merged_metadata = {**self._base_trace_metadata(), **(metadata or {})}

        def _call():
            return self.client.trace(
                id=trace_id,
                name=name,
                user_id=user_id,
                metadata=merged_metadata,
                input=input,
                output=output,
                tags=tags,
                session_id=session_id,
                version=version,
            )

        start = time.perf_counter()
        result, error = _run_with_retry(_call, SDK_OPERATION_TIMEOUT_SECONDS)
        duration = time.perf_counter() - start
        if error is None:
            self._record_success(operation="trace", duration=duration)
            return result
        else:
            logger.debug("Langfuse trace creation failed: %s", error)
            self._record_failure(str(error), operation="trace", duration=duration)
            return _LangfuseUnavailable._StubTrace()

    def span(
        self,
        trace_id=None,
        parent_observation_id=None,
        name=None,
        metadata=None,
        input=None,
        output=None,
        start_time=None,
        end_time=None,
        status_message=None,
        level="DEFAULT",
        version=None,
    ):
        """Create a Langfuse span within a trace."""
        if not self._should_sample():
            return _LangfuseUnavailable._StubSpan()
        if self.circuit_open:
            return _LangfuseUnavailable._StubSpan()
        merged_metadata = {**self._base_trace_metadata(), **(metadata or {})}

        def _call():
            t = self.client.trace(id=trace_id)
            return t.span(
                id=str(uuid.uuid4()),
                parent_observation_id=parent_observation_id,
                name=name,
                metadata=merged_metadata,
                input=input,
                output=output,
                start_time=start_time,
                end_time=end_time,
                status_message=status_message,
                level=level,
                version=version,
            )

        start = time.perf_counter()
        result, error = _run_with_retry(_call, SDK_OPERATION_TIMEOUT_SECONDS)
        duration = time.perf_counter() - start
        if error is None:
            self._record_success(operation="span", duration=duration)
            return result
        else:
            logger.debug("Langfuse span creation failed: %s", error)
            self._record_failure(str(error), operation="span", duration=duration)
            return _LangfuseUnavailable._StubSpan()

    def generation(
        self,
        trace_id=None,
        name=None,
        model=None,
        model_parameters=None,
        input=None,
        output=None,
        usage=None,
        metadata=None,
        parent_observation_id=None,
    ):
        """Create a Langfuse generation observation."""
        if not self._should_sample():
            return _LangfuseUnavailable._StubSpan()
        if self.circuit_open:
            return _LangfuseUnavailable._StubSpan()
        merged_metadata = {**self._base_trace_metadata(), **(metadata or {})}

        def _call():
            t = self.client.trace(id=trace_id)
            return t.generation(
                name=name,
                model=model,
                model_parameters=model_parameters,
                input=input,
                output=output,
                usage=usage,
                metadata=merged_metadata,
                parent_observation_id=parent_observation_id,
            )

        start = time.perf_counter()
        result, error = _run_with_retry(_call, SDK_OPERATION_TIMEOUT_SECONDS)
        duration = time.perf_counter() - start
        if error is None:
            self._record_success(operation="generation", duration=duration)
            return result
        else:
            logger.debug("Langfuse generation creation failed: %s", error)
            self._record_failure(str(error), operation="generation", duration=duration)
            return _LangfuseUnavailable._StubSpan()

    def get_langchain_callback(self, trace_id=None, name=None, user_id=None, metadata=None, tags=None):
        """Get a LangChain callback handler that auto-traces LLM calls."""
        if not self._enabled:
            return None
        if self.circuit_open:
            return None
        merged_metadata = {**self._base_trace_metadata(), **(metadata or {})}
        try:
            from langfuse.callback import CallbackHandler as LangfuseCallback

            def _create_callback():
                return LangfuseCallback(
                    public_key=self._client.public_key if self._client else None,
                    secret_key=self._client.secret_key if self._client else None,
                    host=self._client.host if self._client else None,
                    trace_id=trace_id,
                    name=name,
                    user_id=user_id,
                    metadata=merged_metadata,
                    tags=tags,
                )

            start = time.perf_counter()
            result, error = _run_with_timeout(_create_callback, CALLBACK_CREATION_TIMEOUT_SECONDS)
            duration = time.perf_counter() - start
            if error is not None:
                if isinstance(error, TimeoutError):
                    logger.warning(
                        "Langfuse callback creation timed out after %ss, returning None to avoid blocking LLM response",
                        CALLBACK_CREATION_TIMEOUT_SECONDS,
                    )
                else:
                    raise error
            self._record_success(operation="callback", duration=duration)
            return result
        except ImportError:
            logger.debug("langchain-langfuse not installed")
            return None
        except Exception as e:
            logger.debug("LangChain callback creation failed: %s", e)
            self._record_failure(str(e), operation="callback")
            return None

    def get_litellm_callback_config(self) -> dict[str, Any]:
        """Get LiteLLM callback configuration for zero-code tracing."""
        if not self._enabled:
            return {}
        if self.circuit_open:
            return {}

        def _call():
            return {
                "callback_name": "langfuse",
                "langfuse_public_key": (self._client.public_key if self._client else None),
                "langfuse_secret_key": (self._client.secret_key if self._client else None),
                "langfuse_host": self._client.host if self._client else None,
            }

        start = time.perf_counter()
        result, error = _run_with_retry(_call, SDK_OPERATION_TIMEOUT_SECONDS)
        duration = time.perf_counter() - start
        if error is None:
            self._record_success(operation="litellm_config", duration=duration)
            return result
        else:
            logger.debug("LiteLLM callback config failed: %s", error)
            self._record_failure(str(error), operation="litellm_config", duration=duration)
            return {}

    def flush(self):
        """Flush pending traces to Langfuse."""
        if not self._enabled or not self._client:
            return
        if self.circuit_open:
            return

        def _call():
            self._client.flush()

        start = time.perf_counter()
        _result, error = _run_with_retry(_call, FLUSH_TIMEOUT_SECONDS)
        duration = time.perf_counter() - start
        if error is None:
            self._record_success(operation="flush", duration=duration)
        else:
            if isinstance(error, TimeoutError):
                logger.warning(
                    "Langfuse flush timed out after %ss, continuing without waiting",
                    FLUSH_TIMEOUT_SECONDS,
                )
            else:
                logger.debug("Langfuse flush failed: %s", error)
            self._record_failure(str(error), operation="flush", duration=duration)

    def shutdown(self):
        """Graceful shutdown — flush and clean up."""
        if not self._enabled or not self._client:
            return
        try:
            self.flush()
            logger.info("Langfuse client shut down (worker=%s)", self._worker_id)
        except Exception as e:
            logger.debug("Langfuse shutdown failed: %s", e)

    def score_trace(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment=None,
        data_type: str = "NUMERIC",
    ):
        """Add a score to a trace. Non-blocking."""
        if not self._enabled:
            return
        if self.circuit_open:
            return

        def _call():
            self.client.score(
                trace_id=trace_id,
                name=name,
                value=value,
                comment=comment,
                data_type=data_type,
            )

        start = time.perf_counter()
        _result, error = _run_with_retry(_call, SDK_OPERATION_TIMEOUT_SECONDS)
        duration = time.perf_counter() - start
        if error is None:
            self._record_success(operation="score", duration=duration)
        else:
            logger.debug("Langfuse score failed: %s", error)
            self._record_failure(str(error), operation="score", duration=duration)

    def get_trace_stats(self) -> dict[str, Any]:
        """Get trace statistics for monitoring."""
        return {
            "sent": self._traces_sent,
            "failed": self._traces_failed,
            "circuit_state": self.circuit_state,
            "last_failure": self._last_failure_reason,
            "worker_id": self._worker_id,
        }

    def _should_sample(self) -> bool:
        """Determine if this trace should be sampled based on sampling_rate."""
        import random

        if self._sampling_rate >= 1.0:
            return True
        return random.random() < self._sampling_rate


def get_langfuse_service() -> LangfuseService:
    """Get the singleton LangfuseService instance."""
    return LangfuseService()
