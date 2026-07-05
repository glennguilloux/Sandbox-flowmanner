"""Unit tests for ``_run_with_retry`` (backend/app/api/_mission_cqrs/base.py).

Covers:
- First attempt succeeds (no retry)
- All attempts fail → ERROR log + Prometheus counter
- Fail then succeed (retry recovery)
- CancelledError propagates (not caught by retry)
- Custom max_attempts / base_delay
- Log context propagation (mission_id, user_id, etc.)
- Prometheus counter increment on final failure
- Exponential backoff delay calculation
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from structlog.testing import capture_logs

from app.api._mission_cqrs.base import _run_with_retry


@pytest.mark.asyncio
class TestRunWithRetry:
    """Direct unit tests for _run_with_retry."""

    async def test_first_attempt_succeeds_no_retry(self):
        """When fn succeeds on first call, no retry or logging occurs."""
        call_count = 0

        async def success_fn():
            nonlocal call_count
            call_count += 1

        with (
            capture_logs() as logs,
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _run_with_retry(success_fn, operation="test_op")

        assert call_count == 1
        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        failure_logs = [e for e in logs if e.get("event") == "dual_write_failed"]
        assert not retry_logs, "No retry logs should be emitted on first-try success"
        assert not failure_logs, "No failure logs should be emitted on first-try success"

    async def test_all_attempts_fail_logs_error_and_increments_counter(self):
        """When all 3 attempts fail, ERROR log is emitted and Prometheus counter incremented."""
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError(f"failure #{call_count}")

        mock_counter = MagicMock()

        with (
            capture_logs() as logs,
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
            patch("app.api._mission_cqrs.base.dual_write_failures_total", mock_counter),
        ):
            await _run_with_retry(always_fail, operation="sync_run_status", mission_id="m-1")

        assert call_count == 3, f"Expected 3 attempts, got {call_count}"

        # 2 retry warnings (attempts 1 and 2)
        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        assert len(retry_logs) == 2, f"Expected 2 retry logs, got {len(retry_logs)}"
        assert retry_logs[0]["attempt"] == 1
        assert retry_logs[1]["attempt"] == 2
        assert all(e["log_level"] == "warning" for e in retry_logs)

        # 1 final failure at ERROR
        failure_logs = [e for e in logs if e.get("event") == "dual_write_failed"]
        assert len(failure_logs) == 1
        assert failure_logs[0]["log_level"] == "error"
        assert failure_logs[0]["attempts"] == 3
        assert failure_logs[0]["operation"] == "sync_run_status"
        assert failure_logs[0]["mission_id"] == "m-1"

        # Prometheus counter incremented exactly once with correct site label
        mock_counter.labels.assert_called_once_with(site="sync_run_status")
        mock_counter.labels.return_value.inc.assert_called_once()

    async def test_fail_then_succeed_retries_once(self):
        """When first attempt fails but second succeeds, exactly 1 retry log is emitted."""
        call_count = 0

        async def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient failure")

        with (
            capture_logs() as logs,
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _run_with_retry(flaky_fn, operation="create_blueprint")

        assert call_count == 2
        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        assert len(retry_logs) == 1
        assert retry_logs[0]["attempt"] == 1
        assert retry_logs[0]["operation"] == "create_blueprint"

        failure_logs = [e for e in logs if e.get("event") == "dual_write_failed"]
        assert not failure_logs, "No failure log when retry succeeds"

    async def test_cancelled_error_propagates(self):
        """CancelledError should NOT be caught by the retry loop — it propagates."""
        call_count = 0

        async def cancelled_fn():
            nonlocal call_count
            call_count += 1
            raise asyncio.CancelledError()

        with (
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(asyncio.CancelledError),
        ):
            await _run_with_retry(cancelled_fn, operation="test_cancel")

        assert call_count == 1, "CancelledError should propagate after first attempt, not retry"

    async def test_custom_max_attempts(self):
        """Custom max_attempts controls the number of retry cycles."""
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with (
            capture_logs() as logs,
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _run_with_retry(always_fail, operation="test_custom", max_attempts=5)

        assert call_count == 5
        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        assert len(retry_logs) == 4, "4 retry warnings for 5 attempts"
        failure_logs = [e for e in logs if e.get("event") == "dual_write_failed"]
        assert len(failure_logs) == 1
        assert failure_logs[0]["attempts"] == 5

    async def test_max_attempts_1_no_retry(self):
        """With max_attempts=1, the function fails immediately with no retry."""
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with (
            capture_logs() as logs,
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _run_with_retry(always_fail, operation="no_retry", max_attempts=1)

        assert call_count == 1
        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        assert not retry_logs, "No retry with max_attempts=1"
        failure_logs = [e for e in logs if e.get("event") == "dual_write_failed"]
        assert len(failure_logs) == 1
        assert failure_logs[0]["attempts"] == 1

    async def test_log_context_propagation(self):
        """Extra kwargs are passed through to both retry and failure log events."""

        async def always_fail():
            raise RuntimeError("fail")

        with (
            capture_logs() as logs,
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _run_with_retry(
                always_fail,
                operation="sync_blueprint",
                mission_id="m-abc",
                user_id=42,
                fields=["title", "description"],
            )

        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        assert retry_logs[0]["mission_id"] == "m-abc"
        assert retry_logs[0]["user_id"] == 42
        assert retry_logs[0]["fields"] == ["title", "description"]

        failure_logs = [e for e in logs if e.get("event") == "dual_write_failed"]
        assert failure_logs[0]["mission_id"] == "m-abc"
        assert failure_logs[0]["user_id"] == 42

    async def test_exponential_backoff_delays(self):
        """Verify the delay sequence: 1.0s, 2.0s (capped at 30s)."""
        sleep_calls = []

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        with (
            capture_logs(),
            patch("app.api._mission_cqrs.base.asyncio.sleep", side_effect=mock_sleep),
        ):
            await _run_with_retry(always_fail, operation="test_delay", max_attempts=4, base_delay=1.0)

        assert sleep_calls == [1.0, 2.0, 4.0], f"Expected [1.0, 2.0, 4.0], got {sleep_calls}"

    async def test_delay_capped_at_30_seconds(self):
        """With large base_delay and many attempts, delay is capped at 30s."""
        sleep_calls = []

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        async def always_fail():
            raise RuntimeError("fail")

        with (
            capture_logs(),
            patch("app.api._mission_cqrs.base.asyncio.sleep", side_effect=mock_sleep),
        ):
            await _run_with_retry(
                always_fail,
                operation="test_cap",
                max_attempts=5,
                base_delay=20.0,
            )

        # Attempts: delay(1)=20, delay(2)=40→cap30, delay(3)=80→cap30, delay(4)=160→cap30
        assert sleep_calls == [20.0, 30.0, 30.0, 30.0], f"Expected cap at 30s, got {sleep_calls}"

    async def test_never_raises(self):
        """_run_with_retry must never raise, even when fn always fails."""

        async def always_fail():
            raise RuntimeError("fail")

        # Should NOT raise
        with (
            capture_logs(),
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _run_with_retry(always_fail, operation="no_raise", max_attempts=3)

    async def test_return_value_is_none(self):
        """_run_with_retry always returns None (the fn's return is swallowed)."""

        async def success_fn():
            return 42

        with (
            capture_logs(),
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await _run_with_retry(success_fn, operation="test_return")

        assert result is None

    async def test_retry_error_truncated_to_200_chars(self):
        """The error string in retry logs is truncated to 200 characters."""
        long_error = "x" * 500

        async def fail_with_long_error():
            raise RuntimeError(long_error)

        with (
            capture_logs() as logs,
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _run_with_retry(fail_with_long_error, operation="test_truncate", max_attempts=2)

        retry_logs = [e for e in logs if e.get("event") == "dual_write_retry"]
        assert len(retry_logs[0]["error"]) <= 200
