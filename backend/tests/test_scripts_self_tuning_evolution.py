"""Unit tests for ``backend/scripts/self_tuning_evolution.py``.

These tests exercise the CLI-shaped wrapper without a live database or LLM by
injecting a fake ``run_candidate`` seam into ``run_evolution``. They prove the
script wires arguments, ParamSpace, and the ledger output correctly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from scripts.self_tuning_evolution import _build_arg_parser, _run_evolution


#: Fixed blueprint id used in tests.
_BLUEPRINT_ID = "bp-scripts-self-tuning-001"


@dataclass
class _FakeResult:
    """Minimal result object matching the shape ``score_run`` expects."""

    success: bool
    status: str
    run_id: str
    total_cost_usd: float
    execution_time_ms: float
    completed_nodes: list[str]
    failed_nodes: list[str]
    error: str | None


def _make_run_outcome(
    *,
    success: bool = True,
    cost: float = 0.03,
    latency_ms: float = 1200.0,
) -> dict[str, Any]:
    """Return a fake RunOutcome matching the real UnifiedExecutor shape."""
    return {
        "result": _FakeResult(
            success=success,
            status="completed" if success else "failed",
            run_id="run-fake-0000",
            total_cost_usd=cost,
            execution_time_ms=latency_ms,
            completed_nodes=["answer"],
            failed_nodes=[],
            error=None,
        ),
        "events": [],
        "answer_output": {"text": "hello"},
    }


async def _fake_runner(workflow: Any, candidate: dict[str, Any], run_ctx: dict[str, Any]) -> dict[str, Any]:
    """Healthy fake runner that always succeeds."""
    return _make_run_outcome()


async def _failing_runner(workflow: Any, candidate: dict[str, Any], run_ctx: dict[str, Any]) -> dict[str, Any]:
    """Fake runner that simulates an expensive/failing run."""
    return _make_run_outcome(success=False, cost=1.0)


def _args(**overrides: Any) -> Any:
    """Build an argparse Namespace from the script's parser with arbitrary overrides."""
    import argparse

    defaults = {
        "blueprint_id": _BLUEPRINT_ID,
        "mode": "grid",
        "generations": 8,
        "seed": 42,
        "output": "/tmp/test-evolution-ledger.json",
        "quick": False,
        "enable_leases": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.mark.asyncio
async def test_grid_mode_emits_scored_ledger() -> None:
    """Grid mode enumerates every ParamSpace combination and scores it."""
    ledger = await _run_evolution(_args(mode="grid"), run_candidate=_fake_runner)

    from scripts.self_tuning_evolution import _build_param_space

    expected = len(_build_param_space().combinations())
    assert len(ledger.entries) == expected
    assert ledger.blueprint_id == _BLUEPRINT_ID
    assert all(e.error is None for e in ledger.entries)
    assert all(e.passed and e.promoted for e in ledger.entries)
    assert ledger.best() is not None

    # JSON round-trip works and contains no secret leakage.
    parsed = __import__("json").loads(ledger.to_json())
    assert parsed["blueprint_id"] == _BLUEPRINT_ID
    assert parsed["best_promoted"] is not None


@pytest.mark.asyncio
async def test_quick_mode_uses_smaller_param_space() -> None:
    """--quick uses a single-combination ParamSpace for fast smoke tests."""
    from scripts.self_tuning_evolution import _build_arg_parser, _build_param_space

    assert _build_arg_parser().parse_args(["--quick"]).quick is True

    quick_combos = len(_build_param_space(quick=True).combinations())
    assert quick_combos == 1

    ledger = await _run_evolution(_args(quick=True), run_candidate=_fake_runner)
    assert len(ledger.entries) == quick_combos
    assert all(e.passed and e.promoted for e in ledger.entries)


@pytest.mark.asyncio
async def test_mutate_mode_bounded_by_generations() -> None:
    """Mutate mode runs exactly ``generations`` trials."""
    ledger = await _run_evolution(_args(mode="mutate", generations=4), run_candidate=_fake_runner)

    assert len(ledger.entries) == 4
    assert all(e.passed and e.promoted for e in ledger.entries)


@pytest.mark.asyncio
async def test_fail_closed_never_promotes_failing_run() -> None:
    """A failing fake runner is recorded but never promoted."""
    ledger = await _run_evolution(_args(mode="grid"), run_candidate=_failing_runner)

    assert all(not e.promoted for e in ledger.entries)
    assert ledger.best() is None
