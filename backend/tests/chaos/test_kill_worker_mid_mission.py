"""Chaos test: Kill worker mid-mission (Crash recovery verification).

H3.3 — Part of the CI-enforced durability guarantee.

Verifies that the event-sourced substrate survives simulated worker crashes:
    1. Build a full mission lifecycle event stream
    2. Simulate a crash after partial execution
    3. Rebuild state from the persisted event log
    4. Verify the rebuilt state matches expected intermediate state
    5. Verify determinism: same events -> same state, always

Since true process-kill chaos is not practical in CI, we simulate the crash
boundary by persisting a partial event stream and rebuilding state from it.
This is documented in H2-SUBSTRATE-HARDENING-REPORT.md.
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
from app.services.substrate.replay_engine import ReplayEngine

# ── Helpers ────────────────────────────────────────────────────────


def _make_event(
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict | None = None,
    task_id: str | None = None,
    mission_id: str | None = None,
) -> SubstrateEvent:
    return SubstrateEvent(
        id=str(uuid4()),
        sequence=sequence,
        run_id=run_id,
        type=event_type,
        payload=payload or {},
        actor="test",
        task_id=task_id,
        mission_id=mission_id,
    )


def _simulate_mission_until_crash(
    run_id: str, mission_id: str, crash_after_sequence: int
) -> tuple[list[SubstrateEvent], SubstrateRunState]:
    """Simulate mission execution up to a crash point.

    Returns (persisted_events, expected_state_at_crash).
    """
    all_events = [
        _make_event(
            run_id,
            1,
            SubstrateEventType.MISSION_STARTED,
            {"title": "Crash Test"},
            mission_id=mission_id,
        ),
        _make_event(
            run_id,
            2,
            SubstrateEventType.TASK_STARTED,
            {"task_id": "a", "task_title": "Task A"},
            task_id="a",
            mission_id=mission_id,
        ),
        _make_event(
            run_id,
            3,
            SubstrateEventType.TASK_STARTED,
            {"task_id": "b", "task_title": "Task B"},
            task_id="b",
            mission_id=mission_id,
        ),
        _make_event(
            run_id,
            4,
            SubstrateEventType.TASK_COMPLETED,
            {"task_id": "a", "tokens": 50, "cost_usd": 0.02},
            task_id="a",
            mission_id=mission_id,
        ),
        _make_event(
            run_id,
            5,
            SubstrateEventType.TASK_STARTED,
            {"task_id": "c", "task_title": "Task C"},
            task_id="c",
            mission_id=mission_id,
        ),
        _make_event(
            run_id,
            6,
            SubstrateEventType.TASK_COMPLETED,
            {"task_id": "c", "tokens": 30, "cost_usd": 0.01},
            task_id="c",
            mission_id=mission_id,
        ),
        _make_event(
            run_id,
            7,
            SubstrateEventType.TASK_FAILED,
            {"task_id": "b", "error": "CRASHED"},
            task_id="b",
            mission_id=mission_id,
        ),
    ]

    expected_state = SubstrateRunState(run_id=run_id, mission_id=mission_id)
    persisted = []
    for event in all_events:
        if event.sequence <= crash_after_sequence:
            expected_state.apply(event)
            persisted.append(event)

    return persisted, expected_state


def _mock_event_log(events):
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
# Test: Crash after partial execution
# ═══════════════════════════════════════════════════════════════════


class TestKillWorkerMidMission:
    def test_crash_after_task_started(self):
        """Crash after 2 tasks started: replay shows mission=executing."""
        run_id = str(uuid4())
        mission_id = str(uuid4())

        persisted, expected = _simulate_mission_until_crash(run_id, mission_id, crash_after_sequence=3)

        el = _mock_event_log(persisted)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        rebuilt = asyncio.run(engine.rebuild_state(db, run_id))

        assert rebuilt.status == expected.status == "executing"
        assert rebuilt.current_sequence == expected.current_sequence
        assert rebuilt.completed_tasks == expected.completed_tasks
        assert rebuilt.failed_tasks == expected.failed_tasks

    def test_crash_after_task_completed(self):
        """Crash after task A completed: progress preserved."""
        run_id = str(uuid4())
        mission_id = str(uuid4())

        persisted, expected = _simulate_mission_until_crash(run_id, mission_id, crash_after_sequence=5)

        el = _mock_event_log(persisted)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        rebuilt = asyncio.run(engine.rebuild_state(db, run_id))

        assert "a" in rebuilt.completed_tasks
        assert rebuilt.total_tokens == 50
        assert rebuilt.total_cost_usd == pytest.approx(0.02)
        assert rebuilt.task_states.get("b", {}).get("status") == "running"

    def test_crash_after_all_tasks_completed(self):
        """Crash before MISSION_COMPLETED: all task progress saved."""
        run_id = str(uuid4())
        mission_id = str(uuid4())

        events = [
            _make_event(
                run_id,
                1,
                SubstrateEventType.MISSION_STARTED,
                {"title": "All Done"},
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                2,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "a"},
                task_id="a",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                3,
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "a", "tokens": 100, "cost_usd": 0.05},
                task_id="a",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                4,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "b"},
                task_id="b",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                5,
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "b", "tokens": 200, "cost_usd": 0.10},
                task_id="b",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                6,
                SubstrateEventType.MISSION_FAILED,
                {"error": "worker crash"},
                mission_id=mission_id,
            ),
        ]

        el = _mock_event_log(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        rebuilt = asyncio.run(engine.rebuild_state(db, run_id))

        assert rebuilt.status == "failed"
        assert rebuilt.completed_tasks == {"a", "b"}
        assert rebuilt.total_tokens == 300
        assert rebuilt.total_cost_usd == pytest.approx(0.15)

    def test_crash_after_checkpoint(self):
        """Crash after checkpoint: replay from checkpoint is consistent."""
        run_id = str(uuid4())
        mission_id = str(uuid4())

        events = [
            _make_event(
                run_id,
                1,
                SubstrateEventType.MISSION_STARTED,
                {"title": "Checkpoint"},
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                2,
                SubstrateEventType.CHECKPOINT,
                {"note": "pre-task"},
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                3,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "x"},
                task_id="x",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                4,
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "x", "tokens": 75},
                task_id="x",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                5,
                SubstrateEventType.CHECKPOINT,
                {"note": "post-task-x"},
                mission_id=mission_id,
            ),
        ]

        el = _mock_event_log(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        # Replay up to first checkpoint
        state_at_cp = asyncio.run(engine.rebuild_state_at_sequence(db, run_id, 2))
        assert state_at_cp.status == "executing"
        assert state_at_cp.current_sequence == 2
        assert len(state_at_cp.completed_tasks) == 0

        # Full replay
        full = asyncio.run(engine.rebuild_state(db, run_id))
        assert full.current_sequence == 5
        assert "x" in full.completed_tasks
        assert full.total_tokens == 75

    def test_crash_mid_mission_deterministic(self):
        """Crash recovery replay is deterministic."""
        run_id = str(uuid4())
        mission_id = str(uuid4())

        persisted, _ = _simulate_mission_until_crash(run_id, mission_id, crash_after_sequence=6)

        el = _mock_event_log(persisted)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        s1 = asyncio.run(engine.rebuild_state(db, run_id))
        s2 = asyncio.run(engine.rebuild_state(db, run_id))

        assert s1.status == s2.status
        assert s1.current_sequence == s2.current_sequence
        assert s1.completed_tasks == s2.completed_tasks
        assert s1.failed_tasks == s2.failed_tasks
        assert s1.total_tokens == s2.total_tokens
        assert s1.total_cost_usd == pytest.approx(s2.total_cost_usd)


class TestResumeAfterCrash:
    def test_pending_tasks_identified(self):
        """After crash, tasks not in completed/failed sets are pending."""
        run_id = str(uuid4())
        mission_id = str(uuid4())

        events = [
            _make_event(
                run_id,
                1,
                SubstrateEventType.MISSION_STARTED,
                {"title": "Resume"},
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                2,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "a"},
                task_id="a",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                3,
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "a", "tokens": 10},
                task_id="a",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                4,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "b"},
                task_id="b",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                5,
                SubstrateEventType.TASK_FAILED,
                {"task_id": "b", "error": "crash"},
                task_id="b",
                mission_id=mission_id,
            ),
        ]

        el = _mock_event_log(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        state = asyncio.run(engine.rebuild_state(db, run_id))

        assert state.status == "executing"
        assert state.completed_tasks == {"a"}
        assert state.failed_tasks == {"b"}
        assert "c" not in state.completed_tasks
        assert "c" not in state.failed_tasks
        assert "c" not in state.task_states
