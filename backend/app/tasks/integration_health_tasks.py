"""Celery tasks for integration health checks.

The beat schedule in ``celery_app.py`` dispatches
``integration_health_check_all`` every 15 minutes.
"""

from __future__ import annotations

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Mutable container so the nested async closure can track cleanup state.
_last_cleanup_date: dict[str, object] = {"date": None}


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="integration.health_check_all", bind=True)
def run_integration_health_checks(self) -> dict[str, str]:
    """Run health checks for all integrations and store results.

    Dispatched by Celery beat every 15 minutes.  Reads health-check
    config from integration manifests (or falls back to the manifest
    service singleton).

    Returns:
        Dict mapping slug → status string for logging.
    """
    from app.database import AsyncSessionLocal
    from app.services.integration_health_service import IntegrationHealthService
    from app.services.integration_manifest_service import manifest_service

    async def _run() -> dict[str, str]:
        health_checks = manifest_service.get_all_health_checks()
        if not health_checks:
            logger.warning("No integration health checks found in manifests")
            return {}

        async with AsyncSessionLocal() as db:
            service = IntegrationHealthService(db)
            results = await service.check_all(health_checks)
            # Retention: clean up records older than 90 days (once per calendar day)
            from datetime import UTC, date, datetime

            now = datetime.now(UTC)
            today = now.date()
            if _last_cleanup_date["date"] != today:
                deleted = await service.cleanup_old_records(days=90)
                if deleted:
                    logger.info("Cleaned up %d old health records", deleted)
                _last_cleanup_date["date"] = today
            await db.commit()

        summary = {slug: r.status for slug, r in results.items()}
        healthy = sum(1 for s in summary.values() if s == "healthy")
        total = len(summary)
        logger.info(
            "Integration health checks complete: %d/%d healthy",
            healthy,
            total,
        )
        return summary

    return _run_async(_run())
