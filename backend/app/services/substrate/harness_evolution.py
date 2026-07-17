"""Thin, real harness-evolution loop over the substrate execution substrate.

Proven mechanism of this project (see AGENTS.md / substrate/AGENTS.md): evolutionary
optimization under *fail-closed* constraints. A substrate run is scored by the
assertion / regression engine; only configs that PASS survive. This module is the
"automatic harness evolution" capability the foundation was built to enable,
adapted from the meta-optimizer prototype (``.sisyphus/prototypes/harness_meta_optimizer.py``)
rather than reinvented.

Design
------
* **Bounded** param space. The loop only mutates a small, explicitly-declared set
  of *safe* knobs (e.g. node-routing temperature, budget_enforcer tolerance,
  assertion thresholds). It can NEVER touch auth, tenancy, or the budget
  fail-closed logic -- those axes are outside ``ParamSpace`` by construction.
* **Real execution.** Each candidate is materialized into a ``Workflow`` and run
  through the substrate ``UnifiedExecutor`` (the only production path), exactly
  like ``evaluate_harness.py``. The single infra seam (``run_candidate``) is the
  only function that touches Postgres + LLM + Qdrant, and the offline test
  replaces it with a fake -- so the loop is proven WITHOUT a live DB.
* **Fail-closed.** A candidate whose assertions/regressions do NOT pass is NEVER
  promoted. The loop only records the delta in an in-memory/JSON ledger and
  reports. There is no auto-deploy, no side effect on the live config.
* **No schema / migration.** The ledger is a plain dataclass serialized to JSON;
  nothing is persisted to Postgres. No cross-tenant data is recorded (the ledger
  carries only the blueprint id + the delta + the score -- see ``R7``).

The loop is intentionally thin: mutate -> run -> score -> record. The scoring
reuses the substrate's ``ReplayAssertionEngine`` vocabulary (cost ceiling,
latency, tool sequence, task completion) plus the per-candidate safety gate from
``evaluate_harness`` so a mutated config that would trip the safety contract can
never be reported as "improved".
"""

from __future__ import annotations

import copy
import itertools
import json
import random
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

# Local, fail-closed safety gate reused from the evaluator shim so the loop and
# the single-candidate evaluator share ONE invariant set.
from app.services.substrate.evaluate_harness import safety_check
from app.services.substrate.workflow_models import NodeType, Workflow, WorkflowEdge, WorkflowNode, WorkflowType

# ── Param space (bounded + safe) ────────────────────────────────────────────

# The full set of axes the loop is *allowed* to mutate. Auth, tenancy, and the
# budget fail-closed logic are deliberately absent -- a ParamSpace that declared
# them would be rejected at construction time (see ParamSpace.validate).
SAFE_AXES = (
    "answer.temperature",  # LLM sampling temperature (node config)
    "answer.top_k",  # retrieval breadth passed to RAGService
    "budget.tolerance_pct",  # budget_enforcer headroom, NOT the hard cap
    "assertion.cost_ceiling_mult",  # multiplier applied to the cost-ceiling assertion
    "routing.max_depth",  # graph strategy traversal depth bound
)

# Axes that map to node-level config (require a target node id -> "answer").
NODE_CONFIG_AXES = {"answer.temperature", "answer.top_k"}
# Axes that touch the budget enforcer's *tolerance* (soft, never the hard cap).
BUDGET_AXES = {"budget.tolerance_pct"}
# Axes that tune the assertion spec only (never the live run).
ASSERTION_AXES = {"assertion.cost_ceiling_mult"}
# Axes that tune strategy routing bounds.
ROUTING_AXES = {"routing.max_depth"}


@dataclass(frozen=True)
class Axis:
    """One bounded, safe mutation axis.

    ``choices`` enumerates the discrete values the loop may try. Continuous axes
    are discretized by the caller into a small finite set so the search space
    stays bounded and replayable.
    """

    name: str
    choices: tuple[float | int | str, ...]

    def validate(self) -> None:
        if self.name not in SAFE_AXES:
            raise ValueError(
                f"Axis {self.name!r} is not in the bounded safe set {SAFE_AXES}. "
                "Refusing to mutate an out-of-scope (possibly unsafe) parameter."
            )
        if not self.choices:
            raise ValueError(f"Axis {self.name!r} has no choices -- empty search space.")


class ParamSpace:
    """A bounded, validated set of mutation axes.

    Construction rejects any axis outside ``SAFE_AXES``. This is the hard guard
    that keeps the loop from ever touching auth / tenancy / budget fail-closed
    logic -- those axes simply cannot be expressed here.
    """

    def __init__(self, axes: dict[str, tuple[Any, ...]]):
        self._axes: dict[str, Axis] = {}
        for name, choices in axes.items():
            ax = Axis(name=name, choices=tuple(choices))
            ax.validate()
            self._axes[name] = ax
        if not self._axes:
            raise ValueError("ParamSpace requires at least one bounded axis.")

    @property
    def axes(self) -> dict[str, Axis]:
        return dict(self._axes)

    def combinations(self) -> list[dict[str, Any]]:
        """All bounded combinations (Cartesian product) of the axes.

        The total count is ``prod(len(choices))`` and is intended to be small
        (the task mandates a BOUNDED space). Callers may also use ``mutate`` for
        a randomized neighborhood search instead.
        """
        names = list(self._axes)
        value_lists = [self._axes[n].choices for n in names]
        return [dict(zip(names, combo, strict=True)) for combo in itertools.product(*value_lists)]

    def mutate(self, base: dict[str, Any], rng: random.Random | None = None) -> dict[str, Any]:
        """Produce ONE neighbor of ``base`` by flipping exactly one axis.

        ``base`` maps axis-name -> current value. The returned delta mutates a
        single random axis to a (different) value from its choices. This is the
        fail-closed, bounded step the evolutionary loop uses; it never invents
        values outside ``choices``.
        """
        rng = rng or random.Random()
        name = rng.choice(list(self._axes))
        ax = self._axes[name]
        choices = [c for c in ax.choices if c != base.get(name)]
        if not choices:
            # Only one choice for this axis; fall back to keeping it unchanged.
            return dict(base)
        new_val = rng.choice(choices)
        out = dict(base)
        out[name] = new_val
        return out


# ── Candidate materialization ───────────────────────────────────────────────


def apply_params_to_candidate(candidate: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied candidate with ``params`` overlaid onto safe slots.

    Only the slots enumerated by ``SAFE_AXES`` are written; everything else in
    the candidate (workflow structure, auth, tenancy, the budget hard cap) is
    preserved verbatim. This is what guarantees a mutation can never escalate
    its own authority.
    """
    out = copy.deepcopy(candidate)
    for name, value in params.items():
        if name not in SAFE_AXES:
            # Defensive: ParamSpace already gates this, but never trust a raw
            # params dict that wanders in from a caller.
            raise ValueError(f"Refusing to apply out-of-scope axis {name!r} to a candidate.")
        if name in NODE_CONFIG_AXES:
            node_id = name.split(".", 1)[0]
            node = _find_node(out, node_id)
            node.setdefault("config", {})[name.split(".", 1)[1]] = value
        elif name in BUDGET_AXES:
            out.setdefault("budget", {})["tolerance_pct"] = value
        elif name in ASSERTION_AXES:
            out.setdefault("assertion", {})["cost_ceiling_mult"] = value
        elif name in ROUTING_AXES:
            out.setdefault("routing", {})["max_depth"] = value
    return out


def _find_node(candidate: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in candidate.get("workflow", {}).get("nodes", []):
        if node.get("id") == node_id:
            return node
    raise KeyError(f"ParamSpace axis targets node {node_id!r} which is absent from the candidate.")


# ── Scored ledger ───────────────────────────────────────────────────────────


@dataclass
class LedgerEntry:
    """One scored trial. Fail-closed: ``promoted`` is False unless assertions pass."""

    trial: int
    params: dict[str, Any]
    passed: bool
    promoted: bool
    score: dict[str, Any]  # metric deltas vs baseline
    safety_pass: bool | None
    assertion_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvolutionLedger:
    """In-memory + JSON-serializable scored ledger. No DB, no cross-tenant data.

    Carries only: blueprint id, baseline params, and per-trial deltas + scores.
    No user PII, no tenant secrets -- satisfies R7 (no cross-tenant data).
    """

    blueprint_id: str
    baseline_params: dict[str, Any]
    axis_names: list[str]
    entries: list[LedgerEntry] = field(default_factory=list)

    def record(self, entry: LedgerEntry) -> None:
        # Hard fail-closed invariant: promotion requires BOTH assertions pass AND
        # safety pass. We re-assert it here so no caller can accidentally flip
        # ``promoted`` without the gate.
        if entry.promoted and not (entry.passed and entry.safety_pass):
            raise RuntimeError(
                "Fail-closed violation: a candidate was marked promoted without "
                "passing assertions AND safety. The loop must never promote a "
                "failing config."
            )
        self.entries.append(entry)

    def best(self) -> LedgerEntry | None:
        """Return the best PROMOTED entry by score, or None if none promoted."""
        promoted = [e for e in self.entries if e.promoted]
        if not promoted:
            return None
        return max(promoted, key=lambda e: e.score.get("combined", 0.0))

    def to_dict(self) -> dict[str, Any]:
        best = self.best()
        return {
            "blueprint_id": self.blueprint_id,
            "baseline_params": self.baseline_params,
            "axis_names": self.axis_names,
            "entries": [e.to_dict() for e in self.entries],
            "best_promoted": best.to_dict() if best is not None else None,
        }

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)


# ── Run seam (the ONLY infra-touching function) ─────────────────────────────

# Signature: async (workflow, candidate, run_ctx) -> RunOutcome.
# ``run_ctx`` carries non-tenant, non-secret metadata (trial index, blueprint id)
# so a real run can scope itself to blueprint mode without leaking tenant data.
RunOutcome = dict[str, Any]
RunFn = Callable[[Workflow, dict[str, Any], dict[str, Any]], Awaitable[RunOutcome]]


async def _default_run_candidate(workflow: Workflow, candidate: dict[str, Any], run_ctx: dict[str, Any]) -> RunOutcome:
    """REAL run seam: execute the candidate through UnifiedExecutor.

    Mirrors ``evaluate_harness.run_executor`` -- the only production path. It is
    isolated here so the offline test can monkeypatch ``run_candidate`` with a
    fake that returns the same shape.

    Returns the same dict shape ``evaluate_harness.run_executor`` does:
      {"result": {...}, "events": [...], "answer_output": {...}}
    """
    from app.database import AsyncSessionLocal
    from app.services.substrate.executor import UnifiedExecutor

    async with AsyncSessionLocal() as db:
        executor = UnifiedExecutor()
        result = await executor.execute(
            db,
            workflow,
            run_id=str(run_ctx.get("run_id", __import__("uuid").uuid4())),
        )
        events = await _collect_events(db, str(result.run_id))
        answer_output = _extract_answer_output(events, result)
    return {
        "result": {
            "success": result.success,
            "status": result.status,
            "total_cost_usd": float(result.total_cost_usd),
            "execution_time_ms": float(result.execution_time_ms),
            "completed_nodes": list(result.completed_nodes),
            "failed_nodes": list(result.failed_nodes),
            "error": result.error,
        },
        "events": events,
        "answer_output": answer_output,
    }


async def _collect_events(db: Any, run_id: str) -> list[dict[str, Any]]:
    from app.services.substrate.event_log import get_event_log

    event_log = get_event_log()
    raw = await event_log.get_events(db, run_id)
    out: list[dict[str, Any]] = []
    for ev in raw:
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        out.append({"type": getattr(ev, "type", None) or payload.get("type"), "payload": payload})
    return out


def _extract_answer_output(events: list[dict[str, Any]], result: Any) -> dict[str, Any] | None:
    from app.models.substrate_models import SubstrateEventType

    for ev in events:
        if ev["type"] == SubstrateEventType.NODE_COMPLETED:
            node_id = (ev["payload"] or {}).get("node_id")
            if node_id == "answer":
                return (ev["payload"] or {}).get("output")
    for ev in reversed(events):
        if ev["type"] == SubstrateEventType.LLM_RESPONSE:
            return {"content": (ev["payload"] or {}).get("content")}
    return None


# ── Scoring (reuses substrate assertion vocabulary) ──────────────────────────


def score_run(
    candidate: dict[str, Any],
    run: RunOutcome,
    baseline_metrics: dict[str, float],
    assertion_spec: list[dict[str, Any]] | None = None,
) -> tuple[bool, dict[str, Any], list[dict[str, Any]], float]:
    """Score one run, fail-closed.

    Returns ``(passed, score, assertion_results, safety_pass)``.

    * ``safety_pass`` comes from the reused ``evaluate_harness.safety_check``
      gate (forbidden tools, constraint blocks, static verify_candidate). A
      candidate that trips safety is NEVER promoted.
    * ``passed`` is True only if ``safety_pass`` AND (when an assertion_spec is
      supplied) every assertion's score meets the spec. The assertion_spec lets
      the loop express regressions (e.g. "cost must not exceed baseline × 1.2").
    * ``score`` is the delta vs ``baseline_metrics`` (lower cost / latency is
      better; a ``combined`` scalar rewards improvement without inverting
      safety).
    """
    safety_pass, failures = safety_check(candidate, run)
    result = run["result"]

    # ``result`` may be a real StrategyResult (pydantic), the offline fake
    # dataclass, or a plain dict -- all expose these fields by attribute.
    cost = float(getattr(result, "total_cost_usd", 0.0) or 0.0)
    latency = float(getattr(result, "execution_time_ms", 0.0) or 0.0)
    success = bool(getattr(result, "success", False))

    base_cost = float(baseline_metrics.get("cost_usd", cost))
    base_latency = float(baseline_metrics.get("latency_ms", latency))

    # Deltas (improvement = negative delta for cost/latency).
    d_cost = cost - base_cost
    d_latency = latency - base_latency

    assertion_results: list[dict[str, Any]] = []
    spec_pass = True
    if assertion_spec:
        for a in assertion_spec:
            kind = a.get("type")
            threshold = a.get("threshold")
            actual = None
            ok = True
            if kind == "cost_ceiling":
                mult = float(a.get("multiplier", 1.2))
                actual = cost
                ok = cost <= base_cost * mult
            elif kind == "latency_ceiling":
                mult = float(a.get("multiplier", 2.0))
                actual = latency
                ok = latency <= base_latency * mult
            elif kind == "task_completion":
                actual = success
                ok = success
            assertion_results.append({"type": kind, "passed": bool(ok), "actual": actual, "threshold": threshold})
            spec_pass = spec_pass and ok

    # A run that did not even complete cannot be "better".
    passed = bool(safety_pass and spec_pass and success)

    # Combined scalar: reward improvement, zero if not passed (fail-closed).
    combined = 0.0
    if passed:
        # Normalize deltas against baseline so different scales combine.
        norm_cost = (d_cost / base_cost) if base_cost else 0.0
        norm_lat = (d_latency / base_latency) if base_latency else 0.0
        # Improvement lowers norm_*; subtract so a better config scores higher.
        combined = round(-(norm_cost + norm_lat) * 0.5, 6)

    score = {
        "cost_usd": round(cost, 6),
        "latency_ms": round(latency, 1),
        "success": success,
        "d_cost": round(d_cost, 6),
        "d_latency": round(d_latency, 1),
        "combined": combined,
        "safety_failures": failures,
    }
    return passed, score, assertion_results, safety_pass


# ── The loop ─────────────────────────────────────────────────────────────────


def build_workflow_for_candidate(candidate: dict[str, Any]) -> Workflow:
    """Materialize a real ``Workflow`` from a candidate (adapts evaluate_harness.build_workflow).

    Kept local (rather than importing evaluate_harness.build_workflow) so the loop
    does not depend on the optimizer's full config shape; it only needs the
    ``workflow`` sub-tree that a fixture blueprint provides.
    """
    from app.services.substrate.evaluate_harness import NODE_TYPE_ALIASES

    workflow_cfg = candidate.get("workflow", {})
    raw_nodes = workflow_cfg.get("nodes", [])
    raw_edges = workflow_cfg.get("edges", [])

    nodes: list[WorkflowNode] = []
    for node in raw_nodes:
        raw_type = node.get("type", "llm_call")
        # SAFE lookup: only construct NodeType from the raw value when no alias
        # exists. (Avoids eagerly evaluating NodeType(raw_type) as a default arg,
        # which would raise for alias keys like "llm".)
        node_type = NODE_TYPE_ALIASES[raw_type] if raw_type in NODE_TYPE_ALIASES else NodeType(raw_type)
        config = dict(node.get("config", {}))
        assigned_model = node.get("assigned_model")
        if assigned_model:
            config.setdefault("model_preference", assigned_model)
        nodes.append(
            WorkflowNode(
                id=node["id"],
                type=node_type,
                title=node.get("title", node["id"]),
                description=node.get("description", ""),
                config=config,
                assigned_model=assigned_model,
                reasoning_profile=node.get("reasoning_profile", "normal"),
                effect_class=__import__("app.services.substrate.workflow_models", fromlist=["EffectClass"]).EffectClass(
                    node.get("effect_class", "reversible")
                ),
            )
        )

    edges = [WorkflowEdge(source=e["source"], target=e["target"], condition=e.get("condition")) for e in raw_edges]
    return Workflow(
        id="00000000-0000-0000-0000-0000000000e0",
        type=WorkflowType.DAG if len(nodes) > 1 else WorkflowType.SOLO,
        title="harness-evolution",
        description="harness-evolution candidate",
        nodes=nodes,
        edges=edges,
        user_id="00000000-0000-0000-0000-000000000000",
        workspace_id=candidate.get("workspace_id"),
    )


async def run_evolution(
    blueprint_id: str,
    base_candidate: dict[str, Any],
    param_space: ParamSpace,
    *,
    assertion_spec: list[dict[str, Any]] | None = None,
    mode: str = "grid",  # "grid" | "mutate"
    generations: int = 1,
    seed: int = 0,
    run_candidate: RunFn | None = None,
    baseline_metrics: dict[str, float] | None = None,
) -> EvolutionLedger:
    """Run the harness-evolution loop and return a scored, fail-closed ledger.

    Args:
        blueprint_id: fixture blueprint id the loop operates over. Recorded in the
            ledger (non-secret, non-tenant metadata only).
        base_candidate: the baseline candidate config (workflow + safe slots).
        param_space: bounded, validated ParamSpace (rejects unsafe axes).
        assertion_spec: optional regression assertions (cost/latency/task ceilings).
        mode: ``"grid"`` enumerates every combination; ``"mutate"`` does a
            randomized neighborhood walk for ``generations`` steps.
        generations: number of mutate-steps (ignored in grid mode).
        seed: RNG seed for reproducible mutate walks.
        run_candidate: injectable run seam (defaults to the REAL UnifiedExecutor
            path). The offline test passes a fake here.
        baseline_metrics: known-good cost/latency to delta against. If None, the
            baseline (params = base_candidate's current values) is run first.

    Returns:
        An ``EvolutionLedger``. Every entry with ``promoted=True`` satisfies the
        fail-closed gate; failing configs are recorded but NEVER promoted.
    """
    run = run_candidate or _default_run_candidate
    ledger = EvolutionLedger(
        blueprint_id=blueprint_id,
        baseline_params=_current_params(base_candidate, param_space),
        axis_names=list(param_space.axes.keys()),
    )

    # Establish baseline metrics if not supplied (run the unmutated candidate).
    if baseline_metrics is None:
        base_wf = build_workflow_for_candidate(base_candidate)
        base_run = await run(
            base_wf, base_candidate, {"blueprint_id": blueprint_id, "run_id": __import__("uuid").uuid4()}
        )
        _, _base_score, _, _ = score_run(base_candidate, base_run, {"cost_usd": 0.0, "latency_ms": 0.0}, None)
        baseline_metrics = {
            "cost_usd": float(getattr(base_run["result"], "total_cost_usd", 0.0) or 0.0),
            "latency_ms": float(getattr(base_run["result"], "execution_time_ms", 0.0) or 0.0),
        }

    if mode == "grid":
        trials = param_space.combinations()
    else:
        trials = []
        rng = random.Random(seed)
        cur = _current_params(base_candidate, param_space)
        for _ in range(max(1, generations)):
            cur = param_space.mutate(cur, rng)
            trials.append(dict(cur))

    for i, params in enumerate(trials):
        mutated = apply_params_to_candidate(base_candidate, params)
        wf = build_workflow_for_candidate(mutated)
        try:
            outcome = await run(
                wf, mutated, {"blueprint_id": blueprint_id, "trial": i, "run_id": __import__("uuid").uuid4()}
            )
            passed, score, assertion_results, safety_pass = score_run(
                mutated, outcome, baseline_metrics, assertion_spec
            )
            promoted = passed  # fail-closed: promote only passing configs
            entry = LedgerEntry(
                trial=i,
                params=dict(params),
                passed=passed,
                promoted=promoted,
                score=score,
                safety_pass=safety_pass,
                assertion_results=assertion_results,
            )
        except Exception as exc:  # a crashed trial is recorded, never promoted
            entry = LedgerEntry(
                trial=i,
                params=dict(params),
                passed=False,
                promoted=False,
                score={"error": str(exc)},
                safety_pass=None,
                error=f"{type(exc).__name__}: {exc}",
            )
        ledger.record(entry)

    return ledger


def _current_params(candidate: dict[str, Any], param_space: ParamSpace) -> dict[str, Any]:
    """Read the current value of each axis from the candidate (best-effort)."""
    out: dict[str, Any] = {}
    for name in param_space.axes:
        if name in NODE_CONFIG_AXES:
            node_id = name.split(".", 1)[0]
            node = next(
                (n for n in candidate.get("workflow", {}).get("nodes", []) if n.get("id") == node_id),
                None,
            )
            out[name] = (node or {}).get("config", {}).get(name.split(".", 1)[1])
        elif name in BUDGET_AXES:
            out[name] = candidate.get("budget", {}).get("tolerance_pct")
        elif name in ASSERTION_AXES:
            out[name] = candidate.get("assertion", {}).get("cost_ceiling_mult")
        elif name in ROUTING_AXES:
            out[name] = candidate.get("routing", {}).get("max_depth")
    return out
