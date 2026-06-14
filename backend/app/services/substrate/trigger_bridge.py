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
        """Check and fire due cron triggers + MissionProgram fires.

        Two independent paths run in this tick:

        1. Legacy cron triggers (trigger_service.process_cron_triggers).
        2. NEW (T9): active MissionProgram rows whose trigger_config is
           ``cron`` type — dispatched via
           ``MissionProgramService.fire_program``.

        Each path uses its own DB session so a failure in one does not
        poison the other.
        """
        import time

        self._tick_count += 1
        self._last_tick_time = time.monotonic()
        # Path 1: legacy cron triggers (unchanged).
        try:
            async with AsyncSessionLocal() as db:
                from app.services.trigger_service import process_cron_triggers

                fired = await process_cron_triggers(db)
                await db.commit()
                if fired:
                    logger.info("TriggerBridge dispatched %d cron trigger(s)", fired)
        except Exception as e:
            logger.error("TriggerBridge polling tick failed: %s", e, exc_info=True)
        # Path 2: MissionProgram cron fires (T9). Failures are isolated
        # so the legacy path above is never blocked.
        try:
            async with AsyncSessionLocal() as db:
                program_run_ids = await self._dispatch_program_fires(db)
                await db.commit()
                if program_run_ids:
                    logger.info(
                        "TriggerBridge dispatched %d program fire(s)",
                        len(program_run_ids),
                    )
        except Exception as e:
            logger.error(
                "TriggerBridge program dispatch failed: %s", e, exc_info=True
            )

    async def _dispatch_program_fires(self, db) -> list:
        """Find active MissionProgram rows with cron triggers and dispatch
        them via ``MissionProgramService.fire_program``.

        Returns a list of new ``ProgramRun.id`` UUIDs. The caller is
        responsible for committing the session.

        NOTE: simplified — this implementation fires ALL active programs
        whose ``trigger_config.type == "cron"`` on every tick. In
        production (T15) this will be replaced by proper cron-expression
        matching using a cron parser. For the wiring smoke test this is
        sufficient: it proves the dispatch path works end-to-end.
        """
        # Lazy imports — keeps the bridge lightweight and avoids cycles.
        from uuid import UUID

        from sqlalchemy import select

        from app.models.mission_program_models import MissionProgram
        from app.services.mission_program_service import (
            MissionProgramService,
        )

        programs = list(
            (
                await db.execute(
                    select(MissionProgram).where(
                        MissionProgram.status == "active"
                    )
                )
            )
            .scalars()
            .all()
        )

        fired: list[UUID] = []
        for program in programs:
            cfg = program.trigger_config or {}
            if cfg.get("type") != "cron":
                continue
            try:
                service = MissionProgramService(db)
                run = await service.fire_program(
                    user_id=program.user_id,
                    program_id=program.id,
                    trigger_type="cron",
                    trigger_payload=None,
                )
                fired.append(run.id)
            except Exception as exc:
                logger.warning(
                    "program fire failed for %s: %s",
                    program.id,
                    exc,
                    exc_info=True,
                )
        return fired


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
