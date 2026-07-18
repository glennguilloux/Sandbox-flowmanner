"""Tests for the escalate-constraint → HITL execution path (G-9 fix).

Drives the REAL NodeExecutor._handle_tool escalate branch, which previously
raised AttributeError at runtime because ``_escalate_constraint_to_hitl`` did
not exist. These tests assert the run genuinely pauses via HITLPaused (a real
pause, not a silent block) and that the resume guard resolves correctly
instead of re-escalating forever on re-entry.

Reuses the seeding helpers from test_pre_tool_constraints to keep the
constraint/claim shape identical to the production path.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

sys.path.insert(0, "/opt/flowmanner/backend")

from app.database import fresh_session
from app.models.mission_models import Mission, MissionStatus
from app.services.substrate.hitl_pause import HITLPaused
from app.services.substrate.workflow_models import (
    Workflow,
    WorkflowType,
)
from app.tests.test_pre_tool_constraints import (
    _mk_constraint,
    _seed_user_ws,
    _uid,
    _wsid,
)


def _seed_mission(db, mission_id: str, user_id: int, workspace_id: str) -> None:
    """Insert a minimal Mission row so inbox_items.mission_id FK holds."""
    db.add(
        Mission(
            id=mission_id,
            user_id=user_id,
            title="escalate-test-mission",
            status=MissionStatus.PENDING,
            workspace_id=workspace_id,
        )
    )


def _make_tool_node(tool_name: str, user_id: str):
    from app.services.substrate.workflow_models import NodeType, WorkflowNode

    return WorkflowNode(
        id="node-escalate",
        type=NodeType.TOOL_CALL,
        title="Gated tool",
        config={"tool_name": tool_name},
    )


def _make_node_executor():
    from app.services.substrate.node_executor import NodeExecutor

    mock_executor = MagicMock()
    mock_executor.is_aborted = MagicMock(return_value=False)
    mock_executor.check_circuit_breaker = AsyncMock(return_value=(True, None))
    mock_executor.event_log = MagicMock()
    mock_executor.event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
    return NodeExecutor(mock_executor)


async def _run_handle_tool(db, node, workflow, run_id: str = "run-escalate"):
    """Invoke _handle_tool with circuit-breaker + capability engine stubbed."""
    ne = _make_node_executor()
    with patch("app.services.capability_engine.get_capability_engine") as mock_cap:
        eng = mock_cap.return_value
        eng.issue.return_value = "tok"
        eng.verify_and_require.return_value = None
        return await ne._handle_tool(db, node, {}, MagicMock(), run_id, workflow)


@pytest.mark.asyncio(loop_scope="module")
async def test_escalate_constraint_pauses_via_hitl():
    """An escalate constraint must raise HITLPaused (real pause), not block."""
    from sqlalchemy import select

    from app.models.hitl_models import InboxItem

    user_id = _uid()
    ws = _wsid()
    workflow_id = str(uuid4())
    run_id = str(uuid4())
    async with fresh_session() as db:
        await _seed_user_ws(db, user_id, ws)
        _seed_mission(db, workflow_id, user_id, ws)
        db.add(
            _mk_constraint(
                user_id,
                ws,
                subject="require approval before bulk delete",
                target_tools=["code_executor"],
                action="escalate",
                reason="data loss risk",
            )
        )
        await db.commit()

    workflow = Workflow(
        id=workflow_id,
        type=WorkflowType.SOLO,
        title="escalate-test",
        user_id=str(uuid4()),
        workspace_id=ws,
        blueprint_type="solo",
        nodes=[],
        edges=[],
    )
    node = _make_tool_node("code_executor", str(user_id))
    async with fresh_session() as db:
        with pytest.raises(HITLPaused) as exc:
            await _run_handle_tool(db, node, workflow, run_id=run_id)
        assert exc.value.interrupt_type == "escalation"
        assert exc.value.run_id == run_id
        # An inbox item must have been persisted for human resolution.
        res = await db.execute(select(InboxItem).where(InboxItem.run_id == run_id, InboxItem.node_id == node.id))
        item = res.scalar_one_or_none()
        assert item is not None
        assert item.status == "pending"


@pytest.mark.asyncio(loop_scope="module")
async def test_escalate_resume_approved_proceeds():
    """On resume with an APPROVED inbox item, the tool node proceeds (returns None)."""
    from sqlalchemy import select

    from app.models.hitl_models import HumanInterruptType, InboxItem

    user_id = _uid()
    ws = _wsid()
    workflow_id = str(uuid4())
    async with fresh_session() as db:
        await _seed_user_ws(db, user_id, ws)
        _seed_mission(db, workflow_id, user_id, ws)
        db.add(
            _mk_constraint(
                user_id,
                ws,
                subject="require approval before bulk delete",
                target_tools=["code_executor"],
                action="escalate",
                reason="data loss risk",
            )
        )
        await db.commit()

    workflow = Workflow(
        id=workflow_id,
        type=WorkflowType.SOLO,
        title="escalate-test-2",
        user_id=str(uuid4()),
        workspace_id=ws,
        blueprint_type="solo",
        nodes=[],
        edges=[],
    )
    node = _make_tool_node("code_executor", str(user_id))
    run_id = str(uuid4())
    async with fresh_session() as db:
        # Pre-create an APPROVED inbox item (simulating a human approval).
        from app.models.hitl_models import HumanInterruptType, InboxItem

        item = InboxItem(
            workspace_id=ws,
            user_id=user_id,
            mission_id=None,
            interrupt_type=HumanInterruptType.ESCALATION,
            title="Approval required: require approval before bulk delete",
            status="approved",
            node_id=node.id,
            run_id=run_id,
        )
        db.add(item)
        await db.commit()

        # _handle_tool should NOT raise HITLPaused (guard resolved the
        # approved item and let the tool proceed). The tool then runs and
        # returns its own (non-None) result dict.
        result = await _run_handle_tool(db, node, workflow, run_id=run_id)
        assert result is not None
        assert "success" in result
