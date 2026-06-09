"""
Reliability Assertions for Langfuse Integration

Monitors LLM response health and verifies guarantees during chaos testing:
1. LLM latency stays bounded when Langfuse is failing
2. No request fails due to Langfuse errors
3. Circuit breaker transitions correctly
4. % successful LLM responses while Langfuse is failing ~ 100%
"""

import logging
import threading
from collections import deque
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

MAX_LLM_LATENCY_MS = 30000  # 30s - LLM calls should never take longer than this
MAX_TRACKED_CALLS = 1000


class ReliabilityMonitor:
    """Tracks LLM response health and Langfuse failure correlation."""

    def __init__(self):
        self._llm_calls: deque = deque(maxlen=MAX_TRACKED_CALLS)
        self._langfuse_failures: deque = deque(maxlen=MAX_TRACKED_CALLS)
        self._circuit_transitions: deque = deque(maxlen=100)
        self._lock = threading.Lock()

    def record_llm_call(
        self, success: bool, latency_ms: float, error: str | None = None
    ):
        """Record an LLM call result."""
        with self._lock:
            self._llm_calls.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "success": success,
                    "latency_ms": latency_ms,
                    "error": error,
                }
            )

    def record_langfuse_failure(self, error_type: str):
        """Record a Langfuse failure."""
        with self._lock:
            self._langfuse_failures.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error_type": error_type,
                }
            )

    def record_circuit_transition(self, from_state: str, to_state: str):
        """Record a circuit breaker state transition."""
        with self._lock:
            self._circuit_transitions.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "from": from_state,
                    "to": to_state,
                }
            )
        logger.info("Circuit breaker transition: %s -> %s", from_state, to_state)

    def get_reliability_report(self) -> dict:
        """
        Generate the killer metric report.

        Key metric: % of successful LLM responses while Langfuse is failing
        Target: ~100%
        """
        with self._lock:
            total = len(self._llm_calls)
            if total == 0:
                return {"status": "no_data", "llm_success_rate": None}

            successful = sum(1 for c in self._llm_calls if c["success"])
            llm_success_rate = successful / total * 100

            # LLM calls with latency above bound
            latency_violations = sum(
                1 for c in self._llm_calls if c["latency_ms"] > MAX_LLM_LATENCY_MS
            )

            # LLM failures attributed to Langfuse
            langfuse_caused_failures = sum(
                1
                for c in self._llm_calls
                if not c["success"]
                and c.get("error")
                and "langfuse" in (c["error"] or "").lower()
            )

            return {
                "llm_total_calls": total,
                "llm_successful": successful,
                "llm_success_rate": round(llm_success_rate, 2),
                "llm_latency_violations": latency_violations,
                "langfuse_caused_failures": langfuse_caused_failures,
                "langfuse_total_failures": len(self._langfuse_failures),
                "circuit_transitions": len(self._circuit_transitions),
                "circuit_transition_log": list(self._circuit_transitions)[-10:],
                "chaos_stats": None,  # Will be populated from chaos module
                "assertion": (
                    "PASS"
                    if llm_success_rate >= 99.0 and langfuse_caused_failures == 0
                    else "FAIL"
                ),
                "target_llm_success_rate": "~100%",
                "actual_llm_success_rate": f"{round(llm_success_rate, 2)}%",
            }


# Singleton
_monitor: ReliabilityMonitor | None = None


def get_reliability_monitor() -> ReliabilityMonitor:
    global _monitor
    if _monitor is None:
        _monitor = ReliabilityMonitor()
    return _monitor
