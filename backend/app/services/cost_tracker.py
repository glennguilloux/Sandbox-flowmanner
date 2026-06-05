"""Cost tracking for mission LLM calls — extracted from MissionExecutor.

Provides cost estimation for all supported models and records LLM call
observability data to both the database (LLMCallRecord table) and
Prometheus metrics.

Usage::

    tracker = CostTracker()
    cost = tracker.estimate_cost("deepseek-chat", 1_000_000)
    await tracker.record_llm_call(db, mission_id="m1", task_id="t1", ...)
"""

import logging

from app.config import settings
from app.core.metrics import record_llm_request
from app.models.llm_call_record import LLMCallRecord

logger = logging.getLogger(__name__)


class CostLimitExceeded(Exception):
    """Raised when a cost limit is exceeded."""


class PermissionDenied(Exception):
    """Raised when a cost-related permission check fails."""


class CostTracker:
    """Tracks cost estimation and LLM call recording for mission execution.

    Attributes:
        COST_PER_1M_TOKENS: USD cost per million tokens for each known model.
            Unknown models fall back to the ``"default"`` key (0.50 USD).
    """

    COST_PER_1M_TOKENS: dict[str, float] = {
        "deepseek-chat": 0.14,
        "deepseek-reasoner": 0.55,
        "vllm-qwen3-14b-chat": 0.0,
        "openrouter-gemma-2-9b-free": 0.0,
        "claude-3-5-sonnet": 3.0,
        "claude-3-haiku": 0.25,
        "default": 0.5,
    }

    def estimate_cost(self, model_id: str, total_tokens: int) -> float:
        """Estimate cost in USD for a given model and token count.

        Args:
            model_id: Model identifier (e.g. ``"deepseek-chat"``).  Maps to
                a key in :attr:`COST_PER_1M_TOKENS`; unknown models use the
                ``"default"`` pricing.
            total_tokens: Combined prompt + completion tokens to price.

        Returns:
            Estimated cost in USD.  The divisor is
            ``settings.MISSION_COST_DIVISOR`` (default 1,000,000), so cost
            is ``(total_tokens / divisor) * cost_per_1m``.

        Example:
            >>> tracker = CostTracker()
            >>> tracker.estimate_cost("deepseek-chat", 1_000_000)
            0.14
            >>> tracker.estimate_cost("unknown-model", 500_000)
            0.25  # 0.50 / 2
        """
        cost_per_1m = self.COST_PER_1M_TOKENS.get(
            model_id, self.COST_PER_1M_TOKENS["default"]
        )
        return (total_tokens / settings.MISSION_COST_DIVISOR) * cost_per_1m

    async def record_llm_call(
        self,
        db,
        mission_id: str | None,
        task_id: str | None,
        model_id: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        """Record an LLM call to the DB observability table and Prometheus.

        When ``db`` is ``None`` (e.g. called outside a DB session context),
        only Prometheus metrics are recorded — the DB row is skipped with
        a warning log.

        Args:
            db: SQLAlchemy session, or ``None``.
            mission_id: UUID string of the owning mission, or ``None``.
            task_id: UUID string of the owning task, or ``None``.
            model_id: Model identifier (e.g. ``"deepseek-chat"``).
            provider: Provider label (e.g. ``"deepseek"``, ``"llamacpp"``).
            prompt_tokens: Number of input tokens consumed.
            completion_tokens: Number of output tokens produced.
            cost_usd: Pre-computed cost in USD.
            latency_ms: Round-trip latency in milliseconds.
            success: Whether the LLM call succeeded.
            error_message: Error detail when ``success`` is ``False``.

        Note:
            The DB record is added via ``db.add()`` but **not** committed
            here — the parent transaction owns the commit lifecycle.
        """
        try:
            if db is not None:
                record = LLMCallRecord(
                    mission_id=mission_id,
                    task_id=task_id,
                    model_id=model_id,
                    provider=provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error_message,
                )
                db.add(record)

            # Always record to Prometheus metrics (works without db)
            try:
                record_llm_request(
                    provider=provider,
                    duration_seconds=latency_ms / 1000.0,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    success=success,
                )
            except Exception as e:
                logger.debug("cost_tracker_prometheus_record_failed", error=str(e))
        except Exception as e:
            logger.warning(f"Failed to record LLM call: {e}")


# ── Singleton ──────────────────────────────────────────────────────

_cost_tracker: CostTracker | None = None


def get_cost_tracker() -> CostTracker:
    """Get or create the CostTracker singleton."""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker()
    return _cost_tracker
