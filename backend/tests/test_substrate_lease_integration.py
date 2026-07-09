"""Integration tests for lease integration into UnifiedExecutor (Q1-A Chunk 2).

Tests verify that the executor correctly claims/releases leases, spawns
heartbeat, detects lost leases, and respects the LEASE_ENABLED feature flag.

Uses mocked AsyncSession and strategy patterns consistent with the existing
test_unified_executor.py style.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.substrate.executor import LeaseLostError, UnifiedExecutor
from app.services.substrate.workflow_models import (
    StrategyResult,
    Workflow,
    WorkflowNode,
    WorkflowType,
)

# ── Helpers ────────────────────────────────────────────────────────


def _make_workflow(wtype: WorkflowType = WorkflowType.SOLO) -> Workflow:
    return Workflow(
        id="wf-test-1",
        type=wtype,
        title="Test Workflow",
        nodes=[WorkflowNode(id="n1", type="llm_call", title="Test Node")],
        user_id="1",
    )


def _make_lease_row(worker_id: str, run_id: str, generation: int = 1):
    """Create a mock lease row."""
    now = datetime.now(UTC)
    return MagicMock(
        id=1,
        worker_id=worker_id,
        run_id=run_id,
        acquired_at=now,
        expires_at=now + timedelta(seconds=300),
        renewed_count=0,
        generation=generation,
    )


def _make_mock_executor():
    """Create a UnifiedExecutor with mocked event_log and replay_engine."""
    event_log = MagicMock()
    event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
    event_log.get_latest_sequence = AsyncMock(return_value=0)
    event_log.run_exists = AsyncMock(return_value=False)

    replay_engine = MagicMock()
    replay_engine.rebuild_state = AsyncMock(
        return_value=MagicMock(
            status="executing",
            completed_tasks=set(),
            failed_tasks=set(),
            total_tokens=0,
            total_cost_usd=0.0,
            error_message=None,
        )
    )

    executor = UnifiedExecutor(event_log=event_log, replay_engine=replay_engine)
    return executor, event_log, replay_engine


def _make_mock_strategy(result: StrategyResult | None = None):
    """Create a mock strategy that returns the given result."""
    strategy = MagicMock()
    strategy.validate = AsyncMock(return_value=[])
    strategy.execute = AsyncMock(
        return_value=result or StrategyResult(success=True, status="completed", total_tokens=50)
    )
    return strategy


# ═══════════════════════════════════════════════════════════════════
# Lease claim at execute start
# ═══════════════════════════════════════════════════════════════════


class TestClaimAtExecuteStart:
    def test_claim_at_execute_start(self):
        """execute() claims a lease when LEASE_ENABLED is true."""
        executor, _event_log, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = _make_mock_strategy()

        with (
            patch.object(executor, "_get_strategy", return_value=mock_strategy),
            patch(
                "app.services.substrate.lease_manager.try_claim_lease",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_claim,
            patch(
                "app.services.substrate.lease_manager.release_lease",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.substrate.lease_manager.renew_lease",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("app.config.settings.FLOWMANNER_LEASE_ENABLED", True),
        ):
            result = asyncio.run(executor.execute(db, workflow))

        assert result.success is True
        mock_claim.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# Already running — returns existing state
# ═══════════════════════════════════════════════════════════════════


class TestAlreadyRunning:
    def test_execute_returns_already_running_when_lease_held_by_other(self):
        """Worker B calling execute() for a run held by worker A returns
        'already_running' without re-executing."""
        executor, event_log, _replay_engine = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        # Worker A holds the lease
        worker_a_lease = _make_lease_row("worker-a", "run-1")

        # Patch at lease_manager module level (where LeaseManager imports them)
        with (
            patch(
                "app.services.substrate.lease_manager.try_claim_lease",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.services.substrate.lease_manager.get_active_lease",
                new_callable=AsyncMock,
                return_value=worker_a_lease,
            ),
            patch(
                "app.services.substrate.lease_manager.release_lease",
                new_callable=AsyncMock,
            ),
            patch("app.config.settings.FLOWMANNER_LEASE_ENABLED", True),
        ):
            result = asyncio.run(executor.execute(db, workflow, run_id="run-1"))

        assert result.status == "already_running"
        assert "worker-a" in result.error
        # Should NOT have called mission.started (no execution)
        append_calls = event_log.append.call_args_list
        mission_started_calls = [
            c
            for c in append_calls
            if len(c[0]) > 2 and isinstance(c[0][2], list) and any(e.get("type") == "mission.started" for e in c[0][2])
        ]
        assert len(mission_started_calls) == 0


# ═══════════════════════════════════════════════════════════════════
# Release on success / exception
# ═══════════════════════════════════════════════════════════════════


class TestReleaseOnExit:
    def test_release_on_success(self):
        """Successful execute() releases the lease at the end."""
        executor, _event_log, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = _make_mock_strategy()

        with (
            patch.object(executor, "_get_strategy", return_value=mock_strategy),
            patch(
                "app.services.substrate.lease_manager.try_claim_lease",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.services.substrate.lease_manager.release_lease",
                new_callable=AsyncMock,
            ) as mock_release,
            patch(
                "app.services.substrate.lease_manager.renew_lease",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("app.config.settings.FLOWMANNER_LEASE_ENABLED", True),
        ):
            result = asyncio.run(executor.execute(db, workflow))

        assert result.success is True
        # release_lease should have been called (via LeaseManager.release)
        mock_release.assert_called()

    def test_release_on_exception(self):
        """execute() that raises an exception still releases the lease."""
        executor, _event_log, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = MagicMock()
        mock_strategy.validate = AsyncMock(return_value=[])
        mock_strategy.execute = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch.object(executor, "_get_strategy", return_value=mock_strategy),
            patch(
                "app.services.substrate.lease_manager.try_claim_lease",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.services.substrate.lease_manager.release_lease",
                new_callable=AsyncMock,
            ) as mock_release,
            patch(
                "app.services.substrate.lease_manager.renew_lease",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("app.config.settings.FLOWMANNER_LEASE_ENABLED", True),
        ):
            result = asyncio.run(executor.execute(db, workflow))

        assert result.success is False
        assert result.status == "failed"
        # release_lease should still have been called
        mock_release.assert_called()


# ═══════════════════════════════════════════════════════════════════
# Lease disabled flag
# ═══════════════════════════════════════════════════════════════════


class TestLeaseDisabledFlag:
    def test_lease_disabled_flag(self):
        """When FLOWMANNER_LEASE_ENABLED=false, no lease is claimed."""
        executor, _event_log, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = _make_mock_strategy()

        with (
            patch.object(executor, "_get_strategy", return_value=mock_strategy),
            patch(
                "app.services.substrate.lease_manager.try_claim_lease",
                new_callable=AsyncMock,
            ) as mock_claim,
            patch("app.config.settings.FLOWMANNER_LEASE_ENABLED", False),
        ):
            result = asyncio.run(executor.execute(db, workflow))

        assert result.success is True
        # try_claim_lease should NOT have been called
        mock_claim.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# Heartbeat keeps lease alive
# ═══════════════════════════════════════════════════════════════════


class TestHeartbeatKeepsLeaseAlive:
    def test_heartbeat_keeps_lease_alive(self):
        """A run that takes >TTL but <TTL+heartbeat_interval keeps the lease
        because the heartbeat renews it."""
        from app.services.substrate.lease_manager import LeaseManager

        lm = LeaseManager(worker_id="test-worker", ttl_seconds=1, heartbeat_interval_seconds=1)

        renew_count = [0]

        async def mock_renew(db):
            renew_count[0] += 1
            return True

        lm.renew = mock_renew
        lm._run_id = "run-heartbeat"

        stop = asyncio.Event()

        async def run_heartbeat():
            await lm.heartbeat_loop(AsyncMock(), stop)

        async def test():
            task = asyncio.create_task(run_heartbeat())
            # Wait long enough for at least 2 renewals (interval=1s)
            await asyncio.sleep(2.5)
            stop.set()
            await task

        asyncio.run(test())
        # At least 1 renewal should have occurred
        assert renew_count[0] >= 1


# ═══════════════════════════════════════════════════════════════════
# Heartbeat detects lost lease
# ═══════════════════════════════════════════════════════════════════


class TestHeartbeatDetectsLostLease:
    def test_heartbeat_detects_lost_lease(self):
        """When renew returns False (lease stolen), heartbeat sets lease_lost."""
        from app.services.substrate.lease_manager import LeaseManager

        lm = LeaseManager(worker_id="test-worker", ttl_seconds=1, heartbeat_interval_seconds=1)

        async def mock_renew_fail(db):
            return False

        lm.renew = mock_renew_fail
        lm._run_id = "run-lost"

        stop = asyncio.Event()

        async def run_heartbeat():
            await lm.heartbeat_loop(AsyncMock(), stop)

        async def test():
            task = asyncio.create_task(run_heartbeat())
            await asyncio.sleep(1.5)
            await task

        asyncio.run(test())
        assert lm.lease_lost is True


# ═══════════════════════════════════════════════════════════════════
# Substrate events emitted
# ═══════════════════════════════════════════════════════════════════


class TestSubstrateEventsEmitted:
    def test_substrate_events_emitted(self):
        """execute() emits run.lease.claimed and run.lease.released events."""
        executor, event_log, _ = _make_mock_executor()
        workflow = _make_workflow()
        db = AsyncMock()

        mock_strategy = _make_mock_strategy()

        with (
            patch.object(executor, "_get_strategy", return_value=mock_strategy),
            patch(
                "app.services.substrate.lease_manager.try_claim_lease",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.services.substrate.lease_manager.release_lease",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.substrate.lease_manager.renew_lease",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch("app.config.settings.FLOWMANNER_LEASE_ENABLED", True),
        ):
            result = asyncio.run(executor.execute(db, workflow))

        assert result.success is True

        # Check event_log.append calls for lease events
        append_calls = event_log.append.call_args_list
        event_types = []
        for call in append_calls:
            if len(call[0]) > 2 and isinstance(call[0][2], list):
                for evt in call[0][2]:
                    if isinstance(evt, dict):
                        event_types.append(evt.get("type"))

        assert "run.lease.claimed" in event_types, f"Expected run.lease.claimed in {event_types}"
        assert "run.lease.released" in event_types, f"Expected run.lease.released in {event_types}"


# ═══════════════════════════════════════════════════════════════════
# LeaseManager unit tests
# ═══════════════════════════════════════════════════════════════════


class TestLeaseManager:
    def test_lease_manager_init_defaults(self):
        """LeaseManager initializes with default worker_id and ttl."""
        from app.services.substrate.lease_manager import LeaseManager

        lm = LeaseManager()
        assert lm.worker_id is not None
        assert "-" in lm.worker_id  # hostname-pid format
        assert lm.run_id is None
        assert lm.lease_lost is False

    def test_lease_manager_init_custom(self):
        """LeaseManager accepts custom worker_id and ttl."""
        from app.services.substrate.lease_manager import LeaseManager

        lm = LeaseManager(worker_id="custom-worker", ttl_seconds=120)
        assert lm.worker_id == "custom-worker"
        assert lm._ttl_seconds == 120

    def test_lease_lost_error_exists(self):
        """LeaseLostError is importable and is an Exception subclass."""
        assert issubclass(LeaseLostError, Exception)
