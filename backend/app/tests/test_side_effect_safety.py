"""Regression tests for Comment 3 — idempotent irreversible side effects.

Irreversible nodes must not double-fire after a crash between dispatch and
confirmation. Before dispatching, the executor computes the logical
confirmation key (run-excluded) and queries the event log:

* confirmed present  -> skip the external call, return a replayed success
* intent w/o confirm  -> escalate to HITL (do NOT re-fire)
* clean first fire    -> stage, fire, confirm; a second call replays
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capability_models import Budget
from app.models.substrate_models import SubstrateEventType
from app.services.substrate.event_log import _compute_idempotency_key
from app.services.substrate.executor import UnifiedExecutor
from app.services.substrate.node_executor import NodeExecutor
from app.services.substrate.workflow_models import (
    EffectClass,
    NodeType,
    Workflow,
    WorkflowNode,
    WorkflowType,
)


class _FakeEventLog:
    """In-memory event log that supports idempotency-key lookups."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.appends = 0

    async def append(self, db, run_id, events, **kwargs):
        self.appends += 1
        for ev in events:
            ev = dict(ev)
            ev["run_id"] = run_id
            self.events.append(ev)
        return None

    async def get_events(self, db, run_id, *, event_type=None, **kwargs):
        out = [e for e in self.events if e.get("run_id") == run_id]
        if event_type is not None:
            out = [e for e in out if e.get("type") == event_type]
        return [MagicMock(payload=e.get("payload"), type=e.get("type")) for e in out]

    async def get_latest_sequence(self, db, run_id):
        return 0

    async def find_by_idempotency_key(self, db, idempotency_key):
        for e in self.events:
            if (e.get("payload") or {}).get("idempotency_key") == idempotency_key:
                return MagicMock(payload=e.get("payload"), type=e.get("type"))
        return None


def _make_node() -> WorkflowNode:
    return WorkflowNode(
        id="n1",
        type=NodeType.TOOL_CALL,
        title="send payment",
        config={"tool_name": "payments", "prompt": "pay 1 USD", "action": "send"},
        effect_class=EffectClass.IRREVERSIBLE,
    )


def _make_workflow(node: WorkflowNode) -> Workflow:
    return Workflow(
        id="wf-1",
        type=WorkflowType.SOLO,
        title="side effect",
        nodes=[node],
        user_id="00000000-0000-0000-0000-000000000000",
        workspace_id="ws-1",
    )


def _make_executor(log: _FakeEventLog) -> UnifiedExecutor:
    ex = UnifiedExecutor(event_log=log, replay_engine=MagicMock())
    ex.budget_enforcer = MagicMock()
    ex.is_aborted = MagicMock(return_value=False)
    ex.check_circuit_breaker = AsyncMock(return_value=(True, ""))
    return ex


async def _run(executor, log, node, fire_count, confirmed_first=False):
    """Drive execute_node; returns (last_result, fire_count, log)."""
    budget = Budget(max_cost_usd=10, max_wall_time_seconds=300, max_iterations=5, max_depth=1)
    db = MagicMock(spec=AsyncSession)
    workflow = _make_workflow(node)
    if confirmed_first:
        payload = {
            "task_id": node.id,
            "node_type": node.type.value,
            "effect_class": node.effect_class.value,
            "idempotency_key": _compute_idempotency_key(
                None,
                SubstrateEventType.SIDE_EFFECT_CONFIRMED,
                node.id,
                NodeExecutor._render_effect_payload(node, workflow),
            ),
        }
        await log.append(db, "run-1", [{"type": SubstrateEventType.SIDE_EFFECT_CONFIRMED, "payload": payload}])
    result = await executor.execute_node(db, node, {}, budget, "run-1", workflow)
    return result


@pytest.fixture
def fire():
    calls = {"n": 0}

    async def fake_tool(self, db, node, context, budget, run_id, workflow=None):
        calls["n"] += 1
        return {"success": True, "output": "sent", "tokens": 0, "cost": 0.0}

    with patch.object(NodeExecutor, "_handle_tool", fake_tool):
        yield calls


async def test_confirmed_effect_is_replayed_not_refired(fire):
    log = _FakeEventLog()
    ex = _make_executor(log)
    with patch("app.services.substrate.node_executor.get_event_log", return_value=log):
        result = await _run(ex, log, _make_node(), fire, confirmed_first=True)
    assert result.get("success") is True
    assert result.get("replayed") is True
    assert fire["n"] == 0, "external effect must NOT fire when already confirmed"


async def test_intent_without_confirmation_escalates(fire):
    log = _FakeEventLog()
    ex = _make_executor(log)
    node = _make_node()
    workflow = _make_workflow(node)
    # Stage an intent (run-scoped key) but NO confirmation.
    intent_payload = {
        "task_id": node.id,
        "node_type": node.type.value,
        "effect_class": node.effect_class.value,
        "idempotency_key": _compute_idempotency_key(
            "run-1",
            SubstrateEventType.SIDE_EFFECT_INTENT,
            node.id,
            NodeExecutor._render_effect_payload(node, workflow),
        ),
    }
    db = MagicMock(spec=AsyncSession)
    await log.append(db, "run-1", [{"type": SubstrateEventType.SIDE_EFFECT_INTENT, "payload": intent_payload}])
    with patch("app.services.substrate.node_executor.get_event_log", return_value=log):
        result = await ex.execute_node(
            db,
            node,
            {},
            Budget(max_cost_usd=10, max_wall_time_seconds=300, max_iterations=5, max_depth=1),
            "run-1",
            workflow,
        )
    assert result.get("success") is False
    assert result.get("requires_acknowledgement") is True
    assert fire["n"] == 0, "external effect must NOT re-fire with unconfirmed intent"


async def test_concurrent_retry_replays_after_first_confirm(fire):
    log = _FakeEventLog()
    ex = _make_executor(log)
    node = _make_node()
    budget = Budget(max_cost_usd=10, max_wall_time_seconds=300, max_iterations=5, max_depth=1)
    db = MagicMock(spec=AsyncSession)
    workflow = _make_workflow(node)
    with patch("app.services.substrate.node_executor.get_event_log", return_value=log):
        first = await ex.execute_node(db, node, {}, budget, "run-1", workflow)
        assert first.get("success") is True
        assert fire["n"] == 1, "first call should fire the external effect once"
        second = await ex.execute_node(db, node, {}, budget, "run-1", workflow)
        # Either the side-effect-confirmed guard OR the node.completed guard
        # must prevent a re-fire; both are valid idempotency paths.
        assert second.get("replayed") is True or second.get("skipped_idempotent") is True
        assert fire["n"] == 1, "second call must replay, not re-fire"
