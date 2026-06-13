"""Unit + integration tests for the event-sourced ReplayEngine (H2.1).

Covers:
- rebuild_state() correctness on mission/task lifecycle
- rebuild_state_at_sequence() time-travel correctness
- verify_determinism() true for stable event stream
- checkpoint sequence extraction correctness
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID as UUIDType
from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.api.v1 import substrate as substrate_api
from app.api.v1.substrate import router as substrate_router
from app.models.substrate_models import (
    SubstrateEvent,
    SubstrateEventType,
    SubstrateRunState,
)
from app.services.mission_errors import MissionNotFoundError
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


def _make_mission_lifecycle_events(run_id: str, mission_id: str | None = None) -> list[SubstrateEvent]:
    """Create a realistic mission lifecycle event stream."""
    return [
        _make_event(
            run_id,
            1,
            SubstrateEventType.MISSION_STARTED,
            {"title": "Test Mission", "mission_type": "test"},
            mission_id=mission_id,
        ),
        _make_event(
            run_id,
            2,
            SubstrateEventType.TASK_STARTED,
            {"task_id": "t1", "task_title": "Setup"},
            mission_id=mission_id,
            task_id="t1",
        ),
        _make_event(
            run_id,
            3,
            SubstrateEventType.TASK_COMPLETED,
            {"task_id": "t1", "tokens": 100, "cost_usd": 0.05},
            mission_id=mission_id,
            task_id="t1",
        ),
        _make_event(
            run_id,
            4,
            SubstrateEventType.TASK_STARTED,
            {"task_id": "t2", "task_title": "Process"},
            mission_id=mission_id,
            task_id="t2",
        ),
        _make_event(
            run_id,
            5,
            SubstrateEventType.TASK_COMPLETED,
            {"task_id": "t2", "tokens": 200, "cost_usd": 0.10},
            mission_id=mission_id,
            task_id="t2",
        ),
        _make_event(
            run_id,
            6,
            SubstrateEventType.MISSION_COMPLETED,
            {"status": "completed"},
            mission_id=mission_id,
        ),
    ]


def _mock_event_log_with_events(events: list[SubstrateEvent]):
    """Create a mock EventLog that returns given events from get_events()."""
    el = MagicMock(spec=EventLog)

    async def mock_get_events(db, run_id, *, from_sequence=0, to_sequence=None, event_type=None, limit=10000):
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
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {"title": "Will Fail"}),
            _make_event(
                run_id,
                2,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "t1"},
                task_id="t1",
            ),
            _make_event(
                run_id,
                3,
                SubstrateEventType.TASK_FAILED,
                {"task_id": "t1", "error": "timeout"},
                task_id="t1",
            ),
            _make_event(
                run_id,
                4,
                SubstrateEventType.MISSION_FAILED,
                {"error": "1 tasks failed"},
            ),
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
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {"title": "Aborted"}),
            _make_event(
                run_id,
                2,
                SubstrateEventType.MISSION_ABORTED,
                {"reason": "user_requested"},
            ),
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
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {"title": "Retry"}),
            _make_event(
                run_id,
                2,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "t1"},
                task_id="t1",
            ),
            _make_event(
                run_id,
                3,
                SubstrateEventType.TASK_RETRYING,
                {"task_id": "t1", "attempt": 1},
                task_id="t1",
            ),
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
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {"title": "Budget"}),
            _make_event(run_id, 2, SubstrateEventType.BUDGET_EXHAUSTED, {"budget_type": "cost"}),
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
            _make_event(
                run_id,
                1,
                SubstrateEventType.MISSION_STARTED,
                {"title": "Pausable Mission"},
            ),
            _make_event(
                run_id,
                2,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "t1"},
                task_id="t1",
            ),
            _make_event(
                run_id,
                3,
                SubstrateEventType.MISSION_PAUSED,
                {"reason": "user requested pause"},
            ),
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
            _make_event(
                run_id,
                1,
                SubstrateEventType.MISSION_STARTED,
                {"title": "Resumable Mission"},
            ),
            _make_event(
                run_id,
                2,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "t1"},
                task_id="t1",
            ),
            _make_event(run_id, 3, SubstrateEventType.MISSION_PAUSED, {"reason": "cooldown"}),
            _make_event(
                run_id,
                4,
                SubstrateEventType.MISSION_RESUMED,
                {"resumed_by": "scheduler"},
            ),
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
            _make_event(
                run_id,
                1,
                SubstrateEventType.MISSION_STARTED,
                {"title": "Cycle Mission"},
            ),
            _make_event(
                run_id,
                2,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "t1"},
                task_id="t1",
            ),
            _make_event(
                run_id,
                3,
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "t1", "tokens": 75, "cost_usd": 0.03},
                task_id="t1",
            ),
            _make_event(run_id, 4, SubstrateEventType.MISSION_PAUSED, {"reason": "rate limit"}),
            _make_event(run_id, 5, SubstrateEventType.MISSION_RESUMED, {"resumed_by": "auto"}),
            _make_event(
                run_id,
                6,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "t2"},
                task_id="t2",
            ),
            _make_event(
                run_id,
                7,
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "t2", "tokens": 50, "cost_usd": 0.02},
                task_id="t2",
            ),
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
        paused_state = asyncio.run(engine.rebuild_state_at_sequence(db, run_id, 4))
        assert paused_state.status == "paused"
        assert paused_state.completed_tasks == {"t1"}
        assert paused_state.total_tokens == 75

        # Replay up to resume point (seq 5): status should be executing again
        resumed_state = asyncio.run(engine.rebuild_state_at_sequence(db, run_id, 5))
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

        state = asyncio.run(engine.rebuild_state_at_sequence(db, run_id, 3))

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

        state = asyncio.run(engine.rebuild_state_at_sequence(db, run_id, 0))
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
            _make_event(run_id, 1, SubstrateEventType.MISSION_STARTED, {"title": "test"}),
            _make_event(run_id, 2, SubstrateEventType.CHECKPOINT, {"note": "after setup"}),
            _make_event(run_id, 3, SubstrateEventType.TASK_STARTED, {"task_id": "t1"}),
            _make_event(run_id, 4, SubstrateEventType.CHECKPOINT, {"note": "mid execution"}),
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


API_MISSION_ID = uuid4()
API_RUN_ID = uuid4()

CHUNK_3_TO_6_EVENT_TYPES = {
    SubstrateEventType.TOOL_ROUTE_DECIDED,
    SubstrateEventType.DEPTH_DECIDED,
    SubstrateEventType.HANDOFF_INITIATED,
    SubstrateEventType.HANDOFF_ACCEPTED,
    SubstrateEventType.HANDOFF_COMPLETED,
    SubstrateEventType.HANDOFF_FAILED,
    SubstrateEventType.HANDOFF_BUDGET_EXHAUSTED,
    SubstrateEventType.HANDOFF_LEASE_LOST,
    SubstrateEventType.SELF_CORRECTION_ATTEMPTED,
    SubstrateEventType.SELF_CORRECTION_COMPLETED,
    SubstrateEventType.SELF_CORRECTION_ABORTED,
}


def _make_api_mission(user_id: int, workspace_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=API_MISSION_ID,
        user_id=user_id,
        title="Substrate Mission",
        status="completed",
        plan={"substrate_run_id": str(API_RUN_ID)},
        workspace_id=workspace_id,
    )


def _make_api_event(
    sequence: int,
    event_type: str,
    payload: dict | None = None,
    task_id: str | None = None,
) -> SubstrateEvent:
    return SubstrateEvent(
        id=str(uuid4()),
        sequence=sequence,
        run_id=str(API_RUN_ID),
        mission_id=str(API_MISSION_ID),
        task_id=task_id,
        type=event_type,
        payload=payload or {},
        causal_parent=max(sequence - 1, 0) if sequence > 1 else None,
        actor="test",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _make_replay_state(events: list[SubstrateEvent]) -> SubstrateRunState:
    state = SubstrateRunState(str(API_RUN_ID), str(API_MISSION_ID))
    for event in sorted(events, key=lambda item: item.sequence):
        state.apply(event)
    return state


def _mock_event_log_with_events(events: list[SubstrateEvent]):
    event_log = MagicMock()

    async def get_events(
        db,
        run_id,
        *,
        from_sequence=0,
        to_sequence=None,
        event_type=None,
        limit=10_000,
    ):
        filtered = [event for event in events if str(event.run_id) == str(run_id) and event.sequence >= from_sequence]
        if to_sequence is not None:
            filtered = [event for event in filtered if event.sequence <= to_sequence]
        if isinstance(event_type, (list, tuple, set)):
            allowed_types = set(event_type)
            filtered = [event for event in filtered if event.type in allowed_types]
        elif event_type:
            filtered = [event for event in filtered if event.type == event_type]
        return sorted(filtered, key=lambda item: item.sequence)[:limit]

    event_log.get_events = AsyncMock(side_effect=get_events)
    return event_log


def _mock_replay_engine_with_events(events: list[SubstrateEvent]):
    replay = MagicMock()

    async def rebuild_state(db, run_id):
        return _make_replay_state(events)

    async def rebuild_state_at_sequence(db, run_id, sequence):
        return _make_replay_state([event for event in events if event.sequence <= sequence])

    replay.rebuild_state = AsyncMock(side_effect=rebuild_state)
    replay.rebuild_state_at_sequence = AsyncMock(side_effect=rebuild_state_at_sequence)
    return replay


@pytest.fixture
def substrate_client(mock_db_session, mock_user, monkeypatch):
    async def override_get_db():
        yield mock_db_session

    async def override_get_current_user():
        return mock_user

    monkeypatch.setattr(substrate_api, "UUID", UUIDType, raising=False)
    monkeypatch.setattr(substrate_api, "AsyncSession", object, raising=False)
    monkeypatch.setattr(substrate_api, "Mission", object, raising=False)
    monkeypatch.setattr(substrate_api, "User", object, raising=False)

    app = FastAPI()
    api_router = APIRouter(prefix="/api")
    api_router.include_router(substrate_router)
    app.include_router(api_router)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def _mock_replay_query_with_events(events: list[SubstrateEvent]):
    replay_query = MagicMock()

    async def get_events_for_mission(
        db,
        *,
        mission,
        run_id,
        event_types=None,
        after_sequence=None,
        from_sequence=0,
        to_sequence=None,
        limit=100,
    ):
        lower = from_sequence if after_sequence is None else after_sequence + 1
        filtered = [event for event in events if str(event.run_id) == str(run_id) and event.sequence >= lower]
        if to_sequence is not None:
            filtered = [event for event in filtered if event.sequence <= to_sequence]
        if event_types:
            allowed_types = set(event_types)
            filtered = [event for event in filtered if event.type in allowed_types]
        ordered = sorted(filtered, key=lambda item: item.sequence)
        page_events = ordered[:limit]
        return {
            "events": page_events,
            "total": len(page_events),
            "next_after_sequence": ordered[limit].sequence if len(ordered) > limit else None,
        }

    async def get_event_at_sequence(db, *, mission, run_id, sequence):
        matching = [event for event in events if str(event.run_id) == str(run_id) and event.sequence == sequence]
        return {
            "events": matching,
            "total": len(matching),
            "next_after_sequence": None,
        }

    replay_query.get_events_for_mission = AsyncMock(side_effect=get_events_for_mission)
    replay_query.get_event_at_sequence = AsyncMock(side_effect=get_event_at_sequence)
    return replay_query


def _install_replay_query_mock(monkeypatch, events: list[SubstrateEvent]):
    replay_query = _mock_replay_query_with_events(events)
    replay = _mock_replay_engine_with_events(events)
    monkeypatch.setattr(substrate_api, "get_replay_query", lambda: replay_query)
    monkeypatch.setattr(substrate_api, "get_replay_engine", lambda: replay)
    return replay_query, replay


class TestSubstrateReplayApiHardening:
    @pytest.mark.parametrize(
        "path",
        [
            f"/api/missions/{API_MISSION_ID}/events",
            f"/api/missions/{API_MISSION_ID}/replay-state",
            f"/api/missions/{API_MISSION_ID}/event/3",
        ],
    )
    def test_cross_workspace_denial_returns_404(
        self,
        substrate_client,
        monkeypatch,
        mock_user,
        path,
    ):
        monkeypatch.setattr(
            substrate_api,
            "require_mission_access",
            AsyncMock(side_effect=MissionNotFoundError("Mission not found")),
        )

        response = substrate_client.get(path)

        assert response.status_code == 404

    def test_events_default_pagination_returns_full_stream(
        self,
        substrate_client,
        monkeypatch,
        mock_user,
    ):
        events = [
            _make_api_event(1, SubstrateEventType.MISSION_STARTED),
            _make_api_event(2, SubstrateEventType.TASK_STARTED, {"task_id": "task-1"}, task_id="task-1"),
            _make_api_event(3, SubstrateEventType.TASK_COMPLETED, {"task_id": "task-1"}, task_id="task-1"),
        ]
        monkeypatch.setattr(
            substrate_api, "require_mission_access", AsyncMock(return_value=_make_api_mission(mock_user.id))
        )
        replay_query, _ = _install_replay_query_mock(monkeypatch, events)

        response = substrate_client.get(f"/api/missions/{API_MISSION_ID}/events")

        assert response.status_code == 200
        data = response.json()
        assert [event["sequence"] for event in data["events"]] == [1, 2, 3]
        assert data["total"] == 3
        assert replay_query.get_events_for_mission.call_args.kwargs["from_sequence"] == 0
        assert replay_query.get_events_for_mission.call_args.kwargs["limit"] == 100

    def test_events_after_sequence_cursor_and_limit_are_applied(
        self,
        substrate_client,
        monkeypatch,
        mock_user,
    ):
        events = [
            _make_api_event(sequence, SubstrateEventType.TASK_STARTED, {"task_id": f"task-{sequence}"})
            for sequence in range(1, 6)
        ]
        monkeypatch.setattr(
            substrate_api, "require_mission_access", AsyncMock(return_value=_make_api_mission(mock_user.id))
        )
        replay_query, _ = _install_replay_query_mock(monkeypatch, events)

        response = substrate_client.get(f"/api/missions/{API_MISSION_ID}/events?after_sequence=2&limit=2")

        assert response.status_code == 200
        data = response.json()
        assert [event["sequence"] for event in data["events"]] == [3, 4]
        assert data["total"] == 2
        assert replay_query.get_events_for_mission.call_args.kwargs["from_sequence"] == 0
        assert replay_query.get_events_for_mission.call_args.kwargs["after_sequence"] == 2
        assert replay_query.get_events_for_mission.call_args.kwargs["limit"] == 2

    def test_events_filters_comma_separated_event_type_csv(
        self,
        substrate_client,
        monkeypatch,
        mock_user,
    ):
        events = [
            _make_api_event(1, SubstrateEventType.TASK_STARTED, {"task_id": "task-1"}),
            _make_api_event(2, SubstrateEventType.TASK_COMPLETED, {"task_id": "task-1"}),
            _make_api_event(3, SubstrateEventType.LLM_CALL, {"model": "test"}),
        ]
        monkeypatch.setattr(
            substrate_api, "require_mission_access", AsyncMock(return_value=_make_api_mission(mock_user.id))
        )
        _install_replay_query_mock(monkeypatch, events)

        response = substrate_client.get(f"/api/missions/{API_MISSION_ID}/events?event_type=task.started,task.completed")

        assert response.status_code == 200
        data = response.json()
        assert [event["sequence"] for event in data["events"]] == [1, 2]
        assert {event["type"] for event in data["events"]} == {
            SubstrateEventType.TASK_STARTED,
            SubstrateEventType.TASK_COMPLETED,
        }

    def test_events_returns_deterministic_sequence_order(
        self,
        substrate_client,
        monkeypatch,
        mock_user,
    ):
        events = [
            _make_api_event(4, SubstrateEventType.TASK_COMPLETED, {"task_id": "task-4"}),
            _make_api_event(2, SubstrateEventType.TASK_STARTED, {"task_id": "task-2"}),
            _make_api_event(3, SubstrateEventType.LLM_RESPONSE, {"tokens": 10}),
        ]
        monkeypatch.setattr(
            substrate_api, "require_mission_access", AsyncMock(return_value=_make_api_mission(mock_user.id))
        )
        replay_query, _ = _install_replay_query_mock(monkeypatch, [])
        replay_query.get_events_for_mission = AsyncMock(
            return_value={
                "events": sorted(events, key=lambda item: item.sequence),
                "total": len(events),
                "next_after_sequence": None,
            }
        )

        response = substrate_client.get(f"/api/missions/{API_MISSION_ID}/events")

        assert response.status_code == 200
        assert [event["sequence"] for event in response.json()["events"]] == [2, 3, 4]

    def test_events_round_trips_q2_q3_chunk_3_to_6_event_types(
        self,
        substrate_client,
        monkeypatch,
        mock_user,
    ):
        events = [
            _make_api_event(index, event_type, {"phase": index})
            for index, event_type in enumerate(sorted(CHUNK_3_TO_6_EVENT_TYPES), start=1)
        ]
        monkeypatch.setattr(
            substrate_api, "require_mission_access", AsyncMock(return_value=_make_api_mission(mock_user.id))
        )
        _install_replay_query_mock(monkeypatch, events)

        response = substrate_client.get(f"/api/missions/{API_MISSION_ID}/events")

        assert response.status_code == 200
        assert {event["type"] for event in response.json()["events"]} == CHUNK_3_TO_6_EVENT_TYPES

    def test_events_preserves_backward_compatible_response_keys(
        self,
        substrate_client,
        monkeypatch,
        mock_user,
    ):
        events = [_make_api_event(1, SubstrateEventType.MISSION_STARTED, {"title": "Legacy keys"})]
        monkeypatch.setattr(
            substrate_api, "require_mission_access", AsyncMock(return_value=_make_api_mission(mock_user.id))
        )
        _install_replay_query_mock(monkeypatch, events)

        response = substrate_client.get(f"/api/missions/{API_MISSION_ID}/events")

        assert response.status_code == 200
        data = response.json()
        assert {"events", "total", "mission", "run_id"}.issubset(data)
        assert data["mission"] == {
            "id": str(API_MISSION_ID),
            "title": "Substrate Mission",
            "status": "completed",
        }
        assert data["run_id"] == str(API_RUN_ID)
        assert {
            "id",
            "sequence",
            "run_id",
            "mission_id",
            "task_id",
            "type",
            "payload",
            "causal_parent",
            "actor",
            "timestamp",
        }.issubset(data["events"][0])

    def test_replay_state_preserves_backward_compatible_response_keys(
        self,
        substrate_client,
        monkeypatch,
        mock_user,
    ):
        events = [
            _make_api_event(1, SubstrateEventType.MISSION_STARTED, {"title": "State"}),
            _make_api_event(2, SubstrateEventType.TASK_COMPLETED, {"task_id": "task-1", "tokens": 5}),
        ]
        monkeypatch.setattr(
            substrate_api, "require_mission_access", AsyncMock(return_value=_make_api_mission(mock_user.id))
        )
        _install_replay_query_mock(monkeypatch, events)

        response = substrate_client.get(f"/api/missions/{API_MISSION_ID}/replay-state")

        assert response.status_code == 200
        data = response.json()
        assert {"run_id", "mission_id", "state"}.issubset(data)
        assert data["run_id"] == str(API_RUN_ID)
        assert data["mission_id"] == str(API_MISSION_ID)
        assert {"status", "sequence", "completed_tasks", "failed_tasks", "total_tokens"} <= set(data["state"])

    def test_event_at_sequence_preserves_backward_compatible_response_keys(
        self,
        substrate_client,
        monkeypatch,
        mock_user,
    ):
        events = [
            _make_api_event(1, SubstrateEventType.MISSION_STARTED, {"title": "Event"}),
            _make_api_event(2, SubstrateEventType.TASK_STARTED, {"task_id": "task-1"}),
            _make_api_event(3, SubstrateEventType.TASK_COMPLETED, {"task_id": "task-1", "tokens": 7}),
        ]
        monkeypatch.setattr(
            substrate_api, "require_mission_access", AsyncMock(return_value=_make_api_mission(mock_user.id))
        )
        _install_replay_query_mock(monkeypatch, events)

        response = substrate_client.get(f"/api/missions/{API_MISSION_ID}/event/3")

        assert response.status_code == 200
        data = response.json()
        assert {"event", "state_at_sequence"}.issubset(data)
        assert data["event"]["sequence"] == 3
        assert data["event"]["type"] == SubstrateEventType.TASK_COMPLETED
        assert {"status", "sequence", "completed_tasks", "failed_tasks", "total_tokens"} <= set(
            data["state_at_sequence"]
        )
