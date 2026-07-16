"""Offline test for the evaluator shim.

No Postgres / LLM / Qdrant required: we replace ONLY the ``run_executor``
infra seam with an async fake that returns the same shape a real
``UnifiedExecutor.execute()`` result + event log produces. Everything else
(workflow build, RAG-knob injection, safety gate, accuracy scoring, JSON
emission) is the REAL code path.

This proves the bridge is wired correctly and that a candidate's live axes
(model / temperature / system_prompt / tool_ids) and safety invariants are
scored honestly -- independent of whether the optimizer is currently fed
real LLM outputs.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from app.models.substrate_models import SubstrateEventType
from app.services.substrate import evaluate_harness as eh
from app.services.substrate.workflow_models import StrategyResult

# ── Async fake of the single infra seam ─────────────────────────────


def _make_fake_run(
    success: bool,
    *,
    forbidden_tool: bool = False,
    blocked: bool = False,
    risk_level: str | None = "high",
    cost: float = 0.03,
    latency_ms: float = 1200.0,
):
    events: list[dict] = [
        {"type": SubstrateEventType.MISSION_STARTED, "payload": {"title": "harness-eval"}},
        {"type": SubstrateEventType.LLM_RESPONSE, "payload": {"content": f'{{"risk_level": "{risk_level}"}}'}},
        {
            "type": SubstrateEventType.NODE_COMPLETED,
            "payload": {"node_id": "answer", "output": {"risk_level": risk_level}},
        },
    ]
    if forbidden_tool:
        events.append({"type": SubstrateEventType.TOOL_CALL, "payload": {"tool_name": "delete_data"}})
    if blocked:
        events.append(
            {
                "type": SubstrateEventType.NODE_FAILED,
                "payload": {"node_id": "answer", "reason": "constraint_blocked: production_database"},
            }
        )

    result = StrategyResult(
        success=success,
        status="completed" if success else "failed",
        run_id="run-fake-0000",
        total_cost_usd=cost,
        execution_time_ms=latency_ms,
        completed_nodes=["retrieve", "answer"] if success else [],
        failed_nodes=[] if success else ["answer"],
    )
    return {"result": result.model_dump(), "events": events, "top_k": 5, "answer_output": {"risk_level": risk_level}}


async def _fake_run_executor(workflow, candidate):
    # The fake is success by default; a test can monkeypatch this to vary.
    return _make_fake_run(True)


@pytest.fixture
def _patch_runner():
    with mock.patch.object(eh, "run_executor", _fake_run_executor):
        yield


# ── Golden dataset fixture ──────────────────────────────────────────


@pytest.fixture
def golden_dir(tmp_path: Path, monkeypatch):
    data = tmp_path / "eval_data"
    data.mkdir()
    (data / "train.jsonl").write_text(
        json.dumps({"risk_level": "high"}) + "\n" + json.dumps({"risk_level": "high"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(eh, "EVAL_DATA_DIR", data)
    return data


# ── Tests ───────────────────────────────────────────────────────────


def test_build_workflow_maps_candidate_axes():
    candidate = {
        "workflow": {
            "nodes": [
                {"id": "retrieve", "type": "rag_query", "effect_class": "reversible"},
                {
                    "id": "answer",
                    "type": "llm",
                    "assigned_model": "deepseek-v4-flash",
                    "config": {"temperature": 0.2, "system_prompt": "x", "tool_ids": ["web_search"]},
                    "effect_class": "reversible",
                },
            ],
            "edges": [{"source": "retrieve", "target": "answer"}],
        }
    }
    wf = eh.build_workflow(candidate)
    assert wf.type.value == "dag"
    answer = wf.node_map["answer"]
    assert answer.assigned_model == "deepseek-v4-flash"
    assert answer.config["model_preference"] == "deepseek-v4-flash"
    assert answer.config["temperature"] == 0.2
    assert answer.config["tool_ids"] == ["web_search"]


def test_inject_rag_knobs_applies_live_and_reports_inert():
    candidate = {
        "memory": {
            "top_k": 8,
            "similarity_threshold": 0.65,
            "reranker": False,
            "chunk_size": 1500,
            "chunk_overlap": 240,
        }
    }
    report = eh.inject_rag_knobs(candidate)
    # top_k is captured for n_results pass-through; similarity/reranker applied to settings
    assert report["applied"]["similarity_threshold"] == 0.65
    assert report["applied"]["reranker"] is False
    assert report["applied"]["top_k"] == 8
    # embedding-time knobs are reported inert, never faked as live
    assert "chunk_size" in report["inert"]
    assert "chunk_overlap" in report["inert"]


@pytest.mark.usefixtures("_patch_runner")
def test_safety_pass_clean_run():
    candidate = {
        "verification": {"forbidden_tools": ["delete_data", "send_email"]},
        "workflow": {"nodes": [{"id": "answer", "type": "llm", "effect_class": "reversible"}], "edges": []},
    }
    out = eh.evaluate(candidate, "train")
    assert out["safety_pass"] is True
    assert out["cost_usd"] == 0.03
    assert out["latency_ms"] == 1200.0


@pytest.mark.usefixtures("_patch_runner")
def test_safety_fail_forbidden_tool():
    candidate = {
        "verification": {"forbidden_tools": ["delete_data"]},
        "workflow": {"nodes": [{"id": "answer", "type": "llm", "effect_class": "reversible"}], "edges": []},
    }

    async def _bad(workflow, c):
        return _make_fake_run(True, forbidden_tool=True)

    with mock.patch.object(eh, "run_executor", _bad):
        out = eh.evaluate(candidate, "train")
    assert out["safety_pass"] is False


@pytest.mark.usefixtures("_patch_runner")
def test_safety_fail_constraint_blocked():
    candidate = {
        "verification": {
            "forbidden_tools": [],
            "personal_memory_claim_constraints": [
                {
                    "claim_type": "constraint",
                    "object": {"action": "block", "resource": "production_database"},
                    "sensitivity": "restricted",
                    "scope": "workspace",
                }
            ],
        },
        "workflow": {"nodes": [{"id": "answer", "type": "llm", "effect_class": "reversible"}], "edges": []},
    }

    async def _blocked(workflow, c):
        return _make_fake_run(False, blocked=True)

    with mock.patch.object(eh, "run_executor", _blocked):
        out = eh.evaluate(candidate, "train")
    assert out["safety_pass"] is False


@pytest.mark.usefixtures("_patch_runner")
def test_accuracy_scores_per_case_against_golden(golden_dir):
    # Per-case mode: fake run predicts "high" for each case; golden is 2x "high"
    # -> every case correct -> accuracy 1.0, source "per_case".
    out = eh.evaluate({"workflow": {"nodes": [], "edges": []}}, "train")
    assert out["accuracy"] == 1.0
    assert out["_debug"]["accuracy_detail"]["source"] == "per_case"
    assert out["_debug"]["accuracy_detail"]["n"] == 2
    assert out["_debug"]["accuracy_detail"]["correct"] == 2


@pytest.mark.usefixtures("_patch_runner")
def test_per_case_injects_features_and_scores_per_case(golden_dir):
    # The golden set carries input features (minus the gold label, which must
    # NOT enter the prompt). Prove per-case features are injected into the
    # answer node prompt, and that accuracy is aggregated PER CASE (a runner
    # that always predicts one label is right for exactly the matching cases).
    captured: list[str] = []

    async def _capture_runner(workflow, candidate):
        answer = next((n for n in workflow.nodes if n.id == "answer"), None)
        captured.append((answer.config.get("prompt") if answer else "") or "")
        return _make_fake_run(True, risk_level="high")

    data = golden_dir
    (data / "train.jsonl").write_text(
        json.dumps({"risk_level": "high", "tenure_days": 10})
        + "\n"
        + json.dumps({"risk_level": "low", "tenure_days": 900})
        + "\n",
        encoding="utf-8",
    )
    candidate = {
        "workflow": {
            "nodes": [{"id": "answer", "type": "llm", "config": {"prompt": "BASE"}, "effect_class": "reversible"}],
            "edges": [],
        }
    }

    with mock.patch.object(eh, "run_executor", _capture_runner):
        out = eh.evaluate(candidate, "train")

    # Each case's FEATURES (tenure_days) were injected; the gold label was NOT.
    assert len(captured) == 2
    assert '"tenure_days": 10' in captured[0]
    assert '"tenure_days": 900' in captured[1]
    assert "BASE" in captured[0]
    assert "BASE" in captured[1]
    assert '"risk_level"' not in captured[0]
    assert '"risk_level"' not in captured[1]

    # Runner always predicts "high" against {high, low} -> exactly 1 correct -> 0.5.
    assert out["accuracy"] == 0.5
    assert out["_debug"]["accuracy_detail"]["source"] == "per_case"
    assert out["_debug"]["accuracy_detail"]["n"] == 2
    assert out["_debug"]["accuracy_detail"]["correct"] == 1
    # Per-case labels were the gold labels, predictions the runner's constant.
    assert [pc["label"] for pc in out["_debug"]["per_case"]] == ["high", "low"]
    assert [pc["predicted"] for pc in out["_debug"]["per_case"]] == ["high", "high"]


@pytest.mark.usefixtures("_patch_runner")
def test_per_case_safety_fails_whole_eval_on_any_case(golden_dir):
    # Per-case mode: if ANY case run trips the safety gate, the entire eval's
    # safety_pass is False (accuracy still reported for the other cases).
    data = golden_dir
    (data / "train.jsonl").write_text(
        json.dumps({"risk_level": "high"}) + "\n" + json.dumps({"risk_level": "low"}) + "\n",
        encoding="utf-8",
    )
    candidate = {
        "verification": {"forbidden_tools": ["delete_data"]},
        "workflow": {"nodes": [{"id": "answer", "type": "llm", "effect_class": "reversible"}], "edges": []},
    }

    calls = {"n": 0}

    async def _second_case_forbidden(workflow, c):
        calls["n"] += 1
        # Trip the gate only on the second case; the first stays clean.
        return _make_fake_run(True, forbidden_tool=(calls["n"] == 2))

    with mock.patch.object(eh, "run_executor", _second_case_forbidden):
        out = eh.evaluate(candidate, "train")
    assert out["safety_pass"] is False

    # Two cases, each fake run costs 0.03 / 1200ms -> sum 0.06 / mean 1200.
    out = eh.evaluate({"workflow": {"nodes": [], "edges": []}}, "train")
    assert out["cost_usd"] == 0.06
    assert out["latency_ms"] == 1200.0
    assert out["safety_pass"] is True


@pytest.mark.usefixtures("_patch_runner")
def test_accuracy_none_without_golden():
    # No EVAL_DATA_DIR set to a real dir -> source none, accuracy 0.0 (not faked)
    with mock.patch.object(eh, "EVAL_DATA_DIR", Path("/nonexistent/eval_data_xyz")):
        out = eh.evaluate({"workflow": {"nodes": [], "edges": []}}, "val")
    assert out["accuracy"] == 0.0
    assert out["_debug"]["accuracy_detail"]["source"] == "none"


def test_emit_writes_only_required_json_line(capsys):
    eh._emit({"accuracy": 0.5, "cost_usd": 0.01, "latency_ms": 10.0, "safety_pass": True, "_debug": {"x": 1}})
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert set(parsed.keys()) == {"accuracy", "cost_usd", "latency_ms", "safety_pass"}
    assert parsed["safety_pass"] is True


@pytest.mark.usefixtures("_patch_runner")
def test_invalid_workflow_rejected_by_safety_gate():
    # dangling edge -> verify_candidate fails -> safety_pass False
    candidate = {
        "routing": {"catalog": [{"id": "deepseek-v4-flash", "in": 0.14, "out": 0.28}]},
        "verification": {"edge_target_validation": {"reject_dangling_edges": True}},
        "workflow": {
            "nodes": [
                {"id": "answer", "type": "llm", "assigned_model": "deepseek-v4-flash", "effect_class": "reversible"}
            ],
            "edges": [{"source": "ghost", "target": "answer"}],
        },
    }
    out = eh.evaluate(candidate, "train")
    assert out["safety_pass"] is False


# ── Per-case contract (Card C) ─────────────────────────────────────
#
# Locks the exact aggregate semantics of the per-case loop in
# evaluate_harness.evaluate (evaluate_harness.py:480-548):
#   * the workflow runs ONCE PER CASE, features injected into the answer node
#     prompt via _format_case_prompt (the gold label risk_level is NEVER leaked)
#   * cost is SUMMED across cases; latency is the MEAN
#   * safety_pass is True only when EVERY case run passes the gate
#   * accuracy is correct/total, where a missing/wrong prediction counts WRONG
#
# Uses the same run_executor seam as the rest of this module (monkeypatch
# eh.run_executor) and a per-case fake that returns a prediction keyed on a
# stable case identity so correct/incorrect counting is deterministic.


def _write_golden_cases(path: Path, cases: list[dict[str, Any]]) -> None:
    text = "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n"
    path.write_text(text, encoding="utf-8")


class TestPerCaseContract:
    """Offline lock on the per-case aggregation contract (no live infra)."""

    # 2 high + 2 low golden cases. Stable identity via "id" so the fake
    # executor can map a case -> its prediction deterministically.
    GOLDEN = [
        {"id": "c1", "risk_level": "high", "tenure_days": 12, "logins_30d": 3},
        {"id": "c2", "risk_level": "high", "tenure_days": 20, "logins_30d": 1},
        {"id": "c3", "risk_level": "low", "tenure_days": 880, "logins_30d": 41},
        {"id": "c4", "risk_level": "low", "tenure_days": 640, "logins_30d": 22},
    ]

    @pytest.fixture
    def golden(self, tmp_path: Path, monkeypatch):
        data = tmp_path / "eval_data"
        data.mkdir()
        _write_golden_cases(data / "train.jsonl", self.GOLDEN)
        monkeypatch.setattr(eh, "EVAL_DATA_DIR", data)
        return data

    def _runner_predicting(self, predictions: dict[str, Any], *, cost=0.03, latency_ms=1200.0):
        """Build a fake run_executor that returns answer_output[risk_level]
        from the case's id using ``predictions`` (a case-id -> predicted level
        map). Captures the injected prompt per case."""
        captured: list[str] = []

        async def _fake(workflow, candidate):
            answer = next((n for n in workflow.nodes if n.id == "answer"), None)
            captured.append((answer.config.get("prompt") if answer else "") or "")
            # Resolve the case identity by scanning the injected prompt for id.
            case_id = None
            for c in self.GOLDEN:
                if f'"id": {json.dumps(c["id"])}' in captured[-1] or f'"id": "{c["id"]}"' in captured[-1]:
                    case_id = c["id"]
                    break
            predicted = predictions.get(case_id) if case_id else None
            return _make_fake_run(True, risk_level=predicted, cost=cost, latency_ms=latency_ms)

        return _fake, captured

    def test_per_case_accuracy_is_correct_over_total(self, golden):
        # Predictor gets 3/4 right: high, high, low, high (last low misclassified).
        predictions = {"c1": "high", "c2": "high", "c3": "low", "c4": "high"}
        runner, _captured = self._runner_predicting(predictions)
        with mock.patch.object(eh, "run_executor", runner):
            out = eh.evaluate(
                {
                    "workflow": {
                        "nodes": [
                            {"id": "answer", "type": "llm", "config": {"prompt": "BASE"}, "effect_class": "reversible"}
                        ],
                        "edges": [],
                    }
                },
                "train",
            )
        assert out["accuracy"] == pytest.approx(3 / 4)
        detail = out["_debug"]["accuracy_detail"]
        assert detail["source"] == "per_case"
        assert detail["n"] == 4
        assert detail["correct"] == 3

    def test_per_case_cost_summed_latency_mean(self, golden):
        # Distinct per-case cost/latency so SUM vs MEAN are observable.
        predictions = {"c1": "high", "c2": "high", "c3": "low", "c4": "low"}
        # Vary cost/latency per case by index.
        costs = [0.10, 0.20, 0.30, 0.40]
        latencies = [1000.0, 2000.0, 3000.0, 4000.0]

        async def _fake(workflow, candidate):
            answer = next((n for n in workflow.nodes if n.id == "answer"), None)
            prompt = (answer.config.get("prompt") if answer else "") or ""
            case_id = None
            for c in self.GOLDEN:
                if f'"id": "{c["id"]}"' in prompt or f'"id": {json.dumps(c["id"])}' in prompt:
                    case_id = c["id"]
                    break
            idx = {"c1": 0, "c2": 1, "c3": 2, "c4": 3}[case_id]
            return _make_fake_run(True, risk_level=predictions[case_id], cost=costs[idx], latency_ms=latencies[idx])

        with mock.patch.object(eh, "run_executor", _fake):
            out = eh.evaluate(
                {
                    "workflow": {
                        "nodes": [
                            {"id": "answer", "type": "llm", "config": {"prompt": "BASE"}, "effect_class": "reversible"}
                        ],
                        "edges": [],
                    }
                },
                "train",
            )
        assert out["cost_usd"] == pytest.approx(sum(costs))
        assert out["latency_ms"] == pytest.approx(sum(latencies) / len(latencies))

    def test_per_case_safety_true_only_when_every_case_safe(self, golden):
        # A candidate must carry a routing.catalog + answer.assigned_model so
        # the static verify_candidate gate clears (a missing catalog raises
        # KeyError -> recorded as a *skip*, which evaluate() still counts as a
        # non-empty safety_failures list and fails overall_safety). With a
        # valid candidate, safety_pass is genuinely True only when every case
        # run is clean.
        candidate = {
            "routing": {"catalog": [{"id": "deepseek-v4-flash", "in": 0.14, "out": 0.28}]},
            "verification": {
                "forbidden_tools": ["delete_data"],
                "edge_target_validation": {"reject_dangling_edges": True},
            },
            "workflow": {
                "nodes": [
                    {
                        "id": "answer",
                        "type": "llm",
                        "assigned_model": "deepseek-v4-flash",
                        "config": {"prompt": "BASE"},
                        "effect_class": "reversible",
                    }
                ],
                "edges": [],
            },
        }
        predictions = {"c1": "high", "c2": "high", "c3": "low", "c4": "low"}

        # All cases safe -> safety_pass True.
        calls = {"n": 0}

        async def _all_safe(workflow, c):
            calls["n"] += 1
            return _make_fake_run(True, risk_level=predictions.get(self.GOLDEN[calls["n"] - 1]["id"]))

        with mock.patch.object(eh, "run_executor", _all_safe):
            out = eh.evaluate(candidate, "train")
        assert out["safety_pass"] is True
        assert out["accuracy"] == 1.0  # 4/4 correct

        # Third case trips the gate -> whole-eval safety_pass False, but the
        # other cases are still scored (accuracy still aggregated).
        calls = {"n": 0}

        async def _one_forbidden(workflow, c):
            calls["n"] += 1
            idx = calls["n"] - 1
            return _make_fake_run(True, risk_level=predictions.get(self.GOLDEN[idx]["id"]), forbidden_tool=(idx == 2))

        with mock.patch.object(eh, "run_executor", _one_forbidden):
            out = eh.evaluate(candidate, "train")
        assert out["safety_pass"] is False
        assert out["accuracy"] == 1.0  # scoring is independent of safety gate

    def test_gold_label_never_injected_into_prompt(self, golden):
        # The injected prompt must carry the case features but NEVER the
        # gold risk_level key. This is the anti-leakage contract that keeps
        # accuracy honest (the label cannot be memorized from the prompt).
        predictions = {"c1": "high", "c2": "high", "c3": "low", "c4": "low"}
        runner, captured = self._runner_predicting(predictions)
        with mock.patch.object(eh, "run_executor", runner):
            eh.evaluate(
                {
                    "workflow": {
                        "nodes": [
                            {"id": "answer", "type": "llm", "config": {"prompt": "BASE"}, "effect_class": "reversible"}
                        ],
                        "edges": [],
                    }
                },
                "train",
            )
        assert len(captured) == 4
        for prompt in captured:
            # Features present, base prompt preserved.
            assert "BASE" in prompt
            assert "[CASE INPUT]" in prompt
            assert '"tenure_days"' in prompt
            assert '"logins_30d"' in prompt
            # The gold label key must NOT appear anywhere in the prompt.
            assert "risk_level" not in prompt

    def test_missing_prediction_counts_wrong(self, golden):
        # A runner that returns no risk_level for half the cases -> those
        # cases count WRONG (never credited). 2 predicted correct, 2 missing.
        predictions = {"c1": "high", "c2": "high", "c3": None, "c4": None}
        runner, _captured = self._runner_predicting(predictions)
        with mock.patch.object(eh, "run_executor", runner):
            out = eh.evaluate(
                {
                    "workflow": {
                        "nodes": [
                            {"id": "answer", "type": "llm", "config": {"prompt": "BASE"}, "effect_class": "reversible"}
                        ],
                        "edges": [],
                    }
                },
                "train",
            )
        assert out["accuracy"] == pytest.approx(2 / 4)
