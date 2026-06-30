"""Plan selector — picks the winning candidate by policy.

Policies:
- ``min_cost``: Cheapest plan among those with quality >= threshold.
- ``max_quality``: Highest quality score regardless of cost.
- ``balanced``: Highest composite score (quality already includes cost penalty).
- ``auto``: Same as ``balanced`` today (room for a learned policy later).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .plan_candidate import PlanCandidate

logger = logging.getLogger(__name__)


async def select_plan(
    candidates: list[PlanCandidate],
    policy: str = "auto",
    min_quality_threshold: float = 0.6,
) -> tuple[PlanCandidate, list[PlanCandidate]]:
    """Select the winning plan candidate by policy.

    Args:
        candidates: List of scored ``PlanCandidate`` instances.
        policy: Selection policy — ``"auto"``, ``"min_cost"``,
            ``"max_quality"``, or ``"balanced"``.
        min_quality_threshold: Minimum quality score for a candidate
            to be eligible (default 0.6).

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
        winner = min(eligible, key=lambda c: c.estimated_cost_usd)
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

    return winner, sorted_candidates
