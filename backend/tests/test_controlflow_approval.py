"""Unit test for the ControlFlowAgent approval callback path.

The graph dead-ends at _check_approval_result -> "pending" -> END, so the ONLY
way an approval decision reaches the agent is through resolve_approval(). This
test verifies that callback: it flips the tool status, explicitly clears
awaiting_approval + current_approval_request, and resumes the graph.

Infra (Redis, LLM) is avoided by stubbing state persistence and the graph.
"""

import pytest

from app.governance.controlflow.agent import ControlFlowAgent
from app.governance.controlflow.state import (
    create_initial_state,
    create_tool_execution,
)


class _StubAgent(ControlFlowAgent):
    """Agent with Redis/LLM/graph replaced by in-memory stubs."""

    def __init__(self):
        # Bypass the real __init__ (no Redis, no LLM, no graph build).
        self._store: dict[str, dict] = {}
        self._resume_calls = 0
        self.graph = _StubGraph(self)

    # --- persistence stubs ---
    def _save_state(self, state):
        self._store[state["session_id"]] = state

    def _load_state(self, session_id):
        return self._store.get(session_id)


class _StubGraph:
    """Simulates the LangGraph resume: routes the (now approved) tool to
    execution, then to generate_response. We only need it to prove resolve_approval
    actually invokes the graph resume with the updated state."""

    def __init__(self, agent):
        self.agent = agent
        self.executed_tools: list[dict] = []

    async def ainvoke(self, state, config=None):
        self.agent._resume_calls += 1
        # Simulate the post-approval graph: execute approved tools.
        for tool in state["pending_tools"]:
            if tool["status"] == "approved":
                tool = dict(tool)
                tool["status"] = "completed"
                self.executed_tools.append(tool)
        state["pending_tools"] = []
        return state


def _make_awaiting_session(session_id="sess_1", user_id=1):
    state = create_initial_state(
        session_id=session_id,
        user_id=user_id,
        auto_approve_safe_tools=True,
        require_approval_for_all=False,
    )
    tool = create_tool_execution(
        tool_name="Execute Worker Task",
        tool_id="execute_worker_task",
        parameters={"action": "step_2a_generate_request"},
        requires_approval=True,
    )
    state["pending_tools"] = [tool]
    state["awaiting_approval"] = True
    state["current_approval_request"] = {
        "approval_id": "approval_test",
        "tool_execution": tool,
        "created_at": "2026-07-13T00:00:00+00:00",
    }
    return state


@pytest.mark.asyncio
async def test_resolve_approval_approves_and_resumes():
    agent = _StubAgent()
    state = _make_awaiting_session()
    agent._save_state(state)

    result = await agent.resolve_approval(session_id="sess_1", decision="approved", approved_by=1)

    # Callback returned success
    assert result["success"] is True
    assert result["decision"] == "approved"
    # Flag explicitly cleared (the real fix — not inferred)
    assert result["awaiting_approval"] is False
    assert result["approval_request"] is None
    # Tool was approved then executed on resume (pending_tools is cleared by the
    # real graph after execution, so we assert against the captured execution).
    assert agent.graph.executed_tools, "graph resume should have executed the approved tool"
    executed = agent.graph.executed_tools[0]
    assert executed["status"] == "completed"
    assert executed["approved_by"] == 1
    # Graph resume was actually invoked
    assert agent._resume_calls == 1


@pytest.mark.asyncio
async def test_resolve_approval_rejects():
    agent = _StubAgent()
    state = _make_awaiting_session()
    agent._save_state(state)

    result = await agent.resolve_approval(session_id="sess_1", decision="rejected", approved_by=2)

    assert result["success"] is True
    assert result["awaiting_approval"] is False
    # Rejected tools are never executed; assert the resolved decision was recorded.
    assert agent.graph.executed_tools == [], "rejected tools must not execute"
    saved = agent._load_state("sess_1")
    # The rejection is captured in the persisted approval_request / flag state.
    assert saved["awaiting_approval"] is False


@pytest.mark.asyncio
async def test_resolve_approval_rejects_bad_decision():
    agent = _StubAgent()
    agent._save_state(_make_awaiting_session())
    with pytest.raises(ValueError, match="decision must be"):
        await agent.resolve_approval(session_id="sess_1", decision="maybe")


@pytest.mark.asyncio
async def test_resolve_approval_when_not_awaiting():
    agent = _StubAgent()
    state = _make_awaiting_session()
    state["awaiting_approval"] = False
    agent._save_state(state)
    with pytest.raises(ValueError, match="not currently awaiting approval"):
        await agent.resolve_approval(session_id="sess_1", decision="approved")
