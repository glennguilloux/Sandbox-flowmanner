"""Process-level chaos test: Kill worker mid-mission.

H2 Exit Gate — Verifies crash recovery at the OS process boundary.

This test uses multiprocessing to:
    1. Spawn a worker process that builds an event stream, recording
       events to a temp file (simulating a persisted event log)
    2. Send SIGKILL to the worker mid-execution
    3. Read the partially-written event log (surviving the crash)
    4. Replay the events via ReplayEngine to rebuild RunState
    5. Verify the rebuilt state matches the expected crash-point state
    6. Confirm that replay is deterministic across multiple runs

The simulation-based tests provide equivalent coverage for platforms
where SIGKILL is not available (Windows, restricted CI environments).
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import signal
import sys
import time
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


def _make_event(run_id, seq, etype, payload=None, task_id=None, mission_id=None):
    return SubstrateEvent(
        id=str(uuid4()),
        sequence=seq,
        run_id=run_id,
        type=etype,
        payload=payload or {},
        actor="test",
        task_id=task_id,
        mission_id=mission_id,
    )


def _worker_write_events_and_die(event_log_path: str, sync_path: str):
    """Worker: write mission events to a file, updating a sync file each step.

    Writes events one at a time to a JSON-lines file, and writes the
    current sequence number to a sync file after each write+flush.
    The parent polls the sync file to know exactly which events have
    been persisted, then sends SIGKILL.

    Args:
        event_log_path: Path to the JSON-lines event log file.
        sync_path: Path to the sync marker file (written with current seq).
    """
    import json

    run_id = str(uuid4())
    mission_id = str(uuid4())

    # Full mission lifecycle event stream
    events = [
        (
            SubstrateEventType.MISSION_STARTED,
            {"title": "SIGKILL Chaos Mission", "mission_type": "chaos_test"},
            None,
        ),
        (
            SubstrateEventType.TASK_STARTED,
            {"task_id": "sig_a", "task_title": "Chaos Task A"},
            "sig_a",
        ),
        (
            SubstrateEventType.TASK_STARTED,
            {"task_id": "sig_b", "task_title": "Chaos Task B"},
            "sig_b",
        ),
        (
            SubstrateEventType.TASK_COMPLETED,
            {"task_id": "sig_a", "tokens": 120, "cost_usd": 0.06},
            "sig_a",
        ),
        (
            SubstrateEventType.TASK_STARTED,
            {"task_id": "sig_c", "task_title": "Chaos Task C"},
            "sig_c",
        ),
        (
            SubstrateEventType.TASK_COMPLETED,
            {"task_id": "sig_c", "tokens": 80, "cost_usd": 0.04},
            "sig_c",
        ),
        (
            SubstrateEventType.TASK_FAILED,
            {"task_id": "sig_b", "error": "worker killed by SIGKILL"},
            "sig_b",
        ),
        (
            SubstrateEventType.MISSION_FAILED,
            {"error": "worker process received SIGKILL"},
            None,
        ),
    ]

    with open(event_log_path, "w") as f:
        for seq, (etype, payload, task_id) in enumerate(events, start=1):
            event_line = json.dumps(
                {
                    "sequence": seq,
                    "run_id": run_id,
                    "mission_id": mission_id,
                    "task_id": task_id,
                    "type": etype,
                    "payload": payload,
                }
            )
            f.write(event_line + "\n")
            f.flush()

            # Write sync file so parent knows this event is persisted
            with open(sync_path, "w") as sf:
                sf.write(str(seq))
                sf.flush()

            time.sleep(0.02)  # Brief sleep to simulate real work


def _worker_write_events_checkpoint(event_log_path: str, sync_path: str):
    """Worker that writes events with checkpoint markers and sync file."""
    import json

    run_id = str(uuid4())
    mission_id = str(uuid4())

    events = [
        (SubstrateEventType.MISSION_STARTED, {"title": "Checkpoint Chaos"}, None),
        (SubstrateEventType.CHECKPOINT, {"note": "pre-task-group-1"}, None),
        (SubstrateEventType.TASK_STARTED, {"task_id": "cp_a"}, "cp_a"),
        (
            SubstrateEventType.TASK_COMPLETED,
            {"task_id": "cp_a", "tokens": 60, "cost_usd": 0.03},
            "cp_a",
        ),
        (SubstrateEventType.CHECKPOINT, {"note": "post-task-group-1"}, None),
        (SubstrateEventType.TASK_STARTED, {"task_id": "cp_b"}, "cp_b"),
        (
            SubstrateEventType.TASK_COMPLETED,
            {"task_id": "cp_b", "tokens": 90, "cost_usd": 0.05},
            "cp_b",
        ),
        (SubstrateEventType.CHECKPOINT, {"note": "post-task-group-2"}, None),
        (SubstrateEventType.MISSION_COMPLETED, {}, None),
    ]

    with open(event_log_path, "w") as f:
        for seq, (etype, payload, task_id) in enumerate(events, start=1):
            f.write(
                json.dumps(
                    {
                        "sequence": seq,
                        "run_id": run_id,
                        "mission_id": mission_id,
                        "task_id": task_id,
                        "type": etype,
                        "payload": payload,
                    }
                )
                + "\n"
            )
            f.flush()

            with open(sync_path, "w") as sf:
                sf.write(str(seq))
                sf.flush()

            time.sleep(0.02)


def _wait_for_sync_seq(sync_path: str, target_seq: int, timeout: float = 10.0) -> bool:
    """Poll the sync file until it reaches target_seq or timeout.

    Returns True if target_seq was reached, False on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with open(sync_path, "r") as f:
                content = f.read().strip()
            if content and int(content) >= target_seq:
                return True
        except (FileNotFoundError, ValueError):
            pass
        time.sleep(0.01)
    return False


def _deserialize_events_from_file(path: str) -> list[SubstrateEvent]:
    """Read JSON-lines event log file and deserialize to SubstrateEvent objects.

    Skips malformed lines (partial writes from mid-SIGKILL).
    """
    import json

    events = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    events.append(
                        SubstrateEvent(
                            id=str(uuid4()),
                            sequence=data["sequence"],
                            run_id=data["run_id"],
                            mission_id=data.get("mission_id"),
                            task_id=data.get("task_id"),
                            type=data["type"],
                            payload=data.get("payload", {}),
                            actor="chaos_test",
                        )
                    )
                except (json.JSONDecodeError, KeyError):
                    # Partial write from SIGKILL — skip this line
                    continue
    except FileNotFoundError:
        pass
    return events


def _can_sigkill():
    """Check if SIGKILL/SIGTERM is available on this platform."""
    return hasattr(signal, "SIGTERM") and sys.platform != "win32"


def _build_partial_event_stream(run_id, mission_id, crash_at_seq):
    """Build a mission event stream up to the crash point."""
    events = [
        _make_event(
            run_id,
            1,
            SubstrateEventType.MISSION_STARTED,
            {"title": "Process Crash Test"},
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
            SubstrateEventType.TASK_STARTED,
            {"task_id": "b"},
            task_id="b",
            mission_id=mission_id,
        ),
        _make_event(
            run_id,
            4,
            SubstrateEventType.TASK_COMPLETED,
            {"task_id": "a", "tokens": 80, "cost_usd": 0.04},
            task_id="a",
            mission_id=mission_id,
        ),
        _make_event(
            run_id,
            5,
            SubstrateEventType.TASK_FAILED,
            {"task_id": "b", "error": "worker killed"},
            task_id="b",
            mission_id=mission_id,
        ),
    ]
    # Return events up to (and including) the crash point
    return [e for e in events if e.sequence <= crash_at_seq]


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
# Primary: Process crash boundary simulation
# ═══════════════════════════════════════════════════════════════════


class TestProcessKillMidMission:
    """Simulate worker process death and verify recovery via event replay."""

    def test_crash_boundary_recovery(self):
        """After simulated process crash, replay recovers correct state.

        Simulates: A worker process records 4 events, then is killed.
        On restart, the replay engine must rebuild the correct intermediate
        state from those 4 persisted events.
        """
        run_id = str(uuid4())
        mission_id = str(uuid4())

        # Simulate: worker recorded 4 events before crash
        persisted = _build_partial_event_stream(run_id, mission_id, crash_at_seq=4)

        # Expected state at crash point
        expected = SubstrateRunState(run_id=run_id, mission_id=mission_id)
        for e in persisted:
            expected.apply(e)

        # Verify: expected state reflects partial progress
        assert expected.status == "executing"
        assert "a" in expected.completed_tasks
        assert expected.total_tokens == 80

        # Replay on "restart"
        el = _mock_event_log(persisted)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        rebuilt = asyncio.run(engine.rebuild_state(db, run_id))

        # The rebuilt state must match the expected intermediate state
        assert rebuilt.status == expected.status
        assert rebuilt.completed_tasks == expected.completed_tasks
        assert rebuilt.failed_tasks == expected.failed_tasks
        assert rebuilt.total_tokens == expected.total_tokens
        assert rebuilt.total_cost_usd == pytest.approx(expected.total_cost_usd)

    def test_crash_after_all_tasks_but_before_completion(self):
        """Crash after all tasks done but before MISSION_COMPLETED event.

        The worker completed both tasks but was killed before recording
        MISSION_COMPLETED. On restart, tasks should show as completed
        but mission status should reflect the crash (failed).
        """
        run_id = str(uuid4())
        mission_id = str(uuid4())

        events = [
            _make_event(
                run_id,
                1,
                SubstrateEventType.MISSION_STARTED,
                {"title": "Near Complete"},
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                2,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "x"},
                task_id="x",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                3,
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "x", "tokens": 150, "cost_usd": 0.07},
                task_id="x",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                4,
                SubstrateEventType.TASK_STARTED,
                {"task_id": "y"},
                task_id="y",
                mission_id=mission_id,
            ),
            _make_event(
                run_id,
                5,
                SubstrateEventType.TASK_COMPLETED,
                {"task_id": "y", "tokens": 250, "cost_usd": 0.12},
                task_id="y",
                mission_id=mission_id,
            ),
            # Worker killed here — MISSION_COMPLETED never recorded
            _make_event(
                run_id,
                6,
                SubstrateEventType.MISSION_FAILED,
                {"error": "worker process killed by SIGTERM"},
                mission_id=mission_id,
            ),
        ]

        el = _mock_event_log(events)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        rebuilt = asyncio.run(engine.rebuild_state(db, run_id))

        assert rebuilt.status == "failed"
        assert rebuilt.completed_tasks == {"x", "y"}
        assert rebuilt.total_tokens == 400  # 150 + 250
        assert rebuilt.total_cost_usd == pytest.approx(0.19)  # 0.07 + 0.12
        assert "SIGTERM" in (rebuilt.error_message or "")

    def test_replay_after_crash_is_deterministic(self):
        """Multiple replays after a crash yield identical state."""
        run_id = str(uuid4())
        mission_id = str(uuid4())

        persisted = _build_partial_event_stream(run_id, mission_id, crash_at_seq=5)

        el = _mock_event_log(persisted)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        s1 = asyncio.run(engine.rebuild_state(db, run_id))
        s2 = asyncio.run(engine.rebuild_state(db, run_id))
        s3 = asyncio.run(engine.rebuild_state(db, run_id))

        assert s1.status == s2.status == s3.status
        assert s1.total_tokens == s2.total_tokens == s3.total_tokens
        assert s1.total_cost_usd == pytest.approx(s2.total_cost_usd)
        assert s1.completed_tasks == s2.completed_tasks == s3.completed_tasks


# ═══════════════════════════════════════════════════════════════════
# True SIGKILL: spawn worker → SIGKILL → replay surviving events
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    not _can_sigkill(),
    reason="True process-kill requires SIGKILL signal support (Unix).",
)
class TestTrueSIGKILLRecovery:
    """True SIGKILL chaos test: spawn worker, kill mid-mission, verify recovery.

    Architecture:
        1. Worker subprocess writes SubstrateEvent JSON-lines to a temp file
           and a sync file (current sequence number) after each event.
        2. Parent polls the sync file for a target sequence, then sends
           SIGKILL at a deterministic crash point.
        3. Parent reads the surviving event log.
        4. Parent replays events via ReplayEngine.rebuild_state().
        5. Parent verifies the rebuilt state matches expected crash-point state.
        6. Parent verifies replay determinism.

    This is deterministic because the parent waits for a specific sequence
    to be reached before killing, regardless of machine speed.
    """

    def test_sigkill_mid_mission_recovery(self, tmp_path):
        """SIGKILL after seq 3: replay recovers correct intermediate state.

        Worker writes MISSION_STARTED + 2x TASK_STARTED (seq 1-3),
        then parent kills it. Replay must show mission=executing
        with tasks sig_a and sig_b in running state.
        """
        event_log = tmp_path / "events.jsonl"
        sync_file = tmp_path / "sync.txt"
        target_seq = 3

        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(
            target=_worker_write_events_and_die,
            args=(str(event_log), str(sync_file)),
        )
        proc.start()
        assert proc.is_alive(), "Worker should be running"

        # Wait for sync file to reach target_seq, then SIGKILL
        assert _wait_for_sync_seq(str(sync_file), target_seq), f"Worker did not reach seq {target_seq} in time"
        os.kill(proc.pid, signal.SIGKILL)
        proc.join(timeout=5)
        assert not proc.is_alive(), "Worker should be dead after SIGKILL"
        assert proc.exitcode == -signal.SIGKILL, (
            f"Exit code should be -SIGKILL ({-signal.SIGKILL}), got {proc.exitcode}"
        )

        # Read surviving events — MUST be fewer than total (8)
        surviving = _deserialize_events_from_file(str(event_log))
        assert len(surviving) >= target_seq, (
            f"At least {target_seq} events should survive SIGKILL, got {len(surviving)}"
        )
        assert len(surviving) < 8, (
            f"SIGKILL should interrupt before all 8 events, got {len(surviving)} — worker may have finished"
        )

        run_id = surviving[0].run_id
        for e in surviving:
            assert e.run_id == run_id

        el = _mock_event_log(surviving)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        rebuilt = asyncio.run(engine.rebuild_state(db, run_id))

        # After seq 3: MISSION_STARTED + TASK_STARTED(sig_a) + TASK_STARTED(sig_b)
        assert rebuilt.status == "executing"
        assert rebuilt.current_sequence >= target_seq
        assert "sig_a" in rebuilt.task_states
        assert rebuilt.task_states["sig_a"]["status"] == "running"
        assert "sig_b" in rebuilt.task_states
        assert rebuilt.task_states["sig_b"]["status"] == "running"

    def test_sigkill_replay_deterministic(self, tmp_path):
        """SIGKILL → replay twice → identical states."""
        event_log = tmp_path / "events_det.jsonl"
        sync_file = tmp_path / "sync_det.txt"

        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(
            target=_worker_write_events_and_die,
            args=(str(event_log), str(sync_file)),
        )
        proc.start()
        assert _wait_for_sync_seq(str(sync_file), 3)
        os.kill(proc.pid, signal.SIGKILL)
        proc.join(timeout=5)

        surviving = _deserialize_events_from_file(str(event_log))
        assert len(surviving) >= 3

        run_id = surviving[0].run_id
        el = _mock_event_log(surviving)
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

    def test_sigkill_preserves_completed_work(self, tmp_path):
        """SIGKILL after Task A completed: replay shows progress preserved.

        Seq 4 = TASK_COMPLETED for sig_a (tokens=120, cost=0.06).
        After SIGKILL, replay must show sig_a as completed and
        tokens/cost reflecting Task A's work.
        """
        event_log = tmp_path / "events_progress.jsonl"
        sync_file = tmp_path / "sync_progress.txt"
        target_seq = 4  # Task A completed

        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(
            target=_worker_write_events_and_die,
            args=(str(event_log), str(sync_file)),
        )
        proc.start()
        assert _wait_for_sync_seq(str(sync_file), target_seq), f"Worker did not reach seq {target_seq}"
        os.kill(proc.pid, signal.SIGKILL)
        proc.join(timeout=5)

        surviving = _deserialize_events_from_file(str(event_log))
        assert len(surviving) >= target_seq
        assert len(surviving) < 8

        run_id = surviving[0].run_id
        el = _mock_event_log(surviving)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        rebuilt = asyncio.run(engine.rebuild_state(db, run_id))

        # Task A must be completed (seq 4 was reached before kill)
        assert "sig_a" in rebuilt.completed_tasks, (
            f"Task A should be completed (seq {target_seq} reached), completed_tasks={rebuilt.completed_tasks}"
        )
        assert rebuilt.total_tokens >= 120, f"Task A should add 120 tokens, got {rebuilt.total_tokens}"
        assert rebuilt.total_cost_usd >= 0.06
        assert rebuilt.status == "executing"

    def test_sigkill_with_checkpoint_recovery(self, tmp_path):
        """Worker records checkpoints → SIGKILL → replay from last checkpoint."""
        event_log = tmp_path / "events_cp.jsonl"
        sync_file = tmp_path / "sync_cp.txt"

        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(
            target=_worker_write_events_checkpoint,
            args=(str(event_log), str(sync_file)),
        )
        proc.start()
        # Kill after checkpoint 1 (seq 2) + task cp_a started (seq 3)
        # + task cp_a completed (seq 4) — kill at seq 5 (checkpoint 2)
        assert _wait_for_sync_seq(str(sync_file), 5)
        os.kill(proc.pid, signal.SIGKILL)
        proc.join(timeout=5)

        surviving = _deserialize_events_from_file(str(event_log))
        assert len(surviving) >= 5
        assert len(surviving) < 9

        run_id = surviving[0].run_id
        el = _mock_event_log(surviving)
        engine = ReplayEngine(event_log=el)
        db = AsyncMock()

        # Get checkpoints from surviving events
        checkpoints = asyncio.run(engine.get_checkpoint_sequences(db, run_id))
        assert len(checkpoints) >= 1, f"Should have at least 1 checkpoint, got {checkpoints}"

        # Replay from last checkpoint should produce consistent state
        last_cp = checkpoints[-1]
        cp_state = asyncio.run(engine.rebuild_state_at_sequence(db, run_id, last_cp))
        assert cp_state.current_sequence == last_cp

        # Full replay
        full_state = asyncio.run(engine.rebuild_state(db, run_id))
        assert full_state.status == "executing"
        assert full_state.current_sequence >= last_cp

    def test_sigkill_partial_write_resilience(self, tmp_path):
        """SIGKILL mid-write: partial JSON lines are skipped gracefully."""
        event_log = tmp_path / "events_partial.jsonl"
        sync_file = tmp_path / "sync_partial.txt"

        ctx = multiprocessing.get_context("spawn")
        proc = ctx.Process(
            target=_worker_write_events_and_die,
            args=(str(event_log), str(sync_file)),
        )
        proc.start()
        # Kill very early to increase chance of partial write
        assert _wait_for_sync_seq(str(sync_file), 2)
        os.kill(proc.pid, signal.SIGKILL)
        proc.join(timeout=5)

        # Deserialization must not raise
        surviving = _deserialize_events_from_file(str(event_log))
        assert len(surviving) >= 1, "At least 1 complete event should survive partial-write SIGKILL"

        # Every surviving event must be valid
        for e in surviving:
            assert isinstance(e, SubstrateEvent)
            assert e.sequence > 0
            assert e.type
            assert e.run_id
