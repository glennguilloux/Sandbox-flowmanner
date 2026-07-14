"""Regression tests for Findings C + D in trigger_service.fire_trigger.

Finding C: trigger-fired missions must build a REAL workflow (non-empty node
list) — the old `tasks=[]` produced an empty workflow and nothing executed.

Finding D: trigger-fired missions must transition `Mission.status` to a
terminal state (COMPLETED / FAILED) with `completed_at` set, mirroring the
already-correct Celery path.

Mirrors the mocking style of test_mission_handlers.py: patch the substrate
imports inside the background task and the DB session factory.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.models.mission_models import MissionStatus
from app.services.substrate.workflow_models import StrategyResult

MISSION_ID = UUID("014da489-b7f5-44f7-9e89-046a05a5ab56")
TASK_ID = UUID("114da489-b7f5-44f7-9e89-046a05a5ab57")
TRIGGER_ID = "214da489-b7f5-44f7-9e89-046a05a5ab58"
LOG_ID = "314da489-b7f5-44f7-9e89-046a05a5ab59"
USER_ID = 1


def make_mission(status="pending"):
    """Real-ish Mission object used by mission_to_workflow."""
    return SimpleNamespace(
        id=MISSION_ID,
        user_id=USER_ID,
        workspace_id=None,
        title="Test Mission",
        description="test mission",
        mission_type="general",
        status=status,
        budget_usd=10.0,
        budget_seconds=300,
        actual_cost=0.0,
        tokens_used=0,
        plan=None,
    )


def make_task(order_index=0):
    return SimpleNamespace(
        id=TASK_ID,
        mission_id=MISSION_ID,
        title="Test Task",
        description="Test task desc",
        task_type="llm",
        order_index=order_index,
        status="pending",
        dependencies=None,
        assigned_model=None,
        assigned_agent_id=None,
        max_retries=3,
        output_data=None,
        error_message=None,
        retry_count=0,
        tokens_used=0,
        cost=0.0,
    )


def make_log(status="pending"):
    return SimpleNamespace(
        id=LOG_ID,
        trigger_id=TRIGGER_ID,
        status=status,
        duration_ms=None,
        mission_run_id=None,
        error_message=None,
    )


def build_session(mission, log):
    """AsyncSession whose get() returns the right ORM object by identity."""

    async def _get(cls, ident):
        if cls.__name__ == "Mission" and str(ident) == str(MISSION_ID):
            return mission
        if cls.__name__ == "TriggerLog" and str(ident) == str(LOG_ID):
            return log
        return None

    session = AsyncMock()
    session.get = _get
    session.commit = AsyncMock()
    return session


async def run_background(executor_result, mission, tasks, log):
    """Drive _execute_mission_background with patched substrate + session."""
    captured = {}

    # Capture the real adapter BEFORE we patch its module attribute, so the
    # wrapper can call the genuine conversion (no recursion).
    import app.services.substrate.adapters as _adapters

    _real_mtw = _adapters.mission_to_workflow

    def fake_mission_to_workflow(mission_obj, tasks=None):
        captured["tasks"] = tasks
        wf = _real_mtw(mission_obj, tasks=tasks)
        captured["workflow"] = wf
        return wf

    class FakeExecutor:
        async def execute(self, db, workflow):
            captured["executed_workflow"] = workflow
            return executor_result

    def get_unified_executor():
        captured["get_unified_executor_called"] = True
        return FakeExecutor()

    session = build_session(mission, log)

    class FakeSessionLocal:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    from app.services.trigger_service import _execute_mission_background

    get_tasks_mock = AsyncMock(return_value=tasks)
    with (
        patch(
            "app.services.trigger_service.get_mission_tasks",
            new=get_tasks_mock,
        ),
        patch(
            "app.database.AsyncSessionLocal",
            new=FakeSessionLocal,
        ),
        patch(
            "app.services.substrate.adapters.mission_to_workflow",
            new=fake_mission_to_workflow,
        ),
        patch(
            "app.services.substrate.executor.get_unified_executor",
            new=get_unified_executor,
        ),
    ):
        await _execute_mission_background(str(MISSION_ID), str(LOG_ID), TRIGGER_ID)

    captured["get_mission_tasks_called"] = get_tasks_mock.await_count > 0
    return captured, session, mission, log


class TestTriggerFiresNonEmptyWorkflow:
    """Finding C: workflow must be built from the mission's real tasks."""

    @pytest.mark.asyncio
    async def test_workflow_has_nodes_from_tasks(self):
        mission = make_mission()
        tasks = [make_task(order_index=0)]
        log = make_log()

        result = StrategyResult(success=True, status="completed")
        captured, _session, _mission, _log = await run_background(result, mission, tasks, log)

        # get_mission_tasks was actually awaited and returned our task list
        assert captured["get_mission_tasks_called"] is True
        assert captured["tasks"] == tasks
        # The workflow handed to the executor is non-empty (Finding C)
        wf = captured["executed_workflow"]
        assert wf is not None
        assert len(wf.nodes) >= 1, "Workflow built with tasks=[] would have 0 nodes"
        assert str(wf.nodes[0].id) == str(TASK_ID)

    @pytest.mark.asyncio
    async def test_workflow_empty_without_tasks(self):
        """Sanity: if a mission truly has no tasks, the workflow is empty.

        Confirms the test actually exercises the empty-vs-nonempty boundary.
        """
        mission = make_mission()
        tasks = []
        log = make_log()

        result = StrategyResult(success=True, status="completed")
        captured, _session, _mission, _log = await run_background(result, mission, tasks, log)
        wf = captured["executed_workflow"]
        assert len(wf.nodes) == 0


class TestTriggerMissionStatusTransition:
    """Finding D: Mission.status transitions and completed_at is set."""

    @pytest.mark.asyncio
    async def test_success_sets_completed(self):
        mission = make_mission()
        tasks = [make_task(order_index=0)]
        log = make_log()

        result = StrategyResult(success=True, status="completed")
        _captured, _session, mission, log = await run_background(result, mission, tasks, log)

        # Mission ends COMPLETED (not stuck 'pending')
        assert mission.status == MissionStatus.COMPLETED
        # completed_at is set (not None)
        assert mission.completed_at is not None
        # TriggerLog status preserved as success
        assert log.status == "success"

    @pytest.mark.asyncio
    async def test_failure_sets_failed(self):
        mission = make_mission()
        tasks = [make_task(order_index=0)]
        log = make_log()

        result = StrategyResult(success=False, status="failed", error="boom")
        _captured, _session, mission, log = await run_background(result, mission, tasks, log)

        # Mission ends FAILED
        assert mission.status == MissionStatus.FAILED
        # completed_at is set even on failure
        assert mission.completed_at is not None
        # TriggerLog status preserved as failure
        assert log.status == "failure"
