"""Tests for plan candidate selection round-trip wiring.

Covers:
- Schema validation (selected_plan_id field, SelectPlanCandidateRequest)
- _rebuild_tasks_from_candidate helper
- select_plan_candidate command
- Inline hooks in execute_mission and execute_async
"""

import os
import uuid as uuid_mod
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

# Resolve forward refs for all schema models used in tests (required because
# schemas use `from __future__ import annotations` which defers all type eval).
from app.models.mission_models import MissionStatus, MissionTaskStatus
from app.schemas.mission import MissionExecutionStatus, MissionTaskResponse

_ns = {"uuid": uuid_mod, "datetime": datetime, "MissionTaskStatus": MissionTaskStatus, "MissionStatus": MissionStatus}
MissionTaskResponse.model_rebuild(_types_namespace=_ns)
MissionExecutionStatus.model_rebuild(_types_namespace=_ns)


# ── Schema tests ─────────────────────────────────────────────────────────────


class TestSchemaFieldOptional:
    """Test 1: MissionExecuteRequest.selected_plan_id is optional."""

    def test_selected_plan_id_defaults_to_none(self):
        from app.schemas.mission import MissionExecuteRequest

        req = MissionExecuteRequest.model_validate({})
        assert req.selected_plan_id is None

    def test_selected_plan_id_can_be_set(self):
        from app.schemas.mission import MissionExecuteRequest

        req = MissionExecuteRequest.model_validate({"selected_plan_id": "heuristic_v1"})
        assert req.selected_plan_id == "heuristic_v1"


class TestSelectPlanRequestRejectsUnknownField:
    """Test 2: SelectPlanCandidateRequest with extra='forbid'."""

    def test_rejects_unknown_field(self):
        from app.schemas.mission import SelectPlanCandidateRequest

        with pytest.raises(ValidationError, match="bogus"):
            SelectPlanCandidateRequest.model_validate({"plan_id": "x", "bogus": 1})

    def test_accepts_valid_payload(self):
        from app.schemas.mission import SelectPlanCandidateRequest

        req = SelectPlanCandidateRequest.model_validate({"plan_id": "heuristic_v1"})
        assert req.plan_id == "heuristic_v1"


# ── Helper tests ─────────────────────────────────────────────────────────────


class TestRebuildHelper:
    """Tests 3-5: _rebuild_tasks_from_candidate helper."""

    @pytest.mark.asyncio
    async def test_unknown_candidate_returns_none(self):
        """Test 3: Unknown candidate returns None, no session.add/delete called."""
        from app.api._mission_cqrs.commands import _rebuild_tasks_from_candidate

        mock_session = AsyncMock()
        # Mock the candidate query to return None
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        import uuid

        mid = uuid.uuid4()
        result = await _rebuild_tasks_from_candidate(mock_session, mid, "missing")
        assert result is None
        mock_session.delete.assert_not_called()
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_replaces_pending_tasks_only(self):
        """Test 4: Only PENDING and QUEUED tasks are deleted; COMPLETED/RUNNING untouched."""
        from app.api._mission_cqrs.commands import _rebuild_tasks_from_candidate
        from app.models.mission_models import MissionTaskStatus

        mock_session = AsyncMock()

        # Mock candidate row
        mock_cand = MagicMock()
        mock_cand.tasks_json = [
            {"title": "New task 1", "task_type": "llm"},
        ]
        mock_cand_result = MagicMock()
        mock_cand_result.scalars.return_value.first.return_value = mock_cand

        mock_session.execute = AsyncMock(return_value=mock_cand_result)

        # Mock get_mission_tasks to return tasks with mixed statuses
        pending_task = MagicMock()
        pending_task.status = MissionTaskStatus.PENDING
        completed_task = MagicMock()
        completed_task.status = MissionTaskStatus.COMPLETED
        running_task = MagicMock()
        running_task.status = MissionTaskStatus.RUNNING

        import uuid

        mid = uuid.uuid4()

        with patch(
            "app.api._mission_cqrs.commands.get_mission_tasks",
            AsyncMock(return_value=[pending_task, completed_task, running_task]),
        ):
            result = await _rebuild_tasks_from_candidate(mock_session, mid, "plan_a")

        # Only the PENDING task should have been deleted
        assert mock_session.delete.call_count == 1
        mock_session.delete.assert_called_once_with(pending_task)
        # COMPLETED and RUNNING were NOT deleted
        # Result should have 1 new task
        assert result is not None
        assert len(result) == 1
        # session.add was called once for the new task
        assert mock_session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_creates_tasks_from_candidate(self):
        """Test 5: Creates tasks with correct order_index and title from tasks_json."""
        from app.api._mission_cqrs.commands import _rebuild_tasks_from_candidate

        mock_session = AsyncMock()

        mock_cand = MagicMock()
        mock_cand.tasks_json = [
            {"title": "Analyze", "task_type": "llm", "description": "Step 1"},
            {"title": "Build", "task_type": "code", "description": "Step 2"},
            {"title": "Test", "task_type": "review", "description": "Step 3"},
        ]
        mock_cand_result = MagicMock()
        mock_cand_result.scalars.return_value.first.return_value = mock_cand
        mock_session.execute = AsyncMock(return_value=mock_cand_result)

        import uuid

        mid = uuid.uuid4()

        with patch(
            "app.api._mission_cqrs.commands.get_mission_tasks",
            AsyncMock(return_value=[]),
        ):
            result = await _rebuild_tasks_from_candidate(mock_session, mid, "plan_x")

        assert result is not None
        assert len(result) == 3
        # Verify the MissionTask objects were created correctly
        add_calls = mock_session.add.call_args_list
        assert len(add_calls) == 3
        created_tasks = [call[0][0] for call in add_calls]
        assert created_tasks[0].title == "Analyze"
        assert created_tasks[0].order_index == 0
        assert created_tasks[1].title == "Build"
        assert created_tasks[1].order_index == 1
        assert created_tasks[2].title == "Test"
        assert created_tasks[2].order_index == 2


# ── Command tests ────────────────────────────────────────────────────────────


class TestSelectPlanCandidateCommand:
    """Tests 6-7: select_plan_candidate command method."""

    @pytest.mark.asyncio
    async def test_404_on_missing_candidate(self):
        """Test 6: MissionNotFoundError raised when candidate not found."""
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionNotFoundError

        mock_session = AsyncMock()

        # Mock wrap_command to just call _op directly (like a real tx)
        async def _fake_wrap(fn):
            return await fn()

        handlers = MissionCommandHandlers(session=mock_session, audit=None)
        handlers.wrap_command = _fake_wrap

        mock_user = MagicMock()
        mock_user.id = 1

        import uuid

        mid = uuid.uuid4()
        payload = MagicMock()
        payload.plan_id = "missing"

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "app.api._mission_cqrs.commands._rebuild_tasks_from_candidate",
                AsyncMock(return_value=None),
            ),
            pytest.raises(MissionNotFoundError, match="No plan candidate"),
        ):
            await handlers.select_plan_candidate(mock_user, mid, payload)

    @pytest.mark.asyncio
    async def test_success_sets_override_and_fires_events(self):
        """Test 7: Successful selection sets plan override, fires audit + event + cache invalidation."""
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.schemas.mission import MissionTaskResponse

        mock_session = AsyncMock()
        mock_audit = MagicMock()

        async def _fake_wrap(fn):
            return await fn()

        handlers = MissionCommandHandlers(session=mock_session, audit=mock_audit)
        handlers.wrap_command = _fake_wrap

        mock_user = MagicMock()
        mock_user.id = 1

        import uuid

        mid = uuid.uuid4()
        payload = MagicMock()
        payload.plan_id = "heuristic_v1"

        # Mock rebuilt tasks (ORM objects that model_validate can consume)
        mock_task = MagicMock()
        mock_task.id = uuid.uuid4()
        mock_task.mission_id = mid
        mock_task.title = "Task 1"
        mock_task.description = "Desc"
        mock_task.task_type = "llm"
        mock_task.order_index = 0
        mock_task.assigned_agent_id = None
        mock_task.assigned_model = None
        mock_task.status = "pending"
        mock_task.input_data = None
        mock_task.output_data = None
        mock_task.dependencies = []
        mock_task.retry_count = 0
        mock_task.max_retries = 3
        mock_task.timeout_seconds = None
        mock_task.tokens_used = None
        mock_task.cost = None
        mock_task.error_message = None
        mock_task.started_at = None
        mock_task.completed_at = None
        mock_task.created_at = None

        # Mock mission row (for plan_metadata)
        mock_mission = MagicMock()
        mock_mission.plan = {"existing": "data"}
        mock_mission_result = MagicMock()
        mock_mission_result.scalars.return_value.first.return_value = mock_mission

        # First execute is for _rebuild_tasks_from_candidate's candidate query,
        # second is for the mission row query in select_plan_candidate
        # We mock at the command level instead

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                AsyncMock(return_value=MagicMock()),
            ),
            patch(
                "app.api._mission_cqrs.commands._rebuild_tasks_from_candidate",
                AsyncMock(return_value=[mock_task]),
            ),
            patch(
                "app.api._mission_cqrs.commands.invalidate_mission_cache",
                return_value=AsyncMock(),
            ),
            patch(
                "app.api._mission_cqrs.commands._schedule_fire_and_forget",
            ) as mock_schedule,
            patch("app.services.substrate.event_log.get_event_log") as mock_event_log,
        ):
            # Mock session.execute for the mission row query inside the command
            mock_session.execute = AsyncMock(return_value=mock_mission_result)

            # Mock event_log
            mock_el = MagicMock()
            mock_el.append = AsyncMock()
            mock_event_log.return_value = mock_el

            result = await handlers.select_plan_candidate(mock_user, mid, payload)

        # Verify result is list[MissionTaskResponse]
        assert isinstance(result, list)
        assert len(result) == 1
        # It should be MissionTaskResponse instances
        assert hasattr(result[0], "title")

        # Verify plan_metadata was updated
        assert mock_mission.plan["plan_selection"]["override_id"] == "heuristic_v1"

        # Verify audit was called
        mock_audit.mission_updated.assert_called_once()
        audit_kwargs = mock_audit.mission_updated.call_args[1]
        assert audit_kwargs["override_plan_id"] == "heuristic_v1"
        assert audit_kwargs["task_count"] == 1

        # Verify cache invalidation was scheduled
        mock_schedule.assert_called()


# ── Inline hook tests ────────────────────────────────────────────────────────


class TestExecuteInlineHooks:
    """Tests 8-10: Inline hooks in execute_mission and execute_async."""

    @pytest.mark.asyncio
    async def test_execute_mission_inline_unknown_plan_id_no_crash(self):
        """Test 8: Unknown selected_plan_id logs warning and proceeds with original tasks."""
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_session = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 1

        import uuid

        mid = uuid.uuid4()

        mock_mission = MagicMock()
        mock_mission.id = str(mid)
        mock_mission.status = MissionStatus.PLANNED
        mock_mission.started_at = None
        mock_mission.tokens_used = 0
        mock_mission.workspace_id = None

        mock_task = MagicMock()
        mock_task.status = MissionTaskStatus.PENDING

        payload = MagicMock()
        payload.selected_plan_id = "missing_plan"
        payload.model_preference = None

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands._rebuild_tasks_from_candidate",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                AsyncMock(return_value=[mock_task]),
            ),
            patch(
                "app.services.substrate.adapters.mission_to_workflow",
                return_value=MagicMock(),
            ),
            patch(
                "app.services.substrate.executor.get_unified_executor",
            ) as mock_executor,
        ):
            mock_unified = MagicMock()
            mock_unified.execute = AsyncMock(
                return_value=MagicMock(
                    success=True,
                    status="completed",
                    completed_nodes=[],
                    failed_nodes=[],
                    data={},
                    error=None,
                    total_tokens=0,
                    total_cost_usd=0.0,
                )
            )
            mock_executor.return_value = mock_unified

            # Mock wrap_command to run _op directly
            handlers = MissionCommandHandlers(session=mock_session, audit=None)

            async def _fake_wrap(fn):
                return await fn()

            handlers.wrap_command = _fake_wrap

            # Should NOT raise — the unknown plan_id is logged and skipped
            result = await handlers.execute_mission(mock_user, mid, payload)
            assert result is not None

    @pytest.mark.asyncio
    async def test_execute_mission_inline_rebuild_before_substrate(self):
        """Test 9: When selected_plan_id matches, _rebuild_tasks_from_candidate
        is called before get_unified_executor().execute()."""
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_session = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 1

        import uuid

        mid = uuid.uuid4()

        mock_mission = MagicMock()
        mock_mission.id = str(mid)
        mock_mission.status = MissionStatus.PLANNED
        mock_mission.started_at = None
        mock_mission.tokens_used = 0
        mock_mission.workspace_id = None

        mock_original_task = MagicMock()
        mock_original_task.status = MissionTaskStatus.PENDING

        mock_rebuilt_task = MagicMock()
        mock_rebuilt_task.status = MissionTaskStatus.PENDING

        payload = MagicMock()
        payload.selected_plan_id = "heuristic_v1"
        payload.model_preference = None

        call_order = []

        async def _mock_rebuild(*args, **kwargs):
            call_order.append("rebuild")
            return [mock_rebuilt_task]

        async def _mock_get_tasks(*args, **kwargs):
            call_order.append("get_tasks")
            return [mock_original_task]

        mock_execute_result = MagicMock()
        mock_execute_result.success = True
        mock_execute_result.status = "completed"
        mock_execute_result.completed_nodes = []
        mock_execute_result.failed_nodes = []
        mock_execute_result.data = {}
        mock_execute_result.error = None
        mock_execute_result.total_tokens = 0
        mock_execute_result.total_cost_usd = 0.0

        async def _mock_unified_execute(*args, **kwargs):
            call_order.append("unified_execute")
            return mock_execute_result

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands._rebuild_tasks_from_candidate",
                side_effect=_mock_rebuild,
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                side_effect=_mock_get_tasks,
            ),
            patch(
                "app.services.substrate.adapters.mission_to_workflow",
                return_value=MagicMock(),
            ),
            patch(
                "app.services.substrate.executor.get_unified_executor",
            ) as mock_executor,
        ):
            mock_unified = MagicMock()
            mock_unified.execute = _mock_unified_execute
            mock_executor.return_value = mock_unified

            handlers = MissionCommandHandlers(session=mock_session, audit=None)

            async def _fake_wrap(fn):
                return await fn()

            handlers.wrap_command = _fake_wrap

            # Patch fire-and-forget to avoid unawaited coroutines
            with (
                patch("app.api._mission_cqrs.commands._schedule_fire_and_forget"),
                patch("app.api._mission_cqrs.commands.dual_write_sync_run_status", return_value=AsyncMock()),
                patch("app.api._mission_cqrs.commands.dual_write_sync_blueprint", return_value=AsyncMock()),
            ):
                await handlers.execute_mission(mock_user, mid, payload)

        # Verify rebuild happened before get_tasks (which only runs if rebuild returned None)
        # and before unified_execute
        assert "rebuild" in call_order
        # Since rebuild returned tasks, get_tasks should NOT have been called
        # (the inline hook sets tasks = rebuilt, skipping get_tasks)
        # But the second get_tasks call at the end of _op WILL happen
        assert call_order.index("rebuild") < call_order.index("unified_execute")

    @pytest.mark.asyncio
    async def test_execute_async_rebuild_before_status_commit(self):
        """Test 10: In execute_async, rebuild happens before the status commit
        so the Celery worker sees the rebuilt tasks."""
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_session = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = 1

        import uuid

        mid = uuid.uuid4()

        mock_mission = MagicMock()
        mock_mission.id = str(mid)
        mock_mission.status = MissionStatus.PLANNED
        mock_mission.started_at = None
        mock_mission.tokens_used = 0
        mock_mission.workspace_id = None

        call_order = []

        async def _mock_rebuild(*args, **kwargs):
            call_order.append("rebuild")
            return [MagicMock()]

        original_commit = mock_session.commit

        async def _tracking_commit():
            call_order.append("commit")
            return None

        mock_session.commit = _tracking_commit

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands._rebuild_tasks_from_candidate",
                side_effect=_mock_rebuild,
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                AsyncMock(return_value=[]),
            ),
            patch(
                "app.tasks.mission_execution.dispatch_mission_execution",
            ),
        ):
            payload = MagicMock()
            payload.selected_plan_id = "heuristic_v1"
            payload.model_preference = None

            handlers = MissionCommandHandlers(session=mock_session, audit=None)
            await handlers.execute_async(mock_user, mid, payload)

        # Rebuild must happen before the first commit
        assert "rebuild" in call_order
        assert "commit" in call_order
        assert call_order.index("rebuild") < call_order.index("commit")
