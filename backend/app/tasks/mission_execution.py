"""Celery task for durable async mission execution.

Replaces the fire-and-forget asyncio.create_task pattern with a queue-backed
Celery task that captures failures, supports retries/backoff, and ensures
execution status transitions are safe and durable.

Idempotent trigger: the task checks mission status before executing to
prevent double-execution from retried dispatches.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from celery import Task
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.mission_models import (
    Mission,
    MissionLog,
    MissionStatus,
    MissionTaskStatus,
)
from app.services.mission_executor import MissionExecutor
from app.services.mission_service import get_mission_tasks

logger = structlog.get_logger(__name__)


class ExecuteMissionTask(Task):
    """Celery task for executing a mission asynchronously.

    Features:
    - Idempotency: checks status before executing (avoids double-run)
    - Retry: retries on transient failures with exponential backoff
    - Status transitions: safely transitions QUEUED → RUNNING → COMPLETED/FAILED
    - Logging: writes structured transition logs
    """

    name = "mission.execute_async"
    max_retries = 3
    default_retry_delay = 30  # seconds, increases exponentially
    acks_late = True
    reject_on_worker_lost = True

    def run(self, mission_id: str, user_id: int):
        """Synchronous entry point — runs the async execution via asyncio.

        If no event loop is running, uses asyncio.run().
        If a loop is already running (e.g., under uvicorn), uses a new loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — safe to use asyncio.run()
            return asyncio.run(self._execute_async(mission_id, user_id))
        else:
            # Loop exists — use a separate one for Celery isolation
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(
                    self._execute_async(mission_id, user_id)
                )
            finally:
                new_loop.close()

    async def _execute_async(self, mission_id: str, user_id: int):
        """Async execution with proper session management."""
        async with AsyncSessionLocal() as session:
            try:
                # Idempotency check: only execute if QUEUED
                result = await session.execute(
                    select(Mission).where(Mission.id == mission_id).with_for_update()
                )
                mission = result.scalar_one_or_none()
                if mission is None:
                    logger.error(
                        "mission_execute_async_not_found", mission_id=mission_id
                    )
                    return

                if mission.status != MissionStatus.QUEUED:
                    logger.info(
                        "mission_execute_async_skipped",
                        mission_id=mission_id,
                        status=(
                            mission.status.value
                            if hasattr(mission.status, "value")
                            else mission.status
                        ),
                    )
                    return

                # Transition to RUNNING
                prev = mission.status
                mission.status = MissionStatus.RUNNING
                mission.started_at = datetime.now(UTC)

                log = MissionLog(
                    mission_id=mission_id,
                    level="info",
                    message=f"Async execution started (was: {prev})",
                    data={
                        "actor": "celery",
                        "prev_state": prev.value if hasattr(prev, "value") else prev,
                        "next_state": MissionStatus.RUNNING.value,
                        "user_id": user_id,
                    },
                )
                session.add(log)
                await session.commit()

                # Execute
                executor = MissionExecutor()
                exec_result = await executor.execute_mission(uuid.UUID(mission_id))

                # Finalize
                await session.refresh(mission)
                tasks = await get_mission_tasks(session, mission_id)
                completed = sum(
                    1 for t in tasks if t.status == MissionTaskStatus.COMPLETED
                )
                failed = sum(1 for t in tasks if t.status == MissionTaskStatus.FAILED)

                final_log = MissionLog(
                    mission_id=mission_id,
                    level="info" if exec_result.get("success") else "error",
                    message=f"Async execution finished: success={exec_result.get('success')}",
                    data={
                        "actor": "celery",
                        "success": exec_result.get("success"),
                        "completed_tasks": completed,
                        "failed_tasks": failed,
                        "error": exec_result.get("error"),
                        "user_id": user_id,
                    },
                )
                session.add(final_log)
                await session.commit()

                logger.info(
                    "mission_execute_async_complete",
                    mission_id=mission_id,
                    success=exec_result.get("success"),
                )

            except Exception as exc:
                await session.rollback()

                # Mark as FAILED
                try:
                    async with AsyncSessionLocal() as fail_session:
                        fail_result = await fail_session.execute(
                            select(Mission).where(Mission.id == mission_id)
                        )
                        mission = fail_result.scalar_one_or_none()
                        if mission:
                            mission.status = MissionStatus.FAILED
                            mission.error_message = f"Async execution failed: {exc}"
                            mission.completed_at = datetime.now(UTC)
                            fail_log = MissionLog(
                                mission_id=mission_id,
                                level="error",
                                message=f"Async execution failed: {exc}",
                                data={
                                    "actor": "celery",
                                    "error": str(exc),
                                    "user_id": user_id,
                                },
                            )
                            fail_session.add(fail_log)
                            await fail_session.commit()
                except Exception as inner:
                    logger.error(
                        "mission_execute_async_failure_log_failed", exc_info=True
                    )

                # Retry with backoff
                countdown = self.default_retry_delay * (2**self.request.retries)
                raise self.retry(exc=exc, countdown=countdown)


# ── Dispatch helper ───────────────────────────────────────────────────────────


def dispatch_mission_execution(mission_id: str, user_id: int) -> None:
    """Queue a mission for async execution via Celery.

    Safe to call from within a sync or async context.
    Replace all asyncio.create_task(_run_execution) patterns with this.
    """
    from celery import current_app

    current_app.send_task(
        "mission.execute_async",
        args=[mission_id, user_id],
        queue="celery",
    )
    logger.info("mission_execute_dispatched", mission_id=mission_id)
