"""Background task to purge expired playground sandboxes."""

from __future__ import annotations

import asyncio
import logging

from app.database import AsyncSessionLocal
from app.services.playground_service import PlaygroundService

logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 120  # Check every 2 minutes


async def purge_expired_playgrounds() -> None:
    """Continuously purge expired anonymous playground sandboxes."""
    service = PlaygroundService()
    while True:
        try:
            async with AsyncSessionLocal() as db:
                count = await service.purge_expired(db=db)
                if count > 0:
                    logger.info("Purged %d expired playground sandboxes", count)
        except Exception as e:
            logger.error("Playground purge error: %s", e)
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)


_cleanup_task: asyncio.Task | None = None


def start_playground_cleanup() -> None:
    """Start the playground cleanup background task. Call during app startup."""
    global _cleanup_task
    loop = asyncio.get_event_loop()
    _cleanup_task = loop.create_task(purge_expired_playgrounds())
    logger.info(
        "Playground cleanup task started (interval=%ds)", PURGE_INTERVAL_SECONDS
    )


def stop_playground_cleanup() -> None:
    """Stop the playground cleanup background task."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
        logger.info("Playground cleanup task stopped")
