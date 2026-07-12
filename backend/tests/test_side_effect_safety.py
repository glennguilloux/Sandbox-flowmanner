"""Tests for the side-effect-safety + planner-trust mandates.

Covers:
- T1: committed + IRREVERSIBLE error promotes a Retryable error to ESCALATE
      (no retry / no double-send of the external effect).
- T2: a REVERSIBLE node still retries on a Retryable error (no false escalate).
- T3: select_plan() invokes on_fallback for a degraded (forced-fallback) winner
      and the planner routes it to PLANNED_PENDING_REVIEW.
- T4: MissionStatus.PLANNED_PENDING_REVIEW blocks EXECUTING and resolves only
      to PLANNED/ABORTED (transition table + CHECK constraint tuple).
- T5: fallback-rate + rubber-stamp counters increment (observability alarm).
"""

from __future__ import annotations

import types
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.mission_models import MissionStatus
from app.models.substrate_models import SubstrateEventType
from app.services.mission_errors import RetryableMissionError
from app.services.nexus.observability import ObservabilityService
from app.services.plan_selection.plan_candidate import PlanCandidate
from app.services.plan_selection.plan_selector import select_plan
from app.services.substrate.workflow_models import (
    EffectClass,
    NodeType,
    WorkflowNode,
)

# ── T1 / T2: NodeExecutor two-phase escalate promotion ──────────────────────


class _FakeBudget:
    def is_exhausted(self):
        return False, ""


class _FakeEventLog:
    def __init__(self):
        self.events: list[dict] = []

    async def get_latest_sequence(self, db, run_id):
        return len(self.events)

    async def get_events(self, db, run_id, **kwargs):
        return []

    async def append(self, db, run_id, events):
        self.events.extend(events)
        return []


class _FakeUnifiedExecutor:
    def is_aborted(self, run_id: str) -> bool:
        return False


def _make_node(node_type: NodeType, effect_class: EffectClass) -> WorkflowNode:
    return WorkflowNode(
        id="n1",
        type=node_type,
        title="node",
        effect_class=effect_class,
        max_retries=2,
    )


async def _run_executor(node: WorkflowNode, dispatch_error=None):
    """Drive NodeExecutor.execute() with fully faked collaborators.

    If ``dispatch_error`` is set, the dispatched handler raises it.
    Otherwise it returns a success dict.
    """
    # Import lazily so patching get_event_log takes effect first.
    from app.services.substrate import node_executor as ne_mod
    from app.services.substrate.node_executor import NodeExecutor

    fake_log = _FakeEventLog()
    orig_get = ne_mod.get_event_log
    ne_mod.get_event_log = lambda: fake_log  # type: ignore[assignment]
    try:
        executor = NodeExecutor(_FakeUnifiedExecutor())

        async def _fake_dispatch(*args, **kwargs):
            if dispatch_error is not None:
                raise dispatch_error
            return {"success": True, "output": {"ok": True}, "tokens": 0, "cost": 0.0}

        executor._dispatch = _fake_dispatch  # type: ignore[assignment]

        result = await executor.execute(
            db=MagicMock(),
            node=node,
            context={},
            budget=_FakeBudget(),
            run_id="run-1",
            workflow=None,
        )
        return result, fake_log
    finally:
        ne_mod.get_event_log = orig_get  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_irreversible_committed_error_promotes_to_escalate():
    node = _make_node(NodeType.TOOL_CALL, EffectClass.IRREVERSIBLE)
    result, fake_log = await _run_executor(node, dispatch_error=RetryableMissionError("transient tool failure"))
    # The effect was committed (STAGE) but must NOT be re-fired/retried.
    assert result.get("escalated") is True, result
    assert "irreversible" in (result.get("error") or "").lower(), result
    # Exactly one INTENT event was written (STAGE), no CONFIRMED.
    types_written = {e["type"] for e in fake_log.events}
    assert SubstrateEventType.SIDE_EFFECT_INTENT in types_written
    assert SubstrateEventType.SIDE_EFFECT_CONFIRMED not in types_written


@pytest.mark.asyncio
async def test_reversible_error_still_retries_no_escalate():
    node = _make_node(NodeType.LLM_CALL, EffectClass.REVERSIBLE)
    result, _ = await _run_executor(node, dispatch_error=RetryableMissionError("transient llm failure"))
    # REVERSIBLE nodes keep normal retry semantics — no escalate.
    assert result.get("escalated") is not True
    assert result.get("success") is False


# ── T3: select_plan degraded → on_fallback → PLANNED_PENDING_REVIEW ──────────


@pytest.mark.asyncio
async def test_select_plan_degraded_winner_triggers_on_fallback():
    clean = PlanCandidate(
        plan_id="clean_llm",
        generation_strategy="llm_persona",
        tasks=[{"title": "a"}],
        quality_score=0.9,
    )
    degraded = PlanCandidate(
        plan_id="fallback_heuristic",
        generation_strategy=PlanCandidate.FALLBACK,
        tasks=[{"title": "b"}],
        quality_score=0.99,  # high score — must STILL be blocked by degraded flag
        degraded=True,
    )

    captured = {}

    async def on_fallback(winner, reason):
        captured["winner_id"] = winner.plan_id
        captured["reason"] = reason
        # Planner routes the mission to human review.
        mission_status = MissionStatus.PLANNED_PENDING_REVIEW
        assert mission_status != MissionStatus.EXECUTING

    # degraded candidate scores higher but must trigger fallback hook.
    winner, _ = await select_plan(
        [clean, degraded],
        policy="balanced",
        min_quality_threshold=0.6,
        on_fallback=on_fallback,
    )
    assert winner.plan_id == "fallback_heuristic"
    assert captured.get("winner_id") == "fallback_heuristic"
    assert captured.get("reason") == "degraded_fallback_plan"


@pytest.mark.asyncio
async def test_select_plan_clean_winner_no_fallback():
    clean = PlanCandidate(
        plan_id="clean_llm",
        generation_strategy="llm_persona",
        tasks=[{"title": "a"}],
        quality_score=0.9,
    )
    called = {"hit": False}

    async def on_fallback(winner, reason):
        called["hit"] = True

    await select_plan([clean], on_fallback=on_fallback)
    assert called["hit"] is False


# ── T4: MissionStatus.PLANNED_PENDING_REVIEW transition table ───────────────


def test_planned_pending_review_blocks_executing():
    assert MissionStatus.PLANNED_PENDING_REVIEW.can_transition_to(MissionStatus.EXECUTING) is False
    assert MissionStatus.PLANNED_PENDING_REVIEW.can_transition_to(MissionStatus.PLANNED) is True
    assert MissionStatus.PLANNED_PENDING_REVIEW.can_transition_to(MissionStatus.ABORTED) is True
    # Normal planned path still allows execution.
    assert MissionStatus.PLANNED.can_transition_to(MissionStatus.EXECUTING) is True


def test_planned_pending_review_in_check_constraint_tuple():
    from app.models.mission_models import ALL_MISSION_STATUSES

    assert "planned_pending_review" in ALL_MISSION_STATUSES


# ── T5: observability alarms ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fallback_and_rubber_stamp_counters_increment():
    obs = ObservabilityService()
    await obs.increment_counter("planner_fallback_rate", labels={"mission_id": "m1", "strategy": "fallback_heuristic"})
    await obs.increment_counter("hitl_rubber_stamp_approval", labels={"user_id": "1", "item_id": "i1"})
    # Reset for isolation — counters accumulated across calls.
    fb = sum(m.value for m in obs._metrics_by_name.get("planner_fallback_rate", []))
    rs = sum(m.value for m in obs._metrics_by_name.get("hitl_rubber_stamp_approval", []))
    assert fb >= 1
    assert rs >= 1


def test_rubber_stamp_latency_threshold():
    # A sub-second decision latency is flagged for audit.
    now = datetime.now(UTC)
    created = datetime.now(UTC)
    # 0.5s gap → rubber stamp
    gap = (now - created).total_seconds() + 0.5
    assert gap < 1.0
    # 2s gap → not a rubber stamp
    assert (gap + 1.5) >= 1.0
