"""Shared mission CQRS base classes and helpers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast
from uuid import UUID

import structlog

from app.models.mission_models import Mission, MissionTask, MissionTaskStatus
from app.schemas.mission import MissionExecutionStatus
from app.services.mission_errors import MissionError

from .errors import map_infra_error

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_log = structlog.get_logger(__name__)


def _schedule_fire_and_forget(coro) -> None:
    """Schedule a coroutine as a fire-and-forget task with error logging.

    Replaces the deprecated asyncio.ensure_future.  If the task fails the
    exception is logged rather than silently swallowed.
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


def _make_execution_status(mission: Mission, tasks: list[MissionTask]) -> MissionExecutionStatus:
    return MissionExecutionStatus(
        mission_id=cast(UUID, mission.id),
        status=mission.status,
        total_tasks=len(tasks),
        completed_tasks=sum(1 for t in tasks if t.status == MissionTaskStatus.COMPLETED),
        failed_tasks=sum(1 for t in tasks if t.status == MissionTaskStatus.FAILED),
        total_tokens_used=mission.tokens_used or 0,
        started_at=mission.started_at,
    )


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
        except MissionError:
            raise
        except Exception as exc:
            raise map_infra_error(exc) from exc


class QueryHandlerBase:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
