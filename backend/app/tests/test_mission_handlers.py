"""Unit tests for CQRS mission handlers — migrated from test_mission_handlers.py.

Now imports from app.api._mission_cqrs.queries and app.api._mission_cqrs.commands
directly, patching at the CQRS module level.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

MISSION_ID = UUID("014da489-b7f5-44f7-9e89-046a05a5ab56")
TASK_ID = UUID("114da489-b7f5-44f7-9e89-046a05a5ab57")


def make_mission(status="pending"):
    return SimpleNamespace(
        id=MISSION_ID,
        user_id=1,
        workspace_id=None,
        title="Test Mission",
        description="test",
        mission_type="general",
        status=status,
        priority="medium",
        plan=None,
        results=None,
        error_message=None,
        tokens_used=0,
        estimated_cost=0.0,
        actual_cost=0.0,
        started_at=None,
        completed_at=None,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        fallback_strategy="skip",
    )


def make_user():
    return SimpleNamespace(
        id=1,
        email="user@example.com",
        username="sample-user",
        full_name="Sample User",
        is_active=True,
        role="user",
        is_pro=False,
    )


def make_pro_user():
    return SimpleNamespace(
        id=1,
        email="pro@example.com",
        username="pro-user",
        full_name="Pro User",
        is_active=True,
        role="pro",
        is_pro=True,
    )


def make_task(status="pending", order_index=0):
    return SimpleNamespace(
        id=TASK_ID,
        mission_id=MISSION_ID,
        title="Test Task",
        description="Test task desc",
        task_type="llm",
        order_index=order_index,
        status=status,
        input_data=None,
        output_data=None,
        dependencies=[],
        retry_count=0,
        max_retries=3,
        tokens_used=0,
        cost=0.0,
        error_message=None,
        started_at=None,
        completed_at=None,
        created_at="2026-01-01T00:00:00",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers — patch CQRS module-level service imports
# ═══════════════════════════════════════════════════════════════════════════════


def patch_cqrs_query(*args, **overrides):
    """Patch CQRS query module's internal service imports.

    Usage:
        with patch_cqrs_query(get_mission=mock_mission, get_mission_tasks=mock_tasks):
            ...
    """
    patches = []
    defaults = {
        "get_mission": None,
        "get_mission_logs": None,
        "get_mission_tasks": None,
        "list_missions": None,
        "get_mission_analytics": None,
        "get_mission_analytics_over_time": None,
        "get_token_usage_breakdown": None,
        "get_failure_analysis": None,
        "cache_list": None,
        "cache_active": None,
        "cache_get": None,
        "cache_get_logs": None,
        "cache_get_status": None,
        "cache_get_improvements": None,
    }
    defaults.update(overrides)
    for name, mock_val in defaults.items():
        p = patch(f"app.api._mission_cqrs.queries.{name}", new=mock_val)
        p.start()
        patches.append(p)
    return _MultiPatchContext(patches)


def patch_cqrs_command(*args, **overrides):
    """Patch CQRS command module's internal service imports."""
    patches = []
    defaults = {
        "create_mission": None,
        "update_mission": None,
        "delete_mission": None,
        "create_mission_log": None,
        "create_mission_task": None,
        "get_mission": None,
        "get_mission_tasks": None,
        "MissionExecutor": None,
        "SelfImprovementEngine": None,
        "MissionExecutionStatus": None,
        "invalidate_user_caches": None,
        "invalidate_mission_cache": None,
    }
    defaults.update(overrides)
    for name, mock_val in defaults.items():
        p = patch(f"app.api._mission_cqrs.commands.{name}", new=mock_val)
        p.start()
        patches.append(p)
    return _MultiPatchContext(patches)


class _MultiPatchContext:
    def __init__(self, patches):
        self._patches = patches

    def __enter__(self):
        return self

    def __exit__(self, *args):
        for p in self._patches:
            p.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# List / Create handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleListMissions:
    @pytest.mark.asyncio
    async def test_returns_paginated_results(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_list = AsyncMock(return_value=([make_mission()], 1))
        with (
            patch("app.api._mission_cqrs.queries.list_missions", new=mock_list),
            patch(
                "app.api._mission_cqrs.queries.cache_list",
                new=AsyncMock(return_value=None),
            ),
        ):
            handler = MissionQueryHandlers(MagicMock())
            result = await handler.list_missions(user_id=1, page=1, per_page=20)
            assert len(result.items) == 1
            assert result.total == 1
            assert result.page == 1
            assert result.per_page == 20


class TestHandleCreateMission:
    @pytest.mark.asyncio
    async def test_creates_with_defaults(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.subscription_service import LimitCheckResult

        mock_created = make_mission()
        mock_create = AsyncMock(return_value=mock_created)
        mock_limit = LimitCheckResult(allowed=True)
        with (
            patch("app.api._mission_cqrs.commands.create_mission", new=mock_create),
            patch(
                "app.api._mission_cqrs.commands.invalidate_user_caches",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.subscription_service.check_mission_create_allowed",
                new=AsyncMock(return_value=mock_limit),
            ),
        ):
            payload = SimpleNamespace(
                title="New",
                description="desc",
                mission_type="general",
                priority="medium",
            )
            handler = MissionCommandHandlers(AsyncMock())
            result = await handler.create_mission(make_user(), payload)
            assert result.title == "Test Mission"


# ═══════════════════════════════════════════════════════════════════════════════
# CRUD handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleGetMission:
    @pytest.mark.asyncio
    async def test_returns_mission(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_mission = make_mission()
        with (
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
        ):
            handler = MissionQueryHandlers(MagicMock())
            result = await handler.get_mission(user_id=1, mission_id=MISSION_ID)
            assert result.id == MISSION_ID

    @pytest.mark.asyncio
    async def test_raises_not_found(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        with (
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(side_effect=MissionNotFoundError("Mission not found")),
            ),
        ):
            handler = MissionQueryHandlers(MagicMock())
            with pytest.raises(MissionNotFoundError):
                await handler.get_mission(user_id=1, mission_id=MISSION_ID)

    @pytest.mark.asyncio
    async def test_raises_on_wrong_owner(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        with (
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(side_effect=MissionNotFoundError("Access denied")),
            ),
        ):
            handler = MissionQueryHandlers(MagicMock())
            with pytest.raises(MissionNotFoundError):
                await handler.get_mission(user_id=1, mission_id=MISSION_ID)


class TestHandleUpdateMission:
    @pytest.mark.asyncio
    async def test_updates_returns_result(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_mission = make_mission()
        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.update_mission",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.invalidate_mission_cache",
                new=AsyncMock(return_value=None),
            ),
        ):
            payload = SimpleNamespace(
                title=None,
                description=None,
                status=None,
                priority=None,
                mission_type=None,
                error_message=None,
                results=None,
                tokens_used=None,
                actual_cost=None,
            )
            handler = MissionCommandHandlers(AsyncMock())
            result = await handler.update_mission(make_user(), MISSION_ID, payload)
            assert result.id == MISSION_ID

    @pytest.mark.asyncio
    async def test_raises_not_found_when_update_returns_none(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionNotFoundError

        mock_mission = make_mission()
        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.update_mission",
                new=AsyncMock(return_value=None),
            ),
        ):
            payload = SimpleNamespace(
                title=None,
                description=None,
                status=None,
                priority=None,
                mission_type=None,
                error_message=None,
                results=None,
                tokens_used=None,
                actual_cost=None,
            )
            handler = MissionCommandHandlers(AsyncMock())
            with pytest.raises(MissionNotFoundError):
                await handler.update_mission(make_user(), MISSION_ID, payload)


class TestHandleDeleteMission:
    @pytest.mark.asyncio
    async def test_returns_none_on_success(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_mission = make_mission()
        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.delete_mission",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.api._mission_cqrs.commands.invalidate_user_caches",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.commands.invalidate_mission_cache",
                new=AsyncMock(return_value=None),
            ),
        ):
            handler = MissionCommandHandlers(AsyncMock())
            await handler.delete_mission(make_user(), MISSION_ID)
            # No exception = success

    @pytest.mark.asyncio
    async def test_raises_not_found_when_delete_returns_false(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionNotFoundError

        mock_mission = make_mission()
        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.delete_mission",
                new=AsyncMock(return_value=False),
            ),
        ):
            handler = MissionCommandHandlers(AsyncMock())
            with pytest.raises(MissionNotFoundError):
                await handler.delete_mission(make_user(), MISSION_ID)


# ═══════════════════════════════════════════════════════════════════════════════
# Tasks handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleListTasks:
    @pytest.mark.asyncio
    async def test_returns_task_list(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_tasks = [make_task(order_index=0), make_task(order_index=1)]
        with (
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(return_value=make_mission()),
            ),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
            patch(
                "app.api._mission_cqrs.queries.get_mission_tasks",
                new=AsyncMock(return_value=mock_tasks),
            ),
        ):
            handler = MissionQueryHandlers(MagicMock())
            result = await handler.list_tasks(user_id=1, mission_id=MISSION_ID)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_raises_not_found_on_missing_mission(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        with (
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(side_effect=MissionNotFoundError("Mission not found")),
            ),
        ):
            handler = MissionQueryHandlers(MagicMock())
            with pytest.raises(MissionNotFoundError):
                await handler.list_tasks(user_id=1, mission_id=MISSION_ID)


class TestHandleCreateTask:
    @pytest.mark.asyncio
    async def test_creates_task(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_task = make_task()
        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=make_mission()),
            ),
            patch(
                "app.api._mission_cqrs.commands.create_mission_task",
                new=AsyncMock(return_value=mock_task),
            ),
        ):
            payload = SimpleNamespace(
                title="New Task",
                description="desc",
                task_type="llm",
                order_index=0,
                input_data={},
                dependencies=None,
                assigned_agent_id=None,
                assigned_model=None,
            )
            handler = MissionCommandHandlers(AsyncMock())
            result = await handler.create_task(make_user(), MISSION_ID, payload)
            assert result.title == "Test Task"


class TestHandleUpdateTask:
    @pytest.mark.asyncio
    async def test_updates_task_status(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_mission = make_mission()
        mock_task = MagicMock()
        mock_task.status = "pending"
        mock_task.output_data = None
        mock_task.error_message = None
        mock_task.tokens_used = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch(
            "app.api._mission_cqrs.commands.get_mission",
            new=AsyncMock(return_value=mock_mission),
        ):
            payload = SimpleNamespace(
                title=None,
                description=None,
                status="running",
                output_data=None,
                error_message=None,
                tokens_used=None,
                cost=None,
            )
            handler = MissionCommandHandlers(mock_db)
            result = await handler.update_task(make_user(), MISSION_ID, TASK_ID, payload)
            assert mock_task.status == "running"

    @pytest.mark.asyncio
    async def test_raises_not_found_on_missing_task(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionNotFoundError

        mock_mission = make_mission()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.api._mission_cqrs.commands.get_mission",
            new=AsyncMock(return_value=mock_mission),
        ):
            payload = SimpleNamespace(
                title=None,
                description=None,
                status=None,
                output_data=None,
                error_message=None,
                tokens_used=None,
                cost=None,
            )
            handler = MissionCommandHandlers(mock_db)
            with pytest.raises(MissionNotFoundError):
                await handler.update_task(make_user(), MISSION_ID, TASK_ID, payload)


# ═══════════════════════════════════════════════════════════════════════════════
# Logs handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleListLogs:
    @pytest.mark.asyncio
    async def test_returns_logs_list(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        with (
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(return_value=make_mission()),
            ),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
            patch(
                "app.api._mission_cqrs.queries.get_mission_logs",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.api._mission_cqrs.queries.cache_get_logs",
                new=AsyncMock(return_value=None),
            ),
        ):
            handler = MissionQueryHandlers(MagicMock())
            result = await handler.list_logs(user_id=1, mission_id=MISSION_ID)
            assert isinstance(result, list)


class TestHandleCreateLog:
    @pytest.mark.asyncio
    async def test_creates_log(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_log = SimpleNamespace(id=uuid4(), message="Test log")
        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=make_mission()),
            ),
            patch(
                "app.api._mission_cqrs.commands.create_mission_log",
                new=AsyncMock(return_value=mock_log),
            ),
        ):
            payload = SimpleNamespace(message="Test log", level="info")
            handler = MissionCommandHandlers(AsyncMock())
            result = await handler.create_log(make_user(), MISSION_ID, payload)
            assert result.message == "Test log"


# ═══════════════════════════════════════════════════════════════════════════════
# Planning handler
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandlePlanMission:
    @pytest.mark.asyncio
    async def test_returns_execution_status_on_success(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_mission = make_mission()
        mock_exec = MagicMock()
        mock_exec.plan_mission = AsyncMock(return_value={"success": True})

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new=AsyncMock(return_value=[]),
            ),
            patch("app.api._mission_cqrs.commands.MissionExecutor", return_value=mock_exec),
        ):
            handler = MissionCommandHandlers(AsyncMock())
            result = await handler.plan_mission(make_user(), MISSION_ID)
            assert result.mission_id == MISSION_ID

    @pytest.mark.asyncio
    async def test_raises_validation_error_on_failure(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionValidationError

        mock_mission = make_mission()
        mock_exec = MagicMock()
        mock_exec.plan_mission = AsyncMock(return_value={"success": False, "error": "Plan failed"})

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch("app.api._mission_cqrs.commands.MissionExecutor", return_value=mock_exec),
        ):
            handler = MissionCommandHandlers(AsyncMock())
            with pytest.raises(MissionValidationError):
                await handler.plan_mission(make_user(), MISSION_ID)


# ═══════════════════════════════════════════════════════════════════════════════
# Execution handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleExecuteMission:
    @pytest.mark.asyncio
    async def test_executes_and_returns_status(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.subscription_service import LimitCheckResult

        mock_mission = make_mission()
        mock_exec = MagicMock()
        mock_exec.execute_mission = AsyncMock(return_value={"success": True})
        mock_limit = LimitCheckResult(allowed=True)

        # Mock require_mission_access to return mission directly, plus all execution deps
        mock_unified = MagicMock()
        mock_unified.execute = AsyncMock(
            return_value=MagicMock(
                success=True,
                status="completed",
                completed_nodes=[],
                failed_nodes=[],
                data={},
                error=None,
            )
        )
        mock_workflow = MagicMock()
        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.services.analytics_service.track_event",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.subscription_service.check_mission_execute_allowed",
                new=AsyncMock(return_value=mock_limit),
            ),
            patch(
                "app.services.substrate.executor.get_unified_executor",
                return_value=mock_unified,
            ),
            patch(
                "app.services.substrate.adapters.mission_to_workflow",
                return_value=mock_workflow,
            ),
        ):
            handler = MissionCommandHandlers(AsyncMock())
            result = await handler.execute_mission(make_user(), MISSION_ID)
            assert result.mission_id == MISSION_ID


class TestHandleExecuteAsync:
    @pytest.mark.asyncio
    async def test_queues_and_returns_status(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus
        from app.services.subscription_service import LimitCheckResult

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_limit = LimitCheckResult(allowed=True)

        mock_mission = make_mission()
        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.tasks.mission_execution.dispatch_mission_execution",
                new=MagicMock(),
            ),
            patch(
                "app.services.subscription_service.check_mission_execute_allowed",
                new=AsyncMock(return_value=mock_limit),
            ),
        ):
            handler = MissionCommandHandlers(mock_db)
            result = await handler.execute_async(make_user(), MISSION_ID)
            assert result.status == MissionStatus.QUEUED


# ═══════════════════════════════════════════════════════════════════════════════
# Abort handler
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleAbortMission:
    @pytest.mark.asyncio
    async def test_aborts_and_returns_status(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mock_mission = make_mission(status="running")
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_mission
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.api._mission_cqrs.commands.get_mission",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new=AsyncMock(return_value=[]),
            ),
        ):
            handler = MissionCommandHandlers(mock_db)
            result = await handler.abort_mission(make_user(), MISSION_ID, "user_requested")
            assert result.status == MissionStatus.ABORTED

    @pytest.mark.asyncio
    async def test_raises_validation_on_invalid_reason(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionValidationError

        handler = MissionCommandHandlers(AsyncMock())
        with pytest.raises(MissionValidationError):
            await handler.abort_mission(make_user(), MISSION_ID, "invalid_reason")

    @pytest.mark.asyncio
    async def test_raises_conflict_on_non_abortable_status(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionTransitionConflictError

        mock_db = AsyncMock()
        mock_mission = make_mission(status="completed")
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_mission
        mock_db.execute = AsyncMock(return_value=mock_result)

        handler = MissionCommandHandlers(mock_db)
        with pytest.raises(MissionTransitionConflictError):
            await handler.abort_mission(make_user(), MISSION_ID, "user_requested")


# ═══════════════════════════════════════════════════════════════════════════════
# Status handler
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleGetStatus:
    @pytest.mark.asyncio
    async def test_returns_execution_status(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_mission = make_mission(status="running")
        with (
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
            patch(
                "app.api._mission_cqrs.queries.get_mission_tasks",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.api._mission_cqrs.queries.cache_get_status",
                new=AsyncMock(return_value=None),
            ),
        ):
            handler = MissionQueryHandlers(MagicMock())
            result = await handler.get_status(user_id=1, mission_id=MISSION_ID)
            assert result.mission_id == MISSION_ID
            assert result.status == "running"


# ═══════════════════════════════════════════════════════════════════════════════
# Active missions handler
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleActiveMissions:
    @pytest.mark.asyncio
    async def test_returns_active_list(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.api._mission_cqrs.queries.cache_active",
            new=AsyncMock(return_value=None),
        ):
            handler = MissionQueryHandlers(mock_db)
            result = await handler.list_active(user_id=1)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_raises_forbidden_for_non_pro(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionForbiddenError

        handler = MissionQueryHandlers(MagicMock())
        with pytest.raises(MissionForbiddenError):
            await handler.active_missions(user_id=1, user_role="user", is_pro=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Improvements handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleListImprovements:
    @pytest.mark.asyncio
    async def test_returns_improvements_list(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_mission = make_mission()
        mock_engine = MagicMock()
        mock_engine.get_improvements = AsyncMock(return_value=[])

        with (
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
            patch(
                "app.api._mission_cqrs.queries.cache_get_improvements",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.SelfImprovementEngine",
                return_value=mock_engine,
            ),
        ):
            handler = MissionQueryHandlers(MagicMock())
            result = await handler.list_improvements(user_id=1, mission_id=MISSION_ID)
            assert isinstance(result, list)


class TestHandleCreateImprovement:
    @pytest.mark.asyncio
    async def test_generates_strategy(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_mission = make_mission()
        mock_db = AsyncMock()
        mock_db.refresh = AsyncMock()

        mock_improvement = SimpleNamespace(
            id=uuid4(),
            mission_id=MISSION_ID,
            suggestion="test",
            priority="medium",
            status="pending",
            created_at="2026-01-01T00:00:00",
        )
        mock_engine = MagicMock()
        mock_engine.generate_strategy = AsyncMock(return_value=mock_improvement)

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.SelfImprovementEngine",
                return_value=mock_engine,
            ),
        ):
            payload = SimpleNamespace(failure_type="error", failure_context="test")
            handler = MissionCommandHandlers(mock_db)
            result = await handler.create_improvement(make_user(), MISSION_ID, payload)
            assert result.id is not None


class TestHandleApplyImprovement:
    @pytest.mark.asyncio
    async def test_applies_strategy(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_mission = make_mission()
        improvement_id = uuid4()
        mock_engine = MagicMock()
        mock_engine.apply_strategy = AsyncMock(return_value=True)

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.SelfImprovementEngine",
                return_value=mock_engine,
            ),
        ):
            handler = MissionCommandHandlers(AsyncMock())
            result = await handler.apply_improvement(make_user(), MISSION_ID, improvement_id)
            assert result is True


# ═══════════════════════════════════════════════════════════════════════════════
# Analytics handlers
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleMissionAnalytics:
    @pytest.mark.asyncio
    async def test_returns_analytics_dict(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_mission = make_mission()
        with (
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
            patch(
                "app.api._mission_cqrs.queries.get_mission_analytics",
                new=AsyncMock(return_value={"total": 1}),
            ),
            patch(
                "app.api._mission_cqrs.queries.get_mission_analytics_over_time",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.api._mission_cqrs.queries.get_token_usage_breakdown",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.api._mission_cqrs.queries.get_failure_analysis",
                new=AsyncMock(return_value={}),
            ),
        ):
            handler = MissionQueryHandlers(MagicMock())
            result = await handler.mission_analytics(user_id=1, mission_id=MISSION_ID, days=30)
            assert "summary" in result
            assert "over_time" in result
            assert "token_usage" in result
            assert "failure_analysis" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Stream handler (CQRS)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleStreamStatus:
    """MissionQueryHandlers.stream_status(): SSE streaming responses."""

    def test_returns_streaming_response(self):
        """Should return a StreamingResponse with correct media type."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_mission = make_mission(status="completed")
        with patch(
            "app.api._mission_cqrs.queries.get_mission_tasks",
            new=AsyncMock(return_value=[]),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            result = handler.stream_status(user_id=1, mission_id=MISSION_ID, initial_mission=mock_mission)

        from fastapi.responses import StreamingResponse

        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"

    def test_sets_correct_headers(self):
        """Should set cache-control, connection, and X-Accel-Buffering headers."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_mission = make_mission(status="completed")
        with patch(
            "app.api._mission_cqrs.queries.get_mission_tasks",
            new=AsyncMock(return_value=[]),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            result = handler.stream_status(user_id=1, mission_id=MISSION_ID, initial_mission=mock_mission)

        assert result.headers["Cache-Control"] == "no-cache"
        assert result.headers["Connection"] == "keep-alive"
        assert result.headers["X-Accel-Buffering"] == "no"

    @pytest.mark.asyncio
    async def test_stream_body_starts_with_data_and_ends_with_done(self):
        """Stream body should start with 'data: ' and end with 'data: [DONE]'."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_mission = make_mission(status="completed")
        with (
            patch(
                "app.api._mission_cqrs.queries.get_mission_tasks",
                new=AsyncMock(return_value=[]),
            ),
            patch("app.api._mission_cqrs.queries.use_new_reads", return_value=False),
            patch(
                "app.api._mission_cqrs.queries.require_mission_access",
                new=AsyncMock(return_value=make_mission(status="completed")),
            ),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            result = handler.stream_status(user_id=1, mission_id=MISSION_ID, initial_mission=mock_mission)

            # Collect all SSE events from the async generator
            body = ""
            async for chunk in result.body_iterator:
                body += chunk

        assert body.startswith("data: ")
        assert "data: [DONE]" in body


class TestHandleGlobalAnalytics:
    @pytest.mark.asyncio
    async def test_returns_analytics_dict(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        with patch(
            "app.api._mission_cqrs.queries.get_mission_analytics",
            new=AsyncMock(return_value={"total": 5}),
        ):
            handler = MissionQueryHandlers(MagicMock())
            result = await handler.global_analytics(user_id=1)
            assert "total" in result
