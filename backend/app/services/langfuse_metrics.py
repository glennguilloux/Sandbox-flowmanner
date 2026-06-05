"""Prometheus metrics for Langfuse integration.

Tracks trace throughput, failures, circuit breaker state, and SDK operation
latency. Also monitors LLM latency when Langfuse is failing to verify the
non-blocking guarantee.

Metrics are automatically exported on the /metrics endpoint alongside
existing Prometheus metrics from app.api.middleware.metrics.
"""

from prometheus_client import Counter, Gauge, Histogram

langfuse_traces_sent = Counter(
    "langfuse_traces_sent_total",
    "Total number of traces successfully sent to Langfuse",
)

langfuse_traces_failed = Counter(
    "langfuse_traces_failed_total",
    "Total number of traces that failed to send to Langfuse",
)

langfuse_circuit_breaker_state = Gauge(
    "langfuse_circuit_breaker_state",
    "Current circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN)",
    ["worker_id"],
)

langfuse_operation_duration = Histogram(
    "langfuse_operation_duration_seconds",
    "Duration of Langfuse SDK operations",
    ["operation"],  # trace, span, generation, flush, score, callback
)

langfuse_llm_latency_while_failing = Histogram(
    "langfuse_llm_latency_while_failing_seconds",
    "LLM response latency when Langfuse is failing",
)


# Map circuit breaker states to numeric gauge values
CIRCUIT_STATE_NUMERIC = {
    "CLOSED": 0,
    "HALF_OPEN": 1,
    "OPEN": 2,
}


def update_circuit_breaker_gauge(worker_id: int, state: str) -> None:
    """Update the circuit breaker state gauge for a given worker."""
    value = CIRCUIT_STATE_NUMERIC.get(state, -1)
    langfuse_circuit_breaker_state.labels(worker_id=str(worker_id)).set(value)


def observe_operation(operation: str, duration: float) -> None:
    """Record the duration of a Langfuse SDK operation."""
    langfuse_operation_duration.labels(operation=operation).observe(duration)


def record_llm_latency_while_failing(latency_seconds: float) -> None:
    """Record LLM latency when Langfuse circuit breaker is OPEN.

    This metric verifies the non-blocking guarantee: LLM latency should
    not increase when Langfuse is down.
    """
    langfuse_llm_latency_while_failing.observe(latency_seconds)
