"""Unit + integration tests for the event-sourced ReplayEngine (H2.1).

Covers:
- rebuild_state() correctness on mission/task lifecycle
- rebuild_state_at_sequence() time-travel correctness
- verify_determinism() true for stable event stream
- checkpoint sequence extraction correctness
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.substrate_models import (
    SubstrateEvent,
    SubstrateEventType,
    SubstrateRunState,
)
from app.services.substrate.event_log import EventLog
from app.services.substrate.replay_engine import ReplayEngine, get_replay_engine


# ── Helpers ────────────────────────────────────────────────────────

def _make_event(
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict | None = None,
    mission_id: str | None = None,
    task_id: str | None = None,
) -> SubstrateEvent:
    """Create a SubstrateEvent with given parameters."""
    return SubstrateEvent(
        id=str(uuid4()),
        sequence=sequence,
        run_id=run_id,
        type=event_type,
        payload=payload or {},
        actor="test",
        mission_id=mission_id,
        task_id=task_id,
    )


def _make_mission_lifecycle_events(
    run_id: str, mission_id: str | None = None
) -> list[SubstrateEvent]:
    """Create a realistic mission lifecycle event stream."""
    return [
        _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED,
                    {"title": "Test Mission", "mission_type": "test"},
                    mission_id=mission_id),
        _make_event(run_id, 2, SubstrateEventType.TASK_STARTED,
                    {"task_id": "t1", "task_title": "Setup"},
                    mission_id=mission_id, task_id="t1"),
        _make_event(run_id, 3, SubstrateEventType.TASK_COMPLETED,
                    {"task_id": "t1", "tokens": 100, "cost_usd": 0.05},
                    mission_id=mission_id, task_id="t1"),
        _make_event(run_id, 4, SubstrateEventType.TASK_STARTED,
                    {"task_id": "t2", "task_title": "Process"},
                    mission_id=mission_id, task_id="t2"),
        _make_event(run_id, 5, SubstrateEventType.TASK_COMPLETED,
                    {"task_id": "t2", "tokens": 200, "cost_usd": 0.10},
                    mission_id=mission_id, task_id="t2"),
        _make_event(run_id, 6, SubstrateEventType.MISSION_COMPLETED,
                    {"status": "completed"}, mission_id=mission_id),
    ]


def _mock_event_log_with_events(events: list[SubstrateEvent]):
    """Create a mock EventLog that returns given events from get_events()."""
    el = MagicMock(spec=EventLog)

    async def mock_get_events(db, run_id, *, from_sequence=0, to_sequence=None,
                              event_type=None, limit=10000):
        filtered = [e for e in events if e.sequence >= from_sequence]
        if to_sequence is not None:
            filtered = [e for e in filtered if e.sequence <= to_sequence]
        if event_type is not None:
            filtered = [e for e in filtered if e.type == event_type]
        return filtered[:limit]

    el.get_events = AsyncMock(side_effect=mock_get_events)
    return el


# ═══════════════════════════════════════════════════════════════════
# ReplayEngine: rebuild_state()
# ═══════════════════════════════════════════════════════════════════

class TestRebuildState:

    def test_rebuilds_empty_state_for_no_events(self):
        """rebuild_state() returns pending state when no events exist."""
        el = _mock_event_log_with_events([])
        engine = ReplayEngine(event_log=el)
        run_id = str(uuid4())
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))

        assert state.run_id == run_id
        assert state.status == "pending"
        assert state.current_sequence == 0
        assert len(state.completed_tasks) == 0
        assert len(state.failed_tasks) == 0

    def test_rebuilds_complete_mission_state(self):
        """rebuild_state() correctly replays a full mission lifecycle."""
        run_id = str(uuid4())
        mission_id = str(uuid4())
        events = _make_mission_lifecycle_events(run_id, mission_id=mission_id)
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))

        assert state.status == "completed"
        assert state.mission_id == mission_id
        assert state.current_sequence == 6
        assert state.completed_tasks == {"t1", "t2"}
        assert len(state.failed_tasks) == 0
        assert state.total_tokens == 300
        assert state.total_cost_usd == pytest.approx(0.15)

    def test_rebuilds_failed_mission_state(self):
        """rebuild_state() handles mission.failed events."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED,
                       {"title": "Will Fail"}),
            _make_event(run_id, 2, SubstrateEventType.TASK_STARTED,
                       {"task_id": "t1"}, task_id="t1"),
            _make_event(run_id, 3, SubstrateEventType.TASK_FAILED,
                       {"task_id": "t1", "error": "timeout"}, task_id="t1"),
            _make_event(run_id, 4, SubstrateEventType.MISSION_FAILED,
                       {"error": "1 tasks failed"}),
        ]
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))

        assert state.status == "failed"
        assert state.failed_tasks == {"t1"}
        assert state.error_message == "1 tasks failed"

    def test_rebuilds_aborted_mission_state(self):
        """rebuild_state() handles mission.aborted events."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED,
                       {"title": "Aborted"}),
            _make_event(run_id, 2, SubstrateEventType.MISSION_ABORTED,
                       {"reason": "user_requested"}),
        ]
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))
        assert state.status == "aborted"
        assert state.error_message == "user_requested"

    def test_rebuilds_task_retry_state(self):
        """rebuild_state() handles task.retrying events."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED,
                       {"title": "Retry"}),
            _make_event(run_id, 2, SubstrateEventType.TASK_STARTED,
                       {"task_id": "t1"}, task_id="t1"),
            _make_event(run_id, 3, SubstrateEventType.TASK_RETRYING,
                       {"task_id": "t1", "attempt": 1}, task_id="t1"),
        ]
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))
        assert state.status == "executing"
        assert state.task_states.get("t1", {}).get("status") == "retrying"
        assert state.task_states["t1"]["attempt"] == 1

    def test_rebuilds_budget_exhausted_state(self):
        """rebuild_state() handles substrate.budget_exhausted events."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED,
                       {"title": "Budget"}),
            _make_event(run_id, 2, SubstrateEventType.BUDGET_EXHAUSTED,
                       {"budget_type": "cost"}),
        ]
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))
        assert state.status == "failed"
        assert "cost" in (state.error_message or "")

    def test_rebuilds_paused_state(self):
        """rebuild_state() handles mission.paused — status transitions to paused."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED,
                       {"title": "Pausable Mission"}),
            _make_event(run_id, 2, SubstrateEventType.TASK_STARTED,
                       {"task_id": "t1"}, task_id="t1"),
            _make_event(run_id, 3, SubstrateEventType.MISSION_PAUSED,
                       {"reason": "user requested pause"}),
        ]
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))
        assert state.status == "paused"
        # Task state should be preserved through pause
        assert state.task_states.get("t1", {}).get("status") == "running"
        assert state.current_sequence == 3

    def test_rebuilds_resumed_state(self):
        """rebuild_state() handles mission.resumed — status returns to executing."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED,
                       {"title": "Resumable Mission"}),
            _make_event(run_id, 2, SubstrateEventType.TASK_STARTED,
                       {"task_id": "t1"}, task_id="t1"),
            _make_event(run_id, 3, SubstrateEventType.MISSION_PAUSED,
                       {"reason": "cooldown"}),
            _make_event(run_id, 4, SubstrateEventType.MISSION_RESUMED,
                       {"resumed_by": "scheduler"}),
        ]
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))
        assert state.status == "executing"
        assert state.task_states.get("t1", {}).get("status") == "running"
        assert state.current_sequence == 4

    def test_rebuilds_paused_resumed_cycle_with_completed_task(self):
        """Full pause/resume cycle preserves completed task progress.

        Mission executes Task A → pauses → resumes → completes Task A.
        The paused/resumed transitions must not lose accumulated state.
        """
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED,
                       {"title": "Cycle Mission"}),
            _make_event(run_id, 2, SubstrateEventType.TASK_STARTED,
                       {"task_id": "t1"}, task_id="t1"),
            _make_event(run_id, 3, SubstrateEventType.TASK_COMPLETED,
                       {"task_id": "t1", "tokens": 75, "cost_usd": 0.03},
                       task_id="t1"),
            _make_event(run_id, 4, SubstrateEventType.MISSION_PAUSED,
                       {"reason": "rate limit"}),
            _make_event(run_id, 5, SubstrateEventType.MISSION_RESUMED,
                       {"resumed_by": "auto"}),
            _make_event(run_id, 6, SubstrateEventType.TASK_STARTED,
                       {"task_id": "t2"}, task_id="t2"),
            _make_event(run_id, 7, SubstrateEventType.TASK_COMPLETED,
                       {"task_id": "t2", "tokens": 50, "cost_usd": 0.02},
                       task_id="t2"),
        ]
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))
        assert state.status == "executing"
        assert state.completed_tasks == {"t1", "t2"}
        assert state.total_tokens == 125  # 75 + 50
        assert state.total_cost_usd == pytest.approx(0.05)  # 0.03 + 0.02

        # Replay up to pause point (seq 4): should show task t1 done, status=paused
        paused_state = asyncio.run(
            engine.rebuild_state_at_sequence(db, run_id, 4)
        )
        assert paused_state.status == "paused"
        assert paused_state.completed_tasks == {"t1"}
        assert paused_state.total_tokens == 75

        # Replay up to resume point (seq 5): status should be executing again
        resumed_state = asyncio.run(
            engine.rebuild_state_at_sequence(db, run_id, 5)
        )
        assert resumed_state.status == "executing"
        assert resumed_state.completed_tasks == {"t1"}  # t1 still done
        assert resumed_state.total_tokens == 75  # tokens preserved


# ═══════════════════════════════════════════════════════════════════
# ReplayEngine: rebuild_state_at_sequence()
# ═══════════════════════════════════════════════════════════════════

class TestRebuildStateAtSequence:

    def test_rebuilds_at_specific_sequence(self):
        """rebuild_state_at_sequence() returns state as it was after given seq."""
        run_id = str(uuid4())
        events = _make_mission_lifecycle_events(run_id)
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(
            engine.rebuild_state_at_sequence(db, run_id, 3)
        )

        assert state.status == "executing"
        assert state.completed_tasks == {"t1"}
        assert "t2" not in state.completed_tasks
        assert state.total_tokens == 100
        assert state.total_cost_usd == pytest.approx(0.05)
        assert state.current_sequence == 3

    def test_rebuilds_at_sequence_zero(self):
        """rebuild_state_at_sequence(0) returns pending state."""
        run_id = str(uuid4())
        events = _make_mission_lifecycle_events(run_id)
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(
            engine.rebuild_state_at_sequence(db, run_id, 0)
        )
        assert state.status == "pending"
        assert state.current_sequence == 0


# ═══════════════════════════════════════════════════════════════════
# ReplayEngine: verify_determinism()
# ═══════════════════════════════════════════════════════════════════

class TestVerifyDeterminism:

    def test_deterministic_replay_returns_true(self):
        """verify_determinism() returns True for a stable event stream."""
        run_id = str(uuid4())
        events = _make_mission_lifecycle_events(run_id)
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        result = asyncio.run(engine.verify_determinism(db, run_id))
        assert result is True

    def test_double_replay_yields_same_state(self):
        """Two rebuild_state() calls return identical states."""
        run_id = str(uuid4())
        events = _make_mission_lifecycle_events(run_id)
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state1 = asyncio.run(engine.rebuild_state(db, run_id))
        state2 = asyncio.run(engine.rebuild_state(db, run_id))

        assert state1.status == state2.status
        assert state1.current_sequence == state2.current_sequence
        assert state1.completed_tasks == state2.completed_tasks
        assert state1.failed_tasks == state2.failed_tasks


# ═══════════════════════════════════════════════════════════════════
# ReplayEngine: checkpoint sequences
# ═══════════════════════════════════════════════════════════════════

class TestGetCheckpointSequences:

    def test_returns_checkpoint_sequences(self):
        """get_checkpoint_sequences() returns sequences of checkpoint events."""
        run_id = str(uuid4())
        events = [
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED,
                       {"title": "test"}),
            _make_event(run_id, 2, SubstrateEventType.CHECKPOINT,
                       {"note": "after setup"}),
            _make_event(run_id, 3, SubstrateEventType.TASK_STARTED,
                       {"task_id": "t1"}),
            _make_event(run_id, 4, SubstrateEventType.CHECKPOINT,
                       {"note": "mid execution"}),
            _make_event(run_id, 5, SubstrateEventType.MISSION_COMPLETED, {}),
        ]
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        checkpoints = asyncio.run(engine.get_checkpoint_sequences(db, run_id))
        assert checkpoints == [2, 4]

    def test_returns_empty_when_no_checkpoints(self):
        """get_checkpoint_sequences() returns [] when no checkpoints exist."""
        run_id = str(uuid4())
        events = _make_mission_lifecycle_events(run_id)
        el = _mock_event_log_with_events(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        checkpoints = asyncio.run(engine.get_checkpoint_sequences(db, run_id))
        assert checkpoints == []


# ═══════════════════════════════════════════════════════════════════
# ReplayEngine: singleton
# ═══════════════════════════════════════════════════════════════════

class TestReplayEngineSingleton:

    def test_get_replay_engine_returns_same_instance(self):
        re1 = get_replay_engine()
        re2 = get_replay_engine()
        assert re1 is re2
        assert isinstance(re1, ReplayEngine)
