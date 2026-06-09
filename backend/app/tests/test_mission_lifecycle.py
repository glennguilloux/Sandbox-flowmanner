"""Tests for mission lifecycle endpoints — migrated to CQRS imports.

Now tests CQRS handlers directly (MissionCommandHandlers lifecycle methods)
instead of the legacy _mission_handlers.py shim.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

MISSION_ID = UUID("014da489-b7f5-44f7-9e89-046a05a5ab56")
MISSION_ID_2 = UUID("115da489-b7f5-44f7-9e89-046a05a5ab57")
TEMPLATE_ID = UUID("215da489-b7f5-44f7-9e89-046a05a5ab58")


def make_mission(status="running", error_message=None):
    return SimpleNamespace(
        id=MISSION_ID,
        user_id=1,
        title="Test Mission",
        description="test",
        mission_type="general",
        status=status,
        priority="medium",
        plan=None,
        results=None,
        error_message=error_message,
        tokens_used=0,
        estimated_cost=0.0,
        actual_cost=0.0,
        started_at=None,
        completed_at=None,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        workspace_id=None,
    )


def make_user():
    return SimpleNamespace(
        id=1,
        email="user@example.com",
        username="test-user",
        full_name="Test User",
        is_active=True,
        role="user",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Pause
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandlePauseMission:
    @pytest.mark.asyncio
    async def test_pauses_running_mission(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_mission = make_mission(status="running")

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new=AsyncMock(return_value=[]),
            ),
        ):
            mock_task_result = MagicMock()
            mock_task_result.scalars().all.return_value = []
            mock_db.execute = AsyncMock(return_value=mock_task_result)

            handler = MissionCommandHandlers(mock_db)
            result = await handler.pause_mission(make_user(), MISSION_ID)
            assert result.status == MissionStatus.PAUSED

    @pytest.mark.asyncio
    async def test_raises_conflict_on_non_running(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionTransitionConflictError

        mock_mission = make_mission(status="completed")
        with patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            new=AsyncMock(return_value=mock_mission),
        ):
            handler = MissionCommandHandlers(AsyncMock())
            with pytest.raises(MissionTransitionConflictError):
                await handler.pause_mission(make_user(), MISSION_ID)

    @pytest.mark.asyncio
    async def test_cancels_running_tasks(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionTaskStatus

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_mission = make_mission(status="running")

        mock_task = MagicMock()
        mock_task.status = "running"
        mock_task_result = MagicMock()
        mock_task_result.scalars().all.return_value = [mock_task]

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new=AsyncMock(return_value=[]),
            ),
        ):
            mock_db.execute = AsyncMock(return_value=mock_task_result)
            handler = MissionCommandHandlers(mock_db)
            await handler.pause_mission(make_user(), MISSION_ID)
            assert mock_task.status == MissionTaskStatus.PENDING


# ═══════════════════════════════════════════════════════════════════════════════
# Resume
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleResumeMission:
    @pytest.mark.asyncio
    async def test_resumes_paused_mission(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_mission = make_mission(status="paused")

        with (
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new=AsyncMock(return_value=mock_mission),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new=AsyncMock(return_value=[]),
            ),
        ):
            handler = MissionCommandHandlers(mock_db)
            result = await handler.resume_mission(make_user(), MISSION_ID)
            assert result.status == MissionStatus.QUEUED

    @pytest.mark.asyncio
    async def test_raises_conflict_on_non_paused(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionTransitionConflictError

        mock_mission = make_mission(status="completed")
        with patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            new=AsyncMock(return_value=mock_mission),
        ):
            handler = MissionCommandHandlers(AsyncMock())
            with pytest.raises(MissionTransitionConflictError):
                await handler.resume_mission(make_user(), MISSION_ID)


# ═══════════════════════════════════════════════════════════════════════════════
# Retry
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleRetryMission:
    @pytest.mark.asyncio
    async def test_retries_failed_mission(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        mock_mission = make_mission(status="failed", error_message="prev")

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
            patch(
                "app.api._mission_cqrs.commands.MissionExecutor", return_value=mock_exec
            ),
        ):
            handler = MissionCommandHandlers(mock_db)
            result = await handler.retry_mission(make_user(), MISSION_ID)
            assert mock_mission.status == MissionStatus.PENDING
            assert mock_mission.error_message is None

    @pytest.mark.asyncio
    async def test_raises_conflict_on_non_failed(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionTransitionConflictError

        mock_mission = make_mission(status="completed")
        with patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            new=AsyncMock(return_value=mock_mission),
        ):
            handler = MissionCommandHandlers(AsyncMock())
            with pytest.raises(MissionTransitionConflictError):
                await handler.retry_mission(make_user(), MISSION_ID)


# ═══════════════════════════════════════════════════════════════════════════════
# Batch Abort
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleBatchAbort:
    @pytest.mark.asyncio
    async def test_batch_aborts_multiple_missions(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mock_mission = make_mission(status="running")
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [mock_mission]
        mock_db.execute = AsyncMock(return_value=mock_result)

        handler = MissionCommandHandlers(mock_db)
        result = await handler.batch_abort(make_user(), [MISSION_ID], "user_requested")
        assert result["total_aborted"] == 1

    @pytest.mark.asyncio
    async def test_raises_validation_on_invalid_reason(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionValidationError

        handler = MissionCommandHandlers(MagicMock())
        with pytest.raises(MissionValidationError):
            await handler.batch_abort(make_user(), [MISSION_ID], "bad_reason")

    @pytest.mark.asyncio
    async def test_skips_non_abortable_missions(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mock_mission = make_mission(status="completed")
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [mock_mission]
        mock_db.execute = AsyncMock(return_value=mock_result)

        handler = MissionCommandHandlers(mock_db)
        result = await handler.batch_abort(make_user(), [MISSION_ID], "user_requested")
        assert result["total_aborted"] == 0

    @pytest.mark.asyncio
    async def test_skips_other_users_missions(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mock_mission = make_mission(status="running")
        mock_mission.user_id = 999
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [mock_mission]
        mock_db.execute = AsyncMock(return_value=mock_result)

        handler = MissionCommandHandlers(mock_db)
        result = await handler.batch_abort(make_user(), [MISSION_ID], "user_requested")
        assert result["total_aborted"] == 0
        assert not result["results"][0]["aborted"]


# ═══════════════════════════════════════════════════════════════════════════════
# Create from Template
# ═══════════════════════════════════════════════════════════════════════════════


class TestHandleCreateFromTemplate:
    @pytest.mark.asyncio
    async def test_creates_mission_from_template(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        mock_template = SimpleNamespace(
            id=TEMPLATE_ID,
            name="Template Mission",
            description="From template",
            mission_type="general",
            priority="medium",
            default_plan={"tasks": []},
            default_constraints={},
            default_tasks=[
                {"title": "Task 1", "description": "First task", "task_type": "llm"},
            ],
        )
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        handler = MissionCommandHandlers(mock_db)
        result = await handler.create_from_template(make_user(), TEMPLATE_ID)
        assert result.title == "Template Mission"
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_template(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.services.mission_errors import MissionNotFoundError

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars().first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        handler = MissionCommandHandlers(mock_db)
        with pytest.raises(MissionNotFoundError):
            await handler.create_from_template(make_user(), TEMPLATE_ID)
