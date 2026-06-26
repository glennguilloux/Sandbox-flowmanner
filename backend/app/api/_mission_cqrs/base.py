"""Shared mission CQRS base classes and helpers."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import structlog

from app.core.metrics import dual_write_failures_total
from app.models.mission_models import Mission, MissionTask, MissionTaskStatus
from app.schemas.mission import MissionExecutionStatus
from app.services.mission_errors import MissionError

from .errors import map_infra_error

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

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


async def _run_with_retry(
    fn: Callable[[], Coroutine[Any, Any, None]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    operation: str,
    **log_context: Any,
) -> None:
    """Execute an async callable with exponential-backoff retry and structured logging.

    Designed for fire-and-forget dual-write operations where transient DB
    errors (connection pool exhaustion, serialization failures) should be
    retried rather than silently lost.

    On final failure the exception is logged at ERROR with full context
    and traceback — never re-raised.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            await fn()
            return
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = min(base_delay * (2 ** (attempt - 1)), 30.0)
                _log.warning(
                    "dual_write_retry",
                    operation=operation,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    delay_seconds=delay,
                    error=str(exc)[:200],
                    **log_context,
                )
                await asyncio.sleep(delay)
    dual_write_failures_total.labels(site=operation).inc()
    _log.error(
        "dual_write_failed",
        operation=operation,
        attempts=max_attempts,
        exc_info=last_exc,
        **log_context,
    )


def _make_execution_status(mission: Mission, tasks: list[MissionTask]) -> MissionExecutionStatus:
    return MissionExecutionStatus(
        mission_id=mission.id,
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
