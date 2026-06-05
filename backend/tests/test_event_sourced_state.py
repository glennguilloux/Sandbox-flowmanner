"""Tests for Event-Sourced Operational State.

Verifies:
1. UnifiedExecutor is the sole execution path (Phase 8.1 GA)
2. Event history query methods exist and handle empty state
3. State reconstruction query methods exist and handle empty state
4. Abort signal propagation to UnifiedExecutor
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


class TestUnifiedExecutorGA:
    """Verify the UnifiedExecutor is the sole execution path (Phase 8.1 GA)."""

    def test_unified_executor_is_only_path(self):
        """Phase 8.1: Feature flag removed — UnifiedExecutor is always used."""
        from app.services.substrate.executor import UnifiedExecutor, get_unified_executor
        assert UnifiedExecutor is not None
        executor = get_unified_executor()
        assert isinstance(executor, UnifiedExecutor)

    def test_feature_flag_removed(self):
        """Phase 8.1: _unified_executor_enabled and _should_use_unified no longer exist."""
        import app.services.substrate.executor as executor_mod
        assert not hasattr(executor_mod, '_unified_executor_enabled')
        assert not hasattr(executor_mod, '_should_use_unified')


class TestEventHistoryQuery:
    """Test the event history query handler methods."""

    @pytest.mark.asyncio
    async def test_get_events_no_mission(self):
        """Event query with no mission should raise MissionNotFoundError."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        mock_session = AsyncMock()
        handlers = MissionQueryHandlers(mock_session)
        handlers.get_mission = AsyncMock(side_effect=MissionNotFoundError("Mission not found"))
        with pytest.raises(MissionNotFoundError):
            await handlers.get_events(1, uuid4())

    @pytest.mark.asyncio
    async def test_get_substrate_state_no_mission(self):
        """State query with no mission should raise MissionNotFoundError."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        mock_session = AsyncMock()
        handlers = MissionQueryHandlers(mock_session)
        handlers.get_mission = AsyncMock(side_effect=MissionNotFoundError("Mission not found"))
        with pytest.raises(MissionNotFoundError):
            await handlers.get_substrate_state(1, uuid4())


class TestAbortSignalPropagation:
    """Test that abort signals propagate to UnifiedExecutor."""

    def test_abort_calls_unified_executor(self):
        """abort_mission should signal UnifiedExecutor abort."""
        # This is a structural test — verify the abort method exists
        from app.services.substrate.executor import UnifiedExecutor
        assert hasattr(UnifiedExecutor, 'abort')
        assert callable(UnifiedExecutor.abort)


class TestReplayEngineIntegration:
    """Test ReplayEngine can be used for state reconstruction."""

    @pytest.mark.asyncio
    async def test_replay_engine_singleton(self):
        from app.services.substrate.replay_engine import get_replay_engine
        engine1 = get_replay_engine()
        engine2 = get_replay_engine()
        assert engine1 is engine2

    @pytest.mark.asyncio
    async def test_replay_engine_has_methods(self):
        from app.services.substrate.replay_engine import ReplayEngine
        assert hasattr(ReplayEngine, 'rebuild_state')
        assert hasattr(ReplayEngine, 'rebuild_state_at_sequence')
        assert hasattr(ReplayEngine, 'verify_determinism')
        assert hasattr(ReplayEngine, 'get_checkpoint_sequences')


class TestEventLogIntegration:
    """Test EventLog append/query interface."""

    @pytest.mark.asyncio
    async def test_event_log_singleton(self):
        from app.services.substrate.event_log import get_event_log
        log1 = get_event_log()
        log2 = get_event_log()
        assert log1 is log2

    def test_event_log_has_methods(self):
        from app.services.substrate.event_log import EventLog
        assert hasattr(EventLog, 'append')
        assert hasattr(EventLog, 'get_events')
        assert hasattr(EventLog, 'get_latest_sequence')
        assert hasattr(EventLog, 'run_exists')


class TestSubstrateEventTypes:
    """Verify all substrate event types are defined."""

    def test_all_event_types_exist(self):
        from app.models.substrate_models import SubstrateEventType
        expected = [
            "MISSION_STARTED", "MISSION_COMPLETED", "MISSION_FAILED", "MISSION_ABORTED",
            "MISSION_PAUSED", "MISSION_RESUMED",
            "TASK_STARTED", "TASK_COMPLETED", "TASK_FAILED", "TASK_RETRYING", "TASK_SKIPPED",
            "LLM_CALL", "LLM_RESPONSE",
            "TOOL_CALL", "TOOL_RESPONSE",
            "CHECKPOINT", "BUDGET_EXHAUSTED", "ERROR",
        ]
        for attr in expected:
            assert hasattr(SubstrateEventType, attr), f"Missing event type: {attr}"

    def test_event_type_values(self):
        from app.models.substrate_models import SubstrateEventType
        assert SubstrateEventType.MISSION_STARTED == "mission.started"
        assert SubstrateEventType.TASK_COMPLETED == "task.completed"
        assert SubstrateEventType.CHECKPOINT == "substrate.checkpoint"


class TestRunStateProjection:
    """Test the SubstrateRunState in-memory projection."""

    def test_run_state_apply_mission_started(self):
        from app.models.substrate_models import SubstrateRunState, SubstrateEventType
        state = SubstrateRunState(run_id="test-run")
        event = MagicMock()
        event.type = SubstrateEventType.MISSION_STARTED
        event.sequence = 1
        event.timestamp = "2026-06-05T12:00:00Z"
        event.payload = {}
        state.apply(event)
        assert state.status == "executing"

    def test_run_state_apply_task_completed(self):
        from app.models.substrate_models import SubstrateRunState, SubstrateEventType
        state = SubstrateRunState(run_id="test-run")
        event = MagicMock()
        event.type = SubstrateEventType.TASK_COMPLETED
        event.sequence = 2
        event.timestamp = "2026-06-05T12:00:00Z"
        event.payload = {"task_id": "task-1", "tokens": 100, "cost_usd": 0.01}
        state.apply(event)
        assert "task-1" in state.completed_tasks
        assert state.total_tokens == 100
        assert state.total_cost_usd == 0.01

    def test_run_state_to_dict(self):
        from app.models.substrate_models import SubstrateRunState
        state = SubstrateRunState(run_id="test-run")
        d = state.to_dict()
        assert d["run_id"] == "test-run"
        assert d["status"] == "pending"
        assert "completed_tasks" in d


class TestWorkflowModels:
    """Verify the unified Workflow models are importable."""

    def test_workflow_import(self):
        from app.services.substrate.workflow_models import Workflow, WorkflowNode, WorkflowEdge
        assert Workflow is not None
        assert WorkflowNode is not None
        assert WorkflowEdge is not None

    def test_workflow_type_enum(self):
        from app.services.substrate.workflow_models import WorkflowType
        assert WorkflowType.SOLO.value == "solo"
        assert WorkflowType.DAG.value == "dag"
        assert WorkflowType.SWARM.value == "swarm"
        assert WorkflowType.PIPELINE.value == "pipeline"
        assert WorkflowType.GRAPH.value == "graph"
        assert WorkflowType.META.value == "meta"
        assert WorkflowType.LANGGRAPH.value == "langgraph"

    def test_strategy_result(self):
        from app.services.substrate.workflow_models import StrategyResult
        r = StrategyResult(success=True, status="completed")
        assert r.success is True
        assert r.status == "completed"
        assert r.total_tokens == 0


class TestAdapters:
    """Test ORM → Workflow adapters."""

    def test_mission_to_workflow_import(self):
        from app.services.substrate.adapters import mission_to_workflow
        assert callable(mission_to_workflow)

    def test_mission_to_workflow_with_mock(self):
        from app.services.substrate.adapters import mission_to_workflow
        mission = MagicMock()
        mission.id = uuid4()
        mission.title = "Test Mission"
        mission.description = "A test"
        mission.mission_type = "solo"
        mission.user_id = 1
        mission.budget_usd = 5.0
        mission.budget_seconds = 120
        mission.actual_cost = 0.0
        mission.tokens_used = 0
        mission.plan = None

        task = MagicMock()
        task.id = uuid4()
        task.title = "Task 1"
        task.description = "Do something"
        task.task_type = "llm"
        task.status = "pending"
        task.tool_id = None
        task.assigned_model = None
        task.assigned_agent_id = None
        task.max_retries = 3
        task.dependencies = None
        task.output_data = None
        task.error_message = None
        task.retry_count = 0
        task.tokens_used = 0
        task.cost = 0.0

        workflow = mission_to_workflow(mission, [task])
        assert workflow.title == "Test Mission"
        assert len(workflow.nodes) == 1
        assert workflow.nodes[0].title == "Task 1"
