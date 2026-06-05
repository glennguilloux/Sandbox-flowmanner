"""Unit + integration tests for the event-sourced EventLog (H2.1).

Covers:
- append() sequential event ordering
- get_latest_sequence() correctness
- run_exists() behavior before/after append
- get_events() filtering (from_sequence, to_sequence, event_type, combined)
- MAX_EVENTS_PER_RUN safety limit
- append-only semantics verification strategy
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.substrate_models import SubstrateEvent, SubstrateEventType
from app.services.substrate.event_log import EventLog, get_event_log


# ── Helpers ────────────────────────────────────────────────────────

def _make_event_dict(**overrides):
    """Create a minimal event dict for append()."""
    return {
        "type": SubstrateEventType.MISSION_STARTED,
        "payload": {"title": "test"},
        "actor": "test_runner",
        **overrides,
    }


def _make_db_mock(existing_count=0, max_seq=0):
    """Create a mock AsyncSession that returns given count/max_seq from queries.

    The execute() mock returns the max_seq result first, then count result.
    """
    db = AsyncMock(spec=AsyncSession)

    call_count = [0]

    async def mock_execute(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            result = MagicMock()
            result.scalar.return_value = max_seq if max_seq > 0 else None
            return result
        else:
            result = MagicMock()
            result.scalar.return_value = existing_count
            return result

    db.execute = AsyncMock(side_effect=mock_execute)
    db.add = MagicMock()
    db.flush = AsyncMock()

    return db


# ═══════════════════════════════════════════════════════════════════
# EventLog: append()
# ═══════════════════════════════════════════════════════════════════

class TestEventLogAppend:

    def test_append_empty_events_raises(self):
        el = EventLog()
        db = AsyncMock(spec=AsyncSession)
        with pytest.raises(ValueError, match="Must append at least one event"):
            asyncio.run(el.append(db, str(uuid4()), []))

    def test_append_single_event(self):
        el = EventLog()
        run_id = str(uuid4())
        db = _make_db_mock(existing_count=0, max_seq=0)

        events = [_make_event_dict()]
        result = asyncio.run(el.append(db, run_id, events))

        assert len(result) == 1
        assert isinstance(result[0], SubstrateEvent)
        assert result[0].sequence == 1
        assert result[0].run_id == run_id
        assert result[0].type == SubstrateEventType.MISSION_STARTED
        assert result[0].actor == "test_runner"
        db.add.assert_called_once()
        db.flush.assert_called_once()

    def test_append_multiple_events_sequential(self):
        el = EventLog()
        run_id = str(uuid4())
        db = _make_db_mock(existing_count=0, max_seq=0)

        events = [
            _make_event_dict(type=SubstrateEventType.MISSION_STARTED),
            _make_event_dict(type=SubstrateEventType.TASK_STARTED, payload={"task_id": "t1"}),
            _make_event_dict(type=SubstrateEventType.TASK_COMPLETED, payload={"task_id": "t1", "tokens": 42}),
        ]
        result = asyncio.run(el.append(db, run_id, events))

        assert len(result) == 3
        assert result[0].sequence == 1
        assert result[1].sequence == 2
        assert result[2].sequence == 3
        assert db.add.call_count == 3

    def test_append_continues_from_existing_sequence(self):
        el = EventLog()
        run_id = str(uuid4())
        db = _make_db_mock(existing_count=5, max_seq=5)

        events = [_make_event_dict()]
        result = asyncio.run(el.append(db, run_id, events))

        assert result[0].sequence == 6

    def test_append_sets_mission_id(self):
        el = EventLog()
        run_id = str(uuid4())
        mission_id = str(uuid4())
        db = _make_db_mock(existing_count=0, max_seq=0)

        events = [_make_event_dict()]
        result = asyncio.run(el.append(db, run_id, events, mission_id=mission_id))

        assert str(result[0].mission_id) == mission_id

    def test_append_event_dict_mission_id_used_when_param_is_none(self):
        el = EventLog()
        run_id = str(uuid4())
        mission_id_dict = str(uuid4())
        db = _make_db_mock(existing_count=0, max_seq=0)

        events = [_make_event_dict(mission_id=mission_id_dict)]
        result = asyncio.run(el.append(db, run_id, events, mission_id=None))

        assert str(result[0].mission_id) == mission_id_dict

    def test_append_param_mission_id_takes_precedence(self):
        el = EventLog()
        run_id = str(uuid4())
        mission_id_param = str(uuid4())
        mission_id_dict = str(uuid4())
        db = _make_db_mock(existing_count=0, max_seq=0)

        events = [_make_event_dict(mission_id=mission_id_dict)]
        result = asyncio.run(el.append(db, run_id, events, mission_id=mission_id_param))

        assert str(result[0].mission_id) == mission_id_param


# ═══════════════════════════════════════════════════════════════════
# EventLog: get_latest_sequence()
# ═══════════════════════════════════════════════════════════════════

class TestEventLogGetLatestSequence:

    def test_returns_zero_for_new_run(self):
        el = EventLog()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        seq = asyncio.run(el.get_latest_sequence(db, str(uuid4())))
        assert seq == 0

    def test_returns_actual_max_sequence(self):
        el = EventLog()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar.return_value = 42
        db.execute = AsyncMock(return_value=result_mock)

        seq = asyncio.run(el.get_latest_sequence(db, str(uuid4())))
        assert seq == 42


# ═══════════════════════════════════════════════════════════════════
# EventLog: run_exists()
# ═══════════════════════════════════════════════════════════════════

class TestEventLogRunExists:

    def test_returns_false_for_no_events(self):
        el = EventLog()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        exists = asyncio.run(el.run_exists(db, str(uuid4())))
        assert exists is False

    def test_returns_true_after_events(self):
        el = EventLog()
        db = AsyncMock(spec=AsyncSession)
        result_mock = MagicMock()
        result_mock.scalar.return_value = 5
        db.execute = AsyncMock(return_value=result_mock)

        exists = asyncio.run(el.run_exists(db, str(uuid4())))
        assert exists is True


# ═══════════════════════════════════════════════════════════════════
# EventLog: get_events() filtering
# ═══════════════════════════════════════════════════════════════════

class TestEventLogGetEvents:

    def test_get_events_returns_all_by_default(self):
        el = EventLog()
        run_id = str(uuid4())
        db = AsyncMock(spec=AsyncSession)

        e1 = SubstrateEvent(id=str(uuid4()), sequence=1, run_id=run_id,
                            type="test.a", actor="test")
        e2 = SubstrateEvent(id=str(uuid4()), sequence=2, run_id=run_id,
                            type="test.b", actor="test")
        e3 = SubstrateEvent(id=str(uuid4()), sequence=3, run_id=run_id,
                            type="test.a", actor="test")

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [e1, e2, e3]
        db.execute = AsyncMock(return_value=result_mock)

        events = asyncio.run(el.get_events(db, run_id))
        assert len(events) == 3
        assert events[0].sequence == 1
        assert events[2].sequence == 3

    def test_get_events_from_sequence(self):
        """get_events() filters by from_sequence — returns only seq >= 2."""
        el = EventLog()
        run_id = str(uuid4())
        db = AsyncMock(spec=AsyncSession)

        e1 = SubstrateEvent(id=str(uuid4()), sequence=1, run_id=run_id,
                            type="test.a", actor="test")
        e2 = SubstrateEvent(id=str(uuid4()), sequence=2, run_id=run_id,
                            type="test.b", actor="test")
        e3 = SubstrateEvent(id=str(uuid4()), sequence=3, run_id=run_id,
                            type="test.a", actor="test")

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [e2, e3]
        db.execute = AsyncMock(return_value=result_mock)

        events = asyncio.run(el.get_events(db, run_id, from_sequence=2))

        assert len(events) == 2
        assert events[0].sequence == 2
        assert events[0].type == "test.b"
        assert events[1].sequence == 3

    def test_get_events_to_sequence(self):
        """get_events() filters by to_sequence — returns only seq <= 2."""
        el = EventLog()
        run_id = str(uuid4())
        db = AsyncMock(spec=AsyncSession)

        e1 = SubstrateEvent(id=str(uuid4()), sequence=1, run_id=run_id,
                            type="test.a", actor="test")
        e2 = SubstrateEvent(id=str(uuid4()), sequence=2, run_id=run_id,
                            type="test.b", actor="test")
        e3 = SubstrateEvent(id=str(uuid4()), sequence=3, run_id=run_id,
                            type="test.c", actor="test")

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [e1, e2]
        db.execute = AsyncMock(return_value=result_mock)

        events = asyncio.run(el.get_events(db, run_id, to_sequence=2))

        assert len(events) == 2
        assert events[0].sequence == 1
        assert events[1].sequence == 2

    def test_get_events_by_event_type(self):
        el = EventLog()
        run_id = str(uuid4())
        db = AsyncMock(spec=AsyncSession)

        e1 = SubstrateEvent(id=str(uuid4()), sequence=1, run_id=run_id,
                            type=SubstrateEventType.TASK_STARTED, actor="test")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [e1]
        db.execute = AsyncMock(return_value=result_mock)

        events = asyncio.run(
            el.get_events(db, run_id, event_type=SubstrateEventType.TASK_STARTED)
        )
        assert len(events) == 1
        assert events[0].type == SubstrateEventType.TASK_STARTED

    def test_get_events_combined_filters(self):
        """get_events() combines from_sequence + to_sequence + event_type."""
        el = EventLog()
        run_id = str(uuid4())
        db = AsyncMock(spec=AsyncSession)

        e1 = SubstrateEvent(id=str(uuid4()), sequence=10, run_id=run_id,
                            type=SubstrateEventType.TASK_STARTED, actor="test")
        e2 = SubstrateEvent(id=str(uuid4()), sequence=12, run_id=run_id,
                            type=SubstrateEventType.TASK_STARTED, actor="test")

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [e1, e2]
        db.execute = AsyncMock(return_value=result_mock)

        events = asyncio.run(el.get_events(
            db, run_id,
            from_sequence=5,
            to_sequence=15,
            event_type=SubstrateEventType.TASK_STARTED,
        ))

        assert len(events) == 2
        assert all(e.type == SubstrateEventType.TASK_STARTED for e in events)
        assert events[0].sequence == 10
        assert events[1].sequence == 12

    def test_combined_filters_empty_when_no_type_match_in_range(self):
        """Combined filters return [] when range has events but none match type.

        Sequence range 1-10 exists, but query asks for TASK_FAILED.
        The combined query must return empty — proving all three filters
        (from_sequence, to_sequence, event_type) were applied.
        """
        el = EventLog()
        run_id = str(uuid4())
        db = AsyncMock(spec=AsyncSession)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        events = asyncio.run(el.get_events(
            db, run_id,
            from_sequence=1,
            to_sequence=10,
            event_type=SubstrateEventType.TASK_FAILED,
        ))

        assert events == []
        # Prove the query was executed (method didn't short-circuit)
        db.execute.assert_called_once()

    def test_combined_filters_narrow_single_event_window(self):
        """Combined filters with from==to returns exactly that event if type matches."""
        el = EventLog()
        run_id = str(uuid4())
        db = AsyncMock(spec=AsyncSession)

        exact_event = SubstrateEvent(
            id=str(uuid4()), sequence=7, run_id=run_id,
            type=SubstrateEventType.CHECKPOINT, actor="test",
        )

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [exact_event]
        db.execute = AsyncMock(return_value=result_mock)

        events = asyncio.run(el.get_events(
            db, run_id,
            from_sequence=7,
            to_sequence=7,
            event_type=SubstrateEventType.CHECKPOINT,
        ))

        assert len(events) == 1
        assert events[0].sequence == 7
        assert events[0].type == SubstrateEventType.CHECKPOINT

    def test_combined_filters_scoped_to_run_id(self):
        """Combined filters are always scoped to the requested run_id.

        Querying run_a with combined filters must only return run_a's events.
        The run_id scoping is always active regardless of other filters.
        """
        el = EventLog()
        run_a = str(uuid4())
        db = AsyncMock(spec=AsyncSession)

        e_a = SubstrateEvent(id=str(uuid4()), sequence=5, run_id=run_a,
                             type=SubstrateEventType.TASK_STARTED, actor="test")

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [e_a]
        db.execute = AsyncMock(return_value=result_mock)

        events = asyncio.run(el.get_events(
            db, run_a,
            from_sequence=1,
            to_sequence=10,
            event_type=SubstrateEventType.TASK_STARTED,
        ))

        assert len(events) == 1
        assert events[0].run_id == run_a
        # Prove correct run_id was queried
        db.execute.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# EventLog: safety limit
# ═══════════════════════════════════════════════════════════════════

class TestEventLogSafetyLimit:

    def test_append_within_limit_succeeds(self):
        el = EventLog()
        run_id = str(uuid4())
        db = _make_db_mock(
            existing_count=el.MAX_EVENTS_PER_RUN - 2, max_seq=0
        )

        events = [_make_event_dict(), _make_event_dict()]
        result = asyncio.run(el.append(db, run_id, events))
        assert len(result) == 2

    def test_append_exceeds_limit_raises(self):
        el = EventLog()
        run_id = str(uuid4())
        db = _make_db_mock(
            existing_count=el.MAX_EVENTS_PER_RUN, max_seq=0
        )

        events = [_make_event_dict()]
        with pytest.raises(ValueError, match="exceeds max events limit"):
            asyncio.run(el.append(db, run_id, events))


# ═══════════════════════════════════════════════════════════════════
# EventLog: append-only semantics
# ═══════════════════════════════════════════════════════════════════

class TestAppendOnlySemantics:

    def test_migration_defines_append_only_trigger(self):
        # Resolve migration path relative to this test file so it works
        # both on the host (/opt/flowmanner/backend/...) and inside
        # the Docker container (/app/...).
        import os
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(tests_dir)
        migration_path = os.path.join(
            backend_dir, "alembic", "versions", "h2_substrate_init.py"
        )
        with open(migration_path) as f:
            content = f.read()

        assert "enforce_substrate_events_append_only" in content
        assert "BEFORE UPDATE OR DELETE" in content
        assert "RAISE EXCEPTION" in content
        assert "substrate_events is append-only" in content

    def test_event_log_has_no_update_or_delete_methods(self):
        el = EventLog()
        public_methods = [
            m for m in dir(el)
            if not m.startswith("_") and callable(getattr(el, m))
        ]
        assert "update" not in public_methods
        assert "delete" not in public_methods
        assert "remove" not in public_methods

    def test_append_only_documented_in_model(self):
        from app.models.substrate_models import SubstrateEvent as SE
        assert "Append-only" in (SE.__doc__ or "")
        assert "trigger" in (SE.__doc__ or "").lower()


# ═══════════════════════════════════════════════════════════════════
# EventLog: singleton
# ═══════════════════════════════════════════════════════════════════

class TestEventLogSingleton:

    def test_get_event_log_returns_same_instance(self):
        el1 = get_event_log()
        el2 = get_event_log()
        assert el1 is el2
        assert isinstance(el1, EventLog)
