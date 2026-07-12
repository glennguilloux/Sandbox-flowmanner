"""Plan selector — picks the winning candidate by policy.

Policies:
- ``min_cost``: Cheapest plan among those with quality >= threshold.
- ``max_quality``: Highest quality score regardless of cost.
- ``balanced``: Highest composite score (quality already includes cost penalty).
- ``auto``: Same as ``balanced`` today (room for a learned policy later).
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .plan_candidate import PlanCandidate

logger = logging.getLogger(__name__)

# Callback invoked when the winning candidate is a forced fallback / degraded
# plan. Signature: async (winner: PlanCandidate, reason: str) -> None
# (PlanCandidate is a TYPE_CHECKING import, so we type the alias loosely.)
FallbackHook = Callable[..., None | Awaitable[None]]


async def select_plan(
    candidates: list[PlanCandidate],
    policy: str = "auto",
    min_quality_threshold: float = 0.6,
    on_fallback: FallbackHook | None = None,
) -> tuple[PlanCandidate, list[PlanCandidate]]:
    """Select the winning plan candidate by policy.

    Args:
        candidates: List of scored ``PlanCandidate`` instances.
        policy: Selection policy — ``"auto"``, ``"min_cost"``,
            ``"max_quality"``, or ``"balanced"``.
        min_quality_threshold: Minimum quality score for a candidate
            to be eligible (default 0.6).
        on_fallback: Optional hook invoked when the winning candidate is a
            forced fallback / degraded plan (``degraded=True``). The planner
            wires this to route the mission to ``PLANNED_PENDING_REVIEW``
            and fire the fallback-rate alarm — see
            side-effect-safety-and-planner-trust skill. This is a HARD override:
            a degraded winner is reported regardless of its quality score.

    Returns:
        ``(winner, all_sorted_desc_by_score)`` where ``all_sorted`` is
        the full list sorted by quality score descending, with rank
        annotations applied.

    Raises:
        ValueError: If candidates list is empty.
    """
    if not candidates:
        raise ValueError("Cannot select from empty candidates list")

    # ── Sort all candidates by quality score descending ──────────────────
    sorted_candidates = sorted(candidates, key=lambda c: c.quality_score, reverse=True)

    # ── Filter eligible candidates (quality >= threshold) ────────────────
    eligible = [c for c in sorted_candidates if c.quality_score >= min_quality_threshold]

    if not eligible:
        # If nothing meets threshold, fall back to the best overall
        logger.warning(
            "No candidates meet quality threshold %.2f; falling back to best overall (score=%.2f)",
            min_quality_threshold,
            sorted_candidates[0].quality_score,
        )
        eligible = [sorted_candidates[0]]

    # ── Apply policy ─────────────────────────────────────────────────────
    if policy == "min_cost":
        # Use token count as cost proxy — the local LLM is free, so
        # dollar cost is meaningless.  Tokens correlate with resource
        # consumption (VRAM, time) and are the real cost axis.
        winner = min(eligible, key=lambda c: c.estimated_tokens)
    elif policy == "max_quality":
        winner = eligible[0]  # already sorted desc by quality
    elif policy in ("balanced", "auto"):
        # balanced: quality score already incorporates cost penalty
        winner = eligible[0]
    else:
        logger.warning("Unknown policy '%s'; falling back to 'balanced'", policy)
        winner = eligible[0]

    logger.info(
        "Plan selected: %s (policy=%s, score=%.3f, cost=$%.4f, %d candidates, %d eligible)",
        winner.plan_id,
        policy,
        winner.quality_score,
        winner.estimated_cost_usd,
        len(candidates),
        len(eligible),
    )

    # ── Planner-trust gate: forced-fallback plans NEVER auto-ship ──
    # (side-effect-safety-and-planner-trust skill) A degraded winner is a HARD
    # override — regardless of its quality score it must route to human review
    # (PLANNED_PENDING_REVIEW) and trip the fallback-rate alarm. The planner
    # supplies on_fallback to perform both.
    if winner.degraded and on_fallback is not None:
        result = on_fallback(winner, "degraded_fallback_plan")
        if inspect.isawaitable(result):
            await result

    return winner, sorted_candidates
