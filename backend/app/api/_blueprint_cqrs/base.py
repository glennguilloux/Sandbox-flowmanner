"""Blueprint CQRS base classes — shared transaction management and helpers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_log = structlog.get_logger(__name__)


def _schedule_fire_and_forget(coro) -> None:
    """Schedule a coroutine as fire-and-forget with error logging."""
    task = asyncio.create_task(coro)

    def _on_done(t: asyncio.Task) -> None:
        try:
            exc = t.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            _log.warning("fire_and_forget_task_failed", exc_info=exc)

    task.add_done_callback(_on_done)


class CommandHandlerBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @asynccontextmanager
    async def tx(self):
        try:
            yield
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def wrap_command(self, fn):
        try:
            async with self.tx():
                return await fn()
        except Exception:
            raise


class QueryHandlerBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
