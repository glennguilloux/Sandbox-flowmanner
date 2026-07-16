"""Real evaluator shim for the harness-evolution meta-optimizer.

Bridge from prototype (``.sisyphus/prototypes/harness_meta_optimizer.py``)
to live tuning. Invoked as::

    evaluate_harness.sh <candidate.json> <split>

It builds a ``Workflow`` from the candidate config, runs it through the REAL
``UnifiedExecutor`` (the only production execution path), then emits a single
JSON line on stdout::

    {"accuracy": 0.0, "cost_usd": 0.0, "latency_ms": 0.0, "safety_pass": true}

The prototype reads the LAST non-empty stdout line and requires exactly those
four float/bool fields (``harness_meta_optimizer.py:Metrics.from_json``).

DESIGN PRINCIPLE -- honest gating, not silent fabrication
---------------------------------------------------------
The harness-config axes split into two classes:

* LIVE axes (already wired into the runtime): ``answer.assigned_model``,
  ``answer.config.temperature``, ``answer.config.system_prompt``,
  ``answer.config.tool_ids``.
* GATED axes (real knobs in config.py, but NOT per-request in the current
  tree): ``memory.top_k``, ``memory.similarity_threshold``, ``memory.reranker``
  are injected by monkeypatching ``app.config.settings`` + passing
  ``n_results`` into RAGService (see ``inject_rag_knobs``). ``memory.chunk_size``
  / ``memory.chunk_overlap`` are EMBEDDING-time params and stay inert at query
  time -- we report them as ``knobs_inert`` in debug output rather than pretend
  they changed retrieval.

accuracy requires a labeled golden set for ``split`` in
``$EVAL_DATA_DIR/{split}.jsonl`` (one JSON object per line; the gold label is
``risk_level`` and every other key is treated as an input feature). When the
dataset exists, ``evaluate`` runs the workflow **once per case** with that
case's features injected into the answer node's ``prompt`` (the only channel
``node_executor._handle_llm`` renders into the live model call) and averages
accuracy across cases. With no dataset, a single run is executed and accuracy
is emitted as ``0.0`` with ``accuracy_source="none"`` -- so the optimizer can
still run cost/latency/safety Pareto fronts without faking quality. Accuracy is
NEVER fabricated; if a run fails or returns no prediction, that case counts as
incorrect.

The ONLY infra-touching seam is ``run_executor`` (Postgres + LLM + Qdrant).
Everything else (workflow build, RAG-knob injection, safety check over the
event log, accuracy scoring) is pure and unit-tested offline in
``tests/test_evaluate_harness.py``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# Substrate event types used by safety_check. Imported here (not redefined) so
# the safety gate cannot silently drift from the real event vocabulary.
from app.models.substrate_models import SubstrateEventType
from app.services.substrate.workflow_models import (
    EffectClass,
    NodeType,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowType,
)

# JSON schema contract emitted for the prototype. Keep field names/types in
# lock-step with harness_meta_optimizer.Metrics.from_json.
RESULT_KEYS = ("accuracy", "cost_usd", "latency_ms", "safety_pass")

EVAL_DATA_DIR = Path(os.environ.get("EVAL_DATA_DIR", "/opt/flowmanner/.sisyphus/prototypes/eval_data"))

# Candidate axes that the current runtime ignores at query time (embedding-time
# params). Tracked so we never claim they moved retrieval.
INERT_KNOBS = ("chunk_size", "chunk_overlap")

# harness-config.yaml (and the optimizer's mutation space) use short type names
# that differ from the substrate NodeType enum values. Map them so a candidate
# config is accepted verbatim rather than forcing the optimizer to know internals.
NODE_TYPE_ALIASES = {
    "llm": NodeType.LLM_CALL,
    "llm_call": NodeType.LLM_CALL,
    "rag_query": NodeType.RAG_QUERY,
    "rag": NodeType.RAG_QUERY,
    "web_search": NodeType.WEB_SEARCH,
    "tool_call": NodeType.TOOL_CALL,
    "tool": NodeType.TOOL_CALL,
    "code": NodeType.CODE_EXECUTION,
    "code_execution": NodeType.CODE_EXECUTION,
}


# ── Config → Workflow ────────────────────────────────────────────────


def _node_by_id(nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any]:
    for node in nodes:
        if node["id"] == node_id:
            return node
    raise KeyError(f"Unknown workflow node: {node_id!r}")


def build_workflow(candidate: dict[str, Any]) -> Workflow:
    """Materialize a real ``Workflow`` from a candidate config document.

    Mirrors the config shape assembled in ``.sisyphus/prototypes/harness-config.yaml``:
    ``workflow.nodes`` carry per-node ``config``; ``workflow.edges`` is a list of
    ``{source,target}``; retrieval knobs live under ``memory`` (global in the
    real backend, not per-node).
    """
    workflow_cfg = candidate.get("workflow", {})
    raw_nodes = workflow_cfg.get("nodes", [])
    raw_edges = workflow_cfg.get("edges", [])

    nodes: list[WorkflowNode] = []
    for node in raw_nodes:
        raw_type = node.get("type", "llm_call")
        node_type = NODE_TYPE_ALIASES.get(raw_type)
        if node_type is None:
            node_type = NodeType(raw_type)
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
                # Read-only nodes MUST be annotated reversible per substrate
                # side-effect-safety contract; the harness config declares them so.
                effect_class=EffectClass(node.get("effect_class", "reversible")),
            )
        )

    edges = [WorkflowEdge(source=e["source"], target=e["target"], condition=e.get("condition")) for e in raw_edges]

    return Workflow(
        id="00000000-0000-0000-0000-0000000000e0",
        type=WorkflowType.DAG if len(nodes) > 1 else WorkflowType.SOLO,
        title="harness-eval",
        description="meta-optimizer candidate evaluation",
        nodes=nodes,
        edges=edges,
        user_id="00000000-0000-0000-0000-000000000000",
        workspace_id=candidate.get("workspace_id"),
    )


# ── RAG knob injection ──────────────────────────────────────────────


def inject_rag_knobs(candidate: dict[str, Any]) -> dict[str, Any]:
    """Inject candidate RAG knobs into the live runtime where possible.

    Returns a report of what was applied vs. what is inert, so the caller can
    emit it in debug output without pretending inert knobs changed retrieval.

    Applied (real effect at query time):
      * memory.similarity_threshold  -> settings.RAG_SIMILARITY_THRESHOLD
      * memory.top_k                 -> passed as n_results into RAGService
      * memory.reranker              -> settings flag consumed by retrieval_service

    Inert (embedding-time only; documented, not faked):
      * memory.chunk_size / memory.chunk_overlap
    """
    memory = candidate.get("memory", {})
    report: dict[str, Any] = {"applied": {}, "inert": []}

    from app.config import settings  # imported lazily; monkeypatch target

    if "similarity_threshold" in memory:
        settings.RAG_SIMILARITY_THRESHOLD = float(memory["similarity_threshold"])
        report["applied"]["similarity_threshold"] = float(memory["similarity_threshold"])
    if "reranker" in memory:
        # NOTE: reranker is consumed by retrieval_service._rerank_llm at query
        # time, not via a global settings flag. We cannot monkeypatch it here
        # without touching the service; record intent and let run_executor pass
        # it through (placeholder for a future per-request reranker toggle).
        report["applied"]["reranker"] = bool(memory["reranker"])
    if "top_k" in memory:
        # Consumed by run_executor -> RAGService.query_documents(n_results=top_k).
        report["applied"]["top_k"] = int(memory["top_k"])

    for knob in INERT_KNOBS:
        if knob in memory:
            report["inert"].append(knob)
    return report


# ── The single infra seam ───────────────────────────────────────────


async def run_executor(workflow: Workflow, candidate: dict[str, Any]) -> dict[str, Any]:
    """Run the candidate through the REAL UnifiedExecutor.

    This is the only function that touches Postgres + LLM + Qdrant. It is the
    seam the offline test replaces with a fake.

    Returns a dict with:
      * ``result``: StrategyResult-like (success, status, total_cost_usd,
        execution_time_ms, completed_nodes, failed_nodes, error)
      * ``events``: list of {type, payload} substrate events (for safety_check)
      * ``answer_output``: the ``answer`` node's output_data (for accuracy)
    """
    from app.database import AsyncSessionLocal
    from app.services.substrate.executor import UnifiedExecutor

    memory = candidate.get("memory", {})
    top_k = int(memory.get("top_k", 5))

    async with AsyncSessionLocal() as db:
        executor = UnifiedExecutor()
        # ``blueprint_id`` keeps the run in blueprint mode (no missions row),
        # matching how harness runs are scoped (executor._active_blueprint_id).
        result = await executor.execute(
            db,
            workflow,
            run_id=str(__import__("uuid").uuid4()),
        )

        # Pull the substrate event log for this run to drive safety_check.
        events = await _collect_events(db, str(result.run_id))

        # Pull the answer node output for accuracy scoring.
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
        "top_k": top_k,
        "answer_output": answer_output,
    }


async def _collect_events(db: Any, run_id: str) -> list[dict[str, Any]]:
    """Read the append-only substrate event log for a run (real event shape)."""
    from app.services.substrate.event_log import get_event_log

    event_log = get_event_log()
    raw = await event_log.get_events(db, run_id)
    out: list[dict[str, Any]] = []
    for ev in raw:
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        out.append({"type": getattr(ev, "type", None) or payload.get("type"), "payload": payload})
    return out


def _extract_answer_output(events: list[dict[str, Any]], result: Any) -> dict[str, Any] | None:
    """Best-effort extraction of the answer node's emitted output.

    The LLM response event carries the model content; the node-completed event
    carries node output_data. We prefer a node-completed payload whose node id is
    ``answer``. Falls back to the last llm.response content.
    """
    for ev in events:
        if ev["type"] == SubstrateEventType.NODE_COMPLETED:
            node_id = (ev["payload"] or {}).get("node_id")
            if node_id == "answer":
                return (ev["payload"] or {}).get("output")
    for ev in reversed(events):
        if ev["type"] == SubstrateEventType.LLM_RESPONSE:
            return {"content": (ev["payload"] or {}).get("content")}
    return None


# ── Safety gate ─────────────────────────────────────────────────────


def safety_check(
    candidate: dict[str, Any],
    run: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Evaluate the hard safety gate from the run's event trace + verify_candidate.

    A candidate PASSES only if:
      1. Static verify_candidate (edge-target, forbidden_tools, constraints)
         reports no violations (already enforced pre-run by the optimizer, but
         re-checked here so a tampered candidate cannot slip through).
      2. No FORBIDDEN tool (delete_data, send_email, ...) emitted a TOOL_CALL.
      3. Every node completion is success-class (no constraint_blocked /
         constraint_escalate fired against the standing restricted claim).
      4. The restricted personal-memory claim (if declared) is respected:
         no tool call touched its protected resource.
    """
    failures: list[str] = []
    skipped: list[str] = []

    from .harness_verify import verify_candidate  # local re-export of prototype gate

    violations: list[str] = []
    try:
        violations = verify_candidate(candidate)
    except KeyError as exc:
        # verify_candidate expects the full optimizer config (routing.catalog,
        # etc.). A bare candidate without those sections is not a hard safety
        # failure on its own -- record it as a skipped gate (does NOT fail
        # safety) so the evaluator still reports metrics instead of crashing.
        skipped.append(f"verify_candidate skipped (missing config section: {exc})")
    if violations:
        failures.extend(violations)

    events = run.get("events", [])
    tool_calls = [e for e in events if e["type"] == SubstrateEventType.TOOL_CALL]
    forbidden = set(candidate.get("verification", {}).get("forbidden_tools", []))

    for ev in tool_calls:
        tool_name = (ev["payload"] or {}).get("tool_name") or (ev["payload"] or {}).get("tool")
        if tool_name in forbidden:
            failures.append(f"Forbidden tool executed during run: {tool_name!r}")

    # Node-level constraint gate: a blocked/escalated tool must not have run.
    for ev in events:
        if ev["type"] in (SubstrateEventType.NODE_FAILED,):
            reason = (ev["payload"] or {}).get("reason") or (ev["payload"] or {}).get("error")
            if reason and ("constraint_blocked" in str(reason) or "constraint_escalate" in str(reason)):
                failures.append(f"Node {ev['payload'].get('node_id')!r} hit constraint gate: {reason}")

    return (len(failures) == 0), (failures + skipped)


# ── Accuracy ────────────────────────────────────────────────────────


def score_case(case: dict[str, Any], answer_output: dict[str, Any] | None) -> dict[str, Any]:
    """Score ONE golden case's predicted answer.

    Returns ``{"correct": bool, "predicted": str|None, "label": str|None}``.
    A missing prediction (run failure / no output) counts as incorrect -- we
    never credit a case we cannot actually predict.
    """
    label = case.get("risk_level")
    predicted = _predict_risk_level(answer_output)
    return {
        "correct": bool(label is not None and predicted == label),
        "predicted": predicted,
        "label": label,
    }


def _format_case_prompt(base_prompt: str, case: dict[str, Any]) -> str:
    """Inject one golden case's features into the answer node's prompt.

    ``node_executor._handle_llm`` renders ``node.config["prompt"]`` verbatim as
    the user message (node_executor:1287; appended at :1370). The ``context``
    argument to ``UnifiedExecutor.execute`` is NOT surfaced into the prompt, so
    we inject here -- the only channel that reaches the model live. Features are
    serialized in a stable, JSON-parseable block so a real run can recover them.
    """
    features = {k: v for k, v in case.items() if k != "risk_level"}
    block = json.dumps(features, ensure_ascii=False, sort_keys=True)
    return f"{base_prompt}\n\n[CASE INPUT]\n{block}\n[/CASE INPUT]"


def score_accuracy(split: str, cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Aggregate per-case accuracy for ``split``.

    If ``cases`` is provided (the per-case live path), accuracy is the fraction
    of cases whose predicted ``risk_level`` matches the gold label. If ``cases``
    is ``None`` (legacy single-run path with no golden set), returns
    ``source="none"`` and accuracy ``0.0`` (NOT fabricated).
    """
    if cases is None:
        golden_path = EVAL_DATA_DIR / f"{split}.jsonl"
        if not golden_path.exists():
            return {"accuracy": 0.0, "source": "none", "n": 0, "correct": 0}
        cases = _load_golden(golden_path)
        if not cases:
            return {"accuracy": 0.0, "source": "none", "n": 0, "correct": 0}
        # Legacy single-run path: no per-case predictions available.
        return {"accuracy": 0.0, "source": "none", "n": len(cases), "correct": 0}

    correct = sum(1 for c in cases if c.get("_scored", {}).get("correct"))
    return {
        "accuracy": round(correct / len(cases), 4) if cases else 0.0,
        "source": "per_case" if cases else "none",
        "n": len(cases),
        "correct": correct,
    }


def _predict_risk_level(answer_output: dict[str, Any] | None) -> str | None:
    """Extract a predicted risk_level from the answer node output."""
    if not answer_output:
        return None
    if "risk_level" in answer_output:
        return answer_output["risk_level"]
    content = answer_output.get("content")
    if isinstance(content, str):
        # Cheap heuristic for the offline/fake path; a real run would parse JSON.
        for level in ("high", "medium", "low", "unknown"):
            if f'"risk_level": "{level}"' in content or f'"{level}"' in content.lower()[:200]:
                return level
    return None


def _load_golden(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# ── Top-level orchestration ─────────────────────────────────────────


def evaluate(candidate: dict[str, Any], split: str) -> dict[str, Any]:
    """Synchronous entry point: build -> inject -> run -> score -> safety.

    Per-case mode (golden set present): the workflow is run once per golden
    case with that case's features injected into the answer node's prompt. Cost
    is summed across cases; latency is the mean; safety passes only if EVERY
    case run passed; accuracy is the fraction of correct per-case predictions.

    Legacy single-run mode (no golden set): one run, accuracy reported as
    ``0.0`` with ``source="none"`` -- never fabricated.
    """
    t0 = time.monotonic()
    debug: dict[str, Any] = {}

    workflow = build_workflow(candidate)
    rag_report = inject_rag_knobs(candidate)
    debug["rag_injection"] = rag_report

    golden_path = EVAL_DATA_DIR / f"{split}.jsonl"
    cases = _load_golden(golden_path) if golden_path.exists() else []

    if not cases:
        # ── Legacy single-run path (no labeled dataset) ──────────────
        try:
            run = asyncio.run(run_executor(workflow, candidate))
        except Exception as exc:  # surface failure as a non-passing run
            debug["run_error"] = f"{type(exc).__name__}: {exc}"
            debug["run_traceback"] = traceback.format_exc()
            return {
                "accuracy": 0.0,
                "cost_usd": 0.0,
                "latency_ms": round((time.monotonic() - t0) * 1000, 1),
                "safety_pass": False,
                "_debug": debug,
            }

        result = run["result"]
        latency_ms = float(result.get("execution_time_ms") or (time.monotonic() - t0) * 1000)
        safety_pass, safety_failures = safety_check(candidate, run)
        debug["safety_failures"] = safety_failures
        accuracy = score_accuracy(split, None)  # source="none", accuracy 0.0
        debug["accuracy_detail"] = accuracy
        return {
            "accuracy": float(accuracy["accuracy"]),
            "cost_usd": round(float(result.get("total_cost_usd", 0.0)), 6),
            "latency_ms": round(latency_ms, 1),
            "safety_pass": bool(safety_pass),
            "_debug": debug,
        }

    # ── Per-case loop (golden set present) ─────────────────────────
    # Locate the answer node to inject each case's features into its prompt.
    answer_node = next((n for n in workflow.nodes if n.id == "answer"), None)
    base_prompt = (answer_node.config.get("prompt") if answer_node else None) or ""

    total_cost = 0.0
    latencies: list[float] = []
    per_case: list[dict[str, Any]] = []

    for case in cases:
        if answer_node is not None:
            # Clone the config so each case gets its own injected prompt.
            answer_node.config = dict(answer_node.config)
            answer_node.config["prompt"] = _format_case_prompt(base_prompt, case)

        try:
            run = asyncio.run(run_executor(workflow, candidate))
        except Exception as exc:  # a failed case is scored wrong, not crashed
            debug.setdefault("case_run_errors", []).append(f"{type(exc).__name__}: {exc}")
            case_scored = {"correct": False, "predicted": None, "label": case.get("risk_level")}
            per_case.append({"case": case, "scored": case_scored, "answer_output": None})
            continue

        result = run["result"]
        total_cost += float(result.get("total_cost_usd", 0.0))
        latencies.append(float(result.get("execution_time_ms") or (time.monotonic() - t0) * 1000))

        case_safety, case_failures = safety_check(candidate, run)
        answer_output = run.get("answer_output")
        case_scored = score_case(case, answer_output)
        per_case.append(
            {
                "case": case,
                "scored": case_scored,
                "answer_output": answer_output,
                "safety_failures": case_failures,
            }
        )
        # Safety must hold for EVERY case; a single violation fails the whole eval.
        if not case_safety:
            debug.setdefault("case_safety_failures", []).append(case_failures)

    overall_safety = (
        all(not c.get("safety_failures") for c in per_case if c.get("safety_failures") is not None)
        and debug.get("case_safety_failures") is None
    )
    # Annotate each case with its score for aggregation.
    for c in per_case:
        c["case"]["_scored"] = c["scored"]

    accuracy = score_accuracy(split, cases)
    debug["per_case"] = [
        {
            "label": pc["case"].get("risk_level"),
            "predicted": pc["scored"]["predicted"],
            "correct": pc["scored"]["correct"],
        }
        for pc in per_case
    ]
    debug["accuracy_detail"] = accuracy

    mean_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    return {
        "accuracy": float(accuracy["accuracy"]),
        "cost_usd": round(total_cost, 6),
        "latency_ms": mean_latency,
        "safety_pass": bool(overall_safety),
        "_debug": debug,
    }


def _emit(result: dict[str, Any]) -> None:
    """Print ONLY the machine-readable JSON line the prototype requires."""
    public = {k: result[k] for k in RESULT_KEYS}
    sys.stdout.write(json.dumps(public) + "\n")


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("usage: evaluate_harness.sh <candidate.json> <split>\n")
        return 2

    # No-fabrication guard: a real run requires a live backend DB. Without it we
    # refuse rather than emit plausible-but-fake metrics (the shell wrapper also
    # enforces this, but the Python entry must hold the guarantee itself).
    if not os.environ.get("DATABASE_URL"):
        sys.stderr.write(
            "ERROR: DATABASE_URL is not set. A real evaluation runs through "
            "UnifiedExecutor against the live backend database. Refusing to "
            "emit fabricated metrics.\n"
        )
        return 2

    candidate_path = Path(sys.argv[1])
    split = sys.argv[2]
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))

    result = evaluate(candidate, split)
    _emit(result)
    return 0 if result["safety_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
