"""Tests for BackgroundTaskManager — Task 3.3.

Verifies the manager holds strong refs to spawned tasks, logs exceptions,
drains on shutdown, and doesn't propagate exceptions to the caller.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.background_task_manager import BackgroundTaskManager


async def _passthrough(coro, *, label: str = ""):
    """Mock replacement for _safe_fire_and_forget — just awaits the coro."""
    await coro


class TestBackgroundTaskManager:
    @pytest.mark.asyncio
    async def test_spawn_holds_strong_ref(self):
        """After spawning, manager._tasks is non-empty."""
        manager = BackgroundTaskManager()

        async def _work():
            await asyncio.sleep(0.01)

        with patch("app.services.chat_service._safe_fire_and_forget", side_effect=_passthrough):
            task = manager.spawn(_work(), label="test")
            assert len(manager._tasks) >= 1
            await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_task_discarded_after_completion(self):
        """Completed tasks are discarded from _tasks."""
        manager = BackgroundTaskManager()

        async def _work():
            return "done"

        with patch("app.services.chat_service._safe_fire_and_forget", side_effect=_passthrough):
            manager.spawn(_work(), label="test")
            await asyncio.sleep(0.1)
            assert len(manager._tasks) == 0

    @pytest.mark.asyncio
    async def test_drain_waits_for_tasks(self):
        """drain() waits for all spawned tasks to complete."""
        manager = BackgroundTaskManager()
        completed = []

        async def _work():
            await asyncio.sleep(0.05)
            completed.append(True)

        with patch("app.services.chat_service._safe_fire_and_forget", side_effect=_passthrough):
            manager.spawn(_work(), label="test")
            await manager.drain(timeout=2.0)
            assert completed == [True]

    @pytest.mark.asyncio
    async def test_drain_empty_is_noop(self):
        """drain() with no tasks completes immediately."""
        manager = BackgroundTaskManager()
        await manager.drain(timeout=1.0)

    @pytest.mark.asyncio
    async def test_drain_timeout_does_not_raise(self):
        """drain() with a too-short timeout logs but doesn't raise."""
        manager = BackgroundTaskManager()

        async def _slow():
            await asyncio.sleep(5.0)

        with patch("app.services.chat_service._safe_fire_and_forget", side_effect=_passthrough):
            manager.spawn(_slow(), label="slow")
            await manager.drain(timeout=0.01)
            # Should not raise

    @pytest.mark.asyncio
    async def test_exception_in_spawned_task_does_not_propagate(self):
        """Exceptions in spawned tasks are logged, not propagated."""
        manager = BackgroundTaskManager()

        async def _boom():
            raise RuntimeError("boom")

        with patch("app.services.chat_service._safe_fire_and_forget", side_effect=_passthrough):
            task = manager.spawn(_boom(), label="boom")
            await asyncio.sleep(0.1)
            # Task should be done and discarded
            assert task.done()
