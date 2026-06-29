"""Celery tasks for integration health checks.

The beat schedule in ``celery_app.py`` dispatches
``integration_health_check_all`` every 15 minutes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.tasks.celery_app import celery_app

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.integration_health_service import IntegrationHealthService

logger = logging.getLogger(__name__)

# Mutable container so the nested async closure can track cleanup state.
_last_cleanup_date: dict[str, object] = {"date": None}


# ── Engine lifecycle for prefork workers ──────────────────────────────
# Celery prefork workers fork from the parent process, inheriting the
# async engine's connection pool.  Those connections are bound to the
# parent's event loop and crash with "Task attached to a different loop"
# when used on a fresh event loop in the child.  We work around this by
# disposing the engine at the start of every task run, purging stale
# connections so they are re-created on the current event loop.
from app.database import engine as _async_engine


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
        # Dispose stale connections inherited from the fork parent's event loop
        await _async_engine.dispose()

        health_checks = manifest_service.get_all_health_checks()
        if not health_checks:
            logger.warning("No integration health checks found in manifests")
            return {}

        async with AsyncSessionLocal() as db:
            service = IntegrationHealthService(db)
            results = await service.check_all(health_checks)

            # ── Incident detection (Phase 5) ─────────────────────────────
            await _detect_and_manage_incidents(db, service, results)

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


async def _detect_and_manage_incidents(
    db: AsyncSession,
    service: IntegrationHealthService,
    results: dict,
) -> None:
    """Detect health transitions and create/resolve incidents.

    For each integration that is ``degraded`` or ``down``, check if an open
    incident already exists.  If not, create one.  For integrations that
    returned to ``healthy``, resolve any open incidents.
    """
    from datetime import UTC, datetime
    from uuid import uuid4

    from sqlalchemy import select

    from app.models.integration_models import IntegrationIncident

    for slug, result in results.items():
        # ── Non-healthy: create incident if none open ────────────────
        if result.status in ("degraded", "down"):
            existing = await db.execute(
                select(IntegrationIncident).where(
                    IntegrationIncident.integration_slug == slug,
                    IntegrationIncident.status != "resolved",
                )
            )
            if existing.scalar_one_or_none() is None:
                severity = "major" if result.status == "down" else "minor"
                incident = IntegrationIncident(
                    id=str(uuid4()),
                    integration_slug=slug,
                    severity=severity,
                    title=f"{slug} is {result.status}",
                    description=result.error_message,
                    status="open",
                )
                db.add(incident)
                logger.warning(
                    "Incident created for %s: %s",
                    slug,
                    result.status,
                )

        # ── Healthy: resolve open incidents ──────────────────────────
        elif result.status == "healthy":
            open_incidents = await db.execute(
                select(IntegrationIncident).where(
                    IntegrationIncident.integration_slug == slug,
                    IntegrationIncident.status != "resolved",
                )
            )
            for incident in open_incidents.scalars().all():
                incident.status = "resolved"
                incident.resolved_at = datetime.now(UTC)
                logger.info(
                    "Incident resolved for %s: %s",
                    slug,
                    incident.id,
                )
