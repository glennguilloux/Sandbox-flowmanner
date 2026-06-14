"""Shared program CQRS base classes and helpers.

Mirror of ``_mission_cqrs/base.py`` minus the mission-specific
``_make_execution_status`` helper.  The base classes themselves
(``CommandHandlerBase`` / ``QueryHandlerBase``) are intentionally
generic — no mission imports.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog

from .errors import map_program_infra_error

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.mission_program_service import ProgramError

_log = structlog.get_logger(__name__)


def _schedule_fire_and_forget(coro) -> None:
    """Schedule a coroutine as a fire-and-forget task with error logging.

    Replaces the deprecated ``asyncio.ensure_future``.  If the task fails
    the exception is logged rather than silently swallowed.
    """
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
    """Base class for program command handlers.

    Subclasses get ``self.session`` and the ``tx()`` / ``wrap_command()``
    helpers that bound the unit-of-work to a single commit/rollback.
    """

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
        except ProgramError:
            raise
        except Exception as exc:
            raise map_program_infra_error(exc) from exc


class QueryHandlerBase:
    """Base class for program query handlers (read-only)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
