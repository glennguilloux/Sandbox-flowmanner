"""Calibration — data-driven plan scoring grounded in strategy profiling.

Loads strategy profiling results from ``docs/strategy-profiling-results.json``
and provides:

* Per-strategy success rates for risk-adjusted scoring.
* Task-structure → execution-strategy affinity prediction.
* Empirically-derived normalizing constants for the scorer.

The calibration data is loaded once at import time (filesystem read, <1ms).
If the profiling file is missing, all strategies default to 1.0 success rate
(no penalty applied — graceful degradation).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Default profiling file location ─────────────────────────────────────────
_PROFILING_FILE = Path(__file__).resolve().parents[4] / "docs" / "strategy-profiling-results.json"

# ── Empirical normalizing constants (from strategy-profiling-results.json) ──
# These replace the previous arbitrary constants with values grounded in
# actual 27B model performance data.
#
# Token normalizer: median total_tokens across successful strategy runs = 15
# (the profiling used minimal prompts).  For production plans, a typical
# 3-task heuristic plan ≈ 3,000 tokens.  We use 50,000 as the divisor
# (a moderately complex plan) — anything above that gets the full penalty.
TOKEN_NORMALIZER: int = 50_000

# Latency normalizer: median latency_ms across successful runs ≈ 1,200ms.
# A 3-task sequential plan ≈ 6,000ms.  We use 30,000ms (30s) as the divisor
# — a reasonable upper bound for a local-LLM plan.
LATENCY_NORMALIZER_MS: int = 30_000

# Task count normalizer: keep at 10 (unchanged — 10+ tasks is genuinely complex).
TASK_COUNT_NORMALIZER: int = 10

# ── Strategy affinity heuristics ─────────────────────────────────────────────
# Maps task-structure characteristics to the execution strategy that the
# UnifiedExecutor would most likely select.  Used by ``predict_strategy``
# to apply profiling-based risk penalties.

_STRATEGY_AFFINITY_RULES: list[tuple[str, Any]] = [
    # (strategy_name, predicate_fn(tasks))
    # Order matters: first match wins (most specific → least specific).
    ("swarm", lambda ts: _has_fan_out_fan_in(ts)),
    ("pipeline", lambda ts: _has_phase_gates(ts)),
    ("meta", lambda ts: _has_sub_workflow(ts)),
    ("langgraph", lambda ts: _has_graph_name(ts)),
    ("graph", lambda ts: _has_conditional_edges(ts)),
    ("dag", lambda ts: len(ts) > 1 and _has_dependencies(ts)),
    ("solo", lambda ts: len(ts) == 1),
]


def _has_fan_out_fan_in(tasks: list[dict]) -> bool:
    """Check if tasks suggest fan-out/fan-in pattern (Swarm)."""
    return any(t.get("task_type") == "fan_out" or t.get("spawn_parallel") for t in tasks)


def _has_phase_gates(tasks: list[dict]) -> bool:
    """Check if tasks are phase-gated (Pipeline)."""
    phase_types = {"dispatch", "research", "draft", "debate", "consensus", "synthesis", "review"}
    task_types = {t.get("task_type", "") for t in tasks}
    return len(task_types & phase_types) >= 3


def _has_sub_workflow(tasks: list[dict]) -> bool:
    """Check if tasks contain sub-workflows (Meta)."""
    return any(t.get("task_type") == "sub_workflow" or t.get("recursive") for t in tasks)


def _has_graph_name(tasks: list[dict]) -> bool:
    """Check if tasks reference LangGraph graphs."""
    return any(t.get("graph_name") or t.get("task_type") == "langgraph" for t in tasks)


def _has_conditional_edges(tasks: list[dict]) -> bool:
    """Check if any task has conditional dependencies."""
    for t in tasks:
        deps = t.get("dependencies", [])
        if isinstance(deps, list):
            for d in deps:
                if isinstance(d, dict) and d.get("condition"):
                    return True
        if t.get("conditional") or t.get("branch"):
            return True
    return False


def _has_dependencies(tasks: list[dict]) -> bool:
    """Check if any task has dependencies on other tasks."""
    for t in tasks:
        deps = t.get("dependencies", [])
        if deps:
            return True
    return False


# ── Public API ───────────────────────────────────────────────────────────────

_strategy_success_rates: dict[str, float] | None = None


def _load_profiling_data() -> dict[str, float]:
    """Load strategy success rates from the profiling results file.

    Returns a dict mapping strategy name → success rate (0.0–1.0).
    Falls back to 1.0 for all strategies if the file is missing.
    """
    global _strategy_success_rates
    if _strategy_success_rates is not None:
        return _strategy_success_rates

    try:
        with open(_PROFILING_FILE) as f:
            data: dict[str, Any] = json.load(f)
        results = data.get("results", {})
        rates: dict[str, float] = {}
        for strategy, stats in results.items():
            if isinstance(stats, dict):
                rates[strategy] = float(stats.get("success_rate", 1.0))
            else:
                rates[strategy] = 1.0
        _strategy_success_rates = rates
        logger.debug("Loaded profiling data: %d strategies from %s", len(rates), _PROFILING_FILE)
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        logger.debug("Profiling data not available (%s); defaulting all strategies to 1.0", exc)
        _strategy_success_rates = {
            "solo": 1.0,
            "dag": 1.0,
            "graph": 1.0,
            "pipeline": 1.0,
            "meta": 1.0,
            "swarm": 1.0,
            "langgraph": 1.0,
        }
    return _strategy_success_rates


def get_strategy_success_rate(strategy_name: str) -> float:
    """Return the empirical success rate for an execution strategy.

    Args:
        strategy_name: One of solo, dag, graph, pipeline, meta, swarm, langgraph.

    Returns:
        Success rate in [0.0, 1.0].  Defaults to 1.0 if profiling data is
        unavailable for the given strategy.
    """
    rates = _load_profiling_data()
    return rates.get(strategy_name, 1.0)


def predict_strategy(tasks: list[dict]) -> str:
    """Predict which execution strategy the UnifiedExecutor would select.

    Uses task-structure heuristics (task types, dependencies, special fields)
    to estimate the strategy affinity.  This is a best-effort prediction —
    the actual strategy selection happens at execution time.

    Args:
        tasks: List of task dicts from a PlanCandidate.

    Returns:
        Predicted strategy name (e.g. "solo", "dag", "graph", ...).
    """
    for strategy_name, predicate in _STRATEGY_AFFINITY_RULES:
        try:
            if predicate(tasks):
                return strategy_name
        except Exception:
            continue
    # Default: if we can't determine, assume dag (most common for multi-task plans)
    return "dag" if len(tasks) > 1 else "solo"


def strategy_risk_penalty(tasks: list[dict]) -> float:
    """Compute a risk penalty based on the predicted execution strategy's success rate.

    Returns a penalty in [0.0, 0.25] where:
    - 0.0 = predicted strategy has 100% success rate (no penalty)
    - 0.25 = predicted strategy has 0% success rate (maximum penalty)

    The penalty is scaled linearly: penalty = (1.0 - success_rate) * 0.25.

    Args:
        tasks: List of task dicts from a PlanCandidate.

    Returns:
        Risk penalty float in [0.0, 0.25].
    """
    predicted = predict_strategy(tasks)
    success_rate = get_strategy_success_rate(predicted)
    return (1.0 - success_rate) * 0.25


def reset_profiling_cache() -> None:
    """Reset the cached profiling data.  Useful for testing."""
    global _strategy_success_rates
    _strategy_success_rates = None
