"""Celery beat task: auto-fail missions paused longer than the configured window.

Runs periodically (every 5 minutes via Celery beat). Finds missions that are
``status='paused'`` AND ``paused_at`` is older than
``settings.MISSION_PAUSE_AUTO_FAIL_DAYS`` days, and for each:

  1. Atomically transition PAUSED -> FAILED. The MissionStatus state machine
     now permits this transition (see app/models/mission_models.py). A concurrent
     resume that already moved the row off PAUSED means the row is no longer
     locked+matched by the WHERE clause, so we skip it (no error surfaced).
  2. Append a SubstrateEvent(RUN_FAILED, cause="pause_timeout") via EventLog.
     EventLog owns dedup-on-write (idempotency_key) + sequence assignment, so a
     retried task cannot duplicate the source-of-truth event. SubstrateEvent is
     the reconstruction source for mission state, so writing through EventLog
     (never db.add) is mandatory.
  3. Write a MissionLog line for the human-readable audit trail.
  4. Run CompensationService (release leases, credit refund, notify) — independently
     idempotent via the compensated_at lock, so a retry cannot double-refund.

Mirrors hitl_expiry.py: fresh event loop per invocation, engine.dispose() to
drop fork-inherited asyncpg connections, FOR UPDATE SKIP LOCKED for race
safety, and Celery self.retry with exponential backoff on failure.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal, engine
from app.models.mission_models import Mission, MissionLog, MissionStatus
from app.services.mission_compensation_service import CompensationService
from app.services.substrate.event_log import EventLog, get_event_log
from app.tasks.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task (mirrors hitl_expiry)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _run_id_for(mission: Mission) -> str | None:
    """Derive the substrate run_id for a mission.

    The executor records the substrate run id under mission.plan["substrate_run_id"]
    (see app/services/substrate/adapters.py / app/api/_mission_cqrs/commands.py).
    Falls back to str(mission_id) only if no substrate run exists.
    """
    plan = getattr(mission, "plan", None)
    rid = plan.get("substrate_run_id") if isinstance(plan, dict) else None
    return str(rid) if rid else str(mission.id)


async def _expire_one(db, mission: Mission) -> dict:
    """Fail one paused mission + compensate. Returns a status dict.

    State transition + SubstrateEvent + MissionLog are committed in this
    session; compensation runs via its own service (own session/lock).
    """
    mission_id = mission.id
    run_id = _run_id_for(mission)
    user_id = mission.user_id
    workspace_id = mission.workspace_id

    if mission.status != MissionStatus.PAUSED:
        return {"mission_id": mission_id, "skipped": True, "reason": "not_paused"}

    prev = mission.status.value
    # The ORM validator (MissionStatus._on_mission_status_set) enforces the
    # transition table; PAUSED -> FAILED is permitted. If a concurrent actor
    # changed status between SELECT ... FOR UPDATE and here, this raises and
    # the row is rolled back without committing a FAILED transition.
    mission.status = MissionStatus.FAILED
    mission.error_message = "Auto-failed: paused longer than the allowed window."

    # Source-of-truth event through EventLog (dedup-on-write + sequence).
    event_log: EventLog = get_event_log()
    await event_log.append(
        db,
        run_id,
        [
            {
                "type": "RUN_FAILED",
                "payload": {
                    "status": "failed",
                    "cause": "pause_timeout",
                    "error": "pause_timeout",
                    "prev_state": prev,
                    "next_state": MissionStatus.FAILED.value,
                },
                "actor": "system:expire_paused",
                "idempotency_key": f"pause_timeout_fail:{mission_id}",
            }
        ],
        mission_id=str(mission_id),
    )

    db.add(
        MissionLog(
            mission_id=mission_id,
            level="warning",
            message=f"Mission auto-failed (pause timeout > window). Was: {prev}.",
            data={
                "actor": "system",
                "prev_state": prev,
                "next_state": MissionStatus.FAILED.value,
                "cause": "pause_timeout",
            },
        )
    )
    await db.commit()

    # Compensation (independent idempotency via compensated_at lock).
    comp = CompensationService(db)
    comp_result = await comp.run(
        mission_id=mission_id,
        run_id=run_id,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    await db.commit()
    return {"mission_id": mission_id, "failed": True, "compensation": comp_result}


async def _expire_async() -> dict:
    from app.config import settings

    window_days = int(getattr(settings, "MISSION_PAUSE_AUTO_FAIL_DAYS", 7))
    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    await engine.dispose()

    processed = 0
    skipped = 0
    failures = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Mission)
            .where(
                Mission.status == MissionStatus.PAUSED.value,
                Mission.paused_at.is_not(None),  # NULL = legacy, treat as infinity
                Mission.paused_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        )
        missions = result.scalars().all()

        for mission in missions:
            try:
                outcome = await _expire_one(db, mission)
                if outcome.get("failed"):
                    processed += 1
                else:
                    skipped += 1
            except Exception as exc:
                failures.append({"mission_id": str(mission.id), "error": str(exc)})
                logger.error("expire_paused_mission_failed", mission_id=str(mission.id), error=str(exc))

    return {
        "processed": processed,
        "skipped": skipped,
        "failed": failures,
        "window_days": window_days,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@celery_app.task(
    name="mission.expire_paused",
    bind=True,
    max_retries=2,
    acks_late=False,
    time_limit=300,
    soft_time_limit=240,
)
def expire_paused_missions(self):
    """Auto-fail missions paused longer than the configured window.

    Scheduled via Celery beat every 5 minutes (see celery_app.py).
    Idempotent: SKIP LOCKED + EventLog idempotency_key + compensated_at lock
    prevent double-processing on retry/concurrent runs.
    """
    try:
        result = _run_async(_expire_async())
        if result["processed"] > 0 or result["failed"]:
            logger.info(
                "expire_paused_task_complete",
                processed=result["processed"],
                skipped=result["skipped"],
                failed=len(result["failed"]),
            )
        if result["failed"]:
            logger.warning("expire_paused_partial_failures", failures=result["failed"])
        return result
    except Exception as exc:
        logger.error("expire_paused_task_failed", error=str(exc))
        countdown = 30 * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
