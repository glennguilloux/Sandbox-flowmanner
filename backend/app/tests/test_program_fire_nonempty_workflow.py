"""Regression tests for Comment 2 — programs must dispatch a non-empty workflow.

Previously ``MissionProgramService.fire_program()`` called
``mission_to_workflow(mission, tasks=[])``, producing a workflow with zero
nodes. ``SoloStrategy.validate()`` then failed before any useful work ran.
Now ``fire_program`` plans + persists tasks before dispatch, so a solo
program fires a workflow with exactly one executable node.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.mission_program_models import ProgramStatus
from app.services.mission_program_service import MissionProgramService


def _make_program() -> MagicMock:
    program = MagicMock()
    program.id = 1
    program.user_id = 42
    program.workspace_id = "ws-1"
    program.name = "Deep Dive"
    program.description = "Review the backend."
    program.mission_type = "solo"
    program.base_constraints = {}
    program.learning_brief = None
    program.status = ProgramStatus.ACTIVE.value
    # No budget caps => budget pre-check skips DB queries.
    program.per_run_budget_usd = None
    program.monthly_budget_usd = None
    return program


async def test_fire_program_dispatches_workflow_with_one_executable_node():
    program = _make_program()
    db = AsyncMock()
    db.add = MagicMock()  # add is sync
    service = MissionProgramService(db)

    # ``get`` resolves the program.
    service.get = AsyncMock(return_value=program)

    # Capture the workflow handed to the executor.
    captured = {}

    async def fake_executor_execute(db, workflow, **kwargs):
        captured["workflow"] = workflow
        result = MagicMock()
        result.success = True
        result.total_cost_usd = 0.0
        result.total_tokens = 0
        result.execution_time_ms = 0.0
        result.data = None
        result.error = None
        return result

    with (
        patch(
            "app.services.substrate.executor.get_unified_executor",
            return_value=AsyncMock(execute=fake_executor_execute),
        ),
        patch(
            # Force the deterministic fallback single task (no network/LLM).
            "app.services.mission_planner.MissionPlanner"
        ) as mock_planner_cls,
    ):
        planner_instance = MagicMock()
        planner_instance._build_plan_prompt.return_value = "prompt"
        planner_instance._generate_plan = AsyncMock(return_value=[])
        mock_planner_cls.return_value = planner_instance

        run = await service.fire_program(
            user_id=42,
            program_id=1,
            trigger_type="manual",
            trigger_payload=None,
        )

    workflow = captured["workflow"]
    # Exactly one executable node.
    assert len(workflow.nodes) == 1, f"expected 1 node, got {len(workflow.nodes)}"
    node = workflow.nodes[0]
    # The node must carry a real prompt/config so the solo strategy can run it.
    assert node.config.get("prompt"), "node config missing prompt"
    assert run.status == "completed"
