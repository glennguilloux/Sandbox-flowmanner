"""Phase 3.5 cutover — reconcile_dual_write.py tests (Phase C.1 deliverable).

The five required tests from the cutover plan:
  1. ``test_dry_run_reports_orphan_and_exits_1`` — exit code 1 + counter
     increments + "orphan" reported in stdout.
  2. ``test_fix_creates_missing_blueprint`` — ``db.add`` called with a
     Blueprint whose ``id`` matches ``str(mission.id)``.
  3. ``test_fix_is_idempotent`` — second ``--fix`` run makes zero writes.
  4. ``test_no_divergence_exits_0`` — clean parity returns 0.
  5. ``test_dry_run_does_not_write`` — zero db.add / db.commit calls in
     dry-run mode.

Plus pure-function unit tests for divergence detection and field-mapping
helpers, exposed by ``scripts.reconcile_dual_write``.

Approach: pure-function unit tests + integration tests using a mocked
AsyncSession per the B4-test pattern in
``test_dual_write_failure_logged_at_warning_b4.py``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# Module under test — written AFTER this test file (TDD discipline).
# When the script doesn't exist, this import raises ModuleNotFoundError,
# pre-commit's pytest step reports a collection failure, and the test
# reports the missing file as the cause.
from scripts.reconcile_dual_write import (
    _amain,
    find_orphan_mission_ids,
    make_blueprint_from_mission,
    map_mission_status_to_run_status,
    should_create_run,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _mk_mission(
    *,
    id_: str | None = None,
    status="completed",
    user_id=1,
    title="t",
    description="",
    workspace_id=None,
    mission_type="solo",
    results=None,
    error_message=None,
    tokens_used=0,
    actual_cost=None,
    started_at=None,
    completed_at=None,
    deleted_at=None,
):
    """Construct a Mission-shaped MagicMock with all attrs needed by the script."""
    m = MagicMock()
    m.id = id_ or str(uuid4())
    m.status = status
    m.user_id = user_id
    m.title = title
    m.description = description
    m.workspace_id = workspace_id
    m.mission_type = mission_type
    m.results = results
    m.error_message = error_message
    m.tokens_used = tokens_used
    m.actual_cost = actual_cost
    m.started_at = started_at
    m.completed_at = completed_at
    m.deleted_at = deleted_at
    return m


def _mk_blueprint(*, id_: str | None = None, definition=None, deleted_at=None):
    bp = MagicMock()
    bp.id = id_ or str(uuid4())
    bp.definition = definition or {}
    bp.deleted_at = deleted_at
    return bp


# ── Pure-function tests: find_orphan_mission_ids ───────────────────────────────


class TestFindOrphanMissions:
    def test_direct_id_match_is_not_orphan(self):
        mid = str(uuid4())
        m = _mk_mission(id_=mid)
        bp = _mk_blueprint(id_=mid)
        assert find_orphan_mission_ids([m], [bp]) == set()

    def test_source_mission_id_match_is_not_orphan(self):
        mid = str(uuid4())
        bp_id = str(uuid4())
        m = _mk_mission(id_=mid)
        bp = _mk_blueprint(id_=bp_id, definition={"_source_mission_id": mid})
        assert find_orphan_mission_ids([m], [bp]) == set()

    def test_no_blueprint_is_orphan(self):
        mid = str(uuid4())
        m = _mk_mission(id_=mid)
        assert find_orphan_mission_ids([m], []) == {mid}

    def test_unrelated_blueprint_does_not_match(self):
        mid = str(uuid4())
        bp_id = str(uuid4())
        m = _mk_mission(id_=mid)
        bp = _mk_blueprint(id_=bp_id, definition={"_source_mission_id": "different"})
        assert find_orphan_mission_ids([m], [bp]) == {mid}

    def test_deleted_blueprint_does_not_count(self):
        """Soft-deleted blueprints must NOT mask an orphan."""
        mid = str(uuid4())
        m = _mk_mission(id_=mid)
        bp = _mk_blueprint(id_=mid, deleted_at=datetime.now(UTC))
        assert find_orphan_mission_ids([m], [bp]) == {mid}

    def test_mixed_linkage_returns_correct_orphan_set(self):
        mid_a, mid_b, mid_c = str(uuid4()), str(uuid4()), str(uuid4())
        bp_unrelated = str(uuid4())
        m_a = _mk_mission(id_=mid_a)
        m_b = _mk_mission(id_=mid_b)
        m_c = _mk_mission(id_=mid_c)
        bps = [
            _mk_blueprint(id_=str(uuid4()), definition={"_source_mission_id": mid_a}),
            _mk_blueprint(id_=mid_b),  # direct id match for m_b
            _mk_blueprint(id_=bp_unrelated, definition={"_source_mission_id": "other"}),
        ]
        assert find_orphan_mission_ids([m_a, m_b, m_c], bps) == {mid_c}


# ── Pure-function tests: map_mission_status_to_run_status ──────────────────────


class TestMapMissionStatusToRunStatus:
    def test_terminal_passthrough_completed(self):
        assert map_mission_status_to_run_status("completed") == "completed"

    def test_terminal_passthrough_failed(self):
        assert map_mission_status_to_run_status("failed") == "failed"

    def test_terminal_passthrough_aborted(self):
        assert map_mission_status_to_run_status("aborted") == "aborted"

    def test_running_maps_to_executing(self):
        assert map_mission_status_to_run_status("running") == "executing"

    def test_planning_maps_to_pending(self):
        assert map_mission_status_to_run_status("planning") == "pending"

    def test_planned_maps_to_pending(self):
        assert map_mission_status_to_run_status("planned") == "pending"

    def test_approved_maps_to_completed(self):
        assert map_mission_status_to_run_status("approved") == "completed"


# ── Pure-function tests: should_create_run ─────────────────────────────────────


class TestShouldCreateRun:
    def test_completed_true(self):
        assert should_create_run("completed") is True

    def test_failed_true(self):
        assert should_create_run("failed") is True

    def test_aborted_true(self):
        assert should_create_run("aborted") is True

    def test_pending_false(self):
        assert should_create_run("pending") is False

    def test_planning_false(self):
        assert should_create_run("planning") is False

    def test_draft_false(self):
        assert should_create_run("draft") is False

    def test_unknown_false(self):
        """Unknown/typo'd statuses must NOT trigger a Run creation."""
        assert should_create_run("wat") is False


# ── Pure-function tests: make_blueprint_from_mission ───────────────────────────


class TestMakeBlueprintFromMission:
    def test_id_is_str_of_mission_id(self):
        mid = str(uuid4())
        m = _mk_mission(id_=mid)
        bp = make_blueprint_from_mission(m)
        assert bp["id"] == mid

    def test_definition_has_source_mission_id_only(self):
        """The dual-write linkage MUST be present as `_source_mission_id`."""
        mid = str(uuid4())
        m = _mk_mission(id_=mid)
        bp = make_blueprint_from_mission(m)
        assert bp["definition"] == {"_source_mission_id": mid}

    def test_propagates_user_id_and_workspace_id(self):
        mid = str(uuid4())
        m = _mk_mission(id_=mid, user_id=42, workspace_id="ws-1")
        bp = make_blueprint_from_mission(m)
        assert bp["user_id"] == 42
        assert bp["workspace_id"] == "ws-1"

    def test_published_status_for_completed_mission(self):
        bp = make_blueprint_from_mission(_mk_mission(id_=str(uuid4()), status="completed"))
        assert bp["status"] == "published"

    def test_published_status_for_approved_mission(self):
        bp = make_blueprint_from_mission(_mk_mission(id_=str(uuid4()), status="approved"))
        assert bp["status"] == "published"

    def test_draft_status_for_active_mission(self):
        for active in ("pending", "planning", "running", "queued"):
            bp = make_blueprint_from_mission(_mk_mission(id_=str(uuid4()), status=active))
            assert bp["status"] == "draft", f"status={active} should yield draft"

    def test_handles_status_as_enum(self):
        """Support MissionStatus enum values via .value attribute."""
        m = MagicMock()
        m.id = str(uuid4())
        m.user_id = 1
        m.title = "t"
        m.description = ""
        m.workspace_id = None
        m.mission_type = "solo"
        m.status = MagicMock()
        m.status.value = "running"
        bp = make_blueprint_from_mission(m)
        assert bp["status"] == "draft"


# ── Integration tests (mocked AsyncSession, B4 pattern) ─────────────────────────


def _count_result(n: int):
    """Build a mock .execute() result for ``select(func.count())``."""
    r = MagicMock()
    r.scalar.return_value = n
    return r


def _list_result(items):
    """Build a mock .execute() result for ``select(Mission).scalars().all()``."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = list(items)
    return r


def _session_for_reconcile(*, stats_results, fix_results=()):
    """Return a (db_factory, recorded_calls) pair for a mocked reconcile run.

    ``stats_results`` is the queue of .execute() results the gather pass
    will pop in order: count(missions), count(blueprints),
    count(blueprints_with_source), list(blueprints), list(missions).

    ``fix_results`` is the queue the fix pass opens with — usually empty
    because `_reconcile_missing` only calls db.add / db.commit.
    """
    stats_results = list(stats_results)
    fix_results = list(fix_results)
    sessions: list[AsyncMock] = []

    def _build_db(queue):
        async def _execute(stmt):
            if not queue:
                raise AssertionError("Mock session .execute() called more times than pre-programmed")
            return queue.pop(0)

        db = AsyncMock()
        db.execute = _execute
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        return db

    # First session = gather pass, second = fix pass
    gather_db = _build_db(stats_results)
    fix_db = _build_db(fix_results)
    call_count = [0]

    @asynccontextmanager
    async def session_ctx():
        call_count[0] += 1
        if call_count[0] == 1:
            yield gather_db
        else:
            yield fix_db

    return session_ctx, gather_db, fix_db


@pytest.mark.asyncio
class TestReconcileDryRun:
    """Tests 1 + 4 + 5 from the cutover plan."""

    async def test_dry_run_reports_orphan_and_exits_1(self):
        """Test 1: --dry-run reports orphan mission and exits with code 1.

        Verification: exit_code == 1, Prometheus counter incremented
        once per orphan, no db.add / db.commit calls.
        """
        orphan_id = str(uuid4())
        orphan_mission = _mk_mission(id_=orphan_id, title="orphan mission")

        session_ctx, gather_db, fix_db = _session_for_reconcile(
            stats_results=[
                _count_result(1),  # count(missions where deleted_at is None)
                _count_result(0),  # count(blueprints where deleted_at is None)
                _count_result(0),  # count(blueprints with _source_mission_id)
                _list_result([]),  # list(all non-deleted blueprints)
                _list_result([orphan_mission]),  # list(sampled missions, limit=1000)
            ],
        )

        args = SimpleNamespace(
            dry_run=True,
            fix=False,
            limit=1000,
            batch_size=100,
            json_only=False,
        )

        with (
            patch("app.database.AsyncSessionLocal", session_ctx),
            patch("scripts.reconcile_dual_write.dual_write_failures_total") as metric,
        ):
            exit_code = await _amain(args)

        assert exit_code == 1, "Dry-run with orphans must exit 1 (cron signal)"
        metric.labels.assert_called_with(site="reconcile")
        assert metric.labels().inc.call_count == 1, "Counter incremented once per orphan"

        # No writes occurred
        assert gather_db.add.call_count == 0
        assert gather_db.commit.call_count == 0
        assert fix_db.add.call_count == 0
        assert fix_db.commit.call_count == 0

    async def test_no_divergence_exits_0(self):
        """Test 4: when parity is 100%, dry-run exits cleanly with 0."""
        mid = str(uuid4())
        m = _mk_mission(id_=mid, title="matched")
        bp = _mk_blueprint(id_=mid, definition={"_source_mission_id": mid})

        session_ctx, gather_db, fix_db = _session_for_reconcile(
            stats_results=[
                _count_result(1),
                _count_result(1),
                _count_result(1),
                _list_result([bp]),
                _list_result([m]),
            ],
        )

        args = SimpleNamespace(
            dry_run=True,
            fix=False,
            limit=1000,
            batch_size=100,
            json_only=False,
        )

        with (
            patch("app.database.AsyncSessionLocal", session_ctx),
            patch("scripts.reconcile_dual_write.dual_write_failures_total") as metric,
        ):
            exit_code = await _amain(args)

        assert exit_code == 0, "All-matched parity must exit 0"
        # No orphan found ⇒ no metric increment
        metric.labels().inc.assert_not_called()
        assert gather_db.add.call_count == 0
        assert fix_db.add.call_count == 0

    async def test_dry_run_does_not_write(self):
        """Test 5: --dry-run is truly read-only (zero adds across both sessions)."""
        mid = str(uuid4())
        orphan = _mk_mission(id_=mid, status="completed", title="orphan")

        session_ctx, gather_db, fix_db = _session_for_reconcile(
            stats_results=[
                _count_result(1),
                _count_result(0),
                _count_result(0),
                _list_result([]),
                _list_result([orphan]),
            ],
        )

        args = SimpleNamespace(
            dry_run=True,
            fix=False,
            limit=1000,
            batch_size=100,
            json_only=False,
        )

        with (
            patch("app.database.AsyncSessionLocal", session_ctx),
            patch("scripts.reconcile_dual_write.dual_write_failures_total"),
        ):
            await _amain(args)

        # Invariant: zero writes across both sessions
        assert gather_db.commit.call_count == 0
        assert gather_db.add.call_count == 0
        assert fix_db.commit.call_count == 0
        assert fix_db.add.call_count == 0


@pytest.mark.asyncio
class TestReconcileFixCreatesMissingBlueprint:
    """Tests 2 + 3 from the cutover plan."""

    async def test_fix_creates_missing_blueprint(self):
        """Test 2: --fix produces a Blueprint whose id == str(mission.id)."""
        mid = str(uuid4())
        mission = _mk_mission(
            id_=mid,
            status="completed",
            user_id=42,
            title="Reconcile Me",
            workspace_id="ws-1",
        )

        session_ctx, _, fix_db = _session_for_reconcile(
            stats_results=[
                _count_result(1),
                _count_result(0),
                _count_result(0),
                _list_result([]),
                _list_result([mission]),
            ],
        )

        args = SimpleNamespace(
            dry_run=False,
            fix=True,
            limit=1000,
            batch_size=100,
            json_only=False,
        )

        with (
            patch("app.database.AsyncSessionLocal", session_ctx),
            patch("scripts.reconcile_dual_write.dual_write_failures_total"),
        ):
            exit_code = await _amain(args)

        assert exit_code == 0, "Fix mode with all orphans resolved must exit 0"

        # Blueprint, BlueprintVersion, and Run (because status=completed ⇒ has execution results)
        added = [c.args[0] for c in fix_db.add.call_args_list if c.args]
        added_ids = [obj.id for obj in added if hasattr(obj, "id")]
        assert mid in added_ids, f"Blueprint with id={mid} must be created. Added ids: {added_ids}"
        # Batch was committed
        assert fix_db.commit.call_count >= 1, "Fix must commit at least one batch"

    async def test_fix_is_idempotent(self):
        """Test 3: re-running --fix after a successful run does nothing.

        We model this by running the script twice against two prepared
        sessions. The first session sees an orphan ⇒ creates a blueprint.
        The second session sees parity ⇒ adds zero rows.
        """
        mid = str(uuid4())
        mission_orphan = _mk_mission(id_=mid, status="completed")

        # First session: orphan exists, fix creates a blueprint
        session_ctx_run1, _, fix_db_run1 = _session_for_reconcile(
            stats_results=[
                _count_result(1),
                _count_result(0),
                _count_result(0),
                _list_result([]),
                _list_result([mission_orphan]),
            ],
        )

        args = SimpleNamespace(
            dry_run=False,
            fix=True,
            limit=1000,
            batch_size=100,
            json_only=False,
        )

        with (
            patch("app.database.AsyncSessionLocal", session_ctx_run1),
            patch("scripts.reconcile_dual_write.dual_write_failures_total"),
        ):
            await _amain(args)

        first_run_writes = fix_db_run1.add.call_count
        assert (
            first_run_writes >= 3
        ), f"First --fix must add Blueprint + BlueprintVersion + Run (got {first_run_writes})"

        # Second session: blueprint now exists via _source_mission_id
        # so find_orphan_mission_ids returns empty set
        bp_now = _mk_blueprint(id_=mid, definition={"_source_mission_id": mid})
        mission_now = _mk_mission(id_=mid, status="completed")

        session_ctx_run2, _, fix_db_run2 = _session_for_reconcile(
            stats_results=[
                _count_result(1),
                _count_result(1),
                _count_result(1),
                _list_result([bp_now]),
                _list_result([mission_now]),
            ],
        )

        with (
            patch("app.database.AsyncSessionLocal", session_ctx_run2),
            patch("scripts.reconcile_dual_write.dual_write_failures_total"),
        ):
            await _amain(args)

        assert (
            fix_db_run2.add.call_count == 0
        ), f"Idempotent fix must add zero rows on the second run (got {fix_db_run2.add.call_count})"
