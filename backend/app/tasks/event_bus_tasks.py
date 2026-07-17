"""Celery task: off-request-path dispatch for inbound ExternalEvents.

The webhook route persists an ``ExternalEvent`` (status ``"pending"``) and
returns.  After the request's DB transaction commits, it enqueues
``process_external_event(event_id)`` via a FastAPI ``BackgroundTasks`` hook.
This task loads the event in its own transaction and runs the registered
consumers (trigger matching, audit, failure alerts), then commits the
status transition.

Why this shape (Q4 / Q5 / Q6):
- Q4 (post-commit): the enqueue happens in the route's BackgroundTasks, which
  FastAPI runs only after the response is sent and the ``get_db`` transaction
  has committed.  A crash between commit and enqueue leaves a durable
  ``"pending"`` row that a later recovery sweep can re-enqueue — at-least-once.
- Q5 (idempotency): ``publish()`` already de-dupes by ``delivery_id`` and the
  DB has ``UNIQUE(source, delivery_id)``.  This task adds a claim-step: if the
  event is already ``"processed"``/``"failed"`` with a ``processed_at``, a
  redelivered task is a no-op rather than re-firing triggers.
- Q6 (failure alerts): ``failure_alert_consumer`` is a registered failure
  handler on the EventBus singleton, so it still fires on ``"failed"`` status
  — now gated on the committed (post-dispatch) status, inside this task.
"""

from __future__ import annotations

import asyncio
import logging

from celery import shared_task

from app.database import fresh_session
from app.models.external_event_model import ExternalEvent
from app.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)


def enqueue_event_processing(event_id: str) -> None:
    """Enqueue ``process_external_event`` for an event (safe wrapper).

    Called from the webhook route's ``BackgroundTasks`` (post-commit).  If the
    broker is unavailable (e.g. unit tests, local dev without RabbitMQ), the
    enqueue is logged and swallowed — the durable ``"pending"`` row remains
    and can be recovered later.  This must NEVER raise into the request path.
    """
    try:
        process_external_event.delay(event_id)
    except Exception as exc:  # Broker down / misconfigured — do not fail the ack.
        logger.warning(
            "event_bus: failed to enqueue process_external_event for %s: %s",
            event_id,
            exc,
        )


@shared_task(name="event_bus.process_external_event", bind=True, max_retries=3)
def process_external_event(self, event_id: str) -> str:
    """Dispatch a persisted ExternalEvent to consumers, off the request path.

    Loads the event in its own transaction, runs the registered consumers +
    failure handlers via ``EventBus.process_event``, and commits.  Idempotent:
    a redelivered task for an already-completed event is a no-op.

    Returns:
        The final event status (``"processed"`` / ``"failed"`` / ``"skipped"``
        / ``"not_found"``).
    """
    return asyncio.run(_dispatch(event_id))


async def _dispatch(event_id: str) -> str:
    """Async body: open a session, claim the event, run consumers, commit."""
    async with fresh_session() as db:
        event = await db.get(ExternalEvent, event_id)
        if event is None:
            logger.warning("event_bus: process_external_event %s — event not found", event_id)
            return "not_found"

        # ── Claim-step (Q5 dedup): already completed → no-op ───────
        if event.status in ("processed", "failed") and event.processed_at is not None:
            logger.info(
                "event_bus: process_external_event %s — already %s, skipping (redelivery no-op)",
                event_id,
                event.status,
            )
            return "skipped"

        # Reset to pending so consumers re-run cleanly (e.g. a stale
        # "pending" row from a prior crash that never dispatched).
        event.status = "pending"
        event.processed_at = None
        event.error_message = None
        event.triggers_fired = 0
        await db.flush()

        bus = get_event_bus()
        await bus.process_event(db, event)
        # fresh_session commits on context exit (success) / rolls back on exc.

    logger.info(
        "event_bus: process_external_event %s finished with status=%s",
        event_id,
        event.status,
    )
    return event.status
