"""TDD tests for MemoryCorrectionService (D30-60, T29 — privacy audit trail).

All tests use mocked AsyncSession — no live DB. The integration tests
for the actual ``memory_correction_events`` table live in
``test_memory_correction_models.py`` (``@pytest.mark.integration``).

Coverage:
* Construction and validation contract (event_type, actor enums)
* Persistence discipline: ``db.add`` + ``db.flush`` called,
  ``db.commit`` NOT called (per services/AGENTS.md rule 3)
* Read-side workspace isolation: ``(user_id, workspace_id)`` filter
  enforced on every read
* list_for_user pagination + optional event_type/claim_id filters
* list_for_claim chronological order + cross-tenant safety
* get_provenance summary shape + zero-event handling

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_memory_correction_service.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure DATABASE_URL is set BEFORE importing app modules that need it.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner",
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_db() -> MagicMock:
    """Build a mocked AsyncSession. The session's commit() must NOT be
    called by the service (services/AGENTS.md rule 3)."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = MagicMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_event_row(
    *,
    event_id: uuid.UUID | None = None,
    event_type: str = "view",
    actor: str = "user",
    claim_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> MagicMock:
    """Build a MagicMock that quacks like a MemoryCorrectionEvent row."""
    row = MagicMock()
    row.id = event_id or uuid.uuid4()
    row.event_type = event_type
    row.actor = actor
    row.claim_id = claim_id
    row.created_at = created_at or datetime.now(UTC)
    return row


def _chain_execute_returning(db: MagicMock, *, scalars: list[Any] | None = None, count: int | None = None) -> None:
    """Wire up ``db.execute`` to return a result mock.

    If ``count`` is provided, sets up the *count* result; otherwise
    sets up the *scalars* result. Each call to ``db.execute`` is
    considered a fresh result (one-shot mocks — the service always
    issues two queries: count, then items).
    """
    results: list[MagicMock] = []
    if count is not None:
        r = MagicMock()
        r.scalar_one.return_value = count
        results.append(r)
    if scalars is not None:
        r = MagicMock()
        r.scalars.return_value.all.return_value = scalars
        results.append(r)
    # db.execute is AsyncMock, side_effect with a list pops one per call.
    db.execute = AsyncMock(side_effect=results)


# ═══════════════════════════════════════════════════════════════════════════
# Module surface + construction
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleSurface:
    def test_memory_correction_service_importable(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        assert MemoryCorrectionService is not None

    def test_module_exports_memory_correction_service_error(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionServiceError,
        )

        assert issubclass(MemoryCorrectionServiceError, Exception)

    def test_module_exports_memory_correction_validation_error(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionValidationError,
        )

        # Must be both a domain error AND a ValueError (per pattern).
        assert issubclass(MemoryCorrectionValidationError, ValueError)
        assert issubclass(MemoryCorrectionValidationError, Exception)

    def test_constructable_with_db(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        assert svc is not None
        assert svc.db is db


# ═══════════════════════════════════════════════════════════════════════════
# record_event — happy path
# ═══════════════════════════════════════════════════════════════════════════


class TestRecordEventHappyPath:
    async def test_record_event_persists_row(self) -> None:
        from app.models.memory_correction_models import (
            MemoryCorrectionEvent,
        )
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        claim_id = uuid.uuid4()
        result = await svc.record_event(
            user_id=42,
            workspace_id="ws-1",
            event_type="view",
            claim_id=claim_id,
        )
        # The service must call db.add() with a MemoryCorrectionEvent
        # instance.
        assert db.add.called
        added = db.add.call_args[0][0]
        assert isinstance(added, MemoryCorrectionEvent)
        assert added.user_id == 42
        assert added.workspace_id == "ws-1"
        assert added.event_type == "view"
        assert added.claim_id == claim_id
        # service returns the same object
        assert result is added

    async def test_record_event_sets_user_workspace(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        await svc.record_event(
            user_id=7,
            workspace_id="ws-99",
            event_type="forget",
        )
        added = db.add.call_args[0][0]
        assert added.user_id == 7
        assert added.workspace_id == "ws-99"

    async def test_record_event_optional_claim_id(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        # No claim_id passed — should default to None.
        await svc.record_event(
            user_id=1,
            workspace_id="ws",
            event_type="export",
        )
        added = db.add.call_args[0][0]
        assert added.claim_id is None

    async def test_record_event_default_actor_is_user(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        await svc.record_event(
            user_id=1,
            workspace_id="ws",
            event_type="view",
        )
        added = db.add.call_args[0][0]
        assert added.actor == "user"

    async def test_record_event_explicit_actor(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        await svc.record_event(
            user_id=1,
            workspace_id="ws",
            event_type="view",
            actor="system",
        )
        added = db.add.call_args[0][0]
        assert added.actor == "system"

    async def test_record_event_details_stored_as_jsonb_dict(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        details = {
            "old_value": "dark_mode=true",
            "new_value": "dark_mode=false",
            "reason": "user_toggle",
        }
        await svc.record_event(
            user_id=1,
            workspace_id="ws",
            event_type="edit",
            details=details,
        )
        added = db.add.call_args[0][0]
        assert added.details == details

    async def test_record_event_source_persisted(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        await svc.record_event(
            user_id=1,
            workspace_id="ws",
            event_type="view",
            source="memory_inspector",
        )
        added = db.add.call_args[0][0]
        assert added.source == "memory_inspector"

    async def test_all_event_types_accepted(self) -> None:
        from app.models.memory_correction_models import ALL_EVENT_TYPES
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        for et in ALL_EVENT_TYPES:
            db = _make_mock_db()
            svc = MemoryCorrectionService(db)
            await svc.record_event(
                user_id=1,
                workspace_id="ws",
                event_type=et,
            )
            added = db.add.call_args[0][0]
            assert added.event_type == et

    async def test_all_actors_accepted(self) -> None:
        from app.models.memory_correction_models import ALL_ACTORS
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        for actor in ALL_ACTORS:
            db = _make_mock_db()
            svc = MemoryCorrectionService(db)
            await svc.record_event(
                user_id=1,
                workspace_id="ws",
                event_type="view",
                actor=actor,
            )
            added = db.add.call_args[0][0]
            assert added.actor == actor


# ═══════════════════════════════════════════════════════════════════════════
# record_event — validation
# ═══════════════════════════════════════════════════════════════════════════


class TestRecordEventValidation:
    async def test_record_event_validates_event_type(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
            MemoryCorrectionValidationError,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        with pytest.raises(MemoryCorrectionValidationError):
            await svc.record_event(
                user_id=1,
                workspace_id="ws",
                event_type="bogus_event",
            )
        # And nothing should have been added.
        assert not db.add.called

    async def test_record_event_invalid_event_type_is_value_error(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        with pytest.raises(ValueError):
            await svc.record_event(
                user_id=1,
                workspace_id="ws",
                event_type="bogus_event",
            )

    async def test_record_event_validates_actor(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
            MemoryCorrectionValidationError,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        with pytest.raises(MemoryCorrectionValidationError):
            await svc.record_event(
                user_id=1,
                workspace_id="ws",
                event_type="view",
                actor="bogus_actor",
            )
        # And nothing should have been added.
        assert not db.add.called

    async def test_record_event_invalid_actor_is_value_error(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        with pytest.raises(ValueError):
            await svc.record_event(
                user_id=1,
                workspace_id="ws",
                event_type="view",
                actor="bogus_actor",
            )


# ═══════════════════════════════════════════════════════════════════════════
# record_event — discipline
# ═══════════════════════════════════════════════════════════════════════════


class TestRecordEventDiscipline:
    async def test_record_event_does_not_commit(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        await svc.record_event(
            user_id=1,
            workspace_id="ws",
            event_type="view",
        )
        assert not db.commit.called, (
            "service must NOT call db.commit() — caller owns the " "transaction (services/AGENTS.md rule 3)"
        )

    async def test_record_event_flushes_for_id_visibility(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        await svc.record_event(
            user_id=1,
            workspace_id="ws",
            event_type="view",
        )
        assert db.flush.await_count >= 1, "service must call db.flush() so caller can observe the new id"

    async def test_record_event_refreshes_row(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        await svc.record_event(
            user_id=1,
            workspace_id="ws",
            event_type="view",
        )
        assert db.refresh.await_count >= 1


# ═══════════════════════════════════════════════════════════════════════════
# list_for_user — workspace isolation
# ═══════════════════════════════════════════════════════════════════════════


class TestListForUserIsolation:
    async def test_list_for_user_scopes_query_with_user_and_workspace(
        self,
    ) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        _chain_execute_returning(db, count=0, scalars=[])
        svc = MemoryCorrectionService(db)
        await svc.list_for_user(
            user_id=42,
            workspace_id="ws-99",
        )
        # Both queries (count + items) must reference user_id and
        # workspace_id in the WHERE clause.
        for call in db.execute.await_args_list:
            stmt = call.args[0]
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            assert "user_id" in compiled
            assert "workspace_id" in compiled
            assert "42" in compiled
            assert "ws-99" in compiled

    async def test_list_for_user_returns_count_and_items(
        self,
    ) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        ev1 = _make_event_row(event_type="view")
        ev2 = _make_event_row(event_type="edit")
        _chain_execute_returning(db, count=2, scalars=[ev1, ev2])
        svc = MemoryCorrectionService(db)
        items, total = await svc.list_for_user(
            user_id=1,
            workspace_id="ws",
        )
        assert total == 2
        assert items == [ev1, ev2]

    async def test_list_for_user_empty(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        _chain_execute_returning(db, count=0, scalars=[])
        svc = MemoryCorrectionService(db)
        items, total = await svc.list_for_user(
            user_id=1,
            workspace_id="ws",
        )
        assert total == 0
        assert items == []


# ═══════════════════════════════════════════════════════════════════════════
# list_for_user — optional filters
# ═══════════════════════════════════════════════════════════════════════════


class TestListForUserFilters:
    async def test_list_for_user_filters_by_event_type(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        _chain_execute_returning(db, count=0, scalars=[])
        svc = MemoryCorrectionService(db)
        await svc.list_for_user(
            user_id=1,
            workspace_id="ws",
            event_type="forget",
        )
        # Both queries (count + items) must filter by event_type.
        for call in db.execute.await_args_list:
            stmt = call.args[0]
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            assert "forget" in compiled

    async def test_list_for_user_filters_by_claim_id(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        _chain_execute_returning(db, count=0, scalars=[])
        svc = MemoryCorrectionService(db)
        claim_id = uuid.uuid4()
        await svc.list_for_user(
            user_id=1,
            workspace_id="ws",
            claim_id=claim_id,
        )
        # Both queries (count + items) must reference claim_id.
        for call in db.execute.await_args_list:
            stmt = call.args[0]
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            assert "claim_id" in compiled
            # Postgres UUID column drops the dashes in literal_binds.
            assert str(claim_id).replace("-", "") in compiled

    async def test_list_for_user_pagination(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        _chain_execute_returning(db, count=0, scalars=[])
        svc = MemoryCorrectionService(db)
        await svc.list_for_user(
            user_id=1,
            workspace_id="ws",
            limit=10,
            offset=20,
        )
        # The items query (the second execute call) must include
        # LIMIT 10 and OFFSET 20.
        items_stmt_call = db.execute.await_args_list[1]
        stmt = items_stmt_call.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "10" in compiled
        assert "20" in compiled

    async def test_list_for_user_validates_event_type(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
            MemoryCorrectionValidationError,
        )

        db = _make_mock_db()
        svc = MemoryCorrectionService(db)
        with pytest.raises(MemoryCorrectionValidationError):
            await svc.list_for_user(
                user_id=1,
                workspace_id="ws",
                event_type="bogus",
            )
        # No query should have been issued.
        assert not db.execute.called


# ═══════════════════════════════════════════════════════════════════════════
# list_for_claim
# ═══════════════════════════════════════════════════════════════════════════


class TestListForClaim:
    async def test_list_for_claim_returns_chronological_order(
        self,
    ) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        # Service is expected to order by created_at DESC.
        ev_old = _make_event_row(event_type="create")
        ev_mid = _make_event_row(event_type="view")
        ev_new = _make_event_row(event_type="edit")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [
            ev_new,
            ev_mid,
            ev_old,
        ]
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryCorrectionService(db)
        events = await svc.list_for_claim(
            user_id=1,
            workspace_id="ws",
            claim_id=uuid.uuid4(),
        )
        assert events == [ev_new, ev_mid, ev_old]

    async def test_list_for_claim_scopes_query_with_user_and_workspace(
        self,
    ) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryCorrectionService(db)
        claim_id = uuid.uuid4()
        await svc.list_for_claim(
            user_id=42,
            workspace_id="ws-99",
            claim_id=claim_id,
        )
        # Inspect the WHERE clause.
        stmt = db.execute.await_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "user_id" in compiled
        assert "workspace_id" in compiled
        assert "claim_id" in compiled
        assert "42" in compiled
        assert "ws-99" in compiled
        # Postgres UUID column drops the dashes in literal_binds.
        assert str(claim_id).replace("-", "") in compiled

    async def test_list_for_claim_orders_by_created_at_desc(
        self,
    ) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryCorrectionService(db)
        await svc.list_for_claim(
            user_id=1,
            workspace_id="ws",
            claim_id=uuid.uuid4(),
        )
        # The ORDER BY clause must reference created_at DESC.
        stmt = db.execute.await_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "created_at" in compiled
        # DESC must appear in the order-by spec.
        assert "DESC" in compiled.upper()

    async def test_list_for_claim_empty(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryCorrectionService(db)
        events = await svc.list_for_claim(
            user_id=1,
            workspace_id="ws",
            claim_id=uuid.uuid4(),
        )
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════
# get_provenance
# ═══════════════════════════════════════════════════════════════════════════


class TestGetProvenance:
    async def test_get_provenance_returns_summary_shape(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        # Three events, ordered by created_at DESC: edit, view, create
        ev_recent = _make_event_row(event_type="edit", actor="user")
        ev_mid = _make_event_row(event_type="view", actor="user")
        ev_first = _make_event_row(event_type="create", actor="system")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [
            ev_recent,
            ev_mid,
            ev_first,
        ]
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryCorrectionService(db)
        claim_id = uuid.uuid4()
        prov = await svc.get_provenance(
            user_id=1,
            workspace_id="ws",
            claim_id=claim_id,
        )
        # Required keys.
        assert "claim_id" in prov
        assert "event_count" in prov
        assert "first_event_at" in prov
        assert "last_event_at" in prov
        assert "last_event_type" in prov
        assert "last_actor" in prov
        assert "events_by_type" in prov
        # claim_id should be the stringified UUID.
        assert prov["claim_id"] == str(claim_id)

    async def test_get_provenance_counts_events_by_type(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        # Three views, one edit, two forgets — 6 events total.
        events = [
            _make_event_row(event_type="forget"),
            _make_event_row(event_type="forget"),
            _make_event_row(event_type="edit"),
            _make_event_row(event_type="view"),
            _make_event_row(event_type="view"),
            _make_event_row(event_type="view"),
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = events
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryCorrectionService(db)
        prov = await svc.get_provenance(
            user_id=1,
            workspace_id="ws",
            claim_id=uuid.uuid4(),
        )
        assert prov["event_count"] == 6
        assert prov["events_by_type"]["view"] == 3
        assert prov["events_by_type"]["edit"] == 1
        assert prov["events_by_type"]["forget"] == 2
        # Other buckets should be zero.
        for et in ("create", "delete", "inspect", "export", "pause", "resume"):
            assert prov["events_by_type"][et] == 0, (
                f"events_by_type[{et!r}] must be 0 (stable UI); " f"got {prov['events_by_type'][et]}"
            )

    async def test_get_provenance_first_and_last_event(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        ts_old = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        ts_mid = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        ts_new = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ev_old = _make_event_row(event_type="create", actor="system", created_at=ts_old)
        ev_mid = _make_event_row(event_type="view", actor="user", created_at=ts_mid)
        ev_new = _make_event_row(event_type="edit", actor="admin", created_at=ts_new)
        # DESC order.
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [
            ev_new,
            ev_mid,
            ev_old,
        ]
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryCorrectionService(db)
        prov = await svc.get_provenance(
            user_id=1,
            workspace_id="ws",
            claim_id=uuid.uuid4(),
        )
        assert prov["event_count"] == 3
        assert prov["last_event_at"] == ts_new
        assert prov["first_event_at"] == ts_old
        assert prov["last_event_type"] == "edit"
        assert prov["last_actor"] == "admin"

    async def test_get_provenance_handles_no_events(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryCorrectionService(db)
        claim_id = uuid.uuid4()
        prov = await svc.get_provenance(
            user_id=1,
            workspace_id="ws",
            claim_id=claim_id,
        )
        assert prov["claim_id"] == str(claim_id)
        assert prov["event_count"] == 0
        assert prov["first_event_at"] is None
        assert prov["last_event_at"] is None
        assert prov["last_event_type"] is None
        assert prov["last_actor"] is None
        # Stable bucket map — every known event type shows up with 0.
        for et in (
            "view",
            "edit",
            "delete",
            "forget",
            "create",
            "inspect",
            "export",
            "pause",
            "resume",
        ):
            assert prov["events_by_type"][et] == 0

    async def test_get_provenance_uses_workspace_isolation(self) -> None:
        from app.services.memory_correction_service import (
            MemoryCorrectionService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryCorrectionService(db)
        await svc.get_provenance(
            user_id=42,
            workspace_id="ws-99",
            claim_id=uuid.uuid4(),
        )
        # The underlying list_for_claim query must scope by
        # (user_id, workspace_id) — that's the cross-tenant safety
        # gate. Confirm by inspecting the executed statement.
        stmt = db.execute.await_args.args[0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "user_id" in compiled
        assert "workspace_id" in compiled
        assert "42" in compiled
        assert "ws-99" in compiled
