"""
Celery application configuration.

Q1-A Chunk 3: On worker_ready, starts a LeaseReclaimer background thread
that scans for expired leases and reclaims them.  On worker_shutdown,
signals the reclaimer to stop.  Gated by the FLOWMANNER_LEASE_RECLAIMER_ENABLED
feature flag (default true).

Q1-B Chunk 1 follow-up: Registers all custom Celery tasks at module import
time.  The worker only imports this module on startup; without the explicit
imports below, every @celery_app.task / @shared_task decorator in
app.tasks.* is never executed and the worker silently drops every custom
task ("unregistered task of type X").  Includes a defensive register of
the class-based ExecuteMissionTask.

Q1-B cleanup (2026-06-12): Six task modules were previously disabled
in-place via try/except — they still got imported at worker boot, every
one failed its top-level import, and the worker logged six warnings on
every startup.  Cleanup moved all six to ``app.tasks._disabled/`` with
revival checklists at the original paths, and removed them from the
registry below.  See commit <sha> for the diagnosis (which targets
existed, which were real bugs vs. missing features) and per-module
revival instructions.
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

# ── Q1-B Chunk 2: Beat schedule ──────────────────────────────────
celery_app.conf.beat_schedule = {
    "expire-hitl-items": {
        "task": "hitl.expire_items",
        "schedule": 300.0,  # 5 minutes
    },
    "integration-health-check-all": {
        "task": "integration.health_check_all",
        "schedule": 900.0,  # 15 minutes
    },
}


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


# ---------------------------------------------------------------------------
# Custom task registration
# ---------------------------------------------------------------------------
#
# The Celery worker command in docker-compose.yml is:
#   celery -A app.tasks.celery_app worker --loglevel=info ...
#
# That command only imports `app.tasks.celery_app` on startup.  Every
# `@celery_app.task(...)` and `@shared_task(...)` decorator in
# app.tasks.* lives in a separate module that the worker never imports
# unless something else does.  Without the explicit imports below, the
# worker's task registry contains only built-in Celery tasks (celery.chain,
# celery.starmap, ...) and rejects every custom task at dispatch time
# with `Received unregistered task of type 'X'`.  Missions can be
# dispatched fine, RabbitMQ accepts them, but the worker has no handler
# and the job is silently dropped.  This was a latent production bug
# affecting every custom task (langgraph.*, swarm.*, substrate.resume_hitl,
# batch.process_batch, training.*, webhook.*, mission.execute_async, ...).
#
# Discovered: 2026-06-12, immediately after Q1-B chunk 1 (substrate.resume_hitl).
def _register_custom_tasks() -> None:
    """Import all task modules and register class-based tasks.

    Each module is imported individually inside its own try/except so a
    broken import in one module doesn't prevent the rest from registering.
    The failure mode (worker boots, registry is partial) is strictly better
    than the previous behaviour (worker boots, registry is empty, every
    custom task is dropped with "Received unregistered task of type X").

    Disabled modules (moved to ``app.tasks._disabled/`` on 2026-06-12,
    revival instructions in each stub):
    - base_task:         CeleryTask model never built
    - deepagents_tasks:  app.services.deepagents_integration never built
    - langgraph_tasks:   agent.get_llm() never added to llm_config
    - task_definitions:  WorkflowRuns model + MonitoringService never built
    - webhook_dispatcher: webhook_subscription/delivery/event models
                         never built (different shape from existing
                         webhook_models.py)
    - webhook_tasks:     SyncSessionLocal never added to app/database.py
    """
    # Each entry: (module_name, comment)  - imported for decorator side effects.
    task_modules = [
        ("background_review_tasks", "memory.review_mission  (background self-improvement)"),
        ("batch_processing", "batch.process_batch"),
        ("deepagents_tasks", "deepagents.{execute, stream, batch_execute}"),
        ("hitl_resume", "substrate.resume_hitl  (Q1-B chunk 1)"),
        ("hitl_expiry", "hitl.expire_items  (Q1-B chunk 2)"),
        ("integration_health_tasks", "integration.health_check_all  (Phase 2 health checks)"),
        ("n8n_callback", "5 n8n integration tasks"),
        ("swarm_tasks", "swarm.{execute_task, consensus_timeout, agent_heartbeat_check, cost_budget_check}"),
        ("training_tasks", "training.* (7 tasks)"),
    ]

    registered_modules: list[str] = []
    failed_modules: list[tuple[str, str]] = []  # (module, error message)
    for mod_name, _comment in task_modules:
        try:
            __import__(f"app.tasks.{mod_name}", fromlist=["*"])
            registered_modules.append(mod_name)
        except Exception as exc:
            failed_modules.append((mod_name, f"{type(exc).__name__}: {exc}"))

    # Class-based tasks that don't use the @celery_app.task decorator must
    # be explicitly registered with the app instance.  If the module
    # itself is broken, this will fail too.
    try:
        from app.tasks.mission_execution import ExecuteMissionTask

        celery_app.register_task(ExecuteMissionTask())
    except Exception as exc:
        failed_modules.append(("mission_execution", f"{type(exc).__name__}: {exc}"))

    # Log a clear summary so any partial-registration state is visible
    # at worker startup, not silently discovered at first task dispatch.
    custom_tasks = sorted(k for k in celery_app.tasks if not k.startswith("celery."))
    logger.info(
        "Celery task registration: %d module(s) imported, %d custom task(s) in registry: %s",
        len(registered_modules),
        len(custom_tasks),
        custom_tasks,
    )
    if failed_modules:
        logger.warning(
            "Celery task registration: %d module(s) FAILED to import (pre-existing bugs):",
            len(failed_modules),
        )
        for mod, err in failed_modules:
            logger.warning("  - app.tasks.%s: %s", mod, err)


_register_custom_tasks()
