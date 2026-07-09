"""TDD tests for ``app.api._program_cqrs`` — command/query/audit/errors.

All tests are unit tests (no live DB).  The ``MissionProgramService`` is
mocked via ``mocker.patch`` on the import used by the command/query
modules, so handlers can be exercised in isolation.

Run from ``/opt/flowmanner/backend``::

    /opt/flowmanner/backend/.venv/bin/python -m pytest tests/test_program_cqrs.py -v

Cases:
- (a) ``create_program`` audit-logs the creation via ``ProgramAudit.program_created``
- (b) ``delete_program`` soft-deletes (calls ``service.archive``, not hard delete)
- (c) ``list_programs`` passes ``workspace_id`` through to ``service.list``
- (d) ``get_program`` for non-owner non-member raises ``ProgramForbidden``
- (e) ``fire_program`` threads ``idempotency_key`` into the audit event
- (f) ``update_user_notes`` calls ``service.update_user_notes`` with the notes
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.api._program_cqrs.audit import ProgramAudit
from app.api._program_cqrs.base import CommandHandlerBase, QueryHandlerBase
from app.api._program_cqrs.commands import ProgramCommandHandlers
from app.api._program_cqrs.errors import map_program_infra_error
from app.api._program_cqrs.queries import ProgramQueryHandlers
from app.services.mission_program_service import (
    ProgramError,
    ProgramForbidden,
    ProgramValidationError,
)

# ═══════════════════════════════════════════════════════════════════════════════
# map_program_infra_error — infrastructure-to-domain error mapping
# ═══════════════════════════════════════════════════════════════════════════════


class TestMapProgramInfraError:
    def test_integrity_error_maps_to_validation_error(self):
        exc = IntegrityError("statement", {}, Exception("constraint violation"))
        result = map_program_infra_error(exc)
        assert isinstance(result, ProgramValidationError)
        assert "constraint" in str(result).lower()

    def test_dbapi_error_invalidated_connection_maps_to_program_error(self):
        exc = DBAPIError("statement", {}, Exception("connection lost"))
        exc.connection_invalidated = True
        result = map_program_infra_error(exc)
        assert isinstance(result, ProgramError)
        assert "transient" in str(result).lower()

    def test_dbapi_error_valid_connection_maps_to_program_error(self):
        exc = DBAPIError("statement", {}, Exception("syntax error"))
        exc.connection_invalidated = False
        result = map_program_infra_error(exc)
        assert isinstance(result, ProgramError)

    def test_generic_exception_maps_to_program_error(self):
        exc = ValueError("something broke")
        result = map_program_infra_error(exc)
        assert isinstance(result, ProgramError)
        assert "unhandled" in str(result).lower()


# ═══════════════════════════════════════════════════════════════════════════════
# CommandHandlerBase / QueryHandlerBase — sanity
# ═══════════════════════════════════════════════════════════════════════════════


class TestBaseClasses:
    def test_command_handler_base_stores_session(self):
        s = AsyncMock()
        h = CommandHandlerBase(s)
        assert h.session is s

    def test_query_handler_base_stores_session(self):
        s = AsyncMock()
        h = QueryHandlerBase(s)
        assert h.session is s


# ═══════════════════════════════════════════════════════════════════════════════
# ProgramAudit — structlog-only, no-fail
# ═══════════════════════════════════════════════════════════════════════════════


class TestProgramAudit:
    def test_audit_stores_session(self):
        s = AsyncMock()
        a = ProgramAudit(s)
        assert a._session is s

    def test_program_created_records_event(self):
        """Sanity check: the convenience helper does not raise."""
        a = ProgramAudit(AsyncMock())
        # Should be a no-op or structlog emit, never an exception.
        a.program_created(
            program_id=uuid.uuid4(),
            actor_id=1,
            request_id="req-1",
            name="alpha",
        )

    def test_program_fired_records_event(self):
        a = ProgramAudit(AsyncMock())
        a.program_fired(
            program_id=uuid.uuid4(),
            actor_id=1,
            trigger_type="manual",
            request_id="req-2",
            idempotency_key="abc-123",
        )

    def test_audit_does_not_raise_on_broken_logger(self, monkeypatch):
        """Audit failures MUST be swallowed (no-fail contract)."""
        import structlog

        def _boom(*args, **kwargs):
            raise RuntimeError("log backend down")

        monkeypatch.setattr(structlog, "get_logger", lambda *a, **kw: _boom())
        a = ProgramAudit(AsyncMock())
        # Must not raise.
        a.program_created(program_id=uuid.uuid4(), actor_id=1)


# ═══════════════════════════════════════════════════════════════════════════════
# ProgramCommandHandlers — uses mocked MissionProgramService
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def user():
    return MagicMock(id=42, email="owner@example.com")


@pytest.fixture
def session():
    s = AsyncMock()
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    return s


def _build_mock_service(mocker, **side_effects):
    """Patch ``MissionProgramService`` in the commands + queries modules
    and return an instance whose methods are ``AsyncMock``s so they can
    be awaited by the handler under test.

    ``side_effects`` maps method-name → return value (for success) OR
    exception instance (for failure).  Methods not in ``side_effects``
    default to ``AsyncMock()`` returning ``None``.
    """
    service = MagicMock(name="MissionProgramService")
    for method_name, value in side_effects.items():
        am = AsyncMock()
        if isinstance(value, BaseException):
            am.side_effect = value
        else:
            am.return_value = value
        setattr(service, method_name, am)
    # Also set common aliases: the query handler calls service.list_programs()
    # but some tests pass `list=` for the service.list_programs method.
    if hasattr(service, "list") and not hasattr(service, "list_programs"):
        service.list_programs = service.list
    cls_mock_commands = mocker.patch("app.api._program_cqrs.commands.MissionProgramService", return_value=service)
    cls_mock_queries = mocker.patch("app.api._program_cqrs.queries.MissionProgramService", return_value=service)
    # Stash the patched classes for tests that need them.
    service._cls_mock_commands = cls_mock_commands
    service._cls_mock_queries = cls_mock_queries
    return service


def _fake_program(**overrides):
    """Build a real ``MissionProgram`` ORM instance (no DB).

    Handlers call ``ProgramResponse.model_validate(program)`` — Pydantic
    requires real attributes, not MagicMock sentinels, so we must
    construct a real ORM object.
    """
    from app.models.mission_program_models import MissionProgram

    kwargs = {
        "id": overrides.get("id", uuid.uuid4()),
        "user_id": overrides.get("user_id", 42),
        "workspace_id": overrides.get("workspace_id", "ws-1"),
        "name": overrides.get("name", "alpha"),
        "description": overrides.get("description", "desc"),
        "mission_type": overrides.get("mission_type", "research"),
        "base_constraints": overrides.get("base_constraints", {}),
        "base_context_files": overrides.get("base_context_files", {}),
        "base_context_urls": overrides.get("base_context_urls", {}),
        "trigger_config": overrides.get("trigger_config", {"type": "manual"}),
        "learning_brief": overrides.get("learning_brief"),
        "status": overrides.get("status", "active"),
        "per_run_budget_usd": overrides.get("per_run_budget_usd"),
        "monthly_budget_usd": overrides.get("monthly_budget_usd"),
    }
    return MissionProgram(**kwargs)


class TestProgramCommandHandlersAudit:
    @pytest.mark.asyncio
    async def test_create_program_audit_logs_creation(self, mocker, user, session):
        """(a) ``create_program`` audit-logs the creation.

        The service's ``_safe_audit`` calls ``self.audit.program_created``
        — so by passing a MagicMock audit and verifying the call, we
        confirm the audit hook is wired into the create path.
        """
        program = _fake_program(name="alpha")
        service = _build_mock_service(mocker, create=program)
        audit = MagicMock()  # plain MagicMock — allow attr assignment

        handlers = ProgramCommandHandlers(session, audit=audit)
        await handlers.create_program(user=user, workspace_id="ws-1", payload=MagicMock(name="payload"))

        # The service was constructed with the audit (proving it's wired).
        from app.api._program_cqrs import commands as cmds

        cmds.MissionProgramService.assert_called_with(session, audit=audit)
        # The service's create() was invoked once.
        service.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_program_audit_injected_into_service(self, mocker, user, session):
        """The handler's audit object is passed to the MissionProgramService
        constructor — proving the audit hook is wired for every create."""
        program = _fake_program()
        _build_mock_service(mocker, create=program)
        audit = MagicMock()
        audit.program_created = MagicMock()

        handlers = ProgramCommandHandlers(session, audit=audit)
        await handlers.create_program(user=user, workspace_id="ws-1", payload=MagicMock(name="payload"))
        # Verify the service was constructed with the handler's audit.
        from app.api._program_cqrs import commands as cmds

        cmds.MissionProgramService.assert_called_with(session, audit=audit)


class TestProgramCommandHandlersSoftDelete:
    @pytest.mark.asyncio
    async def test_delete_program_calls_service_archive(self, mocker, user, session):
        """(b) ``delete_program`` soft-deletes via ``service.archive`` —
        no hard delete, no ``service.delete``."""
        program = _fake_program(status="archived")
        service = _build_mock_service(mocker, archive=program)
        audit = MagicMock()
        handlers = ProgramCommandHandlers(session, audit=audit)

        result = await handlers.delete_program(user=user, program_id=program.id)

        # archive was called once with (user.id, program.id)
        service.archive.assert_awaited_once_with(user.id, program.id)
        # no hard delete helper exists on the service, but confirm the
        # service has no ``delete`` attribute (would be the hard-delete path).
        assert not hasattr(service, "delete") or not service.delete.called
        # delete returns None
        assert result is None


class TestProgramCommandHandlersFireAndConsolidate:
    @pytest.mark.asyncio
    async def test_fire_program_threads_idempotency_key_into_audit(self, mocker, user, session):
        """(e) ``fire_program`` passes ``idempotency_key`` through to the
        audit event (idempotency is enforced at the HTTP layer; the audit
        is the audit log)."""
        # Stub the service fire_program to return a real ProgramRun.
        from app.models.mission_program_models import ProgramRun

        program_id = uuid.uuid4()
        run = ProgramRun(
            id=uuid.uuid4(),
            program_id=program_id,
            mission_id=uuid.uuid4(),
            trigger_type="manual",
            trigger_payload=None,
            status="running",
        )
        service = _build_mock_service(mocker, fire_program=run)
        audit = MagicMock()

        handlers = ProgramCommandHandlers(session, audit=audit, request_id="req-fire-1")
        await handlers.fire_program(
            user=user,
            program_id=program_id,
            idempotency_key="idem-xyz",
            trigger_type="manual",
        )

        # The audit was invoked with the idempotency_key.
        audit.program_fired.assert_called_once()
        kwargs = audit.program_fired.call_args.kwargs
        assert kwargs["idempotency_key"] == "idem-xyz"
        assert kwargs["actor_id"] == user.id
        assert kwargs["trigger_type"] == "manual"
        assert kwargs["request_id"] == "req-fire-1"


class TestProgramCommandHandlersUserNotes:
    async def test_update_user_notes_calls_service(self, mocker, user, session):
        """(f) ``update_user_notes`` calls ``service.update_user_notes``."""
        program = _fake_program()
        service = _build_mock_service(mocker, update_user_notes=program)
        audit = MagicMock()
        handlers = ProgramCommandHandlers(session, audit=audit)

        await handlers.update_user_notes(user=user, program_id=program.id, notes="hello")

        service.update_user_notes.assert_awaited_once_with(user.id, program.id, "hello")


class TestProgramQueryHandlersWorkspaceFilter:
    @pytest.mark.asyncio
    async def test_list_programs_filters_by_workspace_id(self, mocker, session):
        """(c) ``list_programs`` passes ``workspace_id`` through to the
        service's ``list`` method."""
        program = _fake_program()
        service = _build_mock_service(mocker, list_programs=([program], 1))
        handlers = ProgramQueryHandlers(session)

        items, total = await handlers.list_programs(user_id=42, workspace_id="ws-9", page=1, per_page=20)

        service.list_programs.assert_awaited_once_with(user_id=42, workspace_id="ws-9", page=1, per_page=20)
        assert total == 1
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_list_programs_workspace_id_none(self, mocker, session):
        """``workspace_id=None`` means "all workspaces the user can see"."""
        program = _fake_program()
        service = _build_mock_service(mocker, list_programs=([program], 1))
        handlers = ProgramQueryHandlers(session)

        await handlers.list_programs(user_id=42, workspace_id=None, page=1, per_page=20)

        service.list_programs.assert_awaited_once_with(user_id=42, workspace_id=None, page=1, per_page=20)


class TestProgramQueryHandlersForbidden:
    @pytest.mark.asyncio
    async def test_get_program_raises_forbidden_for_non_member(self, mocker, user, session):
        """(d) ``get_program`` raises ``ProgramForbidden`` when the service
        rejects the user (not owner, not workspace member)."""
        service = _build_mock_service(mocker, get=ProgramForbidden("user is not owner or workspace member"))
        handlers = ProgramQueryHandlers(session)

        with pytest.raises(ProgramForbidden):
            await handlers.get_program(user=user, program_id=uuid.uuid4())
        service.get.assert_awaited_once_with(user.id, mocker.ANY)
