"""Deterministic heuristic scorer for plan candidates.

Scores each PlanCandidate in <10ms without LLM calls.  The score is a
float in [0.0, 1.0] where higher is better.

Scoring weights (sum to ~1.0 before clamping):
  - Token penalty:        -0.30 (normalized; fewer tokens = higher score)
  - Latency penalty:      -0.20 (normalized; lower latency = higher score)
  - Risk flags:           -0.10 per flag, capped at -0.30
  - Strategy risk penalty: up to -0.25 (profiling-grounded; 0% success = max penalty)
  - Task count:           -0.05 (normalized; fewer = slightly better)
  - Fallback bonus:       +0.20 (every tool-using task has a fallback)
  - Retry penalty:        -0.05 (estimated retries from profile)
  - Budget awareness:     +0.10 (has max_budget declared)
  - Base quality:         +0.70 (starting point)

Normalizing constants are calibrated against actual 27B model profiling data
(see :mod:`calibration`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .calibration import (
    LATENCY_NORMALIZER_MS,
    TASK_COUNT_NORMALIZER,
    TOKEN_NORMALIZER,
    predict_strategy,
    strategy_risk_penalty,
)

if TYPE_CHECKING:
    from .plan_candidate import PlanCandidate

logger = logging.getLogger(__name__)

# ── Known risk flags ─────────────────────────────────────────────────────────

KNOWN_RISK_FLAGS = frozenset(
    {
        "unbounded_retry",
        "human_input_blocking",
        "no_fallback",
        "external_api_dependency",
        "large_context_window",
        "concurrent_writes",
    }
)

# ── Task type token estimates (tokens per task) ──────────────────────────────

_TASK_TYPE_BASE_TOKENS: dict[str, int] = {
    "llm": 1200,
    "tool": 400,
    "rag": 800,
    "code": 1500,
    "review": 600,
}


def estimate_tokens_for_tasks(tasks: list[dict]) -> int:
    """Estimate total tokens for a list of task dicts.

    Uses a deterministic heuristic: base tokens per task type plus a
    small bonus for longer descriptions.  No LLM or I/O involved.

    Args:
        tasks: List of task dicts with ``task_type`` and ``description``.

    Returns:
        Estimated total token count.
    """
    total = 0
    for task in tasks:
        task_type = task.get("task_type", "llm")
        base = _TASK_TYPE_BASE_TOKENS.get(task_type, 800)
        # Longer descriptions suggest more complex tasks → more tokens
        desc_len = len(task.get("description", ""))
        desc_bonus = min(desc_len // 10, 500)  # cap at 500 extra tokens
        total += base + desc_bonus
    return total


def estimate_latency_ms(tasks: list[dict]) -> int:
    """Estimate wall-clock latency in milliseconds for a task list.

    Heuristic: each task adds a base latency plus a dependency multiplier.

    Args:
        tasks: List of task dicts with ``dependencies``.

    Returns:
        Estimated latency in milliseconds.
    """
    base_per_task_ms = 2000  # 2s base per task
    dependency_overhead_ms = 500  # extra per dependency edge
    total = 0
    for task in tasks:
        total += base_per_task_ms
        deps = task.get("dependencies", [])
        if isinstance(deps, list):
            total += len(deps) * dependency_overhead_ms
    return total


def detect_risk_flags(tasks: list[dict]) -> list[str]:
    """Detect risk flags from a task list.

    Checks for structural patterns that indicate risk:
    - unbounded_retry: tasks with very high max_retries
    - human_input_blocking: tasks that require human approval
    - no_fallback: tool-using tasks without a fallback strategy

    Args:
        tasks: List of task dicts.

    Returns:
        List of risk flag strings.
    """
    flags: list[str] = []

    for task in tasks:
        task_type = task.get("task_type", "llm")

        # Tool-using tasks without fallback
        if task_type == "tool" and not task.get("fallback") and "no_fallback" not in flags:
            flags.append("no_fallback")

        # Tasks that block on human input
        if (task.get("approval_required") or task.get("requires_human")) and "human_input_blocking" not in flags:
            flags.append("human_input_blocking")

        # Tasks with unbounded retries
        max_retries = task.get("max_retries", 3)
        if isinstance(max_retries, int) and max_retries > 10 and "unbounded_retry" not in flags:
            flags.append("unbounded_retry")

    return flags


def score_plan(candidate: PlanCandidate) -> float:
    """Score a plan candidate deterministically.

    Returns a float in [0.0, 1.0] where higher is better.  The scoring
    is deterministic (no LLM, no I/O) and runs in <10ms.

    Scoring uses calibrated normalizing constants from :mod:`calibration`
    (grounded in 27B model profiling data) and applies a strategy-risk
    penalty based on the predicted execution strategy's empirical success
    rate.

    Args:
        candidate: The PlanCandidate to score.

    Returns:
        Quality score in [0.0, 1.0].
    """
    score = 0.70  # base quality

    # ── Token penalty (-0.30 max) ───────────────────────────────────────
    # Penalize resource-intensive plans.  Calibrated normalizer: 50k tokens.
    token_penalty = min(candidate.estimated_tokens / TOKEN_NORMALIZER, 1.0) * 0.30
    score -= token_penalty

    # ── Latency penalty (-0.20 max) ────────────────────────────────────
    # Penalize slow plans.  Calibrated normalizer: 30s.
    latency_penalty = min(candidate.estimated_latency_ms / LATENCY_NORMALIZER_MS, 1.0) * 0.20
    score -= latency_penalty

    # ── Risk flags penalty (-0.10 per flag, capped at -0.30) ────────────
    risk_count = len(candidate.risk_flags)
    risk_penalty = min(risk_count * 0.10, 0.30)
    score -= risk_penalty

    # ── Strategy risk penalty (up to -0.25) ─────────────────────────────
    # Grounded in strategy profiling data: plans whose predicted execution
    # strategy has a low success rate get penalized proportionally.
    strat_penalty = strategy_risk_penalty(candidate.tasks)
    score -= strat_penalty

    # ── Task count penalty (-0.05 max) ──────────────────────────────────
    # Normalize: 1 task = 0 penalty, 10+ tasks = full penalty.
    task_count = len(candidate.tasks)
    task_penalty = min(task_count / TASK_COUNT_NORMALIZER, 1.0) * 0.05
    score -= task_penalty

    # ── Fallback bonus (+0.20) ──────────────────────────────────────────
    # Every tool-using task should have a fallback.
    tool_tasks = [t for t in candidate.tasks if t.get("task_type") == "tool"]
    if tool_tasks:
        tasks_with_fallback = sum(1 for t in tool_tasks if t.get("fallback"))
        fallback_ratio = tasks_with_fallback / len(tool_tasks)
        score += fallback_ratio * 0.20
    else:
        # No tool tasks → no fallback risk → full bonus
        score += 0.20

    # ── Retry penalty (-0.05 max) ──────────────────────────────────────
    # Penalize plans likely to retry >2x on average.
    avg_max_retries = 0
    retry_counts = [t.get("max_retries", 3) for t in candidate.tasks]
    if retry_counts:
        avg_max_retries = sum(retry_counts) / len(retry_counts)
    if avg_max_retries > 2:
        retry_penalty = min((avg_max_retries - 2) / 8.0, 1.0) * 0.05
        score -= retry_penalty

    # ── Budget awareness bonus (+0.10) ─────────────────────────────────
    # Plans that declare a max_budget are self-aware about cost.
    has_budget = any(t.get("max_budget") for t in candidate.tasks)
    if has_budget:
        score += 0.10

    # ── Clamp to [0.0, 1.0] ────────────────────────────────────────────
    return max(0.0, min(1.0, score))
