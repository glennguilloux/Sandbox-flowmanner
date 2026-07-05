"""Phase 3.5 cutover — B4 regression tests.

B4: ``backend/app/api/_mission_cqrs/compat.py::dual_write_sync_run_status``
previously swallowed failures at DEBUG level. Now ``_run_with_retry`` provides:
- WARNING-level structured logs on each retry attempt
- ERROR-level structured log with full traceback on final failure

FIX (per ``plans/blueprint-run-phase3.5-cutover-plan.md`` §0 row B4):
- ``_run_with_retry`` provides exponential-backoff retry (3 attempts) and
  structured logging at WARNING (retry) and ERROR (final failure).
- Prometheus counter ``dual_write_failures_total{site}`` (tracked elsewhere).
- ``scripts/reconcile_dual_write.py`` (out of scope; tracked elsewhere).

These tests verify the retry + structured logging behavior.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structlog.testing import capture_logs


@pytest.mark.asyncio
class TestDualWriteFailureVisibility:
    """Test-first regression for B4."""

    async def test_dual_write_sync_run_status_retries_then_errors(self):
        """_run_with_retry must emit WARNING on retry and ERROR on final failure.

        The old implementation used ``logger.debug`` which is filtered
        out of operational log streams. The new _run_with_retry ensures:
        - Attempt 1-2: WARNING with operation/attempt/error context
        - Attempt 3 (final): ERROR with full traceback
        """
        broken_db = AsyncMock()
        broken_db.execute.side_effect = RuntimeError("simulated dual-write failure")

        @asynccontextmanager
        async def broken_session():
            yield broken_db

        with (
            capture_logs() as logs,
            patch("app.database.AsyncSessionLocal", broken_session),
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            from app.api._mission_cqrs.compat import dual_write_sync_run_status

            await dual_write_sync_run_status("mission-test-id-b4", 1, "completed")

        # Check for retry warnings (attempts 1 and 2)
        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        assert len(retry_logs) >= 1, (
            f"Expected at least 1 'dual_write_retry' event during retry attempts. "
            f"Got events: {[e.get('event') for e in logs]}"
        )
        assert all(e["log_level"] == "warning" for e in retry_logs), "Retry events must be at WARNING level"
        # Verify structured context on retry logs
        assert retry_logs[0]["operation"] == "sync_run_status"
        assert retry_logs[0]["mission_id"] == "mission-test-id-b4"

        # Check for final failure at ERROR level
        failure_logs = [e for e in logs if e.get("event") == "dual_write_failed"]
        assert (
            failure_logs
        ), f"Expected a 'dual_write_failed' event on final failure. Got events: {[e.get('event') for e in logs]}"
        assert failure_logs[0]["log_level"] == "error", (
            f"B4 FIX: dual_write_failed must log at ERROR level (got {failure_logs[0]['log_level']}). "
            f"This ensures operators have a clear signal for blueprint/mission divergence."
        )
        assert failure_logs[0]["attempts"] == 3

    async def test_dual_write_sync_blueprint_retries_then_errors(self):
        """Same ERROR-level requirement for ``dual_write_sync_blueprint``."""
        broken_db = AsyncMock()
        broken_db.execute.side_effect = RuntimeError("simulated dual-write failure")

        @asynccontextmanager
        async def broken_session():
            yield broken_db

        with (
            capture_logs() as logs,
            patch("app.database.AsyncSessionLocal", broken_session),
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            from app.api._mission_cqrs.compat import dual_write_sync_blueprint

            await dual_write_sync_blueprint("mission-test-id-b4-bp", 1, title="x")

        # Check for retry warnings
        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        assert (
            len(retry_logs) >= 1
        ), f"Expected at least 1 'dual_write_retry' event during retry attempts. Got: {[e.get('event') for e in logs]}"

        # Check for final failure at ERROR level
        failure_logs = [e for e in logs if e.get("event") == "dual_write_failed"]
        assert failure_logs, "Expected a 'dual_write_failed' event on final failure"
        assert (
            failure_logs[0]["log_level"] == "error"
        ), f"B4 FIX: dual_write_failed must log at ERROR level (got {failure_logs[0]['log_level']})."
        assert failure_logs[0]["operation"] == "sync_blueprint"

    async def test_dual_write_succeeds_on_retry(self):
        """When the first attempt fails but the second succeeds, no ERROR should be emitted."""
        call_count = 0

        class _FlakyCtx:
            async def __aenter__(self):
                nonlocal call_count
                call_count += 1
                db = AsyncMock()
                if call_count == 1:
                    db.execute.side_effect = RuntimeError("transient failure")
                else:
                    # Second call: succeed — MagicMock for scalar_one_or_none (sync method)
                    mock_result = MagicMock()
                    mock_result.scalar_one_or_none.return_value = None
                    db.execute = AsyncMock(return_value=mock_result)
                return db

            async def __aexit__(self, *args):
                return False

        def _flaky_session_factory():
            return _FlakyCtx()

        with (
            capture_logs() as logs,
            patch("app.database.AsyncSessionLocal", _flaky_session_factory),
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            from app.api._mission_cqrs.compat import dual_write_sync_run_status

            await dual_write_sync_run_status("mission-test-id-b4-retry", 1, "completed")

        # First attempt failed, but second succeeded — there should be exactly 1 retry WARNING
        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        assert len(retry_logs) == 1, (
            f"Expected exactly 1 retry event (first attempt failed, second succeeded), "
            f"got {len(retry_logs)}: {[e.get('event') for e in logs]}"
        )

        # No final failure should be logged
        failure_logs = [e for e in logs if e.get("event") == "dual_write_failed"]
        assert not failure_logs, "Should NOT emit dual_write_failed when retry succeeds"
