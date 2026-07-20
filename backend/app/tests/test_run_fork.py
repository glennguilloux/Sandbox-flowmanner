# ─────────────────────────────────────────────────────────────────────
# Tests for Phase-3 fork-a-run: re-run a completed run from a mid-step
# edit, with the edited instruction patched into the node that was active
# at the fork checkpoint.
#
# Hermetic unit tests — no Postgres / Docker / Alembic. The run row, the
# replay engine, the event log, and the unified executor are faked with
# AsyncMock / SimpleNamespace / MagicMock so the suite runs on the host.
#
# Coverage:
#   * fork_run locates the active fork node from the replayed event log.
#   * fork_run patches the fork node's prompt with the edited instruction.
#   * fork_run creates a NEW run (parent_run_id set) and dispatches it,
#     returning the new run id + fork metadata.
#   * ownership rejection: forking a run you don't own raises RunNotFoundError.
#
# Run from the backend worktree:
#     PYTHONPATH=. uv run pytest app/tests/test_run_fork.py -q
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.blueprint_models import Run, RunStatus
from app.services.run_service import RunNotFoundError, RunService


def _solo_snapshot() -> dict:
    """A minimal solo-style snapshot: one goal node."""
    return {
        "blueprint_type": "solo",
        "title": "Original goal",
        "nodes": [{"id": "goal", "type": "llm_call", "title": "Goal"}],
        "edges": [],
    }


def _fake_original_run() -> MagicMock:
    run = MagicMock()
    object.__setattr__(run, "id", "orig-1")
    object.__setattr__(run, "blueprint_id", "bp-1")
    object.__setattr__(run, "workspace_id", "ws-1")
    object.__setattr__(run, "user_id", 1)
    object.__setattr__(run, "status", "completed")
    object.__setattr__(run, "snapshot", _solo_snapshot())
    object.__setattr__(run, "budget_limit_usd", None)
    return run


def _fake_strategy_result(status: str = "completed") -> SimpleNamespace:
    return SimpleNamespace(
        success=status == "completed",
        status=status,
        run_id="new-1",
        data={"result": "ok"},
        error=None,
        completed_nodes=[],
        failed_nodes=[],
        total_tokens=42,
        total_cost_usd=0.01,
        execution_time_ms=100,
        event_count=3,
    )


async def test_fork_run_patches_node_and_dispatches_new_run():
    """Fork must patch the active node, create a child run, and execute it."""
    original = _fake_original_run()
    # Event log at the fork point: the `goal` node was running.
    replay_state = SimpleNamespace(task_states={"goal": {"status": "running"}})

    created_run = None

    db = MagicMock()
    service = RunService(db=db)

    fake_executor = SimpleNamespace(
        execute=AsyncMock(return_value=_fake_strategy_result())
    )

    with (
        patch.object(RunService, "get", new=AsyncMock(return_value=original)),
        patch(
            "app.services.run_service.get_replay_engine",
            return_value=SimpleNamespace(
                rebuild_state_at_sequence=AsyncMock(return_value=replay_state)
            ),
        ),
        patch(
            "app.services.run_service.get_event_log",
            return_value=SimpleNamespace(
                get_events=AsyncMock(return_value=[])
            ),
        ),
        patch(
            "app.services.run_service.get_unified_executor",
            return_value=fake_executor,
        ),
        patch.object(db, "add", new=MagicMock(side_effect=lambda obj: setattr(obj, "id", obj.id or "new-1"))),
    ):
        # Capture the created Run so we can assert parent linkage.
        real_add = db.add

        def _add(obj):
            nonlocal created_run
            if isinstance(obj, Run):
                created_run = obj
            return real_add(obj)

        db.add = _add
        db.flush = AsyncMock()

        result = await service.fork_run(
            "orig-1", 1, from_sequence=3, instruction="Do it better, with citations."
        )

    # Returns fork metadata + the new run id.
    assert result["new_run_id"]
    assert result["parent_run_id"] == "orig-1"
    assert result["forked_from_sequence"] == 3
    assert result["forked_node"] == "goal"
    assert result["status"] == "completed"

    # A new Run was created, linked to the original via parent_run_id.
    assert created_run is not None
    assert created_run.parent_run_id == "orig-1"
    assert created_run.id != "orig-1"

    # The executor was called to dispatch the fork.
    fake_executor.execute.assert_awaited_once()

    # The patched instruction landed on the fork node's prompt.
    call_kwargs = fake_executor.execute.await_args.kwargs
    wf = call_kwargs["workflow"]
    goal_node = next(n for n in wf.nodes if n.id == "goal")
    assert "Do it better, with citations." in goal_node.config["prompt"]


async def test_fork_run_rejects_cross_user_access():
    """Forking a run owned by another user must raise RunNotFoundError."""
    original = _fake_original_run()
    object.__setattr__(original, "user_id", 999)  # not the caller

    db = MagicMock()
    service = RunService(db=db)
    with (
        patch.object(
            RunService,
            "get",
            new=AsyncMock(side_effect=RunNotFoundError("denied")),
        ),
        pytest.raises(RunNotFoundError),
    ):
        await service.fork_run("orig-1", 1, from_sequence=0, instruction="x")


async def test_fork_run_falls_back_to_first_node_when_no_state():
    """If the event log is empty at the fork point, fork from node 0."""
    original = _fake_original_run()
    replay_state = SimpleNamespace(task_states={})  # nothing recorded yet

    db = MagicMock()
    service = RunService(db=db)
    fake_executor = SimpleNamespace(
        execute=AsyncMock(return_value=_fake_strategy_result())
    )
    with (
        patch.object(RunService, "get", new=AsyncMock(return_value=original)),
        patch(
            "app.services.run_service.get_replay_engine",
            return_value=SimpleNamespace(
                rebuild_state_at_sequence=AsyncMock(return_value=replay_state)
            ),
        ),
        patch(
            "app.services.run_service.get_event_log",
            return_value=SimpleNamespace(get_events=AsyncMock(return_value=[])),
        ),
        patch(
            "app.services.run_service.get_unified_executor",
            return_value=fake_executor,
        ),
    ):
        db.add = MagicMock()
        db.flush = AsyncMock()
        result = await service.fork_run(
            "orig-1", 1, from_sequence=0, instruction="Start over, cleaner."
        )

    # Falls back to the first topology node.
    assert result["forked_node"] == "goal"
    assert result["new_run_id"]
