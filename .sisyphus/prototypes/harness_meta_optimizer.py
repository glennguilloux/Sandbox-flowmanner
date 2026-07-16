#!/usr/bin/env python3
"""
Constrained automatic harness-evolution prototype for Flowmanner.

This is intentionally an adapter/prototype rather than a direct backend import:
Flowmanner currently has the component primitives (WorkflowNode, ModelRouter,
ReplayAssertionEngine, RAG settings), but not a single runtime HarnessConfig
object. This module materializes one candidate configuration document per trial.

Usage
-----
# Run against a real evaluator. The command receives:
#   <candidate-config.json> <split>
#
# It must emit one JSON object on stdout, for example:
# {"accuracy": 0.86, "cost_usd": 0.018, "latency_ms": 1420, "safety_pass": true}
#
# HARNESS_EVAL_COMMAND="./scripts/evaluate_harness.sh" \
#   python .sisyphus/prototypes/harness_meta_optimizer.py \
#     --config harness-config.yaml --budget 50

# Run the dependency-free deterministic demonstration:
# python .sisyphus/prototypes/harness_meta_optimizer.py \
#   --config harness-config.yaml --budget 40 --demo

YAML input requires PyYAML. JSON input uses the standard library only:
# pip install pyyaml
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import random
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODEL_CHOICES = (
    "llamacpp-qwen3.6-27b",
    "glennguilloux-demo-llm",
    "deepseek-v4-flash",
    "deepseek-chat",
    "deepseek-reasoner",
    "claude-3-haiku",
    "claude-3-5-sonnet",
    "openrouter-gemini-2.0-flash",
)
# NOTE: MODEL_CHOICES is the feature-vector VOCABULARY only (feature_vector /
# _model_index use it for distance + acquisition). mutate() selects from the
# candidate's routing.catalog instead, because the catalog carries the exact
# runtime model ids (slash form for llamacpp) that app.services.llm_providers
# resolves. A mutated id not in MODEL_CHOICES yields the out-of-range sentinel
# in _model_index and never crashes the loop.

SYSTEM_PROMPT_VARIANTS = (
    """You are a senior research analyst. Use retrieved context as the primary
knowledge source. Cite the source node id for every factual claim. If retrieval
is empty or insufficient, explicitly say so. Return only the requested JSON.""",
    """You are a senior research analyst. Produce a grounded churn-risk assessment
strictly from retrieved evidence. For each claim, cite its source node id. Do not
invent facts; when evidence is missing, report the uncertainty. Return valid JSON
with risk_level, basis, and recommended_action.""",
    """Analyze the account using the retrieved churn cases. Prefer concise,
verifiable claims and identify the source node id supporting each claim. If the
retrieved set cannot support a conclusion, set risk_level to "unknown". Return
only JSON: {risk_level, basis, recommended_action}.""",
)

TOOL_DESCRIPTION_VARIANTS = (
    """Semantic retrieval over the workspace collection. Use this as the primary
knowledge source for workspace facts. Returns ranked chunks with source node ids.
Use before web_search when the question concerns internal history or prior cases.""",
    """Retrieve evidence from the workspace collection. Best for historical churn
cases, internal documents, and source-grounded answers. Returns ranked chunks and
source node ids. Prefer this tool over web_search for information that may exist
in the workspace.""",
    """Search the live web (SearXNG) for recent, attributable public information.
Use only when required facts are absent from retrieved workspace context. Never use
for internal, confidential, or PII data. Returns ranked snippets with source URLs.""",
)


@dataclass(frozen=True)
class Metrics:
    accuracy: float
    cost_usd: float
    latency_ms: float
    safety_pass: bool

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Metrics:
        required = ("accuracy", "cost_usd", "latency_ms", "safety_pass")
        missing = [key for key in required if key not in raw]
        if missing:
            raise ValueError(f"Evaluator output is missing fields: {missing}")

        return cls(
            accuracy=float(raw["accuracy"]),
            cost_usd=float(raw["cost_usd"]),
            latency_ms=float(raw["latency_ms"]),
            safety_pass=bool(raw["safety_pass"]),
        )


@dataclass
class Observation:
    config: dict[str, Any]
    metrics: Metrics
    split: str


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")

    if path.suffix.lower() == ".json":
        return json.loads(text)

    try:
        import yaml  # type: ignore
    except ImportError as error:
        raise SystemExit(
            "YAML configuration requires PyYAML. Install it with `pip install pyyaml`, or provide JSON input."
        ) from error

    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError("The harness configuration must be a mapping/object.")
    return document


def node_by_id(config: dict[str, Any], node_id: str) -> dict[str, Any]:
    for node in config["workflow"]["nodes"]:
        if node["id"] == node_id:
            return node
    raise KeyError(f"Unknown workflow node: {node_id}")


def model_catalog(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in config["routing"]["catalog"]}


def candidate_key(config: dict[str, Any]) -> str:
    """Stable identity used to prevent duplicate expensive evaluations."""
    return json.dumps(config, sort_keys=True, separators=(",", ":"))


def verify_candidate(config: dict[str, Any]) -> list[str]:
    """
    Hard feasibility gate.

    This mirrors the structural portion of:
      * edge-target validation;
      * ReplayAssertionEngine expected behaviors;
      * PersonalMemoryClaim constraint invariants.

    The real evaluator should additionally invoke ReplayAssertionEngine.evaluate()
    over its execution trace. This static gate prevents obviously invalid candidates
    from consuming an evaluation budget.
    """
    errors: list[str] = []

    workflow = config.get("workflow", {})
    nodes = workflow.get("nodes", [])
    node_ids = {node.get("id") for node in nodes}
    if len(node_ids) != len(nodes):
        errors.append("Workflow contains duplicate node IDs.")

    edge_rules = config.get("verification", {}).get("edge_target_validation", {})
    edges = workflow.get("edges", [])
    normalized_edges = {(edge.get("source"), edge.get("target")) for edge in edges}

    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if edge_rules.get("reject_dangling_edges", True) and (
            source not in node_ids or target not in node_ids
        ):
            errors.append(f"Dangling workflow edge: {source!r} -> {target!r}.")
        if edge_rules.get("reject_self_loops", True) and source == target:
            errors.append(f"Self-loop is forbidden: {source!r} -> {target!r}.")

    for required_edge in config.get("verification", {}).get("required_edges", []):
        edge = tuple(required_edge)
        if edge not in normalized_edges:
            errors.append(f"Required edge is absent from workflow: {edge!r}.")

    forbidden = set(config.get("verification", {}).get("forbidden_tools", []))
    for node in nodes:
        configured_tools = set(node.get("config", {}).get("tool_ids", []))
        prohibited = configured_tools & forbidden
        if prohibited:
            errors.append(
                f"Node {node.get('id')!r} enables forbidden tool(s): {sorted(prohibited)}."
            )

    valid_actions = {"block", "escalate", "allow"}
    for claim in config.get("verification", {}).get(
        "personal_memory_claim_constraints", []
    ):
        if claim.get("claim_type") != "constraint":
            errors.append("Personal-memory constraint has invalid claim_type.")
        action = claim.get("object", {}).get("action")
        if action not in valid_actions:
            errors.append(f"Constraint has invalid action: {action!r}.")
        if claim.get("sensitivity") == "restricted" and not claim.get("scope"):
            errors.append("Restricted constraint must define a scope.")

    answer = next((node for node in nodes if node.get("id") == "answer"), None)
    if answer and answer.get("assigned_model") not in model_catalog(config):
        errors.append("answer.assigned_model is not present in routing.catalog.")

    return errors


def mutate(base: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """
    Mixed-space proposal generator.

    Production integration point:
      Replace the fixed prompt and description variants with a GEPA/ProTeGi
      mutator that proposes candidates from failed evaluation traces.
    """
    candidate = copy.deepcopy(base)
    memory = candidate["memory"]
    answer = node_by_id(candidate, "answer")
    catalog = model_catalog(candidate)

    memory["chunk_size"] = rng.choice((600, 800, 1000, 1200, 1500))
    memory["chunk_overlap"] = rng.choice((80, 120, 160, 200, 240))
    memory["top_k"] = rng.choice((3, 4, 5, 6, 8))
    memory["similarity_threshold"] = rng.choice((0.55, 0.60, 0.65, 0.70, 0.75))
    memory["reranker"] = rng.choice((True, True, True, False))
    memory["decay_rate_per_day"] = rng.choice((0.003, 0.005, 0.01, 0.015, 0.02))

    answer["config"]["temperature"] = rng.choice((0.0, 0.1, 0.2, 0.3))
    answer["config"]["system_prompt"] = rng.choice(SYSTEM_PROMPT_VARIANTS)

    # Prefer the CATALOG's exact model ids over MODEL_CHOICES. The catalog uses
    # the runtime model id form (e.g. slash-form ``llamacpp/Qwen3.6-27B``) that
    # app.services.llm_providers._get_provider_for_model actually resolves, while
    # MODEL_CHOICES uses hyphen tokens (``llamacpp-qwen3.6-27b``) that would fall
    # through to the default cloud key env. Selecting from the catalog keeps the
    # mutated candidate consistent with verify_candidate AND runnable at runtime
    # (including the keyless local llamacpp model). MODEL_CHOICES is retained
    # only as the feature-vector vocabulary in feature_vector()/_model_index().
    enabled_models = [
        model_id for model_id, spec in catalog.items() if spec.get("enabled", True)
    ] or list(catalog.keys())
    answer["assigned_model"] = rng.choice(enabled_models)

    # Experimental metadata: it remains inert until semantic caching exists in
    # app.api.middleware / ModelRouter. Keep it in candidates so old trials can
    # become comparable after the middleware is implemented.
    candidate["routing"]["semantic_cache_threshold"] = rng.choice(
        (0.82, 0.86, 0.89, 0.92, 0.95, 0.97)
    )

    retrieve_tool = next(
        tool for tool in candidate["tools"] if tool["id"] == "retrieve"
    )
    retrieve_tool["description"] = rng.choice(TOOL_DESCRIPTION_VARIANTS[:2])

    web_tool = next(tool for tool in candidate["tools"] if tool["id"] == "web_search")
    web_tool["description"] = TOOL_DESCRIPTION_VARIANTS[2]

    return candidate


def dominates(left: Metrics, right: Metrics) -> bool:
    """True when left is at least as good on all objectives and better on one."""
    if not left.safety_pass:
        return False
    if not right.safety_pass:
        return True

    no_worse = (
        left.accuracy >= right.accuracy
        and left.cost_usd <= right.cost_usd
        and left.latency_ms <= right.latency_ms
    )
    strictly_better = (
        left.accuracy > right.accuracy
        or left.cost_usd < right.cost_usd
        or left.latency_ms < right.latency_ms
    )
    return no_worse and strictly_better


def pareto_front(observations: list[Observation]) -> list[Observation]:
    feasible = [item for item in observations if item.metrics.safety_pass]
    return [
        item
        for item in feasible
        if not any(
            other is not item and dominates(other.metrics, item.metrics)
            for other in feasible
        )
    ]


def feature_vector(config: dict[str, Any]) -> tuple[float, ...]:
    """Structured representation for a dependency-free kernel surrogate."""
    memory = config["memory"]
    answer = node_by_id(config, "answer")
    return (
        memory["chunk_size"] / 1500.0,
        memory["chunk_overlap"] / 250.0,
        memory["top_k"] / 8.0,
        memory["similarity_threshold"],
        float(memory["reranker"]),
        memory["decay_rate_per_day"] / 0.02,
        answer["config"]["temperature"] / 0.3,
        config["routing"]["semantic_cache_threshold"],
        _model_index(answer["assigned_model"]) / max(1, len(MODEL_CHOICES) - 1),
        _variant_index(answer["config"]["system_prompt"])
        / max(1, len(SYSTEM_PROMPT_VARIANTS) - 1),
    )


def _model_index(model_id: str) -> int:
    """Index of a model in MODEL_CHOICES, or a sentinel for unknown models.

    A real evaluator may surface a config whose model/ prompt is not one of the
    discrete choices this prototype enumerates; never let that crash the loop.
    """
    try:
        return MODEL_CHOICES.index(model_id)
    except ValueError:
        return len(MODEL_CHOICES)  # out-of-range sentinel


def _variant_index(text: str) -> int:
    try:
        return SYSTEM_PROMPT_VARIANTS.index(text)
    except ValueError:
        return len(SYSTEM_PROMPT_VARIANTS)  # out-of-range sentinel


def distance(left: dict[str, Any], right: dict[str, Any]) -> float:
    a, b = feature_vector(left), feature_vector(right)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=False)))


def acquisition(
    candidate: dict[str, Any],
    observations: list[Observation],
) -> float:
    """
    Kernel-regression surrogate + uncertainty bonus.

    The scalar exists only to choose the *next experiment*. Promotion remains
    Pareto-based, not scalar-score based.
    """
    train = [item for item in observations if item.split == "train"]
    if not train:
        return float("inf")

    weighted: list[tuple[float, Observation]] = []
    nearest_distance = float("inf")
    for observation in train:
        d = distance(candidate, observation.config)
        nearest_distance = min(nearest_distance, d)
        weighted.append((math.exp(-12.0 * d * d), observation))

    weight_sum = sum(weight for weight, _ in weighted) or 1.0
    predicted_accuracy = (
        sum(weight * obs.metrics.accuracy for weight, obs in weighted) / weight_sum
    )
    predicted_cost = (
        sum(weight * obs.metrics.cost_usd for weight, obs in weighted) / weight_sum
    )
    predicted_latency = (
        sum(weight * obs.metrics.latency_ms for weight, obs in weighted) / weight_sum
    )

    # Acquisition-only normalization. The final reported decision is Pareto-based.
    cost_scale = max(0.01, max(obs.metrics.cost_usd for _, obs in weighted))
    latency_scale = max(100.0, max(obs.metrics.latency_ms for _, obs in weighted))
    exploitation = (
        predicted_accuracy
        - 0.25 * (predicted_cost / cost_scale)
        - 0.15 * (predicted_latency / latency_scale)
    )
    exploration = 0.20 * min(1.0, nearest_distance)
    return exploitation + exploration


def run_external_evaluator(
    command: str,
    config: dict[str, Any],
    split: str,
) -> Metrics:
    with tempfile.TemporaryDirectory(prefix="harness-candidate-") as temp_dir:
        candidate_path = Path(temp_dir) / "candidate.json"
        candidate_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

        completed = subprocess.run(
            [*shlex.split(command), str(candidate_path), split],
            check=False,
            capture_output=True,
            text=True,
            timeout=60 * 60,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Evaluator failed ({completed.returncode}):\n{completed.stderr}"
            )

        # Permit logging before the final machine-readable JSON line.
        output_lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if not output_lines:
            raise ValueError("Evaluator produced no JSON output.")
        return Metrics.from_json(json.loads(output_lines[-1]))


def run_demo_evaluator(config: dict[str, Any]) -> Metrics:
    """
    Deterministic stand-in only. It demonstrates optimizer mechanics; it is not a
    quality measurement and must not be used for promotion decisions.
    """
    memory = config["memory"]
    answer = node_by_id(config, "answer")
    model = model_catalog(config)[answer["assigned_model"]]
    model_cost = float(model["in"]) + float(model["out"])

    accuracy = 0.66
    accuracy += 0.10 if memory["reranker"] else -0.03
    accuracy += 0.05 if 4 <= memory["top_k"] <= 6 else -0.03
    accuracy += 0.05 if 0.60 <= memory["similarity_threshold"] <= 0.72 else -0.02
    accuracy += 0.04 if answer["config"]["temperature"] <= 0.2 else -0.03
    accuracy += (
        0.03
        if answer["assigned_model"]
        in (
            "deepseek-reasoner",
            "claude-3-5-sonnet",
        )
        else 0.0
    )
    accuracy = min(0.97, max(0.0, accuracy))

    token_factor = memory["top_k"] * (memory["chunk_size"] / 1000.0)
    cost = 0.002 + model_cost * token_factor / 1000.0
    latency = 450 + 120 * memory["top_k"] + 400 * bool(memory["reranker"])
    latency += (
        250
        if answer["assigned_model"] in ("claude-3-5-sonnet", "deepseek-reasoner")
        else 0
    )

    return Metrics(
        accuracy=round(accuracy, 4),
        cost_usd=round(cost, 6),
        latency_ms=float(latency),
        safety_pass=True,
    )


def optimize(
    base: dict[str, Any],
    budget: int,
    warmup: int,
    seed: int,
    demo: bool,
    evaluator_command: str | None,
) -> list[Observation]:
    rng = random.Random(seed)
    observations: list[Observation] = []
    seen: set[str] = set()

    for trial in range(budget):
        if trial == 0:
            candidate = copy.deepcopy(base)
        elif trial < warmup or not observations:
            candidate = mutate(base, rng)
        else:
            proposal_pool = [mutate(base, rng) for _ in range(96)]
            candidate = max(
                proposal_pool,
                key=lambda proposal: acquisition(proposal, observations),
            )

        key = candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)

        violations = verify_candidate(candidate)
        if violations:
            print(f"[trial {trial + 1:02d}] rejected: {'; '.join(violations)}")
            continue

        metrics = (
            run_demo_evaluator(candidate)
            if demo
            else run_external_evaluator(evaluator_command or "", candidate, "train")
        )
        if not metrics.safety_pass:
            print(f"[trial {trial + 1:02d}] rejected by runtime safety gate")
            continue

        observations.append(Observation(candidate, metrics, "train"))
        front = pareto_front(observations)
        print(
            f"[trial {trial + 1:02d}] "
            f"accuracy={metrics.accuracy:.3f} "
            f"cost=${metrics.cost_usd:.5f} "
            f"latency={metrics.latency_ms:.0f}ms "
            f"pareto={len(front)}"
        )

    return observations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=12)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("harness-optimizer-results.json"),
    )
    args = parser.parse_args()

    command = os.environ.get("HARNESS_EVAL_COMMAND")
    if not args.demo and not command:
        raise SystemExit(
            "Set HARNESS_EVAL_COMMAND for a real evaluation, or use --demo."
        )

    base = load_config(args.config)
    violations = verify_candidate(base)
    if violations:
        raise SystemExit(
            "Base configuration is infeasible:\n- " + "\n- ".join(violations)
        )

    observations = optimize(
        base=base,
        budget=args.budget,
        warmup=args.warmup,
        seed=args.seed,
        demo=args.demo,
        evaluator_command=command,
    )
    front = pareto_front(observations)

    # Validation is deliberately separated from train optimization.
    results = {
        "evaluations": len(observations),
        "pareto_front": [
            {
                "metrics": vars(item.metrics),
                "config": item.config,
            }
            for item in front
        ],
    }
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\nWrote {len(front)} Pareto candidate(s) to {args.output}")
    print(
        "Promote only after rerunning these Pareto candidates against a held-out "
        "validation suite and ReplayAssertionEngine execution traces."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
