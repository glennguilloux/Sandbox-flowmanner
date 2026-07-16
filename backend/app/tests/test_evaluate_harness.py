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
def test_accuracy_scores_against_golden(golden_dir):
    # fake run predicts "high"; golden is 2x "high" -> accuracy 1.0
    out = eh.evaluate({"workflow": {"nodes": [], "edges": []}}, "train")
    assert out["accuracy"] == 1.0
    assert out["_debug"]["accuracy_detail"]["source"] == "exact"


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
