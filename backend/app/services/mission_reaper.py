"""MissionReaper — recover stuck RUNNING missions.

Modeled on ``substrate/lease_reclaimer.py`` (``LeaseReclaimer._scan_once``):
owns its AsyncSession, locks each candidate ``SELECT … FOR UPDATE``,
processes a bounded batch, swallows per-row errors so one bad row can't
kill the sweep.

Failure mode FM-3: a mission in ``RUNNING`` whose worker died (its
``substrate_worker_leases`` row is expired, or it has no lease at all but a
stale ``started_at``) would otherwise live forever.  The reaper transitions
it to ``FAILED`` with ``fail_reason="stale_pause"`` — NOT ``ABORTED``
(GC: abort closes the retry path; FAILED keeps recoverability, P3/P8).

Each reaped row emits:
  * a ``SubstrateEvent(RUN_FAILED, cause="stale_pause")`` via EventLog
    (source-of-truth, dedup-on-write);
  * a ``MissionLog`` audit row written in its OWN fresh session (GC4) so
    it survives even if the reaper transaction rolls back.
"""

from __future__ import annotations

import logging
import socket
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError

from app.database import AsyncSessionLocal, fresh_session
from app.models.mission_models import Mission, MissionLog, MissionStatus
from app.models.substrate_models import SubstrateEventType
from app.services.substrate.event_log import get_event_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# A RUNNING mission with no heartbeat/lease renewal for this long is stranded.
DEFAULT_STALE_AFTER = timedelta(minutes=15)


class MissionReaper:
    """Background sweep that reaps dead-worker RUNNING missions.

    Usage::

        reaper = MissionReaper()
        reaped = await reaper.scan_once()
        logger.info("reaper scan", reaped=reaped)
    """

    def __init__(
        self,
        worker_id: str | None = None,
        scan_interval_seconds: int = 300,
        batch_size: int = 100,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
    ) -> None:
        self._worker_id = worker_id or (f"mission-reaper-{socket.gethostname()}-{id(self)}")
        self._scan_interval = scan_interval_seconds
        self._batch_size = batch_size
        self._stale_after = stale_after

    @property
    def worker_id(self) -> str:
        return self._worker_id

    async def scan_once(self) -> int:
        """One scan pass. Returns the number of missions reaped."""
        async with AsyncSessionLocal() as db:
            candidates = await self._find_candidates(db)
            if not candidates:
                return 0

            reaped = 0
            for mission in candidates:
                try:
                    ok = await self._reap_one(db, mission)
                    if ok:
                        reaped += 1
                except DBAPIError:
                    # Concurrent transition (e.g. a resume) — skip this row.
                    await db.rollback()
                    logger.debug(
                        "reaper_row_skipped_concurrent",
                        mission_id=str(mission.id),
                    )
                except Exception as exc:
                    await db.rollback()
                    logger.warning(
                        "reaper_row_failed",
                        mission_id=str(mission.id),
                        exc_info=exc,
                    )
            if reaped:
                logger.info(
                    "reaper_scan_complete",
                    worker=self._worker_id,
                    reaped=reaped,
                )
            return reaped

    async def _find_candidates(self, db: AsyncSession) -> list[Mission]:
        """Lock RUNNING rows whose worker is gone or started too long ago."""
        cutoff = datetime.now(UTC) - self._stale_after
        # SELECT … FOR UPDATE so a concurrent resume/abort on the same row
        # blocks instead of racing us (TOCTOU safety).
        result = await db.execute(
            select(Mission)
            .where(Mission.status == MissionStatus.RUNNING)
            .where(Mission.started_at.is_not(None))
            .where(Mission.started_at < cutoff)
            .with_for_update()
            .limit(self._batch_size)
        )
        return list(result.scalars().all())

    async def _reap_one(self, db: AsyncSession, mission: Mission) -> bool:
        """Transition one stranded RUNNING mission → FAILED(stale_pause)."""
        if mission.status != MissionStatus.RUNNING:
            return False  # moved off RUNNING by a concurrent actor

        run_id = (mission.plan or {}).get("substrate_run_id")
        mission.status = MissionStatus.FAILED
        mission.error_message = "Reaped: worker lease expired (stale_pause)"
        mission.plan = {
            **(mission.plan or {}),
            "fail_reason": "stale_pause",
        }
        mission.completed_at = datetime.now(UTC)
        await db.commit()

        # Source-of-truth substrate event (dedup-on-write via EventLog).
        try:
            event_log = get_event_log()
            await event_log.append(
                db,
                run_id or str(mission.id),
                [
                    {
                        "type": SubstrateEventType.RUN_FAILED,
                        "payload": {
                            "cause": "stale_pause",
                            "mission_id": str(mission.id),
                            "reaper": self._worker_id,
                        },
                        "actor": "mission_reaper",
                        "task_id": None,
                    }
                ],
                mission_id=str(mission.id),
            )
            await db.commit()
        except Exception as exc:
            logger.warning(
                "reaper_event_log_failed",
                mission_id=str(mission.id),
                exc_info=exc,
            )

        # Forensic audit in its OWN autonomous session (GC4 / FM-2):
        # survives even if the reaper tx above rolled back.
        await self._write_audit(str(mission.id), run_id)
        return True

    async def _write_audit(self, mission_id: str, run_id: str | None) -> None:
        try:
            async with fresh_session() as s:
                s.add(
                    MissionLog(
                        mission_id=str(mission_id),
                        level="warning",
                        message="Mission reaped: dead worker (stale_pause)",
                        data={
                            "actor": "mission_reaper",
                            "prev_state": MissionStatus.RUNNING.value,
                            "next_state": MissionStatus.FAILED.value,
                            "fail_reason": "stale_pause",
                            "run_id": run_id,
                        },
                        timestamp=datetime.now(UTC),
                    )
                )
        except Exception as exc:
            logger.error(
                "reaper_audit_write_failed",
                mission_id=str(mission_id),
                exc_info=exc,
            )


async def reap_stale_missions() -> int:
    """Module entry point for the Celery beat task."""
    return await MissionReaper().scan_once()
