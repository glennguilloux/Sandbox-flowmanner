"""Celery task for durable HITL resume (Q1-B chunk 1).

When a human resolves an HITL inbox item (approve/reject/clarify),
this task re-queues the mission execution via the UnifiedExecutor.

The executor detects the existing run (crash recovery path), rebuilds
state, and re-enters the HITL node — which now checks the inbox item
status and returns the resolution result.

This is the durable resume path: survives server restarts because
the Celery broker (RabbitMQ) holds the task until a worker picks it up.
"""

from __future__ import annotations

import asyncio
import logging

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()


async def _resume_async(
    mission_id: str,
    run_id: str,
    inbox_item_id: str,
    resolution: str,
) -> dict:
    """Resume mission execution after HITL resolution.

    Exceptions propagate to the Celery task-level retry handler.

    Q1-B chunk 1 follow-up (2026-06-12): disposes the global async engine
    at task start to avoid the "got Future ... attached to a different
    loop" RuntimeError that fired on the first attempt of every Celery
    invocation that touches the engine.  See commit 7b4646e for the same
    fix applied to hitl_expiry.py and the full root-cause writeup.
    """
    from app.database import AsyncSessionLocal, engine
    from app.models.mission_models import Mission, MissionStatus
    from sqlalchemy import select

    # Drop any cached asyncpg connections left over from a previous task's
    # event loop.  Each Celery task gets a fresh loop, but the pool is global
    # and reuses connections; without this, asyncpg raises
    # "got Future ... attached to a different loop" on the first await.
    await engine.dispose()

    async with AsyncSessionLocal() as db:
        # Load the mission
        result = await db.execute(select(Mission).where(Mission.id == mission_id))
        mission = result.scalar_one_or_none()
        if mission is None:
            logger.error("hitl_resume_not_found", mission_id=mission_id)
            return {"success": False, "error": "Mission not found"}

        # Only resume if the mission is paused
        current_status = mission.status.value if hasattr(mission.status, "value") else mission.status
        if current_status not in ("paused", "running"):
            logger.info(
                "hitl_resume_skipped",
                mission_id=mission_id,
                status=current_status,
            )
            return {"success": False, "error": f"Mission is {current_status}, not paused"}

        # Transition to RUNNING
        mission.status = MissionStatus.RUNNING
        await db.commit()

        logger.info(
            "hitl_resume_started",
            mission_id=mission_id,
            run_id=run_id,
            inbox_item_id=inbox_item_id,
            resolution=resolution,
        )

        # Convert mission to workflow and execute via UnifiedExecutor
        from app.models.substrate_models import SubstrateEventType
        from app.services.substrate.adapters import mission_to_workflow
        from app.services.substrate.event_log import get_event_log
        from app.services.substrate.executor import get_unified_executor

        workflow = mission_to_workflow(mission)
        executor = get_unified_executor()

        exec_result = await executor.execute(
            db=db,
            workflow=workflow,
            run_id=run_id,
        )

        # Q1-B: Emit HITL_RESUMED event on successful resume
        if exec_result.success or exec_result.status != "paused":
            try:
                event_log = get_event_log()
                await event_log.append(
                    db,
                    run_id,
                    [{
                        "type": SubstrateEventType.HITL_RESUMED,
                        "payload": {
                            "inbox_item_id": inbox_item_id,
                            "resolution": resolution,
                            "resume_status": exec_result.status,
                        },
                        "actor": "hitl_resume_task",
                        "mission_id": mission_id,
                    }],
                )
            except Exception as ev_err:
                logger.debug("Failed to emit HITL_RESUMED event: %s", ev_err)

        logger.info(
            "hitl_resume_complete",
            mission_id=mission_id,
            run_id=run_id,
            status=exec_result.status,
            success=exec_result.success,
        )

    return {
        "success": exec_result.success,
        "status": exec_result.status,
        "mission_id": mission_id,
        "run_id": run_id,
    }


@celery_app.task(
    name="substrate.resume_hitl",
    bind=True,
    max_retries=3,
    acks_late=True,
    reject_on_worker_lost=True,
    time_limit=600,
    soft_time_limit=540,
)
def resume_hitl_task(self, mission_id: str, run_id: str, inbox_item_id: str, resolution: str):
    """Resume a mission after HITL resolution.

    Uses crash recovery: the UnifiedExecutor detects the existing run
    and rebuilds state from the event log, then re-enters the HITL node.
    """
    try:
        return _run_async(
            _resume_async(mission_id, run_id, inbox_item_id, resolution)
        )
    except Exception as exc:
        countdown = 10 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)


def dispatch_hitl_resume(
    mission_id: str,
    run_id: str,
    inbox_item_id: str,
    resolution: str,
) -> None:
    """Dispatch a HITL resume task via Celery.

    Called from the HITL API after an inbox item is resolved.
    Safe to call from sync or async context.
    """
    resume_hitl_task.delay(mission_id, run_id, inbox_item_id, resolution)
    logger.info(
        "hitl_resume_dispatched",
        mission_id=mission_id,
        run_id=run_id,
        inbox_item_id=inbox_item_id,
        resolution=resolution,
    )
