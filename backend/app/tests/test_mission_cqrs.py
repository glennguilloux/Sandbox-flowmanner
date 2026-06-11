"""Unit tests for _mission_cqrs — command/query handlers, error mapping."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.api._mission_cqrs.base import CommandHandlerBase, QueryHandlerBase
from app.api._mission_cqrs.commands import MissionCommandHandlers
from app.api._mission_cqrs.errors import map_infra_error
from app.api._mission_cqrs.queries import MissionQueryHandlers, PaginatedMissions
from app.models.mission_models import MissionTaskStatus
from app.services.mission_errors import (
    MissionError,
    MissionNotFoundError,
    MissionValidationError,
    PermanentMissionError,
    RetryableMissionError,
)

# ═══════════════════════════════════════════════════════════════════════════════
# map_infra_error — infrastructure-to-domain error mapping
# ═══════════════════════════════════════════════════════════════════════════════


class TestMapInfraError:
    def test_integrity_error_maps_to_validation_error(self):
        exc = IntegrityError("statement", {}, Exception("constraint violation"))
        result = map_infra_error(exc)
        assert isinstance(result, MissionValidationError)
        assert "constraint" in str(result).lower()

    def test_dbapi_error_invalidated_connection_maps_to_retryable(self):
        exc = DBAPIError("statement", {}, Exception("connection lost"))
        exc.connection_invalidated = True
        result = map_infra_error(exc)
        assert isinstance(result, RetryableMissionError)
        assert "transient" in str(result).lower()

    def test_dbapi_error_valid_connection_maps_to_permanent(self):
        exc = DBAPIError("statement", {}, Exception("syntax error"))
        exc.connection_invalidated = False
        result = map_infra_error(exc)
        assert isinstance(result, PermanentMissionError)

    def test_generic_exception_maps_to_permanent(self):
        exc = ValueError("something broke")
        result = map_infra_error(exc)
        assert isinstance(result, PermanentMissionError)
        assert "unhandled" in str(result).lower()

    def test_none_connection_invalidated_maps_to_permanent(self):
        """DBAPIError without connection_invalidated set at all."""
        exc = DBAPIError("statement", {}, Exception("timeout"))
        # connection_invalidated defaults to False (or None) — either way → Permanent
        result = map_infra_error(exc)
        assert isinstance(result, PermanentMissionError)


# ═══════════════════════════════════════════════════════════════════════════════
# CommandHandlerBase — transaction management (tx + wrap_command)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCommandHandlerTx:
    """Tests for the tx() async context manager and wrap_command()."""

    @pytest.fixture
    def session(self):
        s = AsyncMock()
        s.commit = AsyncMock()
        s.rollback = AsyncMock()
        return s

    @pytest.fixture
    def handler(self, session):
        return CommandHandlerBase(session)

    # ── tx() context manager ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_tx_commits_on_success(self, handler, session):
        async with handler.tx():
            pass  # no exception
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tx_rollback_on_exception(self, handler, session):
        with pytest.raises(ValueError, match="boom"):
            async with handler.tx():
                raise ValueError("boom")
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tx_rollback_on_mid_block_exception(self, handler, session):
        """commit should not be called if an exception occurs halfway."""
        call_order = []

        async def _track_commit():
            call_order.append("commit")

        async def _track_rollback():
            call_order.append("rollback")

        session.commit = _track_commit
        session.rollback = _track_rollback

        with pytest.raises(RuntimeError):
            async with handler.tx():
                raise RuntimeError()

        assert call_order == ["rollback"]
        assert "commit" not in call_order

    # ── wrap_command() ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_wrap_command_commits_and_returns_result(self, handler, session):
        async def _op():
            return 42

        result = await handler.wrap_command(_op)
        assert result == 42
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wrap_command_re_raises_mission_error_as_is(self, handler, session):
        class CustomMissionError(MissionError):
            pass

        async def _op():
            raise CustomMissionError("domain failure")

        with pytest.raises(CustomMissionError, match="domain failure"):
            await handler.wrap_command(_op)
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wrap_command_maps_integrity_error(self, handler, session):
        async def _op():
            raise IntegrityError("stmt", {}, Exception("unique violation"))

        with pytest.raises(MissionValidationError):
            await handler.wrap_command(_op)
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wrap_command_maps_invalidated_dbapi_error(self, handler, session):
        exc = DBAPIError("stmt", {}, Exception("connection gone"))
        exc.connection_invalidated = True

        async def _op():
            raise exc

        with pytest.raises(RetryableMissionError):
            await handler.wrap_command(_op)
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wrap_command_maps_generic_exception(self, handler, session):
        async def _op():
            raise TypeError("unexpected type")

        with pytest.raises(PermanentMissionError):
            await handler.wrap_command(_op)
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wrap_command_rollback_on_commit_failure(self, handler, session):
        """If commit itself raises, rollback is called in tx().__aexit__."""
        session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))

        async def _op():
            return "ok"

        with pytest.raises(PermanentMissionError):
            # commit raises RuntimeError → caught by tx() → rollback → re-raised
            # wrap_command catches the re-raise and maps it via map_infra_error
            await handler.wrap_command(_op)
        # tx() calls rollback on exception
        session.rollback.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# QueryHandlerBase — read-only handler (no commit, no rollback)
# ═══════════════════════════════════════════════════════════════════════════════


class TestQueryHandlerBase:
    @pytest.fixture
    def session(self):
        return AsyncMock()

    def test_stores_session(self, session):
        handler = QueryHandlerBase(session)
        assert handler.session is session


# ═══════════════════════════════════════════════════════════════════════════════
# MissionQueryHandlers — ownership validation
# ═══════════════════════════════════════════════════════════════════════════════


def _configure_session(s: AsyncMock) -> None:
    """Configure a mock DB session so that ``await session.execute(stmt)``
    returns a synchronous MagicMock instead of an unawaited coroutine.

    Without this, ANY method call on an AsyncMock result (e.g.
    ``result.scalar_one_or_none()``) returns a coroutine rather than a value,
    which then escapes as the return value of the async function that called it.

    Also configures ``.first()`` → None, ``.scalar()`` → 0, and
    ``.scalar_one_or_none()`` → None so that subscription-service lookups
    (``resolve_user_tier``, ``check_mission_create_allowed``) gracefully
    fall through to the free-tier / no-limit defaults instead of raising
    ``ValueError: not enough values to unpack``.
    """

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.first.return_value = None
        result.scalar.return_value = 0
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value = result
        result.all.return_value = []
        return result

    s.execute = _execute


class TestMissionQueryHandlersOwnership:
    @pytest.fixture
    def session(self):
        s = AsyncMock()
        _configure_session(s)
        return s

    @pytest.fixture
    def handlers(self, session):
        return MissionQueryHandlers(session)

    @pytest.mark.asyncio
    async def test_get_mission_success_when_owned(self, handlers, session, mocker):
        mission = MagicMock()
        mission.user_id = 1
        mission.id = "abc-123"

        mock_access = mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            return_value=mission,
        )
        result = await handlers.get_mission(user_id=1, mission_id="abc-123")
        assert result is mission
        mock_access.assert_awaited_once_with(session, "abc-123", 1)

    @pytest.mark.asyncio
    async def test_get_mission_raises_when_not_found(self, handlers, mocker):
        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            side_effect=MissionNotFoundError("Mission not found"),
        )
        with pytest.raises(MissionNotFoundError, match="Mission not found"):
            await handlers.get_mission(user_id=1, mission_id="abc-123")

    @pytest.mark.asyncio
    async def test_get_mission_raises_when_not_owned(self, handlers, mocker):
        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            side_effect=MissionNotFoundError("Mission not found"),
        )
        with pytest.raises(MissionNotFoundError, match="Mission not found"):
            await handlers.get_mission(user_id=1, mission_id="abc-123")

    @pytest.mark.asyncio
    async def test_get_mission_raises_when_both_none_and_mismatch(self, handlers, mocker):
        """Edge case: None mission should still raise the same error."""
        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            side_effect=MissionNotFoundError("Mission not found"),
        )
        with pytest.raises(MissionNotFoundError):
            await handlers.get_mission(user_id=1, mission_id="does-not-exist")


# ═══════════════════════════════════════════════════════════════════════════════
# PaginatedMissions dataclass
# ═══════════════════════════════════════════════════════════════════════════════


class TestPaginatedMissions:
    def test_pages_rounds_up(self):
        p = PaginatedMissions(items=[], total=25, page=1, per_page=10)
        assert p.pages == 3

    def test_pages_exact_division(self):
        p = PaginatedMissions(items=[], total=30, page=1, per_page=10)
        assert p.pages == 3

    def test_pages_zero_total(self):
        p = PaginatedMissions(items=[], total=0, page=1, per_page=10)
        assert p.pages == 0

    def test_pages_single_page(self):
        p = PaginatedMissions(items=[], total=5, page=1, per_page=10)
        assert p.pages == 1

    def test_pages_zero_per_page_guards(self):
        """per_page of 0 should not cause ZeroDivisionError."""
        p = PaginatedMissions(items=[], total=100, page=1, per_page=0)
        assert p.pages == 100  # 100 / 1 = 100


# ═══════════════════════════════════════════════════════════════════════════════
# MissionCommandHandlers — ownership + transaction
# ═══════════════════════════════════════════════════════════════════════════════


class TestMissionCommandHandlersOwnership:
    @pytest.fixture
    def session(self):
        s = AsyncMock()
        _configure_session(s)
        return s

    @pytest.fixture
    def user(self):
        return MagicMock(id=1, email="test@example.com")

    @pytest.mark.asyncio
    async def test_update_mission_raises_when_not_owned(self, session, user, mocker):
        handlers = MissionCommandHandlers(session)
        payload = MagicMock(
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

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            side_effect=MissionNotFoundError("Mission not found"),
        )
        with pytest.raises(MissionNotFoundError):
            await handlers.update_mission(user, "abc-123", payload)

    @pytest.mark.asyncio
    async def test_update_mission_raises_when_not_found(self, session, user, mocker):
        handlers = MissionCommandHandlers(session)
        payload = MagicMock(
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

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            side_effect=MissionNotFoundError("Mission not found"),
        )
        with pytest.raises(MissionNotFoundError):
            await handlers.update_mission(user, "abc-123", payload)

    @pytest.mark.asyncio
    async def test_delete_mission_raises_when_not_owned(self, session, user, mocker):
        handlers = MissionCommandHandlers(session)

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            side_effect=MissionNotFoundError("Mission not found"),
        )
        with pytest.raises(MissionNotFoundError):
            await handlers.delete_mission(user, "abc-123")

    @pytest.mark.asyncio
    async def test_delete_mission_raises_when_not_found(self, session, user, mocker):
        handlers = MissionCommandHandlers(session)

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            side_effect=MissionNotFoundError("Mission not found"),
        )
        with pytest.raises(MissionNotFoundError):
            await handlers.delete_mission(user, "abc-123")


# ═══════════════════════════════════════════════════════════════════════════════
# MissionCommandHandlers — success paths (wrap_command + service calls)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMissionCommandHandlersSuccess:
    @pytest.fixture
    def session(self):
        s = AsyncMock()
        _configure_session(s)
        return s

    @pytest.fixture
    def user(self):
        return MagicMock(id=1, email="test@example.com")

    @pytest.fixture
    def handlers(self, session):
        return MissionCommandHandlers(session)

    # ── create_mission ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_mission_calls_service_and_commits(self, handlers, session, user, mocker):
        payload = MagicMock(
            title="Test",
            description="desc",
            mission_type="general",
            priority="medium",
        )
        expected_mission = MagicMock()

        mock_create = mocker.patch(
            "app.api._mission_cqrs.commands.create_mission",
            new=AsyncMock(return_value=expected_mission),
        )
        result = await handlers.create_mission(user, payload)

        assert result is expected_mission
        mock_create.assert_awaited_once_with(
            session,
            title="Test",
            description="desc",
            mission_type="general",
            priority="medium",
            user_id=1,
            status="pending",
            workspace_id=None,
        )
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_mission_defaults_description(self, handlers, session, user, mocker):
        """None description is coerced to empty string."""
        payload = MagicMock(
            title="Minimal",
            description=None,
            mission_type="general",
            priority="low",
        )

        mock_create = mocker.patch(
            "app.api._mission_cqrs.commands.create_mission",
            new=AsyncMock(return_value=MagicMock()),
        )
        await handlers.create_mission(user, payload)

        _, kwargs = mock_create.call_args
        # description=None becomes ""
        assert kwargs["description"] == ""

    # ── update_mission ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_mission_calls_service_and_commits(self, handlers, session, user, mocker):
        mission = MagicMock()
        mission.user_id = 1
        updated = MagicMock()

        payload = MagicMock(
            title="Updated",
            description="new desc",
            status="running",
            priority="high",
            mission_type="research",
            error_message=None,
            results=None,
            tokens_used=100,
            actual_cost=0.05,
        )

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mock_update = mocker.patch(
            "app.api._mission_cqrs.commands.update_mission",
            new=AsyncMock(return_value=updated),
        )
        result = await handlers.update_mission(user, "abc-123", payload)

        assert result is updated
        mock_update.assert_awaited_once_with(
            session,
            "abc-123",
            title="Updated",
            description="new desc",
            status="running",
            priority="high",
            mission_type="research",
            error_message=None,
            results=None,
            tokens_used=100,
            actual_cost=0.05,
        )
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_mission_raises_when_service_returns_none(self, handlers, session, user, mocker):
        """If update_mission returns None, wrap_command raises MissionNotFoundError."""
        mission = MagicMock()
        mission.user_id = 1
        payload = MagicMock(
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

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.update_mission",
            new=AsyncMock(return_value=None),
        )
        with pytest.raises(MissionNotFoundError):
            await handlers.update_mission(user, "abc-123", payload)

        session.rollback.assert_awaited_once()

    # ── delete_mission ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_mission_calls_service_and_commits(self, handlers, session, user, mocker):
        mission = MagicMock()
        mission.user_id = 1

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mock_delete = mocker.patch(
            "app.api._mission_cqrs.commands.delete_mission",
            new=AsyncMock(return_value=True),
        )
        await handlers.delete_mission(user, "abc-123")

        mock_delete.assert_awaited_once_with(session, "abc-123", deleted_by=user.id)
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_mission_raises_when_service_returns_false(self, handlers, session, user, mocker):
        """If delete_mission returns False, wrap_command raises MissionNotFoundError."""
        mission = MagicMock()
        mission.user_id = 1

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.delete_mission",
            new=AsyncMock(return_value=False),
        )
        with pytest.raises(MissionNotFoundError):
            await handlers.delete_mission(user, "abc-123")

        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_mission_rollback_on_service_failure(self, handlers, session, user, mocker):
        """Service exception inside wrap_command triggers rollback."""
        payload = MagicMock(
            title="Test",
            description="desc",
            mission_type="general",
            priority="medium",
        )

        mocker.patch(
            "app.api._mission_cqrs.commands.create_mission",
            new=AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("boom"))),
        )
        with pytest.raises(MissionValidationError):
            await handlers.create_mission(user, payload)

        session.commit.assert_not_awaited()
        session.rollback.assert_awaited_once()

    # ── create_task ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_task_calls_service_and_commits(self, handlers, session, user, mocker):
        mission = MagicMock()
        mission.user_id = 1
        expected_task = MagicMock()

        payload = MagicMock(
            title="New Task",
            task_type="llm",
            order_index=0,
            input_data={"key": "val"},
            description="desc",
            assigned_agent_id=None,
            assigned_model="gpt-4",
        )

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mock_create = mocker.patch(
            "app.api._mission_cqrs.commands.create_mission_task",
            new=AsyncMock(return_value=expected_task),
        )
        result = await handlers.create_task(user, "abc-123", payload)

        assert result is expected_task
        mock_create.assert_awaited_once_with(
            session,
            "abc-123",
            "New Task",
            "llm",
            MissionTaskStatus.PENDING,
            0,
            {"key": "val"},
            "desc",
            None,
            "gpt-4",
        )
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_task_defaults_title_and_type(self, handlers, session, user, mocker):
        """None title → 'Untitled Task', None task_type → 'general'."""
        mission = MagicMock()
        mission.user_id = 1

        payload = MagicMock(
            title=None,
            task_type=None,
            order_index=None,
            input_data=None,
            description=None,
            assigned_agent_id=None,
            assigned_model=None,
        )

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mock_create = mocker.patch(
            "app.api._mission_cqrs.commands.create_mission_task",
            new=AsyncMock(return_value=MagicMock()),
        )
        await handlers.create_task(user, "abc-123", payload)

        # create_mission_task is called with positional args, not kwargs
        args = mock_create.call_args[0]
        assert args[2] == "Untitled Task"  # 3rd positional: title
        assert args[3] == "general"  # 4th positional: task_type

    # ── update_task ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_task_calls_execute_and_commits(self, handlers, session, user, mocker):
        mission = MagicMock()
        mission.user_id = 1

        existing_task = MagicMock()
        existing_task.status = "pending"

        # Mock session.execute to return the task
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_task
        session.execute = AsyncMock(return_value=mock_result)

        payload = MagicMock(
            status="completed",
            output_data={"result": "ok"},
            error_message=None,
            tokens_used=50,
        )

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        result = await handlers.update_task(user, "mid-1", "tid-1", payload)

        assert result is existing_task
        assert existing_task.status == "completed"
        assert existing_task.output_data == {"result": "ok"}
        assert existing_task.tokens_used == 50
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_task_partial_payload(self, handlers, session, user, mocker):
        """Only provided fields are mutated."""
        mission = MagicMock()
        mission.user_id = 1

        existing_task = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_task
        session.execute = AsyncMock(return_value=mock_result)

        payload = MagicMock(
            status="failed",
            output_data=None,
            error_message=None,
            tokens_used=None,
        )

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        await handlers.update_task(user, "mid-1", "tid-1", payload)

        assert existing_task.status == "failed"
        # output_data, error_message, tokens_used: None → not mutated
        session.commit.assert_awaited_once()

    # ── create_log ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_log_calls_service_and_commits(self, handlers, session, user, mocker):
        mission = MagicMock()
        mission.user_id = 1
        expected_log = MagicMock()

        payload = MagicMock(level="info", message="Task started")

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mock_log = mocker.patch(
            "app.api._mission_cqrs.commands.create_mission_log",
            new=AsyncMock(return_value=expected_log),
        )
        result = await handlers.create_log(user, "abc-123", payload)

        assert result is expected_log
        mock_log.assert_awaited_once_with(session, "abc-123", "info", "Task started")
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    # ── plan_mission ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_plan_mission_commits_on_success(self, handlers, session, user, mocker):
        mission = MagicMock()
        mission.user_id = 1
        mission.id = "550e8400-e29b-41d4-a716-446655440003"
        mission.status = "pending"
        mission.tokens_used = 0
        mission.started_at = None

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mock_exec_cls = mocker.patch(
            "app.api._mission_cqrs.commands.MissionExecutor",
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.get_mission_tasks",
            new=AsyncMock(return_value=[]),
        )

        executor = MagicMock()
        executor.plan_mission = AsyncMock(return_value={"success": True})
        mock_exec_cls.return_value = executor

        result = await handlers.plan_mission(user, "550e8400-e29b-41d4-a716-446655440003")

        assert result.status == "pending"
        assert result.total_tasks == 0
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_plan_mission_rollback_on_planning_failure(self, handlers, session, user, mocker):
        """If planning returns success=False, MissionValidationError + rollback."""
        mission = MagicMock()
        mission.user_id = 1
        mission.id = "550e8400-e29b-41d4-a716-446655440004"
        mission.status = "pending"
        mission.tokens_used = 0
        mission.started_at = None

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mock_exec_cls = mocker.patch(
            "app.api._mission_cqrs.commands.MissionExecutor",
        )

        executor = MagicMock()
        executor.plan_mission = AsyncMock(return_value={"success": False, "error": "bad config"})
        mock_exec_cls.return_value = executor

        with pytest.raises(MissionValidationError, match="bad config"):
            await handlers.plan_mission(user, "550e8400-e29b-41d4-a716-446655440004")

        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    # ── execute_mission ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_execute_mission_uses_default_executor(self, handlers, session, user, mocker):
        """When no feature flags are enabled, uses UnifiedExecutor via get_unified_executor()."""
        mission = MagicMock()
        mission.user_id = 1
        mission.id = "550e8400-e29b-41d4-a716-446655440005"
        mission.status = "running"
        mission.tokens_used = 100
        mission.started_at = None

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.get_mission_tasks",
            new=AsyncMock(return_value=[]),
        )
        # Phase 8.1 GA: UnifiedExecutor is the sole execution path.
        # Mock mission_to_workflow to return a dummy workflow …
        mocker.patch(
            "app.services.substrate.adapters.mission_to_workflow",
            return_value=MagicMock(),
        )
        # … and get_unified_executor to return a mock executor.
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(
            return_value=MagicMock(
                success=True,
                status="completed",
                completed_nodes=[],
                failed_nodes=[],
                data={},
                error=None,
                total_tokens=0,
                total_cost_usd=0.0,
            ),
        )
        mocker.patch(
            "app.services.substrate.executor.get_unified_executor",
            return_value=mock_executor,
        )
        mocker.patch(
            # track_event is called fire-and-forget inside execute_mission;
            # must be patched to prevent a second session.commit()
            "app.services.analytics_service.track_event",
            new=AsyncMock(return_value=None),
        )

        result = await handlers.execute_mission(user, "550e8400-e29b-41d4-a716-446655440005")

        assert result.status == "running"
        assert result.total_tokens_used == 100
        mock_executor.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
        session.rollback.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# MissionQueryHandlers — success paths (service calls + return shapes)
# ═══════════════════════════════════════════════════════════════════════════════


class TestMissionQueryHandlersSuccess:
    @pytest.fixture
    def session(self):
        s = AsyncMock()
        _configure_session(s)
        return s

    @pytest.fixture
    def handlers(self, session):
        return MissionQueryHandlers(session)

    # ── list_missions pagination ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_missions_returns_paginated_result(self, handlers, session, mocker):
        """list_missions returns PaginatedMissions with items, total, page, per_page."""
        mission = MagicMock()
        mission.user_id = 1
        # Configure attributes needed by MissionResponse.model_validate
        mission.id = "550e8400-e29b-41d4-a716-446655440000"
        mission.title = "Test"
        mission.description = "desc"
        mission.mission_type = "general"
        mission.status = "pending"
        mission.priority = "medium"
        mission.plan = {}
        mission.results = {}
        mission.error_message = None
        mission.tokens_used = 0
        mission.estimated_cost = 0.0
        mission.actual_cost = 0.0
        mission.started_at = None
        mission.completed_at = None
        mission.created_at = None
        mission.updated_at = None

        mocker.patch(
            "app.api._mission_cqrs.queries.list_missions",
            new=AsyncMock(return_value=([mission], 1)),
        )
        result = await handlers.list_missions(user_id=1, page=1, per_page=20)

        assert isinstance(result, PaginatedMissions)
        assert len(result.items) == 1
        assert result.total == 1
        assert result.page == 1
        assert result.per_page == 20

    @pytest.mark.asyncio
    async def test_list_missions_correct_offset(self, handlers, session, mocker):
        """offset = (page - 1) * per_page."""
        mock_list = mocker.patch(
            "app.api._mission_cqrs.queries.list_missions",
            new=AsyncMock(return_value=([], 0)),
        )
        await handlers.list_missions(user_id=1, page=3, per_page=10)

        # offset = (3-1)*10 = 20
        mock_list.assert_awaited_once_with(session, 1, offset=20, limit=10, workspace_id=None)

    @pytest.mark.asyncio
    async def test_list_missions_empty_result(self, handlers, mocker):
        """Zero total, empty items."""
        mocker.patch(
            "app.api._mission_cqrs.queries.list_missions",
            new=AsyncMock(return_value=([], 0)),
        )
        result = await handlers.list_missions(user_id=1, page=1, per_page=20)

        assert result.total == 0
        assert result.items == []
        assert result.pages == 0

    # ── list_tasks ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_tasks_returns_correct_tasks(self, handlers, session, mocker):
        """list_tasks returns the tasks from get_mission_tasks after ownership check."""
        mission = MagicMock()
        mission.user_id = 1
        task_a = MagicMock()
        task_b = MagicMock()

        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            new=AsyncMock(return_value=mission),
        )
        mock_tasks = mocker.patch(
            "app.api._mission_cqrs.queries.get_mission_tasks",
            new=AsyncMock(return_value=[task_a, task_b]),
        )
        result = await handlers.list_tasks(user_id=1, mission_id="abc-123")

        assert result == [task_a, task_b]
        mock_tasks.assert_awaited_once_with(session, "abc-123")

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, handlers, mocker):
        """No tasks returns empty list."""
        mission = MagicMock()
        mission.user_id = 1

        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            new=AsyncMock(return_value=mission),
        )
        mocker.patch(
            "app.api._mission_cqrs.queries.get_mission_tasks",
            new=AsyncMock(return_value=[]),
        )
        result = await handlers.list_tasks(user_id=1, mission_id="abc-123")

        assert result == []

    @pytest.mark.asyncio
    async def test_list_tasks_enforces_ownership(self, handlers, mocker):
        """list_tasks raises MissionNotFoundError for wrong owner."""
        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            side_effect=MissionNotFoundError("Mission not found"),
        )
        with pytest.raises(MissionNotFoundError):
            await handlers.list_tasks(user_id=1, mission_id="abc-123")

    # ── get_status ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_status_returns_expected_keys(self, handlers, mocker):
        """get_status returns MissionExecutionStatus with expected fields."""
        mission = MagicMock()
        mission.user_id = 1
        mission.id = "550e8400-e29b-41d4-a716-446655440001"
        mission.status = "running"
        mission.tokens_used = 500
        mission.started_at = None

        task = MagicMock()
        task.status = MissionTaskStatus.COMPLETED

        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            new=AsyncMock(return_value=mission),
        )
        mocker.patch(
            "app.api._mission_cqrs.queries.get_mission_tasks",
            new=AsyncMock(return_value=[task]),
        )
        result = await handlers.get_status(user_id=1, mission_id="550e8400-e29b-41d4-a716-446655440001")

        assert str(result.mission_id) == "550e8400-e29b-41d4-a716-446655440001"
        assert result.status == "running"
        assert result.total_tasks == 1
        assert result.completed_tasks == 1
        assert result.failed_tasks == 0
        assert result.total_tokens_used == 500

    @pytest.mark.asyncio
    async def test_get_status_mixed_tasks(self, handlers, mocker):
        """Completed + failed tasks are correctly counted."""
        mission = MagicMock()
        mission.user_id = 1
        mission.id = "550e8400-e29b-41d4-a716-446655440002"
        mission.status = "failed"
        mission.tokens_used = 100
        mission.started_at = None

        passed = MagicMock()
        passed.status = MissionTaskStatus.COMPLETED
        failed = MagicMock()
        failed.status = MissionTaskStatus.FAILED
        pending = MagicMock()
        pending.status = MissionTaskStatus.PENDING

        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            new=AsyncMock(return_value=mission),
        )
        mocker.patch(
            "app.api._mission_cqrs.queries.get_mission_tasks",
            new=AsyncMock(return_value=[passed, failed, pending]),
        )
        result = await handlers.get_status(user_id=1, mission_id="550e8400-e29b-41d4-a716-446655440002")

        assert result.total_tasks == 3
        assert result.completed_tasks == 1
        assert result.failed_tasks == 1

    # ── mission_analytics ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_mission_analytics_returns_dict_structure(self, handlers, mocker):
        """mission_analytics returns dict with summary, over_time, token_usage, failure_analysis."""
        mission = MagicMock()
        mission.user_id = 1

        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            new=AsyncMock(return_value=mission),
        )
        mocker.patch(
            "app.api._mission_cqrs.queries.get_mission_analytics",
            new=AsyncMock(return_value={"total": 5}),
        )
        mocker.patch(
            "app.api._mission_cqrs.queries.get_mission_analytics_over_time",
            new=AsyncMock(return_value=[{"date": "2026-01-01", "count": 3}]),
        )
        mocker.patch(
            "app.api._mission_cqrs.queries.get_token_usage_breakdown",
            new=AsyncMock(return_value={"total_tokens": 10000}),
        )
        mocker.patch(
            "app.api._mission_cqrs.queries.get_failure_analysis",
            new=AsyncMock(return_value={"failure_rate": 0.1}),
        )
        result = await handlers.mission_analytics(user_id=1, mission_id="abc-123", days=30)

        assert isinstance(result, dict)
        assert "summary" in result
        assert "over_time" in result
        assert "token_usage" in result
        assert "failure_analysis" in result
        assert result["summary"] == {"total": 5}
        assert result["over_time"] == [{"date": "2026-01-01", "count": 3}]
        assert result["token_usage"] == {"total_tokens": 10000}
        assert result["failure_analysis"] == {"failure_rate": 0.1}
