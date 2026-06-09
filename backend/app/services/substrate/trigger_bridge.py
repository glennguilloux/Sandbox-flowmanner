"""Event-driven trigger bridge (H2.4).

Replaces the polling-based trigger scheduler (30s tick) with 2-second
polling for near-sub-second trigger dispatch.

Architecture:
- Polls every 2 seconds (vs. 30s in the old scheduler)
- Always started at application startup (legacy TriggerScheduler removed)
- The notify_trigger_due() helper is called from trigger_service.py
  on create/update/resume/fire — this is a future hook for
  event-driven dispatch (PG LISTEN/NOTIFY or Redis pubsub).

Usage:
    from app.services.substrate.trigger_bridge import start_trigger_bridge
    await start_trigger_bridge()
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime

from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

# Polling interval — 2 seconds approaches the sub-second target
# while being robust across all SQLAlchemy versions.
FALLBACK_TICK_SECONDS = 2


class TriggerBridge:
    """Near-real-time trigger dispatcher with 2-second polling.

    Runs as a background asyncio task. Polls the database every 2 seconds
    for due cron triggers — a 15x improvement over the old 30s scheduler.
    """

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_tick_time: float = 0.0
        self._tick_count: int = 0

    async def start(self) -> None:
        """Start the trigger bridge with 2-second polling."""
        if self._task is not None:
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("TriggerBridge started (H2.4, %ds polling)", FALLBACK_TICK_SECONDS)

    async def stop(self) -> None:
        """Stop the trigger bridge."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("TriggerBridge stopped (%d ticks processed)", self._tick_count)

    @property
    def stats(self) -> dict:
        return {
            "ticks_processed": self._tick_count,
            "last_tick": self._last_tick_time,
            "running": self._running,
        }

    async def _run(self) -> None:
        """Main polling loop.

        Uses a simple while loop with 2-second polling interval.
        Robust across all SQLAlchemy versions — no asyncpg-specific
        LISTEN/NOTIFY API needed.
        """
        while self._running:
            await self._poll_once()
            await asyncio.sleep(FALLBACK_TICK_SECONDS)

    async def _poll_once(self) -> None:
        """Check and fire due cron triggers."""
        import time

        self._tick_count += 1
        self._last_tick_time = time.monotonic()
        try:
            async with AsyncSessionLocal() as db:
                from app.services.trigger_service import process_cron_triggers

                fired = await process_cron_triggers(db)
                await db.commit()
                if fired:
                    logger.info("TriggerBridge dispatched %d cron trigger(s)", fired)
        except Exception as e:
            logger.error("TriggerBridge polling tick failed: %s", e, exc_info=True)


# ── Notify helper: called from trigger_service when next_fire_at changes ──


async def notify_trigger_due(next_fire_at: datetime | None = None) -> None:
    """Future hook: notify that a trigger's fire time has changed.

    Called by trigger_service.py when:
    - A new cron trigger is created (next_fire_at is computed)
    - A cron trigger's next_fire_at is updated
    - A paused trigger is resumed
    - A cron trigger fires and computes a new next_fire_at

    Currently a no-op placeholder.  When PG LISTEN/NOTIFY or Redis pubsub
    is properly wired (H5 or beyond), this will send the notification.
    For now, the 2s polling loop catches all changes within 2 seconds.
    """
    # Placeholder for future event-driven dispatch.
    # The 2s polling in TriggerBridge already handles this well enough for H2.
    logger.debug(
        "notify_trigger_due called (next_fire_at=%s) — bridge polling at %ds handles dispatch",
        next_fire_at.isoformat() if next_fire_at else "check_all",
        FALLBACK_TICK_SECONDS,
    )


# ── Singleton / lifecycle ──────────────────────────────────────────

_bridge: TriggerBridge | None = None


def get_trigger_bridge() -> TriggerBridge:
    """Get or create the TriggerBridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = TriggerBridge()
    return _bridge


async def start_trigger_bridge() -> None:
    """Start the event-driven trigger bridge (called from app startup)."""
    bridge = get_trigger_bridge()
    await bridge.start()


async def stop_trigger_bridge() -> None:
    """Stop the trigger bridge (called from app shutdown)."""
    if _bridge is not None:
        await _bridge.stop()
