"""Offline test for the substrate harness-evolution loop (no live infra).

Proves the loop:
  * runs over a fixture blueprint + bounded param space and emits a scored ledger
  * is FAIL-CLOSED: a mutated config that fails assertions / safety is NEVER
    promoted (recorded, but ``promoted=False``)
  * is BOUNDED + SAFE: ParamSpace rejects any axis outside the safe set, so the
    loop can never mutate auth / tenancy / budget fail-closed logic
  * does not execute real LLM/Postgres/Qdrant (we replace the single run seam
    with a fake that returns the same shape a real UnifiedExecutor run produces)

Adapts the offline seam pattern from test_evaluate_harness.py.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.substrate.harness_evolution import (
    EvolutionLedger,
    LedgerEntry,
    ParamSpace,
    RunOutcome,
    apply_params_to_candidate,
    run_evolution,
    score_run,
)


# ── Fixture blueprint / base candidate ──────────────────────────────────────

def _base_candidate() -> dict[str, Any]:
    """A minimal fixture blueprint candidate the loop mutates over.

    Only SAFE slots are present (temperature, top_k, budget tolerance, assertion
    multiplier, routing max_depth). No auth / tenancy / hard budget cap.
    """
    return {
        "workspace_id": "00000000-0000-0000-0000-000000000000",
        "verification": {"forbidden_tools": ["delete_data", "send_email"]},
        "budget": {"tolerance_pct": 10.0},
        "assertion": {"cost_ceiling_mult": 1.2},
        "routing": {"max_depth": 3},
        "workflow": {
            "nodes": [
                {"id": "retrieve", "type": "rag_query", "effect_class": "reversible"},
                {
                    "id": "answer",
                    "type": "llm",
                    "assigned_model": "deepseek-v4-flash",
                    "config": {"temperature": 0.2, "top_k": 5, "tool_ids": ["web_search"]},
                    "effect_class": "reversible",
                },
            ],
            "edges": [{"source": "retrieve", "target": "answer"}],
        },
    }


def _bounded_space() -> ParamSpace:
    return ParamSpace(
        {
            "answer.temperature": (0.1, 0.2, 0.4),
            "answer.top_k": (3, 5, 8),
            "budget.tolerance_pct": (5.0, 10.0, 20.0),
            "assertion.cost_ceiling_mult": (1.1, 1.2, 1.5),
            "routing.max_depth": (2, 3, 4),
        }
    )


# ── Fake run seam (returns the SAME shape as the real UnifiedExecutor path) ──

def _make_fake_run(
    success: bool,
    *,
    cost: float = 0.03,
    latency_ms: float = 1200.0,
    forbidden_tool: bool = False,
) -> RunOutcome:
    from app.models.substrate_models import SubstrateEventType
    from dataclasses import dataclass

    @dataclass
    class _R:
        success: bool
        status: str
        run_id: str
        total_cost_usd: float
        execution_time_ms: float
        completed_nodes: list[str]
        failed_nodes: list[str]
        error: None

    events: list[dict[str, Any]] = [
        {"type": SubstrateEventType.MISSION_STARTED, "payload": {"title": "harness-evolution"}},
        {"type": SubstrateEventType.LLM_RESPONSE, "payload": {"content": '{"risk_level": "high"}'}},
        {
            "type": SubstrateEventType.NODE_COMPLETED,
            "payload": {"node_id": "answer", "output": {"risk_level": "high"}},
        },
    ]
    if forbidden_tool:
        events.append({"type": SubstrateEventType.TOOL_CALL, "payload": {"tool_name": "delete_data"}})

    result = _R(
        success=success,
        status="completed" if success else "failed",
        run_id="run-fake-0000",
        total_cost_usd=cost,
        execution_time_ms=latency_ms,
        completed_nodes=["retrieve", "answer"] if success else [],
        failed_nodes=[] if success else ["answer"],
        error=None,
    )
    return {
        "result": result,
        "events": events,
        "answer_output": {"risk_level": "high"},
    }


async def _fake_runner(workflow, candidate, run_ctx):
    # Default healthy run. A test can monkeypatch this to vary cost/forbidden.
    return _make_fake_run(True)


# ── ParamSpace safety gate ───────────────────────────────────────────────────

def test_param_space_rejects_unsafe_axis():
    # Any axis outside SAFE_AXES must be rejected at construction -- this is the
    # hard guard that keeps the loop from ever touching auth/tenancy/budget-cap.
    with pytest.raises(ValueError):
        ParamSpace({"auth.api_key": ("x",)})  # not in SAFE_AXES
    with pytest.raises(ValueError):
        ParamSpace({"tenant.id": ("t1",)})
    with pytest.raises(ValueError):
        ParamSpace({"budget.hard_cap_usd": (10.0,)})  # the fail-closed cap


def test_param_space_requires_at_least_one_axis():
    with pytest.raises(ValueError):
        ParamSpace({})


def test_param_space_combinations_are_bounded():
    space = _bounded_space()
    combos = space.combinations()
    # 3^5 = 243 bounded trials; the loop is explicitly exhaustive but small.
    assert len(combos) == 243
    # Every combo only carries safe axis names.
    for c in combos:
        assert set(c.keys()) == set(space.axes.keys())


def test_mutate_flips_exactly_one_safe_axis():
    space = _bounded_space()
    base = {name: axis.choices[0] for name, axis in space.axes.items()}
    # Deterministic RNG so we can assert the neighborhood step.
    out = space.mutate(base, __import__("random").Random(1))
    diffs = [k for k in base if base[k] != out[k]]
    assert len(diffs) == 1  # exactly one axis moved
    assert all(k in space.axes for k in out)


# ── apply_params_to_candidate preserves everything but the safe slot ─────────

def test_apply_params_overlays_only_safe_slot():
    candidate = _base_candidate()
    mutated = apply_params_to_candidate(
        candidate, {"answer.temperature": 0.4, "answer.top_k": 8}
    )
    # The safe slot changed on the target node.
    answer = next(n for n in mutated["workflow"]["nodes"] if n["id"] == "answer")
    assert answer["config"]["temperature"] == 0.4
    assert answer["config"]["top_k"] == 8
    # Everything else (auth/tenancy/workflow structure) is preserved verbatim.
    assert mutated["verification"] == candidate["verification"]
    assert mutated["workflow"]["edges"] == candidate["workflow"]["edges"]
    # Original candidate is NOT mutated (deep copy).
    orig_answer = next(n for n in candidate["workflow"]["nodes"] if n["id"] == "answer")
    assert orig_answer["config"]["temperature"] == 0.2


def test_apply_params_refuses_out_of_scope_axis():
    with pytest.raises(ValueError):
        apply_params_to_candidate(_base_candidate(), {"auth.secret": "x"})


# ── score_run fail-closed ────────────────────────────────────────────────────

def test_score_run_passes_clean_candidate():
    candidate = _base_candidate()
    run = _make_fake_run(True)
    passed, score, results, safety = score_run(
        candidate, run, {"cost_usd": 0.03, "latency_ms": 1200.0}, None
    )
    assert safety is True
    assert passed is True


def test_score_run_fails_on_forbidden_tool():
    candidate = _base_candidate()
    run = _make_fake_run(True, forbidden_tool=True)
    passed, score, results, safety = score_run(
        candidate, run, {"cost_usd": 0.03, "latency_ms": 1200.0}, None
    )
    assert safety is False
    assert passed is False  # fail-closed: safety failure => not passed


def test_score_run_fails_on_cost_regression():
    candidate = _base_candidate()
    run = _make_fake_run(True, cost=0.10)  # 3.3x baseline
    spec = [{"type": "cost_ceiling", "multiplier": 1.2}]
    passed, score, results, safety = score_run(
        candidate, run, {"cost_usd": 0.03, "latency_ms": 1200.0}, spec
    )
    # Safety is fine but the regression assertion fails => not passed.
    assert safety is True
    assert passed is False
    assert results[0]["passed"] is False


# ── The loop: emits a scored ledger, fail-closed ────────────────────────────

@pytest.mark.asyncio
async def test_run_evolution_emits_scored_ledger_grid():
    ledger = await run_evolution(
        blueprint_id="bp-fixture-001",
        base_candidate=_base_candidate(),
        param_space=_bounded_space(),
        mode="grid",
        run_candidate=_fake_runner,
    )
    # 243 bounded trials; every one scored.
    assert isinstance(ledger, EvolutionLedger)
    assert len(ledger.entries) == 243
    # No exceptions recorded (fake runner always succeeds + safe).
    assert all(e.error is None for e in ledger.entries)
    # The ledger serializes to JSON without tenant/secret leakage.
    blob = ledger.to_json()
    parsed = __import__("json").loads(blob)
    assert parsed["blueprint_id"] == "bp-fixture-001"
    assert "api_key" not in blob and "tenant" not in blob and "secret" not in blob


@pytest.mark.asyncio
async def test_run_evolution_fail_closed_never_promotes_failing_config():
    # A runner that trips the safety gate (forbidden tool) on the FIRST trial
    # only, and is clean otherwise. The failing trial must be recorded but
    # NEVER promoted; a passing trial may be promoted.
    calls = {"n": 0}

    async def _runner(workflow, candidate, run_ctx):
        calls["n"] += 1
        return _make_fake_run(True, forbidden_tool=(calls["n"] == 1))

    ledger = await run_evolution(
        blueprint_id="bp-fixture-002",
        base_candidate=_base_candidate(),
        param_space=_bounded_space(),
        mode="grid",
        # Supply baseline metrics so the loop doesn't pre-run the (counted)
        # baseline -- the failing trial must be a grid trial, not the baseline.
        baseline_metrics={"cost_usd": 0.03, "latency_ms": 1200.0},
        run_candidate=_runner,
    )
    # Exactly one trial tripped the gate (call #1 of the grid).
    failing = [e for e in ledger.entries if not e.passed]
    assert len(failing) == 1
    assert failing[0].promoted is False  # hard fail-closed
    assert failing[0].safety_pass is False
    # Every other entry is promoted (all pass).
    promoted = [e for e in ledger.entries if e.promoted]
    assert len(promoted) == len(ledger.entries) - 1
    # The ledger's best promoted is one of the clean runs.
    assert ledger.best() is not None
    assert ledger.best().promoted is True


@pytest.mark.asyncio
async def test_run_evolution_mutate_mode_bounded_by_generations():
    ledger = await run_evolution(
        blueprint_id="bp-fixture-003",
        base_candidate=_base_candidate(),
        param_space=_bounded_space(),
        mode="mutate",
        generations=5,
        seed=7,
        run_candidate=_fake_runner,
    )
    # mutate mode runs exactly `generations` trials (+ nothing else).
    assert len(ledger.entries) == 5
    assert all(e.passed and e.promoted for e in ledger.entries)


@pytest.mark.asyncio
async def test_run_evolution_records_but_never_promotes_crashed_trial():
    # A runner that raises on one specific trial. The trial is recorded with an
    # error and promoted=False; the loop continues (no propagation).
    calls = {"n": 0}

    async def _boom(workflow, candidate, run_ctx):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated executor failure")
        return _make_fake_run(True)

    # Use a tiny space so the grid is small and deterministic.
    small = ParamSpace({"answer.temperature": (0.1, 0.2), "answer.top_k": (3, 5)})
    ledger = await run_evolution(
        blueprint_id="bp-fixture-004",
        base_candidate=_base_candidate(),
        param_space=small,
        mode="grid",
        run_candidate=_boom,
    )
    assert len(ledger.entries) == 4  # 2 x 2
    crashed = [e for e in ledger.entries if e.error is not None]
    assert len(crashed) == 1
    assert crashed[0].promoted is False
    assert crashed[0].passed is False
    # Healthy trials still recorded + promoted.
    assert sum(1 for e in ledger.entries if e.promoted) == 3


def test_ledger_record_enforces_fail_closed_invariant():
    # Even if a caller tried to force promoted=True on a failing entry, the
    # ledger refuses to record it (the invariant lives in EvolutionLedger.record).
    ledger = EvolutionLedger(
        blueprint_id="bp-x", baseline_params={}, axis_names=["a"]
    )
    bad = LedgerEntry(
        trial=0, params={"a": 1}, passed=False, promoted=True,
        score={}, safety_pass=False,
    )
    with pytest.raises(RuntimeError):
        ledger.record(bad)
