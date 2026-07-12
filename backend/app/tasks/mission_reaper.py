"""Celery beat task for the MissionReaper (FM-3).

Reaps RUNNING missions stranded by a dead worker. Reaped rows transition
to ``FAILED(stale_pause)`` — NOT ``ABORTED`` (GC: abort closes the
retry path; FAILED keeps recoverability, P3/P8).

Registered with the worker via ``app.tasks.celery_app._register_custom_tasks``
(see app/tasks/celery_app.py task_modules list).
"""

import asyncio

from app.services.mission_reaper import reap_stale_missions
from app.tasks.celery_app import celery_app


@celery_app.task(name="mission.reap_stale", bind=True, max_retries=1)
def reap_stale_missions_task(self):
    """Beat-triggered sweep of dead-worker RUNNING missions."""
    try:
        reaped = asyncio.run(reap_stale_missions())
        return {"reaped": reaped}
    except Exception as exc:
        self.logger.error("mission_reap_stale_failed", exc_info=exc)
        return {"error": str(exc)}
