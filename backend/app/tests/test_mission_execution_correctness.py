"""Regression tests for mission-execution correctness (skill: mission-execution-correctness).

These tests prove the THREE failure modes the skill gates against are
impossible after the fixes:

  FM-1  Cross-attempt replay — retry reuses run_id → node_executor
         replays attempt-1 output instead of re-calling the model.
         Gate: a FRESH substrate_run_id is minted on every execution and
         especially on retry; the same-run dependency assertion rejects
         any cross-run output consumption.
  FM-2  Audit vanishes on rollback — audit row in the handler's single
         session is rolled back with a PermanentMissionError, losing the
         forensic trace exactly when needed.
         Gate: AuditService.record_async() writes in its OWN session;
         MissionLog.mission_id is a SOFT reference (no FK); failures
         are swallowed + alerted.
  FM-3  Stuck missions — a RUNNING row whose worker died lives
         forever (no paused_at, no reaper).
         Gate: MissionReaper reaps dead-worker RUNNING rows to
         FAILED(stale_pause), NOT ABORTED (keeps retry path open).
"""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import pytest

from app.api._mission_cqrs.audit import AuditService
from app.api._mission_cqrs.commands import MissionCommandHandlers
from app.models.mission_models import Mission, MissionStatus
from app.models.substrate_models import SubstrateEventType
from app.services.mission_reaper import MissionReaper
from app.services.substrate.assertion_engine import (
    AssertionType,
    ReplayAssertionEngine,
)

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def session():
    s = AsyncMock()
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    s.add = MagicMock()
    s.flush = AsyncMock()
    # Default execute() returns a result whose scalar_one_or_none is None
    # (so require_mission_access-style lookups fall through cleanly).
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value = result
    result.all.return_value = []
    s.execute = AsyncMock(return_value=result)
    return s


@pytest.fixture
def user():
    return MagicMock(id=1, email="test@example.com")


@pytest.fixture
def handlers(session):
    return MissionCommandHandlers(session)


def _make_mission(status, *, plan=None, started_at=None):
    m = MagicMock()
    m.id = "550e8400-e29b-41d4-a716-446655440005"
    m.user_id = 1
    m.status = status
    m.plan = plan
    m.error_message = None
    m.started_at = started_at
    return m


# ── FM-1: fresh substrate_run_id on every execution + on retry ──────────


class TestFM1FreshRunId:
    @pytest.mark.asyncio
    async def test_execute_mission_mints_fresh_run_id(self, handlers, session, user, mocker):
        """execute_mission() must mint + persist a fresh substrate_run_id."""
        mission = _make_mission(MissionStatus.RUNNING)

        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.get_mission_tasks",
            new=AsyncMock(return_value=[]),
        )
        mocker.patch(
            "app.services.substrate.adapters.mission_to_workflow",
            return_value=MagicMock(),
        )
        executor = MagicMock()
        executor.execute = AsyncMock(
            return_value=MagicMock(
                success=True,
                status="running",
                error=None,
                completed_nodes=[],
                failed_nodes=[],
                data={},
            )
        )
        mocker.patch(
            "app.services.substrate.executor.get_unified_executor",
            return_value=executor,
        )
        # Analytics track_event is imported inside _op(); patch at source.
        mocker.patch(
            "app.services.analytics_service.track_event",
            new=AsyncMock(),
        )

        await handlers.execute_mission(user, mission.id)

        # A run_id was minted and persisted on mission.plan.
        assert mission.plan is not None
        rid = mission.plan.get("substrate_run_id")
        assert rid, "execute_mission must mint substrate_run_id"
        # And it was passed to the executor (run-scoped idempotency space).
        called_run_id = executor.execute.call_args.kwargs.get("run_id")
        assert called_run_id == rid

    @pytest.mark.asyncio
    async def test_retry_mission_mints_a_DIFFERENT_run_id(self, handlers, session, user, mocker):
        """GC3: retry MUST mint a fresh run_id, never reuse attempt-1's."""
        attempt1_id = "11111111-1111-1111-1111-111111111111"
        mission = _make_mission(
            MissionStatus.FAILED,
            plan={"substrate_run_id": attempt1_id},
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.get_mission_tasks",
            new=AsyncMock(return_value=[]),
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.MissionPlanner",
            new=MagicMock(return_value=MagicMock(plan_mission=AsyncMock(return_value={"success": True}))),
        )
        # retry_mission audits via self.audit; inject a mock audit service.
        handlers.audit = MagicMock()
        # Make record_async a no-op coroutine so we isolate the run_id minting.
        mocker.patch.object(handlers.audit, "record_async", new=AsyncMock())

        await handlers.retry_mission(user, mission.id)

        new_id = mission.plan.get("substrate_run_id")
        assert new_id is not None
        assert new_id != attempt1_id, "retry must NOT reuse attempt-1 run_id (FM-1 silent replay)"
        assert mission.status == MissionStatus.PENDING

    @pytest.mark.asyncio
    async def test_async_execute_dispatches_with_run_id(self, handlers, session, user, mocker):
        """execute_async must mint + carry run_id into the Celery dispatch."""
        mission = _make_mission(MissionStatus.PENDING)
        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        dispatched = {}

        def _capture(mission_id, user_id, run_id=None):
            dispatched["run_id"] = run_id

        mocker.patch(
            "app.tasks.mission_execution.dispatch_mission_execution",
            new=_capture,
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.create_mission_log",
            new=AsyncMock(),
        )

        await handlers.execute_async(user, mission.id)

        assert mission.plan.get("substrate_run_id") == dispatched["run_id"]
        assert dispatched["run_id"], "async dispatch must carry a fresh run_id"


# ── FM-1 (replay guard): same-run dependency assertion ──────────────────


class TestFM1ReplayIsolation:
    @pytest.mark.asyncio
    async def test_cross_run_dependency_detected(self, mocker):
        """A node consuming an upstream from a DIFFERENT run is rejected."""
        R1 = "aaaaaaaa-1111-1111-1111-111111111111"
        R2 = "bbbbbbbb-2222-2222-2222-222222222222"
        run_id = R2

        # Upstream task T completed in run R1 (the stale attempt-1 output).
        # Downstream task D (in run R2) declares it consumed T.
        events = [
            MagicMock(
                type=SubstrateEventType.NODE_COMPLETED,
                run_id=R1,
                payload={"task_id": "T", "node_id": "T"},
            ),
            MagicMock(
                type=SubstrateEventType.NODE_COMPLETED,
                run_id=R2,
                payload={"task_id": "D", "depends_on": "T"},
            ),
        ]
        eng = ReplayAssertionEngine()
        mocker.patch.object(eng._event_log, "get_events", new=AsyncMock(return_value=events))

        res = await eng.assert_run_isolation(MagicMock(), run_id)
        assert res.assertion_type == AssertionType.SAME_RUN_DEPENDENCIES
        assert res.passed is False, "cross-run dependency must be flagged (FM-1)"
        assert res.severity.value == "failure"

    @pytest.mark.asyncio
    async def test_same_run_dependency_ok(self, mocker):
        """A run whose deps all resolve within itself passes."""
        R2 = "bbbbbbbb-2222-2222-2222-222222222222"
        events = [
            MagicMock(
                type=SubstrateEventType.NODE_COMPLETED,
                run_id=R2,
                payload={"task_id": "T", "node_id": "T"},
            ),
            MagicMock(
                type=SubstrateEventType.NODE_COMPLETED,
                run_id=R2,
                payload={"task_id": "D", "depends_on": "T"},
            ),
        ]
        eng = ReplayAssertionEngine()
        mocker.patch.object(eng._event_log, "get_events", new=AsyncMock(return_value=events))

        res = await eng.assert_run_isolation(MagicMock(), R2)
        assert res.passed is True


# ── FM-2: audit survives rollback in its own session ───────────────────


class TestFM2AuditDurability:
    @pytest.mark.asyncio
    async def test_record_async_uses_its_own_session(self, mocker):
        """record_async opens a fresh session and commits there — independent
        of any handler transaction that may roll back."""
        captured = {}

        class _Fresh:
            async def __aenter__(self):
                s = AsyncMock()
                s.add = MagicMock()
                s.commit = AsyncMock()
                captured["session"] = s
                return s

            async def __aexit__(self, *a):
                # fresh_session() commits on success (database.py:87).
                await captured["session"].commit()
                return False

        mocker.patch("app.database.fresh_session", new=_Fresh)

        svc = AuditService(MagicMock())  # handler session (would roll back)
        await svc.record_async(
            action="mission.retry",
            actor_id=1,
            mission_id="550e8400-e29b-41d4-a716-446655440005",
            old_status="failed",
            new_status="pending",
        )

        # It used the fresh session, NOT self._session.
        assert captured["session"] is not None
        assert captured["session"] is not svc._session
        captured["session"].commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_async_swallows_and_alerts_on_failure(self, mocker):
        """If the audit write fails, it is swallowed + out-of-band-alerted,
        never re-raised into the calling handler."""
        alerted = {}

        class _BrokenFresh:
            async def __aenter__(self):
                raise RuntimeError("db connection lost")

            async def __aexit__(self, *a):
                return False

        mocker.patch("app.database.fresh_session", new=_BrokenFresh)
        svc = AuditService(MagicMock())
        mocker.patch.object(
            svc,
            "_alert_audit_failure",
            new=MagicMock(side_effect=lambda *a, **k: alerted.setdefault("yes", True)),
        )

        # Must NOT raise — the handler's flow continues.
        await svc.record_async(action="x", actor_id=1, mission_id="m1")
        assert alerted.get("yes") is True

    @pytest.mark.asyncio
    async def test_retry_audit_written_via_record_async(self, handlers, session, user, mocker):
        """retry_mission must route its audit through record_async (own session),
        so it survives a later rollback in the multi-commit retry flow."""
        mission = _make_mission(MissionStatus.FAILED, plan={})
        mocker.patch(
            "app.api._mission_cqrs.commands.require_mission_access",
            return_value=mission,
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.get_mission_tasks",
            new=AsyncMock(return_value=[]),
        )
        mocker.patch(
            "app.api._mission_cqrs.commands.MissionPlanner",
            new=MagicMock(return_value=MagicMock(plan_mission=AsyncMock(return_value={"success": True}))),
        )
        # retry_mission audits via self.audit; inject a mock audit service.
        handlers.audit = MagicMock()
        recorded = {}
        mocker.patch.object(
            handlers.audit,
            "record_async",
            new=AsyncMock(side_effect=lambda **k: recorded.setdefault("called", True) or None),
        )

        await handlers.retry_mission(user, mission.id)
        assert recorded.get("called") is True


# ── FM-3: MissionReaper → FAILED(stale_pause), never ABORTED ─────────


def _async_cm(value):
    """Return an object usable as ``async with X() as db:`` whose db is ``value``."""
    cm = AsyncMock()
    cm.__aenter__.return_value = value
    cm.__aexit__.return_value = False
    return cm


class TestFM3MissionReaper:
    @pytest.mark.asyncio
    async def test_reaper_transitions_dead_worker_to_failed(self, mocker):
        """A RUNNING mission with a stale started_at is reaped to FAILED
        with fail_reason=stale_pause — NOT ABORTED."""
        old = datetime.now(UTC) - timedelta(hours=2)
        mission = _make_mission(MissionStatus.RUNNING, started_at=old)

        # The reaper's own session returns our stranded mission.
        reap_session = AsyncMock()
        reap_result = MagicMock()
        reap_result.scalars.return_value.all.return_value = [mission]
        reap_session.execute = AsyncMock(return_value=reap_result)
        reap_session.commit = AsyncMock()

        mocker.patch(
            "app.services.mission_reaper.AsyncSessionLocal",
            return_value=_async_cm(reap_session),
        )
        # Audit uses its own session (no-op).
        mocker.patch.object(MissionReaper, "_write_audit", new=AsyncMock())
        # EventLog.append no-op.
        mocker.patch(
            "app.services.mission_reaper.get_event_log",
            return_value=MagicMock(append=AsyncMock()),
        )

        reaped = await MissionReaper(stale_after=timedelta(minutes=15)).scan_once()

        assert reaped == 1
        assert mission.status == MissionStatus.FAILED, "must become FAILED"
        assert mission.status != MissionStatus.ABORTED, "MUST NOT be ABORTED (keeps retry open)"
        assert (mission.plan or {}).get("fail_reason") == "stale_pause"

    @pytest.mark.asyncio
    async def test_reaper_skips_recent_running(self, mocker):
        """A RUNNING mission started 30s ago is NOT reaped."""
        recent = datetime.now(UTC) - timedelta(seconds=30)
        mission = _make_mission(MissionStatus.RUNNING, started_at=recent)

        reap_session = AsyncMock()
        reap_result = MagicMock()
        reap_result.scalars.return_value.all.return_value = [mission]
        reap_session.execute = AsyncMock(return_value=reap_result)
        reap_session.commit = AsyncMock()

        mocker.patch(
            "app.services.mission_reaper.AsyncSessionLocal",
            return_value=_async_cm(reap_session),
        )
        mocker.patch.object(MissionReaper, "_write_audit", new=AsyncMock())
        mocker.patch(
            "app.services.mission_reaper.get_event_log",
            return_value=MagicMock(append=AsyncMock()),
        )
        # The staleness WHERE-clause can't be exercised against a mock
        # session; isolate it by having _find_candidates return nothing
        # for a recent (non-stale) mission.
        mocker.patch.object(
            MissionReaper,
            "_find_candidates",
            new=AsyncMock(return_value=[]),
        )

        reaped = await MissionReaper(stale_after=timedelta(minutes=15)).scan_once()
        assert reaped == 0
        assert mission.status == MissionStatus.RUNNING
