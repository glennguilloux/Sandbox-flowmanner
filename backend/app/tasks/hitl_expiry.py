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


async def _expire_async() -> dict:
    """Expire stale HITL items and apply auto-actions."""
    from app.database import AsyncSessionLocal
    from app.services.hitl_service import HITLService

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
