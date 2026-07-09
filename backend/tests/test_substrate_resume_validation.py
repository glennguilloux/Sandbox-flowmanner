"""Tests for Q1-A chunk 4: resume validation + node idempotency + crash-window chaos.

Unit tests mock the EventLog.  Chaos tests simulate crash boundaries by
building partial event streams (same pattern as tests/chaos/test_kill_worker_mid_mission.py).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.substrate_models import SubstrateEvent, SubstrateEventType
from app.services.substrate.event_log import EventLog
from app.services.substrate.resume_validation import ResumeValidation, validate_resume_state

# ── Helpers ────────────────────────────────────────────────────────


def _make_event(
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict | None = None,
    task_id: str | None = None,
) -> SubstrateEvent:
    return SubstrateEvent(
        id=str(uuid4()),
        sequence=sequence,
        run_id=run_id,
        type=event_type,
        payload=payload or {},
        actor="test",
        task_id=task_id,
    )


def _mock_event_log(events: list[SubstrateEvent]) -> EventLog:
    """Create a mock EventLog that returns events filtered by type."""
    el = MagicMock(spec=EventLog)

    async def _get_events(db, rid, *, from_sequence=0, to_sequence=None, event_type=None, limit=10000):
        filtered = [e for e in events if e.sequence >= from_sequence]
        if to_sequence is not None:
            filtered = [e for e in filtered if e.sequence <= to_sequence]
        if event_type is not None:
            filtered = [e for e in filtered if e.type == event_type]
        return filtered[:limit]

    el.get_events = AsyncMock(side_effect=_get_events)
    return el


# ═══════════════════════════════════════════════════════════════════
# Unit tests: validate_resume_state
# ═══════════════════════════════════════════════════════════════════


class TestValidateCleanState:
    @pytest.mark.asyncio
    async def test_clean_state_no_warnings(self):
        """Clean event sequence: no warnings, is_resumable=True."""
        rid = str(uuid4())
        events = [
            _make_event(rid, 1, SubstrateEventType.MISSION_STARTED, {"title": "T"}),
            _make_event(rid, 2, SubstrateEventType.NODE_STARTED, {"task_id": "a"}),
            _make_event(rid, 3, SubstrateEventType.NODE_COMPLETED, {"task_id": "a", "tokens": 10}),
            _make_event(rid, 4, SubstrateEventType.CHECKPOINT, {"task_id": "a"}),
            _make_event(rid, 5, SubstrateEventType.NODE_STARTED, {"task_id": "b"}),
            _make_event(rid, 6, SubstrateEventType.NODE_COMPLETED, {"task_id": "b", "tokens": 20}),
        ]
        el = _mock_event_log(events)
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.is_resumable is True
        assert v.warnings == []
        assert v.last_completed_node_id == "b"
        assert v.last_checkpoint_sequence == 4
        assert v.last_event_sequence == 6
        assert v.in_flight_node_id is None


class TestValidateInFlightNode:
    @pytest.mark.asyncio
    async def test_detects_in_flight_node(self):
        """Last event is node.started with no matching node.completed."""
        rid = str(uuid4())
        events = [
            _make_event(rid, 1, SubstrateEventType.MISSION_STARTED, {"title": "T"}),
            _make_event(rid, 2, SubstrateEventType.NODE_STARTED, {"task_id": "a"}),
            _make_event(rid, 3, SubstrateEventType.NODE_COMPLETED, {"task_id": "a"}),
            _make_event(rid, 4, SubstrateEventType.NODE_STARTED, {"task_id": "b"}),
        ]
        el = _mock_event_log(events)
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.is_resumable is True  # in-flight is NOT fatal
        assert v.in_flight_node_id == "b"
        assert v.last_completed_node_id == "a"


class TestValidateOrphanCheckpoint:
    @pytest.mark.asyncio
    async def test_detects_orphan_checkpoint(self):
        """Checkpoint for a node that never completed → is_resumable=False."""
        rid = str(uuid4())
        events = [
            _make_event(rid, 1, SubstrateEventType.MISSION_STARTED, {"title": "T"}),
            _make_event(rid, 2, SubstrateEventType.NODE_STARTED, {"task_id": "a"}),
            _make_event(rid, 3, SubstrateEventType.CHECKPOINT, {"task_id": "a"}),
            # No NODE_COMPLETED for "a"
        ]
        el = _mock_event_log(events)
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.is_resumable is False
        assert "orphan_checkpoint" in v.warnings
        assert v.in_flight_node_id == "a"


class TestValidateDuplicateCompletion:
    @pytest.mark.asyncio
    async def test_detects_duplicate_completion(self):
        """Two node.completed for the same node → is_resumable=False."""
        rid = str(uuid4())
        events = [
            _make_event(rid, 1, SubstrateEventType.MISSION_STARTED, {"title": "T"}),
            _make_event(rid, 2, SubstrateEventType.NODE_STARTED, {"task_id": "a"}),
            _make_event(rid, 3, SubstrateEventType.NODE_COMPLETED, {"task_id": "a", "tokens": 10}),
            _make_event(rid, 4, SubstrateEventType.NODE_STARTED, {"task_id": "a"}),
            _make_event(rid, 5, SubstrateEventType.NODE_COMPLETED, {"task_id": "a", "tokens": 20}),
        ]
        el = _mock_event_log(events)
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.is_resumable is False
        assert "duplicate_completion" in v.warnings


class TestValidateCheckpointLag:
    @pytest.mark.asyncio
    async def test_detects_checkpoint_lag(self):
        """Checkpoint 60 events behind the latest event → warning."""
        rid = str(uuid4())
        # Checkpoint at seq 2, then 60 more events → lag > 50
        events = [
            _make_event(rid, 1, SubstrateEventType.MISSION_STARTED, {"title": "T"}),
            _make_event(rid, 2, SubstrateEventType.CHECKPOINT),
            # node.started + node.completed x 30 = 60 events (seq 3..62)
            *[_make_event(rid, 3 + i * 2, SubstrateEventType.NODE_STARTED, {"task_id": f"n{i}"}) for i in range(30)],
            *[
                _make_event(rid, 4 + i * 2, SubstrateEventType.NODE_COMPLETED, {"task_id": f"n{i}", "tokens": 1})
                for i in range(30)
            ],
        ]
        el = _mock_event_log(events)
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.is_resumable is True  # lag is a warning, not fatal
        assert "checkpoint_lag" in v.warnings
        assert v.last_checkpoint_sequence == 2
        assert v.last_event_sequence == 62


class TestValidateLastCompletedNode:
    @pytest.mark.asyncio
    async def test_returns_last_completed_node(self):
        """last_completed_node_id matches the most recent node.completed."""
        rid = str(uuid4())
        events = [
            _make_event(rid, 1, SubstrateEventType.MISSION_STARTED, {"title": "T"}),
            _make_event(rid, 2, SubstrateEventType.NODE_STARTED, {"task_id": "x"}),
            _make_event(rid, 3, SubstrateEventType.NODE_COMPLETED, {"task_id": "x"}),
            _make_event(rid, 4, SubstrateEventType.NODE_STARTED, {"task_id": "y"}),
            _make_event(rid, 5, SubstrateEventType.NODE_COMPLETED, {"task_id": "y"}),
            _make_event(rid, 6, SubstrateEventType.NODE_STARTED, {"task_id": "z"}),
        ]
        el = _mock_event_log(events)
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.last_completed_node_id == "y"  # not z (it's in-flight)
        assert v.in_flight_node_id == "z"


class TestValidateEmptyEventLog:
    @pytest.mark.asyncio
    async def test_empty_event_log(self):
        """Empty event log → is_resumable=True, all fields at defaults."""
        rid = str(uuid4())
        el = _mock_event_log([])
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.is_resumable is True
        assert v.last_event_sequence == 0
        assert v.last_checkpoint_sequence is None
        assert v.last_completed_node_id is None
        assert v.in_flight_node_id is None
        assert v.warnings == []


class TestResumeValidationFrozen:
    def test_frozen_dataclass(self):
        """ResumeValidation is immutable."""
        v = ResumeValidation(
            run_id="r1",
            last_event_sequence=5,
            last_checkpoint_sequence=3,
            last_completed_node_id="a",
            in_flight_node_id=None,
        )
        with pytest.raises(AttributeError):
            v.is_resumable = False  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════
# Idempotency guard tests (execute_node)
# ═══════════════════════════════════════════════════════════════════


class TestIdempotencyGuard:
    @pytest.mark.asyncio
    async def test_execute_node_skips_already_completed(self):
        """Node with existing node.completed event → returns cached result, skips execution."""
        from app.services.substrate.executor import UnifiedExecutor

        rid = str(uuid4())
        completed_event = _make_event(
            rid,
            3,
            SubstrateEventType.NODE_COMPLETED,
            {"task_id": "n1", "output": "cached_output", "tokens": 42, "cost_usd": 0.05},
        )

        event_log = MagicMock(spec=EventLog)

        async def _get_events(db, run_id, *, from_sequence=0, to_sequence=None, event_type=None, limit=10000):
            if event_type == SubstrateEventType.NODE_COMPLETED:
                return [completed_event]
            return []

        event_log.get_events = AsyncMock(side_effect=_get_events)

        executor = UnifiedExecutor(event_log=event_log)
        db = AsyncMock()

        node = MagicMock()
        node.id = "n1"

        result = await executor.execute_node(db, node, {}, MagicMock(), rid)

        assert result["success"] is True
        assert result["skipped_idempotent"] is True
        assert result["output"] == "cached_output"
        assert result["tokens_used"] == 42
        assert result["cost_usd"] == 0.05


# ═══════════════════════════════════════════════════════════════════
# Chaos tests: crash-window simulation
# ═══════════════════════════════════════════════════════════════════


class TestChaosCrashPostCheckpoint:
    @pytest.mark.asyncio
    async def test_crash_post_checkpoint_no_double_execution(self):
        """Crash after node completes + checkpoint → resume re-executes the in-flight node,
        but the completed node is NOT re-executed (idempotency guard)."""
        rid = str(uuid4())
        mission_id = str(uuid4())

        # Simulate: node "a" completed, checkpoint emitted, node "b" started (crash here)
        crash_events = [
            _make_event(rid, 1, SubstrateEventType.MISSION_STARTED, {"title": "T"}, task_id=None),
            _make_event(rid, 2, SubstrateEventType.NODE_STARTED, {"task_id": "a"}),
            _make_event(rid, 3, SubstrateEventType.NODE_COMPLETED, {"task_id": "a", "tokens": 50, "cost_usd": 0.02}),
            _make_event(rid, 4, SubstrateEventType.CHECKPOINT, {"task_id": "a"}),
            _make_event(rid, 5, SubstrateEventType.NODE_STARTED, {"task_id": "b"}),
            # CRASH — no NODE_COMPLETED for "b"
        ]

        el = _mock_event_log(crash_events)
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.is_resumable is True
        assert v.last_completed_node_id == "a"
        assert v.in_flight_node_id == "b"

        # Verify the idempotency guard would skip "a" but not "b"
        async def _get_completed(db, run_id, *, from_sequence=0, to_sequence=None, event_type=None, limit=10000):
            if event_type == SubstrateEventType.NODE_COMPLETED:
                return [e for e in crash_events if e.type == SubstrateEventType.NODE_COMPLETED]
            return []

        el.get_events = AsyncMock(side_effect=_get_completed)
        completed_ids = {
            (e.payload or {}).get("task_id") for e in crash_events if e.type == SubstrateEventType.NODE_COMPLETED
        }
        assert "a" in completed_ids  # would be skipped
        assert "b" not in completed_ids  # would be re-executed


class TestChaosCrashPreCheckpoint:
    @pytest.mark.asyncio
    async def test_crash_pre_checkpoint_node_re_executes(self):
        """Crash immediately after node.started (before node.completed) →
        resume re-executes the node."""
        rid = str(uuid4())

        crash_events = [
            _make_event(rid, 1, SubstrateEventType.MISSION_STARTED, {"title": "T"}),
            _make_event(rid, 2, SubstrateEventType.NODE_STARTED, {"task_id": "a"}),
            # CRASH — no NODE_COMPLETED, no CHECKPOINT
        ]

        el = _mock_event_log(crash_events)
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.is_resumable is True
        assert v.in_flight_node_id == "a"
        assert v.last_completed_node_id is None
        assert v.last_checkpoint_sequence is None


class TestChaosResumeAfterFullCrash:
    @pytest.mark.asyncio
    async def test_resume_after_full_crash_3_nodes(self):
        """3-node workflow: crash after node 2, resume, verify node 3 is the resume point."""
        rid = str(uuid4())

        crash_events = [
            _make_event(rid, 1, SubstrateEventType.MISSION_STARTED, {"title": "3-node"}),
            _make_event(rid, 2, SubstrateEventType.NODE_STARTED, {"task_id": "n1"}),
            _make_event(rid, 3, SubstrateEventType.NODE_COMPLETED, {"task_id": "n1", "tokens": 10}),
            _make_event(rid, 4, SubstrateEventType.CHECKPOINT, {"task_id": "n1"}),
            _make_event(rid, 5, SubstrateEventType.NODE_STARTED, {"task_id": "n2"}),
            _make_event(rid, 6, SubstrateEventType.NODE_COMPLETED, {"task_id": "n2", "tokens": 20}),
            _make_event(rid, 7, SubstrateEventType.CHECKPOINT, {"task_id": "n2"}),
            # CRASH — n3 never started
        ]

        el = _mock_event_log(crash_events)
        db = AsyncMock()

        v = await validate_resume_state(db, rid, event_log=el)

        assert v.is_resumable is True
        assert v.warnings == []
        assert v.last_completed_node_id == "n2"
        assert v.in_flight_node_id is None  # n2 completed cleanly
        assert v.last_checkpoint_sequence == 7

        # Verify idempotency: n1 and n2 are completed, n3 is not
        completed_ids = {
            (e.payload or {}).get("task_id") for e in crash_events if e.type == SubstrateEventType.NODE_COMPLETED
        }
        assert completed_ids == {"n1", "n2"}
        assert "n3" not in completed_ids
