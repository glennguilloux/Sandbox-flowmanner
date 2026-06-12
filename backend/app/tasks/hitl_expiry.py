"""Celery task for HITL timeout + auto-action expiry (Q1-B chunk 2).

Runs every 5 minutes via Celery beat.  Finds stale HITL inbox items
(past expires_at, still PENDING) and applies the workspace-configured
auto-action: reject (fail mission), approve (continue), or stay (alert).

Uses HITLService.expire_and_act() for the actual logic.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import structlog

from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task context.

    Uses the `langgraph_tasks.py` pattern: create a new event loop, register
    it globally with `asyncio.set_event_loop()` so asyncpg / SQLAlchemy
    futures bind to it, then run until complete.  The previous
    `asyncio.run()` approach fails on the first attempt in a Celery
    prefork worker because asyncpg creates connections tied to whatever
    loop is current at the time of the call; with `asyncio.run()` the
    loop is created, the coroutine runs, the loop closes, and any
    pending asyncpg cleanup crashes with "got Future ... attached to a
    different loop" (visible in worker logs as a 30s retry that
    succeeds).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _expire_async() -> dict:
    """Expire stale HITL items and apply auto-actions."""
    from app.database import AsyncSessionLocal, engine
    from app.services.hitl_service import HITLService

    # Dispose the engine's connection pool so we don't reuse asyncpg
    # connections that were bound to a previous event loop (Celery
    # prefork workers create a new loop per task, but the global
    # engine + its connection pool persist across tasks — see worker
    # logs for "got Future ... attached to a different loop" before
    # this fix).
    await engine.dispose()

    async with AsyncSessionLocal() as db:
        service = HITLService(db)
        results = await service.expire_and_act()
        await db.commit()

    return {
        "processed": len(results),
        "actions": results,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@celery_app.task(
    name="hitl.expire_items",
    bind=True,
    max_retries=2,
    acks_late=False,
    time_limit=120,
    soft_time_limit=100,
)
def expire_hitl_items(self):
    """Expire stale HITL inbox items and apply per-workspace auto-action.

    Scheduled via Celery beat every 5 minutes (see celery_app.py).
    Idempotent: uses SELECT FOR UPDATE SKIP LOCKED to prevent races.
    """
    try:
        result = _run_async(_expire_async())
        if result["processed"] > 0:
            logger.info(
                "hitl_expiry_task_complete",
                processed=result["processed"],
                actions=[r["auto_action"] for r in result["actions"]],
            )
        return result
    except Exception as exc:
        logger.error("hitl_expiry_task_failed", error=str(exc))
        countdown = 30 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
