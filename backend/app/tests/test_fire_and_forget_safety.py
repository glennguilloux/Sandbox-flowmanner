"""Tests for _safe_fire_and_forget helper in chat_service.py."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest


async def _failing_coro():
    """A coroutine that always raises."""
    raise ValueError("intentional test error")


async def _succeeding_coro():
    """A coroutine that succeeds."""
    return 42


@pytest.mark.asyncio
async def test_safe_fire_and_forget_logs_exceptions(caplog):
    """Verify that exceptions in the coroutine are logged, not propagated."""
    from app.services.chat_service import _safe_fire_and_forget

    with caplog.at_level(logging.ERROR, logger="app.services.chat_service"):
        # Should NOT raise despite the failing coroutine
        await _safe_fire_and_forget(_failing_coro(), label="test_failure")

    assert "fire-and-forget task failed" in caplog.text
    assert "test_failure" in caplog.text
    assert "intentional test error" in caplog.text


@pytest.mark.asyncio
async def test_safe_fire_and_forget_passes_through_success():
    """Verify that successful coroutines complete normally."""
    from app.services.chat_service import _safe_fire_and_forget

    result = await _safe_fire_and_forget(_succeeding_coro(), label="test_success")
    # The helper returns None (no return statement), but the coroutine ran
    assert result is None


@pytest.mark.asyncio
async def test_safe_fire_and_forget_does_not_propagate():
    """Verify the exception does NOT propagate to the caller."""
    from app.services.chat_service import _safe_fire_and_forget

    # If this raises, the test fails — the whole point is no propagation
    try:
        await _safe_fire_and_forget(_failing_coro(), label="no_propagate")
    except Exception:
        pytest.fail("_safe_fire_and_forget should not propagate exceptions")


@pytest.mark.asyncio
async def test_safe_fire_and_forget_as_task():
    """Verify it works correctly when wrapped in asyncio.create_task."""
    from app.services.chat_service import _safe_fire_and_forget

    task = asyncio.create_task(_safe_fire_and_forget(_failing_coro(), label="as_task"))
    # Wait for the task to complete
    await asyncio.sleep(0.1)

    # Task should be done (not hung) and should NOT have raised
    assert task.done()
    assert task.exception() is None
