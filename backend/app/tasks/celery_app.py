"""
Celery application configuration.

Q1-A Chunk 3: On worker_ready, starts a LeaseReclaimer background thread
that scans for expired leases and reclaims them.  On worker_shutdown,
signals the reclaimer to stop.  Gated by the FLOWMANNER_LEASE_RECLAIMER_ENABLED
feature flag (default true).
"""

import logging
import os

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

logger = logging.getLogger(__name__)

# Create Celery app with RabbitMQ broker
celery_app = Celery(
    "workflows",
    broker=os.getenv("CELERY_BROKER_URL", "amqp://rabbitmq:rabbitmq_password@rabbitmq:5672//"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379"),
    include=[],
)

# Optional configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


# ── Q1-A Chunk 3: Lease reclaimer lifecycle ────────────────────────


@worker_ready.connect
def _start_lease_reclaimer(**kwargs):
    """Start the stale-lease reclaimer when the Celery worker is ready.

    Each worker process gets its own reclaimer instance running in a
    daemon thread with a dedicated asyncio event loop.
    """
    try:
        from app.config import settings

        if not settings.FLOWMANNER_LEASE_RECLAIMER_ENABLED:
            logger.info("LeaseReclaimer disabled by FLOWMANNER_LEASE_RECLAIMER_ENABLED=false")
            return

        from app.services.substrate.lease_reclaimer import start_reclaimer

        start_reclaimer()
    except Exception as exc:
        logger.warning("Failed to start LeaseReclaimer: %s", exc)


@worker_shutdown.connect
def _stop_lease_reclaimer(**kwargs):
    """Stop the stale-lease reclaimer when the Celery worker shuts down."""
    try:
        from app.services.substrate.lease_reclaimer import stop_reclaimer

        stop_reclaimer()
    except Exception as exc:
        logger.debug("LeaseReclaimer stop error (may not have been running): %s", exc)
