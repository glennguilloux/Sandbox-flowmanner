"""BackgroundTaskManager — ref-held ephemeral task runner (Task 3.3).

Replaces raw ``asyncio.create_task()`` calls that don't hold strong
refs (GC risk).  The manager holds a set of ``asyncio.Task`` objects,
logs exceptions via the existing ``_safe_fire_and_forget`` wrapper,
and discards completed tasks automatically.

Usage::

    from app.services.background_task_manager import background_task_manager

    background_task_manager.spawn(some_coro(), label="my_task")

On application shutdown, call ``await background_task_manager.drain()``
to wait for all in-flight tasks to complete.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Holds strong refs to spawned tasks, logs exceptions, drains on shutdown."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]

    def spawn(self, coro, *, label: str) -> asyncio.Task:  # type: ignore[type-arg]
        """Spawn a fire-and-forget coroutine with a strong ref held by the manager.

        Exceptions are logged via ``_safe_fire_and_forget`` semantics
        (logged, never propagated to the caller).
        """
        from app.services.chat_service import _safe_fire_and_forget

        task = asyncio.create_task(_safe_fire_and_forget(coro, label=label))
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task) -> None:  # type: ignore[type-arg]
        """Discard completed tasks and log any unhandled exceptions."""
        self._tasks.discard(task)
        if task.done() and not task.cancelled():
            exc = task.exception()
            if exc is not None:
                logger.exception(
                    "BackgroundTaskManager: task failed with exception",
                    exc_info=exc,
                )

    async def drain(self, timeout: float = 5.0) -> None:
        """Wait for all in-flight tasks to complete, with a timeout.

        Called during application shutdown to allow background work to
        finish gracefully.
        """
        if not self._tasks:
            return
        logger.info("BackgroundTaskManager: draining %d tasks", len(self._tasks))
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning(
                "BackgroundTaskManager: drain timed out after %.1fs, %d tasks still pending",
                timeout,
                len(self._tasks),
            )


# Module-level singleton
background_task_manager = BackgroundTaskManager()
