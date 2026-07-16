"""Comment 11: dedicated long-context management layer for Opus deep dives."""

from __future__ import annotations

import asyncio

import pytest

from app.services.substrate.context_manager import ContextManager, chunk_text
from app.services.substrate.workflow_models import ReasoningProfile


def test_chunk_text_paragraph_aware():
    text = "Para one line a.\n\nPara two line b.\n\nPara three line c."
    chunks = chunk_text(text, max_chars=40)
    assert len(chunks) >= 2
    # Reassembled (allowing overlap duplication) recovers all paragraphs.
    joined = "\n".join(chunks)
    assert "Para one line a." in joined
    assert "Para two line b." in joined
    assert "Para three line c." in joined


def test_chunk_text_force_split_giant_token():
    giant = "x" * 5000
    chunks = chunk_text(giant, max_chars=1000)
    assert len(chunks) > 1
    # Every char of the original is present across chunks (overlap may dup).
    assert giant.count("x") <= sum(c.count("x") for c in chunks)


def test_source_manifest_and_retrieval():
    mgr = ContextManager(token_budget=20000)
    mgr.add_source(source_id="s1", uri="file://a.md", text="Opus reasoning budget caching", kind="document")
    mgr.add_source(source_id="s2", uri="file://b.md", text="totally unrelated cat facts", kind="document")
    assert len(mgr._sources) == 2
    assert mgr.has_sources()

    results = mgr.retrieve("reasoning budget", k=4)
    assert results
    assert "reasoning" in results[0][1].lower()


def test_pin_survives_compaction():
    mgr = ContextManager(token_budget=20000)
    mgr.add_source(source_id="s1", uri="file://a.md", text="evidence must persist across compaction", kind="document")
    cids = [c for c in mgr._chunks if c.startswith("s1::")]
    assert cids
    for cid in cids:
        mgr.pin(cid)
    mgr.compact("summary of research", checkpoint="ck1")
    assert mgr._rolling_summary == "summary of research"
    assert mgr._compaction_checkpoint == "ck1"
    for cid in cids:
        assert cid in mgr._chunks


def test_build_plan_allocates_budget_and_renders():
    mgr = ContextManager(token_budget=2000)
    mgr.add_source(source_id="s1", uri="file://a.md", text="Opus reasoning budget caching tokens", kind="document")
    plan, rendered = mgr.build_plan("run-1", "node-1", query="reasoning", token_budget=2000)
    assert plan.run_id == "run-1"
    assert plan.token_budget == 2000
    assert plan.selected_chunk_ids
    assert "Retrieved context" in rendered
    payload = plan.as_event_payload()
    assert payload["run_id"] == "run-1"
    assert payload["selected_chunk_ids"] == plan.selected_chunk_ids


def test_record_context_event_persists_to_event_log(monkeypatch):
    import app.services.substrate.event_log as ev

    mgr = ContextManager(token_budget=2000)
    mgr.add_source(source_id="s1", uri="file://a.md", text="Opus reasoning budget caching tokens", kind="document")
    plan, _ = mgr.build_plan("run-1", "node-1", query="reasoning")

    captured = {}

    class FakeEventLog:
        async def append(self, db, run_id, events):
            captured["run_id"] = run_id
            captured["events"] = events

    monkeypatch.setattr(ev, "get_event_log", lambda: FakeEventLog())

    asyncio.get_event_loop().run_until_complete(mgr.record_context_event(None, "run-1", plan, node_id="node-1"))

    assert captured["run_id"] == "run-1"
    assert captured["events"][0]["type"] == "context.plan"
    assert captured["events"][0]["payload"]["run_id"] == "run-1"


# ── _handle_llm integration ──────────────────────────────────────────────


class _FakeEvent:
    def __init__(self, type, payload=None, sequence=0, actor=None):
        self.type = type
        self.payload = payload or {}
        self.sequence = sequence
        self.actor = actor


class _FakeEventLog:
    def __init__(self):
        self.events = []
        self.seq = 0

    async def append(self, db, run_id, events):
        for e in events:
            self.seq += 1
            self.events.append(_FakeEvent(e["type"], e.get("payload"), self.seq, e.get("actor")))

    async def get_events(self, db, run_id, from_sequence=0, to_sequence=None, limit=50):
        return [e for e in self.events if from_sequence <= e.sequence <= (to_sequence or 10**9)]

    async def get_latest_sequence(self, db, run_id):
        return self.seq

    async def find_by_idempotency_key(self, db, key):
        return None


class _FakeBudget:
    def remaining(self):
        return {"cost_usd": 10.0}


class _FakeBudgetEnforcer:
    def __init__(self):
        self.calls = []

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "success": True,
            "response": "deep answer",
            "model": kwargs.get("model_id", "unknown"),
            "provider": "fake",
            "cost": {"usd": 0.01, "input_tokens": 5, "output_tokens": 5},
        }


def _make_workflow():
    from app.services.substrate.workflow_models import NodeType, Workflow, WorkflowNode, WorkflowType

    node = WorkflowNode(
        id="n1",
        type=NodeType.LLM_CALL,
        title="deep dive",
        config={"prompt": "Summarize the Opus long-context research"},
        reasoning_profile=ReasoningProfile.DEEP,
    )
    wf = Workflow(id="wf1", type=WorkflowType.SOLO, title="wf", nodes=[node], user_id="u1")
    return wf, node


def test_handle_llm_persists_context_plan_for_deep_node(monkeypatch):
    import app.services.budget_enforcer as be
    import app.services.substrate.event_log as ev
    import app.services.substrate.node_executor as ne

    fake_log = _FakeEventLog()
    fake_enforcer = _FakeBudgetEnforcer()
    monkeypatch.setattr(ne, "get_event_log", lambda: fake_log)
    monkeypatch.setattr(ev, "get_event_log", lambda: fake_log)
    monkeypatch.setattr(be, "get_budget_enforcer", lambda: fake_enforcer)

    class _FakeExecutor:
        def check_circuit_breaker(self, **kwargs):
            return asyncio.sleep(0, result=(True, "ok"))

        def is_aborted(self, run_id):
            return False

    wf, node = _make_workflow()
    exec_ = ne.NodeExecutor(_FakeExecutor())

    async def run():
        exec_._context_manager("run-1").add_source(
            source_id="s1", uri="file://a.md", text="Opus reasoning budget caching tokens", kind="document"
        )
        return await exec_._handle_llm(None, node, {}, _FakeBudget(), "run-1", wf)

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result["success"] is True

    types = [e.type for e in fake_log.events]
    assert "context.plan" in types
    ctx_event = next(e for e in fake_log.events if e.type == "context.plan")
    assert ctx_event.payload["run_id"] == "run-1"
    assert ctx_event.payload["node_id"] == "n1"

    assert fake_enforcer.calls
    injected = " ".join(m.get("content", "") for call in fake_enforcer.calls for m in call.get("messages", []))
    assert "Long-context research window" in injected
    assert "Opus reasoning budget caching" in injected


def test_handle_llm_skips_context_when_no_sources(monkeypatch):
    import app.services.budget_enforcer as be
    import app.services.substrate.event_log as ev
    import app.services.substrate.node_executor as ne

    fake_log = _FakeEventLog()
    fake_enforcer = _FakeBudgetEnforcer()
    monkeypatch.setattr(ne, "get_event_log", lambda: fake_log)
    monkeypatch.setattr(ev, "get_event_log", lambda: fake_log)
    monkeypatch.setattr(be, "get_budget_enforcer", lambda: fake_enforcer)

    class _FakeExecutor:
        def check_circuit_breaker(self, **kwargs):
            return asyncio.sleep(0, result=(True, "ok"))

        def is_aborted(self, run_id):
            return False

    wf, node = _make_workflow()
    exec_ = ne.NodeExecutor(_FakeExecutor())

    async def run():
        return await exec_._handle_llm(None, node, {}, _FakeBudget(), "run-1", wf)

    result = asyncio.get_event_loop().run_until_complete(run())
    assert result["success"] is True
    assert "context.plan" not in [e.type for e in fake_log.events]
    injected = " ".join(m.get("content", "") for call in fake_enforcer.calls for m in call.get("messages", []))
    assert "Long-context research window" not in injected
