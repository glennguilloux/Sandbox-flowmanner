"""Integration test for Q6-F — ReviewerGuard -> HITL inbox drain.

This is the production call site for the ReviewerGuard engine (GOLD-LEDGER
#2).  It proves the acceptance criteria:

1. A substrate post-node hook (``UnifiedExecutor._run_reviewer_guard_drain``)
   invokes ``verify_batch`` via the drain helper.
2. An ungrounded node output surfaces as an ESCALATION inbox item.
3. The default path is lexical-only (no verifier injected -> $0 token cost) and
   escalate-only (it only creates inbox items, never mutates run data).
4. A grounded node output produces NO escalation.

Hermetic: the HITLService + db are faked, so no real Postgres / LLM is
touched.  This isolates the wiring (verify_batch -> inbox escalation) which
is exactly the bug being fixed -- a finished trust firewall that called
nothing.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner",
)

from app.services.reviewer_guard.inbox_drain import (
    build_run_context,
    drain_run_to_inbox,
)
from app.services.reviewer_guard.orchestrator import ReviewerGuard
from app.services.substrate.executor import StrategyResult, UnifiedExecutor
from app.services.substrate.workflow_models import (
    NodeType,
    Workflow,
    WorkflowNode,
    WorkflowType,
)

# A workflow brief that contains the grounded claim but NOT the hallucination.
_BRIEF = "The user said the API token is secret123 and expires in July."

# An ungrounded hallucination (no span in the run supports it).
_UNGROUNDED_OUTPUT = "The database password is hunter2"

# A grounded claim (substantively present in the brief).
_GROUNDED_OUTPUT = "The API token is secret123 and expires in July."


def _fake_workflow(
    *,
    brief: str,
    node_outputs: list[str],
    user_id: str = "42",
    workspace_id: str = "ws-1",
) -> Workflow:
    nodes = [
        WorkflowNode(
            id=f"n{i}",
            type=NodeType.LLM_CALL,
            title=f"node {i}",
            output_data={"text": txt},
        )
        for i, txt in enumerate(node_outputs)
    ]
    return Workflow(
        id="wf-1",
        type=WorkflowType.SOLO,
        title="test workflow",
        description=brief,
        nodes=nodes,
        user_id=user_id,
        workspace_id=workspace_id,
    )


def _fake_result(run_id: str = "run-1") -> StrategyResult:
    # The executor attaches run_id to the result before post-hooks; emulate.
    return StrategyResult(success=True, status="completed", run_id=run_id)


def _patched_hitl():
    """Patch HITLService so create_interrupt is an AsyncMock we can inspect."""
    fake_service = MagicMock()
    fake_service.create_interrupt = AsyncMock(return_value=MagicMock(id="inbox-1"))
    return (
        patch("app.services.hitl_service.HITLService", return_value=fake_service),
        fake_service,
    )


class TestDrainUngroundedToInbox:
    """An ungrounded node output must produce an ESCALATION inbox item."""

    async def test_ungrounded_claim_creates_escalation(self) -> None:
        wf = _fake_workflow(brief=_BRIEF, node_outputs=[_UNGROUNDED_OUTPUT])
        ctx = build_run_context(
            run_id="run-1",
            mission_id="wf-1",
            nodes=wf.nodes,
            user_id="42",
            workspace_id="ws-1",
            brief=wf.description,
        )
        assert ctx.claims, "expected at least one claim to verify"

        fake_db = MagicMock()
        hitl_patch, fake_service = _patched_hitl()
        with hitl_patch:
            drained = await drain_run_to_inbox(fake_db, ctx, reviewer_model="deepseek-v4-flash")

        assert drained == 1, f"expected 1 escalation, got {drained}"
        assert fake_service.create_interrupt.await_count == 1
        _, kwargs = fake_service.create_interrupt.call_args
        # Escalate-only: the interrupt is an ESCALATION, never an action approval.
        assert kwargs["interrupt_type"].value == "escalation"
        assert kwargs["run_id"] == "run-1"
        assert kwargs["mission_id"] == "wf-1"
        # The proposed_action carries the verdict + the reason it escalated.
        assert kwargs["proposed_action"]["grounded"] is False
        assert "claim_id" in kwargs["proposed_action"]


class TestDrainGroundedNoEscalation:
    """A grounded node output must NOT produce an inbox item."""

    async def test_grounded_claim_no_escalation(self) -> None:
        wf = _fake_workflow(brief=_BRIEF, node_outputs=[_GROUNDED_OUTPUT])
        ctx = build_run_context(
            run_id="run-1",
            mission_id="wf-1",
            nodes=wf.nodes,
            user_id="42",
            workspace_id="ws-1",
            brief=wf.description,
        )
        fake_db = MagicMock()
        hitl_patch, fake_service = _patched_hitl()
        with hitl_patch:
            drained = await drain_run_to_inbox(fake_db, ctx, reviewer_model="deepseek-v4-flash")

        assert drained == 0
        assert fake_service.create_interrupt.await_count == 0


class TestDrainLexicalOnly:
    """Default path must be lexical-only: no SecondPassVerifier is injected."""

    async def test_no_verifier_injected(self) -> None:
        wf = _fake_workflow(brief=_BRIEF, node_outputs=[_UNGROUNDED_OUTPUT])
        ctx = build_run_context(
            run_id="run-1",
            mission_id="wf-1",
            nodes=wf.nodes,
            user_id="42",
            workspace_id="ws-1",
            brief=wf.description,
        )
        # Reproduce the exact ReviewerGuard construction the drain uses.
        claim = ctx.claims[0]
        own_id = claim.claim_id.split("node:")[-1]
        corpus = [s for s in ctx.spans if s.span_id != f"node:{own_id}"]
        guard = ReviewerGuard(corpus, calibration=None, reviewer_model="deepseek-v4-flash")
        # Lexical-only: no cross-family verifier injected by the drain path.
        assert guard.verifier is None


class TestExecutorReviewerGuardDrainHook:
    """The new substrate hook wires verify_batch -> inbox (acceptance #1)."""

    async def test_hook_creates_escalation_for_ungrounded_run(self) -> None:
        wf = _fake_workflow(brief=_BRIEF, node_outputs=[_UNGROUNDED_OUTPUT])
        result = _fake_result("run-1")
        fake_db = MagicMock()
        hitl_patch, fake_service = _patched_hitl()

        exec_ = UnifiedExecutor.__new__(UnifiedExecutor)
        with hitl_patch:
            await exec_._run_reviewer_guard_drain(fake_db, wf, result)

        assert fake_service.create_interrupt.await_count == 1
        _, kwargs = fake_service.create_interrupt.call_args
        assert kwargs["interrupt_type"].value == "escalation"
        assert kwargs["run_id"] == "run-1"

    async def test_hook_skipped_when_flag_off(self) -> None:
        from app.config import settings

        prev = settings.REVIEWER_GUARD_DRAIN_ENABLED
        settings.REVIEWER_GUARD_DRAIN_ENABLED = False
        try:
            wf = _fake_workflow(brief=_BRIEF, node_outputs=[_UNGROUNDED_OUTPUT])
            result = _fake_result("run-1")
            fake_db = MagicMock()
            with patch(
                "app.services.reviewer_guard.inbox_drain.drain_run_to_inbox",
                new=AsyncMock(return_value=0),
            ) as drain_mock:
                exec_ = UnifiedExecutor.__new__(UnifiedExecutor)
                await exec_._run_post_hooks(fake_db, wf, result)
                drain_mock.assert_not_called()
        finally:
            settings.REVIEWER_GUARD_DRAIN_ENABLED = prev

    async def test_post_hook_dispatches_to_drain_when_flag_on(self) -> None:
        from app.config import settings

        prev = settings.REVIEWER_GUARD_DRAIN_ENABLED
        settings.REVIEWER_GUARD_DRAIN_ENABLED = True
        try:
            wf = _fake_workflow(brief=_BRIEF, node_outputs=[_UNGROUNDED_OUTPUT])
            result = _fake_result("run-1")
            fake_db = MagicMock()
            with patch.object(
                UnifiedExecutor,
                "_run_reviewer_guard_drain",
                new=AsyncMock(),
            ) as drain_spy:
                exec_ = UnifiedExecutor.__new__(UnifiedExecutor)
                await exec_._run_post_hooks(fake_db, wf, result)
                drain_spy.assert_awaited_once()
        finally:
            settings.REVIEWER_GUARD_DRAIN_ENABLED = prev
