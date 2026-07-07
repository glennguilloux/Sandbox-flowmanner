"""Celery task for durable memory extraction.

P0-1: Wraps ``_maybe_extract_memory_claims`` in a Celery task so memory
extraction survives process crashes and is visible in the Celery dashboard.

Previously, memory extraction used ``asyncio.create_task(_safe_fire_and_forget(...))``
which had two problems:
  1. No strong reference → GC could kill the task mid-flight
  2. No durability → lost on process crash

This task opens its own DB session (via fresh_session) so it's fully
independent of the web worker's request lifecycle.
"""

from __future__ import annotations

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="memory.extract_claims",
    max_retries=1,
    default_retry_delay=30,
    acks_late=True,
)
def extract_memory_claims_task(
    self,
    thread_id: int,
    user_id: int,
    user_message: str,
    assistant_response: str,
) -> dict:
    """Extract personal-memory claims from a chat exchange.

    Runs as a Celery task for durability.  Opens its own event loop
    because Celery workers are synchronous by default.
    """
    result: dict[str, str | int | None] = {
        "thread_id": thread_id,
        "user_id": user_id,
        "claims_extracted": 0,
        "error": None,
    }
    try:
        from app.services.chat_service import _maybe_extract_memory_claims

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                _maybe_extract_memory_claims(
                    thread_id=thread_id,
                    user_id=user_id,
                    user_message=user_message,
                    assistant_response=assistant_response,
                )
            )
        finally:
            loop.close()

        logger.info(
            "memory.extract_claims: completed for thread %s user %s",
            thread_id,
            user_id,
        )
    except Exception as exc:
        logger.warning(
            "memory.extract_claims: failed for thread %s: %s",
            thread_id,
            exc,
        )
        result["error"] = str(exc)

    return result
