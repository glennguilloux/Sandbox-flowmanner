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

    Creates a fresh event loop per invocation so asyncpg connections are
    always bound to the current loop.  The loop is closed in ``finally``
    to avoid leaking file-descriptors across task retries.  Stale
    connections inherited from the fork parent are purged by
    ``await engine.dispose()`` inside the async coroutine.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _expire_async() -> dict:
    """Expire stale HITL items and apply auto-actions.

    Mirrors the fix applied to hitl_resume.py on 2026-06-12: disposes the
    global async engine at task start so any asyncpg connections inherited
    from the parent celery-worker process (fork-time artifact) are dropped
    before we open a fresh session on the current event loop.  Without
    this, asyncpg raises "got Future ... attached to a different loop"
    in SQLAlchemy's connection-pool cleanup after the task completes.
    """
    from app.database import AsyncSessionLocal, engine
    from app.services.hitl_service import HITLService

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
        countdown = 30 * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
