"""Unit tests for SwarmStrategy (app/services/substrate/strategies/swarm.py)."""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.substrate.strategies.swarm import SwarmStrategy
from app.services.substrate.workflow_models import (
    Workflow,
    WorkflowNode,
    WorkflowType,
    NodeType,
    StrategyResult,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_swarm_workflow(
    fan_out_count=1,
    fan_in_count=1,
    extra_nodes=None,
    metadata=None,
):
    nodes = []
    for i in range(fan_out_count):
        nodes.append(
            WorkflowNode(id=f"fo{i}", type=NodeType.FAN_OUT, title=f"Fan Out {i}")
        )
    for i in range(fan_in_count):
        nodes.append(
            WorkflowNode(id=f"fi{i}", type=NodeType.FAN_IN, title=f"Fan In {i}")
        )
    if extra_nodes:
        nodes.extend(extra_nodes)
    return Workflow(
        id=str(uuid4()),
        type=WorkflowType.SWARM,
        title="Swarm Test",
        description="Test swarm workflow",
        nodes=nodes,
        edges=[],
        user_id="1",
        metadata=metadata or {},
    )


def _make_executor():
    executor = MagicMock()
    executor.is_aborted = MagicMock(return_value=False)
    executor.execute_node = AsyncMock(
        return_value={
            "success": True,
            "output": {"text": "Agent output"},
            "tokens": 50,
            "cost": 0.05,
        }
    )
    executor.call_llm = AsyncMock(
        return_value={
            "success": True,
            "response": json.dumps(
                {
                    "subtasks": [
                        {
                            "id": "task_1",
                            "description": "Research phase",
                            "task_type": "research",
                        },
                        {
                            "id": "task_2",
                            "description": "Analysis phase",
                            "task_type": "analysis",
                        },
                    ]
                }
            ),
            "tokens": 100,
        }
    )
    return executor


# ── can_handle ───────────────────────────────────────────────────────


class TestSwarmCanHandle:
    def test_handles_swarm(self):
        s = SwarmStrategy()
        assert s.can_handle(WorkflowType.SWARM) is True

    def test_rejects_solo(self):
        s = SwarmStrategy()
        assert s.can_handle(WorkflowType.SOLO) is False

    def test_rejects_dag(self):
        s = SwarmStrategy()
        assert s.can_handle(WorkflowType.DAG) is False

    def test_rejects_graph(self):
        s = SwarmStrategy()
        assert s.can_handle(WorkflowType.GRAPH) is False


# ── validate ─────────────────────────────────────────────────────────


class TestSwarmValidate:
    @pytest.mark.asyncio
    async def test_valid_swarm(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        errors = await s.validate(wf)
        assert errors == []

    @pytest.mark.asyncio
    async def test_missing_fan_out(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow(fan_out_count=0)
        errors = await s.validate(wf)
        assert any("FAN_OUT" in e for e in errors)

    @pytest.mark.asyncio
    async def test_missing_fan_in(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow(fan_in_count=0)
        errors = await s.validate(wf)
        assert any("FAN_IN" in e for e in errors)

    @pytest.mark.asyncio
    async def test_missing_both(self):
        s = SwarmStrategy()
        wf = Workflow(
            id=str(uuid4()),
            type=WorkflowType.SWARM,
            title="Empty swarm",
            nodes=[WorkflowNode(id="n1", type="llm_call", title="N")],
            user_id="1",
        )
        errors = await s.validate(wf)
        assert len(errors) == 2


# ── execute ──────────────────────────────────────────────────────────


class TestSwarmExecute:
    @pytest.mark.asyncio
    async def test_execute_happy_path(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {"goal": "Do research"}, executor, db)

        assert result.success is True
        assert result.status == "completed"
        assert len(result.completed_nodes) == 2  # 2 subtasks dispatched
        assert "synthesis" in result.data
        assert "agent_outputs" in result.data

    @pytest.mark.asyncio
    async def test_execute_uses_workflow_description_as_goal(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        # Verify call_llm was called with the workflow description as goal
        decompose_call = executor.call_llm.call_args_list[0]
        prompt_msg = decompose_call[1]["messages"][1]["content"]
        assert "Test swarm workflow" in prompt_msg

    @pytest.mark.asyncio
    async def test_execute_uses_context_goal_over_description(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {"goal": "Custom goal"}, executor, db)

        assert result.success is True
        decompose_call = executor.call_llm.call_args_list[0]
        prompt_msg = decompose_call[1]["messages"][1]["content"]
        assert "Custom goal" in prompt_msg

    @pytest.mark.asyncio
    async def test_execute_with_substrate_run_id(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow(metadata={"substrate_run_id": "swarm-run-1"})
        db = AsyncMock()
        executor = _make_executor()

        await s.execute(wf, {}, executor, db)

        decompose_call = executor.call_llm.call_args_list[0]
        assert decompose_call[1]["run_id"] == "swarm-run-1"

    @pytest.mark.asyncio
    async def test_execute_aborted(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()
        executor.is_aborted = MagicMock(return_value=True)

        result = await s.execute(wf, {}, executor, db)

        assert result.success is False
        assert result.status == "aborted"

    @pytest.mark.asyncio
    async def test_execute_decompose_failure_fallback(self):
        """When decompose LLM fails, falls back to single task."""
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()
        # First call (decompose) fails, second (synthesis) succeeds
        executor.call_llm = AsyncMock(
            side_effect=[
                {"success": False, "error": "LLM unavailable"},
                {"success": True, "response": "Synthesized result", "tokens": 50},
            ]
        )

        result = await s.execute(wf, {"goal": "Test goal"}, executor, db)

        assert result.success is True
        # Should have dispatched 1 fallback task + synthesis call
        assert executor.execute_node.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_decompose_invalid_json_fallback(self):
        """When decompose returns invalid JSON, falls back to single task."""
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()
        executor.call_llm = AsyncMock(
            side_effect=[
                {"success": True, "response": "not valid json at all", "tokens": 10},
                {"success": True, "response": "Done", "tokens": 20},
            ]
        )

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is True
        assert executor.execute_node.call_count == 1  # single fallback task

    @pytest.mark.asyncio
    async def test_execute_decompose_json_with_code_fences(self):
        """Decompose strips ``` fences before parsing."""
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()
        executor.call_llm = AsyncMock(
            side_effect=[
                {
                    "success": True,
                    "response": '```json\n{"subtasks": [{"id": "t1", "description": "A"}]}\n```',
                    "tokens": 10,
                },
                {"success": True, "response": "Done", "tokens": 20},
            ]
        )

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is True
        assert executor.execute_node.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_agent_exception(self):
        """When an agent raises an exception during dispatch."""
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()
        executor.execute_node = AsyncMock(side_effect=RuntimeError("agent crashed"))

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        # Synthesis still runs, but with error outputs
        assert executor.call_llm.call_count == 2  # decompose + synthesis
        assert result.success is True  # synthesis succeeded

    @pytest.mark.asyncio
    async def test_execute_agent_failure(self):
        """When an agent returns failure (not exception)."""
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()
        executor.execute_node = AsyncMock(
            return_value={
                "success": False,
                "error": "Agent failed",
            }
        )

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        # Synthesis still runs
        assert executor.call_llm.call_count == 2
        # Check agent outputs include failure info
        synthesis_call = executor.call_llm.call_args_list[1]
        prompt = synthesis_call[1]["messages"][1]["content"]
        assert "Failed" in prompt

    @pytest.mark.asyncio
    async def test_execute_synthesis_failure(self):
        """When synthesis LLM fails, overall result is failed."""
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()
        executor.call_llm = AsyncMock(
            side_effect=[
                {
                    "success": True,
                    "response": json.dumps(
                        {"subtasks": [{"id": "t1", "description": "A"}]}
                    ),
                    "tokens": 10,
                },
                {"success": False, "error": "Synthesis failed"},
            ]
        )

        result = await s.execute(wf, {"goal": "Test"}, executor, db)

        assert result.success is False
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_execute_three_subtasks(self):
        """Three subtasks from decompose → three parallel agents."""
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        db = AsyncMock()
        executor = _make_executor()
        executor.call_llm = AsyncMock(
            side_effect=[
                {
                    "success": True,
                    "response": json.dumps(
                        {
                            "subtasks": [
                                {
                                    "id": "t1",
                                    "description": "Research",
                                    "agent_name": "Researcher",
                                },
                                {"id": "t2", "description": "Analysis"},
                                {
                                    "id": "t3",
                                    "description": "Review",
                                    "task_type": "review",
                                },
                            ]
                        }
                    ),
                    "tokens": 50,
                },
                {"success": True, "response": "Synthesis done", "tokens": 100},
            ]
        )

        result = await s.execute(wf, {"goal": "Multi-task goal"}, executor, db)

        assert result.success is True
        assert executor.execute_node.call_count == 3
        assert len(result.completed_nodes) == 3

    @pytest.mark.asyncio
    async def test_execute_with_title_fallback_goal(self):
        """When no goal in context and no description, uses title."""
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        wf.description = None
        db = AsyncMock()
        executor = _make_executor()

        result = await s.execute(wf, {}, executor, db)

        assert result.success is True
        decompose_call = executor.call_llm.call_args_list[0]
        prompt = decompose_call[1]["messages"][1]["content"]
        assert "Swarm Test" in prompt


# ── _decompose ───────────────────────────────────────────────────────


class TestSwarmDecompose:
    @pytest.mark.asyncio
    async def test_decompose_success(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        executor = MagicMock()
        executor.call_llm = AsyncMock(
            return_value={
                "success": True,
                "response": json.dumps(
                    {
                        "subtasks": [
                            {
                                "id": "t1",
                                "description": "First task",
                                "task_type": "research",
                            }
                        ]
                    }
                ),
                "tokens": 50,
            }
        )

        result = await s._decompose("Test goal", executor, wf, "run-1")

        assert len(result) == 1
        assert result[0]["id"] == "t1"

    @pytest.mark.asyncio
    async def test_decompose_llm_failure_returns_fallback(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        executor = MagicMock()
        executor.call_llm = AsyncMock(
            return_value={
                "success": False,
                "error": "Rate limited",
            }
        )

        result = await s._decompose("Goal", executor, wf, "run-1")

        assert len(result) == 1
        assert result[0]["description"] == "Goal"
        assert result[0]["task_type"] == "general"

    @pytest.mark.asyncio
    async def test_decompose_invalid_json_returns_fallback(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        executor = MagicMock()
        executor.call_llm = AsyncMock(
            return_value={
                "success": True,
                "response": "I can't parse this as JSON",
                "tokens": 10,
            }
        )

        result = await s._decompose("Goal", executor, wf, "run-1")

        assert len(result) == 1
        assert result[0]["task_type"] == "general"

    @pytest.mark.asyncio
    async def test_decompose_strips_code_fences(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        executor = MagicMock()
        executor.call_llm = AsyncMock(
            return_value={
                "success": True,
                "response": '```json\n{"subtasks": [{"id": "t1", "description": "A"}]}\n```',
                "tokens": 10,
            }
        )

        result = await s._decompose("Goal", executor, wf, "run-1")

        assert len(result) == 1
        assert result[0]["id"] == "t1"

    @pytest.mark.asyncio
    async def test_decompose_strips_trailing_fence(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        executor = MagicMock()
        executor.call_llm = AsyncMock(
            return_value={
                "success": True,
                "response": '{"subtasks": [{"id": "t1", "description": "A"}]}\n```',
                "tokens": 10,
            }
        )

        result = await s._decompose("Goal", executor, wf, "run-1")

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_decompose_empty_subtasks_returns_default(self):
        s = SwarmStrategy()
        wf = _make_swarm_workflow()
        executor = MagicMock()
        executor.call_llm = AsyncMock(
            return_value={
                "success": True,
                "response": json.dumps({"subtasks": []}),
                "tokens": 10,
            }
        )

        result = await s._decompose("Goal", executor, wf, "run-1")

        # Empty subtasks list is returned as-is (no fallback)
        assert result == []
