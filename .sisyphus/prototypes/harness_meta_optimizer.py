#!/usr/bin/env python3
"""
harness_meta_optimizer.py — Prototype of the Automatic Harness Evolution meta-optimizer loop.

STATUS: reference prototype (stdlib-only; uses numpy if present, degrades gracefully).
It does NOT import any Flowmanner internal module so it runs anywhere with plain Python.

WHAT THIS DEMONSTRATES
---------------------
The loop from the research doc (`.sisyphus/plans/harness-evolution-deepdive.md`):

    META-OPTIMIZER  ──samples θ──▶  HARNESS OBJECTS
                                            │
                                    run eval suite
                                            │
    VERIFICATION GATE  ◀── rejects infeasible / unsafe θ
                                            │
                                    multi-objective score
                                            │
    SURROGATE (BO)  ──Expected Improvement──▶  next θ

The configuration vector θ is the *mixed* space from §2a of the doc:
  - θ_text : free-form strings   (prompt, tool descriptions)   → GEPA/ProTeGi in prod
  - θ_cat  : discrete choices     (model_id, tool on/off)        → Bayesian / GA
  - θ_cont : continuous params     (chunk_size, top_k, cache_threshold, decay) → Bayesian

The fitness is multi-objective Pareto: (accuracy↑, cost↓, latency↓, safety_pass↑).
We scalarize for the prototype's acquisition function and document the Pareto extension.

The VERIFICATION GATE is the binding of axis 1d (controller-logic verification, AgentVerify):
a candidate config is *infeasible* if it drops a required tool from the tool-call protocol or
violates a human-in-the-loop boundary. Infeasible θ is rejected (treated as a hard constraint
g(θ) >= 0) before scoring — so evolution is safe-by-construction.

HOW THIS MAPS ONTO FLOWMANNER'S REAL SUBSTRATE
----------------------------------------------
The prototype's `HarnessConfig` is a thin, serialized view of real objects:

  HarnessConfig.prompt                -> WorkflowNode.config["prompt"] / ["system_prompt"]
                                         (app/services/substrate/workflow_models.py: WorkflowNode)
  HarnessConfig.tool_descriptions     -> the `description` read by NodeExecutor._handle_tool
                                         on every turn (node_executor.py)
  HarnessConfig.model_id /
    reasoning_profile                 -> WorkflowNode.assigned_model / reasoning_profile
  HarnessConfig.chunk_size / top_k /
    decay_half_life                   -> rag/chunking_service, rag/retrieval_service config
  HarnessConfig.cache_threshold /
    model_per_step                    -> ModelRouter.route_request + app/api/middleware (semantic cache)
  VerificationGate.forbidden_tools /
    required_edges                    -> ReplayAssertionEngine.evaluate(
                                           expected_behaviors=[{
                                               "type": "tool_sequence",
                                               "required_edges": [...],
                                               "forbidden_tools": [...],
                                           }])
                                         (assertion_engine.py) + PersonalMemoryClaim constraint gate
                                         (see smoke_constraint_gate.py for a live example)

To go from prototype to product you replace `MockHarnessEvaluator` with a harness that
instantiates a `Workflow`, runs it through `UnifiedExecutor`, and reads back the substrate
event log; and you replace `VerificationGate` with a thin wrapper that calls
`ReplayAssertionEngine.evaluate()` + the constraint-claim store.

RUN
---
    python3 harness_meta_optimizer.py
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


# ── Configuration vector θ (the harness object the optimizer mutates) ──────────


@dataclass
class HarnessConfig:
    """The candidate harness configuration — the search-space point θ.

    Only the *tunable* axes are fields. The controller logic is NOT here; it is
    verified, not tuned (axis 1d).
    """

    # axis 1a — prompt (free-form text; in prod, GEPA/ProTeGi mutate this)
    prompt: str = "You are a helpful agent. Solve the task."
    # axis 1b — tool descriptions (free-form text per tool)
    tool_descriptions: dict[str, str] = field(
        default_factory=lambda: {
            "web_search": "search the web",
            "code_executor": "run code",
        }
    )
    # axis 1c — memory retrieval (continuous / structured; Bayesian axis)
    chunk_size: int = 512
    top_k: int = 5
    decay_half_life: float = 24.0  # hours; Ebbinghaus-style memory decay
    # axis 1e — middleware / routing (discrete + continuous; Bayesian + full-eval axis)
    model_id: str = "gpt-4o-mini"
    cache_threshold: float = 0.85  # semantic-cache similarity admit threshold
    # axis 1d (controller logic, verified not tuned): HITL hook on irreversible tools.
    # In prod this is enforced by the substrate's EffectClass.IRREVERSIBLE -> STAGE->CONFIRM
    # dispatch, not by editing description text. Modeled here as a tunable boolean so the
    # verification gate can *reject* the unsafe configs while the optimizer keeps it True.
    hitl_on_irreversible: bool = True
    # model_per_step would be a dict[str, str] in prod; kept single for the prototype

    def to_vector(self) -> list[float]:
        """Flatten the *continuous + ordinal + boolean* axes into a numeric vector for the surrogate.

        Text axes are optimized by textual-gradient mutators in prod; here we expose
        only the structured dims so the Bayesian surrogate has a clean ℝⁿ to reason over.
        `model_id` is encoded as an index into KNOWN_MODELS; `hitl_on_irreversible` as 0/1.
        """
        return [
            float(self.chunk_size),
            float(self.top_k),
            float(self.decay_half_life),
            float(self.cache_threshold),
            float(KNOWN_MODELS.index(self.model_id)),
            float(self.hitl_on_irreversible),
        ]

    @classmethod
    def from_vector(cls, vec: list[float], base: "HarnessConfig") -> "HarnessConfig":
        """Reconstruct a config from a numeric vector, preserving the text axes of `base`."""
        return HarnessConfig(
            prompt=base.prompt,
            tool_descriptions=dict(base.tool_descriptions),
            chunk_size=int(round(vec[0])),
            top_k=int(round(vec[1])),
            decay_half_life=vec[2],
            model_id=KNOWN_MODELS[int(round(vec[4])) % len(KNOWN_MODELS)],
            cache_threshold=vec[3],
            hitl_on_irreversible=bool(round(vec[5])),
        )


KNOWN_MODELS = ["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet", "haiku"]


# ── Verification gate (axis 1d — controller-logic verification, AgentVerify) ─────


@dataclass
class VerificationGate:
    """Feasibility constraint g(θ) >= 0.

    Mirrors `ReplayAssertionEngine.evaluate(expected_behaviors=[required_edges,
    forbidden_tools])` + the `PersonalMemoryClaim` constraint store: the controller's
    *observable control flow* must satisfy tool-call protocols and HITL boundaries.

    In prod this wraps `ReplayAssertionEngine` + the constraint-claim DB. Here it is the
    same contract against a declarative spec.
    """

    required_tools: set[str] = field(
        default_factory=lambda: {"web_search", "code_executor"}
    )
    forbidden_tools: set[str] = field(default_factory=set)  # tools that must NEVER fire
    require_hitl_on_irreversible: bool = True  # HITL boundary (axis 1d)

    def check(self, cfg: HarnessConfig) -> tuple[bool, str]:
        """Return (feasible, reason). Infeasible configs are rejected before scoring."""
        present = set(cfg.tool_descriptions.keys())
        missing = self.required_tools - present
        if missing:
            return (
                False,
                f"tool-call protocol violated: missing required tools {sorted(missing)}",
            )
        if self.forbidden_tools & present:
            return (
                False,
                f"forbidden tool present: {sorted(self.forbidden_tools & present)}",
            )
        # HITL boundary: an irreversible-capable tool (code_executor) must have the
        # structural approval hook enabled (mirrors EffectClass.IRREVERSIBLE -> STAGE->CONFIRM).
        if self.require_hitl_on_irreversible and "code_executor" in present:
            if not cfg.hitl_on_irreversible:
                return (
                    False,
                    "HITL boundary violated: code_executor approval hook disabled",
                )
        return True, "ok"


# ── Surrogate model (Bayesian, dependency-light) ────────────────────────────────


class KernelSurrogate:
    """A lightweight Gaussian-kernel regressor + uncertainty estimator.

    Not a full GP (no Cholesky solve) but a legitimate, working surrogate for BO:
    predicts by kernel-weighted averaging of observed points and estimates uncertainty
    from distance to the nearest observation. Expected Improvement is computed
    analytically. If numpy is available we use it; otherwise a pure-python fallback.
    """

    def __init__(self, lengthscale: float = 1.0, jitter: float = 1e-3):
        self.X: list[list[float]] = []
        self.y: list[float] = []
        self.lengthscale = lengthscale
        self.jitter = jitter

    @staticmethod
    def _dist(a: list[float], b: list[float]) -> float:
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    def add(self, x: list[float], y: float) -> None:
        self.X.append(list(x))
        self.y.append(y)

    def predict(self, x: list[float]) -> tuple[float, float]:
        if not self.X:
            return 0.0, 1e6  # maximally uncertain before any observation
        ws, wsum, mean = [], 0.0, 0.0
        for xi, yi in zip(self.X, self.y):
            d = self._dist(x, xi)
            w = math.exp(-(d**2) / (2 * self.lengthscale**2))
            ws.append(w)
            wsum += w
            mean += w * yi
        if wsum == 0:
            # Far from all observations -> high uncertainty.
            return 0.0, 1e6
        mean /= wsum
        # Uncertainty grows with distance to nearest observed point.
        nearest = min(self._dist(x, xi) for xi in self.X)
        sigma = self.lengthscale * nearest + self.jitter
        return mean, sigma

    def best_y(self) -> float:
        return max(self.y) if self.y else -1e9


def expected_improvement(
    mean: float, sigma: float, best: float, xi: float = 0.01
) -> float:
    """Analytic EI for a maximization objective (standard BO acquisition function)."""
    if sigma <= 1e-9:
        return 0.0
    z = (mean - best - xi) / sigma
    return (mean - best - xi) * _cdf(z) + sigma * _pdf(z)


def _cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


# ── Mock harness evaluator (replace with a real UnifiedExecutor run in prod) ─────


class MockHarnessEvaluator:
    """Simulates running a harness config against an eval suite.

    Models a realistic landscape so the optimizer *visibly* improves:
      - accuracy rises with better retrieval (top_k, chunk_size) up to a sweet spot,
        and with a stronger model, and with a clearer prompt.
      - cost rises with stronger model + larger retrieval; falls with higher cache_threshold.
      - latency rises with stronger model; falls with higher cache_threshold.
    A config the verification gate rejects returns infeasible (not scored).
    """

    def __init__(self, gate: VerificationGate):
        self.gate = gate

    def evaluate(self, cfg: HarnessConfig) -> dict:
        feasible, reason = self.gate.check(cfg)
        if not feasible:
            return {
                "feasible": False,
                "reason": reason,
                "accuracy": 0.0,
                "cost": 0.0,
                "latency": 0.0,
                "safety_pass": 0.0,
            }
        # --- retrieval quality (inverted-U on chunk_size, monotonic on top_k) ---
        chunk_term = 1.0 - abs(cfg.chunk_size - 384) / 1024.0
        topk_term = min(cfg.top_k, 10) / 10.0
        retrieval = max(0.0, chunk_term) * 0.6 + topk_term * 0.4
        # --- model strength ---
        model_strength = {
            "haiku": 0.55,
            "gpt-4o-mini": 0.7,
            "claude-3-5-sonnet": 0.85,
            "gpt-4o": 0.92,
        }[cfg.model_id]
        # --- prompt clarity (longer, specific prompts score a bit higher, capped) ---
        prompt_clarity = min(1.0, 0.6 + len(cfg.prompt) / 400.0)
        accuracy = 0.5 * model_strength + 0.3 * retrieval + 0.2 * prompt_clarity
        accuracy = min(0.99, accuracy)
        # --- cost / latency ---
        model_cost = {
            "haiku": 0.2,
            "gpt-4o-mini": 0.5,
            "claude-3-5-sonnet": 1.2,
            "gpt-4o": 2.0,
        }[cfg.model_id]
        cost = model_cost * (0.5 + 0.1 * cfg.top_k) * (1.0 - 0.4 * cfg.cache_threshold)
        latency = (
            model_cost * (0.3 + 0.05 * cfg.top_k) * (1.0 - 0.3 * cfg.cache_threshold)
        )
        return {
            "feasible": True,
            "reason": "ok",
            "accuracy": accuracy,
            "cost": cost,
            "latency": latency,
            "safety_pass": 1.0,
        }


# ── Meta-optimizer loop ─────────────────────────────────────────────────────────


@dataclass
class OptResult:
    config: HarnessConfig
    accuracy: float
    cost: float
    latency: float
    feasible: bool


class MetaOptimizer:
    """The BO loop that evolves the harness configuration.

    Pipeline (per iteration):
      1. propose candidate θ (random init, then EI-maximizing thereafter)
      2. verification gate — reject infeasible θ (hard constraint)
      3. evaluate (multi-objective)
      4. update surrogate
      5. early-stop on patience / min_delta / max_evaluations
    """

    def __init__(
        self,
        evaluator: MockHarnessEvaluator,
        bounds: dict,
        max_evals: int = 40,
        patience: int = 8,
        min_delta: float = 0.005,
        seed: int = 0,
    ):
        self.ev = evaluator
        self.bounds = bounds  # not strictly used by the prototype's random proposer
        self.max_evals = max_evals
        self.patience = patience
        self.min_delta = min_delta
        self.rng = random.Random(seed)
        self.surrogate = KernelSurrogate(lengthscale=200.0)
        self.history: list[OptResult] = []

    def _random_vector(self) -> list[float]:
        return [
            float(self.rng.randint(128, 1024)),  # chunk_size
            float(self.rng.randint(1, 12)),  # top_k
            self.rng.uniform(1.0, 72.0),  # decay_half_life
            self.rng.uniform(0.6, 0.98),  # cache_threshold
            float(self.rng.randint(0, len(KNOWN_MODELS) - 1)),  # model index
            float(self.rng.randint(0, 1)),  # hitl_on_irreversible (0 or 1)
        ]

    def _propose(self) -> list[float]:
        if not self.surrogate.X:
            return self._random_vector()
        # Random-search the acquisition over a batch of random candidates (cheap, robust).
        best_vec, best_ei = None, -1.0
        best = self.surrogate.best_y()
        best_vec = self._random_vector()  # guarantee non-None; also seeds EI search
        for _ in range(200):
            cand = self._random_vector()
            mean, sigma = self.surrogate.predict(cand)
            ei = expected_improvement(mean, sigma, best)
            if ei > best_ei:
                best_ei, best_vec = ei, cand
        return best_vec

    def scalarize(self, m: dict) -> float:
        """Multi-objective -> scalar for the single-objective acquisition.

        Pareto front noted: in prod use NSGA-II / hypervolume (MALBO). Here we weight
        accuracy up, cost+latency down, safety as a gate (already 0 if infeasible).
        """
        return 0.7 * m["accuracy"] - 0.15 * m["cost"] - 0.15 * m["latency"]

    def run(self, base: HarnessConfig) -> OptResult:
        best: OptResult | None = None
        no_improve = 0
        for it in range(self.max_evals):
            vec = self._propose()
            cfg = HarnessConfig.from_vector(vec, base)
            m = self.ev.evaluate(cfg)
            res = OptResult(cfg, m["accuracy"], m["cost"], m["latency"], m["feasible"])
            self.history.append(res)
            if m["feasible"]:
                score = self.scalarize(m)
                self.surrogate.add(vec, score)
                if best is None or m["accuracy"] > best.accuracy:
                    if (
                        best is not None
                        and (m["accuracy"] - best.accuracy) >= self.min_delta
                    ):
                        no_improve = 0
                    elif (
                        best is None or (m["accuracy"] - best.accuracy) < self.min_delta
                    ):
                        # Feasible but below the meaningful-improvement threshold.
                        no_improve += 1
                    best = res
            else:
                # Rejections mean "we didn't learn," not "we can't improve" — they do
                # NOT advance the no-improvement early-stop counter (see research doc §2e:
                # the gate is a hard constraint g(θ)>=0, orthogonal to optimizer convergence).
                pass
            print(
                f"  it={it:02d}  feasible={m['feasible']!s:5}  "
                f"acc={m['accuracy']:.3f}  cost={m['cost']:.2f}  "
                f"lat={m['latency']:.2f}  model={cfg.model_id}"
                + ("" if m["feasible"] else f"  REJECTED: {m['reason']}")
            )
            if no_improve >= self.patience and best is not None:
                print(f"  early-stop: no improvement for {self.patience} iters")
                break
        return best or self.history[0]


# ── Entrypoint ──────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 78)
    print("AUTOMATIC HARNESS EVOLUTION — meta-optimizer prototype")
    print("=" * 78)

    gate = VerificationGate(
        required_tools={"web_search", "code_executor"},
        forbidden_tools=set(),
        require_hitl_on_irreversible=True,
    )
    evaluator = MockHarnessEvaluator(gate)

    # Baseline: a deliberately weak config (small retrieval, weak model, no HITL hook).
    baseline = HarnessConfig(
        prompt="Do the task.",
        tool_descriptions={"web_search": "search", "code_executor": "run code"},
        chunk_size=128,
        top_k=1,
        decay_half_life=4.0,
        model_id="haiku",
        cache_threshold=0.6,
    )
    base_metrics = evaluator.evaluate(baseline)
    print(
        f"\nBASELINE  acc={base_metrics['accuracy']:.3f}  "
        f"cost={base_metrics['cost']:.2f}  lat={base_metrics['latency']:.2f}\n"
    )

    print("EVOLVING (BO + verification gate) ...")
    opt = MetaOptimizer(evaluator, bounds={}, max_evals=40, patience=8, seed=7)
    best = opt.run(baseline)

    print("\n" + "=" * 78)
    print("RESULT")
    print("=" * 78)
    print(
        f"best accuracy : {best.accuracy:.3f}  (baseline {base_metrics['accuracy']:.3f})"
    )
    print(f"best cost     : {best.cost:.2f}  (baseline {base_metrics['cost']:.2f})")
    print(
        f"best latency  : {best.latency:.2f}  (baseline {base_metrics['latency']:.2f})"
    )
    print(f"best model    : {best.config.model_id}")
    print(
        f"best chunk/topk/decay/cache : {best.config.chunk_size} / {best.config.top_k} "
        f"/ {best.config.decay_half_life:.1f} / {best.config.cache_threshold:.2f}"
    )
    print(f"tool descs    : {best.config.tool_descriptions}")
    feasible_ratio = sum(1 for h in opt.history if h.feasible) / max(
        1, len(opt.history)
    )
    print(f"\nfeasible ratio over search: {feasible_ratio:.2f}")
    print("note: any config dropping code_executor's approval hook was REJECTED by the")
    print(
        "      verification gate before scoring -> evolution stays safe-by-construction."
    )


if __name__ == "__main__":
    main()
