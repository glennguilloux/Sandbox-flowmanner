"""Phase 3.5 cutover — B4 regression tests.

B4: ``backend/app/api/_mission_cqrs/compat.py::dual_write_sync_run_status``
swallows failures at
``logger.debug("dual_write_sync_run_status_failed mission_id=%s", ...)``.
That means a successful mission mutation that subsequently fails to
propagate to the Blueprint/Run tables produces no operational signal —
the divergence stays silent until the consistency check finds it.

FIX (per ``plans/blueprint-run-phase3.5-cutover-plan.md`` §0 row B4):
- Promote the failure log to ``logger.warning``.
- Add a Prometheus counter ``dual_write_failures_total{site}`` and
  increment it at every failure site (run_status, blueprint, soft_delete).
- Add ``scripts/reconcile_dual_write.py`` (out of scope for these tests;
  tracked elsewhere).

These tests MUST FAIL on the current code.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
class TestDualWriteFailureVisibility:
    """Test-first regression for B4."""

    async def test_dual_write_sync_run_status_failure_logs_at_warning(self, caplog):
        """FIX: failures in dual_write_sync_run_status must log at WARNING.

        The current implementation uses ``logger.debug`` which is filtered
        out of operational log streams — intentional DEBUG suppression of
        a divergence signal.
        """
        broken_db = AsyncMock()
        broken_db.execute.side_effect = RuntimeError("simulated dual-write failure")

        @asynccontextmanager
        async def broken_session():
            yield broken_db

        # Force the except-branch: AsyncSessionLocal() calls the broken
        # contextmanager, which yields the broken session, whose .execute
        # raises. The except clause in dual_write_sync_run_status should
        # catch it and log.
        #
        # CRITICAL: patch the source module attribute
        # (app.database.AsyncSessionLocal), NOT compat.AsyncSessionLocal
        # — the production function does ``from app.database import
        # AsyncSessionLocal`` INSIDE its body, rebinding on every call.
        # Patching the destination would not intercept anything.
        with caplog.at_level(logging.DEBUG, logger="app.api._mission_cqrs.compat"):
            with patch("app.database.AsyncSessionLocal", broken_session):
                from app.api._mission_cqrs.compat import dual_write_sync_run_status

                await dual_write_sync_run_status("mission-test-id-b4", 1, "completed")

        failure_records = [r for r in caplog.records if "dual_write_sync_run_status_failed" in r.getMessage()]
        assert failure_records, "Expected a 'dual_write_sync_run_status_failed' log record on failure"
        # Currently DEBUG. Fix promotes to WARNING.
        assert failure_records[0].levelname == "WARNING", (
            f"B4 FIX MISSING: dual_write_sync_run_status logs at "
            f"{failure_records[0].levelname} on failure, must be WARNING. "
            f"Silent DEBUG means operators have no signal for blueprint/mission "
            f"divergence until the consistency check finds it."
        )

    async def test_dual_write_sync_blueprint_failure_logs_at_warning(self, caplog):
        """FIX: same WARNING-level requirement for ``dual_write_sync_blueprint``."""
        broken_db = AsyncMock()
        broken_db.execute.side_effect = RuntimeError("simulated dual-write failure")

        @asynccontextmanager
        async def broken_session():
            yield broken_db

        with caplog.at_level(logging.DEBUG, logger="app.api._mission_cqrs.compat"):
            with patch("app.database.AsyncSessionLocal", broken_session):
                from app.api._mission_cqrs.compat import dual_write_sync_blueprint

                await dual_write_sync_blueprint("mission-test-id-b4-bp", 1, title="x")

        failure_records = [r for r in caplog.records if "dual_write_sync_blueprint_failed" in r.getMessage()]
        assert failure_records, "Expected a 'dual_write_sync_blueprint_failed' log record on failure"
        assert failure_records[0].levelname == "WARNING", (
            f"B4 FIX MISSING: dual_write_sync_blueprint logs at " f"{failure_records[0].levelname}, must be WARNING."
        )
