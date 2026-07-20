"""Mission Trigger Service (FLO-118).

Core business logic for cron scheduling, webhook triggers, and trigger history.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from croniter import croniter
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trigger_models import MissionTrigger, TriggerLog
from app.services.mission_service import get_mission_tasks

logger = logging.getLogger(__name__)


# ── CRUD ──────────────────────────────────────────────────────────────────────


async def create_trigger(db: AsyncSession, user_id: int, payload) -> MissionTrigger:
    """Create a new trigger. Computes next_fire_at for cron triggers."""
    webhook_path = None
    if payload.trigger_type == "webhook":
        webhook_path = f"{uuid4().hex[:16]}"

    trigger = MissionTrigger(
        user_id=user_id,
        mission_id=payload.mission_id,
        trigger_type=payload.trigger_type,
        name=payload.name,
        status="active",
        cron_expression=payload.cron_expression,
        cron_timezone=payload.cron_timezone or "UTC",
        webhook_secret=payload.webhook_secret,
        webhook_path=webhook_path,
        config=payload.config,
    )

    if payload.trigger_type == "cron" and payload.cron_expression:
        trigger.next_fire_at = _compute_next_fire(payload.cron_expression, payload.cron_timezone or "UTC")

    db.add(trigger)
    await db.flush()
    await db.refresh(trigger)

    # H2.4: Notify the event-driven trigger bridge
    if trigger.trigger_type == "cron" and trigger.next_fire_at:
        try:
            from app.services.substrate.trigger_bridge import notify_trigger_due

            await notify_trigger_due(trigger.next_fire_at)
        except Exception as e:
            logger.debug("trigger_notify_create_failed trigger_id=%s error=%s", trigger.id, str(e))

    return trigger


async def list_triggers(db: AsyncSession, user_id: int) -> list[MissionTrigger]:
    """List all non-deleted triggers for a user."""
    result = await db.execute(
        select(MissionTrigger)
        .where(and_(MissionTrigger.user_id == user_id, MissionTrigger.is_deleted == False))
        .order_by(MissionTrigger.created_at.desc())
    )
    return list(result.scalars().all())


async def get_trigger(db: AsyncSession, trigger_id: str, user_id: int) -> MissionTrigger | None:
    """Get a single trigger with ownership check."""
    result = await db.execute(
        select(MissionTrigger).where(
            and_(
                MissionTrigger.id == trigger_id,
                MissionTrigger.user_id == user_id,
                MissionTrigger.is_deleted == False,
            )
        )
    )
    return result.scalar_one_or_none()


async def get_trigger_by_webhook_path(db: AsyncSession, webhook_path: str) -> MissionTrigger | None:
    """Look up a trigger by its webhook path (public endpoint)."""
    result = await db.execute(
        select(MissionTrigger).where(
            and_(
                MissionTrigger.webhook_path == webhook_path,
                MissionTrigger.trigger_type == "webhook",
                MissionTrigger.status == "active",
                MissionTrigger.is_deleted == False,
            )
        )
    )
    return result.scalar_one_or_none()


async def get_trigger_any(db: AsyncSession, trigger_id: str) -> MissionTrigger | None:
    """Get trigger by ID without ownership check (for internal use)."""
    result = await db.execute(select(MissionTrigger).where(MissionTrigger.id == trigger_id))
    return result.scalar_one_or_none()


async def update_trigger(db: AsyncSession, trigger_id: str, user_id: int, payload) -> MissionTrigger | None:
    """Update trigger fields. Recomputes next_fire_at if cron_expression changes."""
    trigger = await get_trigger(db, trigger_id, user_id)
    if not trigger:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(trigger, field, value)

    if "cron_expression" in update_data or "cron_timezone" in update_data:
        expr = update_data.get("cron_expression", trigger.cron_expression)
        tz = update_data.get("cron_timezone", trigger.cron_timezone)
        if expr:
            trigger.next_fire_at = _compute_next_fire(expr, tz)

    await db.flush()
    await db.refresh(trigger)

    # H2.4: Notify the event-driven trigger bridge on update
    if trigger.trigger_type == "cron" and trigger.next_fire_at:
        try:
            from app.services.substrate.trigger_bridge import notify_trigger_due

            await notify_trigger_due(trigger.next_fire_at)
        except Exception as e:
            logger.debug("trigger_notify_update_failed trigger_id=%s error=%s", trigger.id, str(e))

    return trigger


async def delete_trigger(db: AsyncSession, trigger_id: str, user_id: int) -> bool:
    """Soft delete a trigger."""
    trigger = await get_trigger(db, trigger_id, user_id)
    if not trigger:
        return False
    trigger.is_deleted = True
    await db.flush()
    return True


async def pause_trigger(db: AsyncSession, trigger_id: str, user_id: int) -> MissionTrigger | None:
    """Pause an active trigger."""
    trigger = await get_trigger(db, trigger_id, user_id)
    if not trigger:
        return None
    trigger.status = "paused"
    trigger.next_fire_at = None
    await db.flush()
    await db.refresh(trigger)
    return trigger


async def resume_trigger(db: AsyncSession, trigger_id: str, user_id: int) -> MissionTrigger | None:
    """Resume a paused trigger."""
    trigger = await get_trigger(db, trigger_id, user_id)
    if not trigger:
        return None
    trigger.status = "active"
    if trigger.trigger_type == "cron" and trigger.cron_expression:
        trigger.next_fire_at = _compute_next_fire(trigger.cron_expression, trigger.cron_timezone)
    await db.flush()
    await db.refresh(trigger)

    # H2.4: Notify the event-driven trigger bridge on resume
    if trigger.trigger_type == "cron" and trigger.next_fire_at:
        try:
            from app.services.substrate.trigger_bridge import notify_trigger_due

            await notify_trigger_due(trigger.next_fire_at)
        except Exception as e:
            logger.debug("trigger_notify_resume_failed trigger_id=%s error=%s", trigger.id, str(e))

    return trigger


async def get_trigger_logs(db: AsyncSession, trigger_id: str, user_id: int) -> list[TriggerLog]:
    """Get execution history for a trigger (with ownership check)."""
    trigger = await get_trigger(db, trigger_id, user_id)
    if not trigger:
        return []
    result = await db.execute(
        select(TriggerLog).where(TriggerLog.trigger_id == trigger_id).order_by(TriggerLog.fired_at.desc())
    )
    return list(result.scalars().all())


# ── TRIGGER FIRING ────────────────────────────────────────────────────────────


async def fire_trigger(db: AsyncSession, trigger: MissionTrigger, payload: dict | None = None) -> TriggerLog:
    """Fire a trigger: log the event and spawn mission execution.

    H2.4: After firing, notifies the trigger bridge for the next fire time (if cron).
    """
    log = TriggerLog(
        trigger_id=trigger.id,
        trigger_type=trigger.trigger_type,
        status="pending",
        payload=payload,
        fired_at=datetime.now(UTC),
    )
    db.add(log)
    await db.flush()

    # Update trigger tracking
    trigger.fire_count = (trigger.fire_count or 0) + 1
    trigger.last_fired_at = datetime.now(UTC)
    if trigger.trigger_type == "cron" and trigger.cron_expression:
        trigger.next_fire_at = _compute_next_fire(trigger.cron_expression, trigger.cron_timezone)
    await db.flush()

    # Spawn mission execution in background
    mission_id = str(trigger.mission_id)
    log_id = str(log.id)
    asyncio.create_task(_execute_mission_background(mission_id, log_id, trigger.id))

    # H2.4: Notify the trigger bridge about the next fire time
    if trigger.trigger_type == "cron" and trigger.next_fire_at:
        try:
            from app.services.substrate.trigger_bridge import notify_trigger_due

            asyncio.create_task(notify_trigger_due(trigger.next_fire_at))
        except Exception as e:
            logger.debug("trigger_notify_fire_failed trigger_id=%s error=%s", trigger.id, str(e))

    return log


async def _execute_mission_background(mission_id: str, log_id: str, trigger_id: str):
    """Background task to execute a mission triggered by cron/webhook.

    H5.1: Routes through UnifiedExecutor for durable execution, replay,
    budget enforcement, and capability tokens.
    """
    from app.database import AsyncSessionLocal
    from app.models.mission_models import Mission, MissionStatus
    from app.services.substrate.adapters import mission_to_workflow
    from app.services.substrate.executor import get_unified_executor

    start_time = time.monotonic()
    async with AsyncSessionLocal() as db:
        try:
            # Load the mission ORM object
            mission = await db.get(Mission, mission_id)
            if not mission:
                raise ValueError(f"Mission {mission_id} not found")

            # Mark the mission running before substrate execution (mirrors Celery path)
            mission.status = MissionStatus.RUNNING

            # Load the mission's real tasks and convert to a unified Workflow
            tasks = await get_mission_tasks(db, mission_id)
            workflow = mission_to_workflow(mission, tasks=tasks)
            executor = get_unified_executor()
            result = await executor.execute(db, workflow)
            duration_ms = int((time.monotonic() - start_time) * 1000)

            # Set terminal status from the execution result
            mission.status = MissionStatus.COMPLETED if getattr(result, "success", False) else MissionStatus.FAILED
            mission.completed_at = datetime.now(UTC)

            # ── Inbox/Notifications emission (explicit, non-raising) ──
            # Lazy import + guarded so a notification failure can NEVER block the
            # mission transition or fail the trigger. Owner is mission.user_id.
            try:
                from app.services.notification_service import send_notification

                ntype = "mission_completed" if getattr(result, "success", False) else "mission_failed"
                await send_notification(
                    user_id=mission.user_id,
                    notification_type=ntype,
                    data={
                        "title": f"Mission {'completed' if getattr(result, 'success', False) else 'failed'}: {mission.title}",
                        "message": (
                            mission.title
                            if getattr(result, "success", False)
                            else f"Mission failed: {str(getattr(result, 'error', ''))[:500]}"
                        ),
                        "mission_id": str(mission.id),
                        "entity_type": "mission",
                        "entity_id": str(mission.id),
                        "dashboard_url": f"/missions/{mission.id}",
                    },
                    db=db,
                )
            except Exception as _notify_exc:  # pragma: no cover - defensive
                logger.warning(
                    "trigger_service_notification_emission_failed mission_id=%s error=%s",
                    mission_id,
                    _notify_exc,
                )

            # Update log
            log = await db.get(TriggerLog, log_id)
            if log:
                log.status = "success" if getattr(result, "success", False) else "failure"
                log.duration_ms = duration_ms
                log.mission_run_id = mission_id
                if not getattr(result, "success", False):
                    log.error_message = str(getattr(result, "error", ""))[:1000]
            await db.commit()
            logger.info(
                "Trigger %s fired mission %s via UnifiedExecutor in %sms (success=%s)",
                trigger_id,
                mission_id,
                duration_ms,
                getattr(result, "success", None),
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            log = await db.get(TriggerLog, log_id)
            if log:
                log.status = "failure"
                log.error_message = str(e)[:1000]
                log.duration_ms = duration_ms
            await db.commit()
            logger.error("Trigger %s failed to fire mission %s: %s", trigger_id, mission_id, e)


# ── WEBHOOK SIGNATURE VERIFICATION ───────────────────────────────────────────


def verify_webhook_signature(body: bytes, secret: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature on webhook payload.

    Supports hex-encoded signature in X-Signature or X-Hub-Signature-256 headers.
    """
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    # Support both bare hex and "sha256=..." prefix formats
    sig = signature.strip()
    if sig.startswith("sha256="):
        sig = sig[7:]
    return hmac.compare_digest(expected, sig)


# ── CRON PROCESSING ───────────────────────────────────────────────────────────


async def process_cron_triggers(db: AsyncSession) -> int:
    """Find and fire all due cron triggers. Returns count of triggers fired."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(MissionTrigger).where(
            and_(
                MissionTrigger.trigger_type == "cron",
                MissionTrigger.status == "active",
                MissionTrigger.is_deleted == False,
                MissionTrigger.next_fire_at <= now,
            )
        )
    )
    triggers = list(result.scalars().all())

    fired = 0
    for trigger in triggers:
        try:
            await fire_trigger(db, trigger, payload={"source": "cron", "scheduled_at": now.isoformat()})
            fired += 1
        except Exception as e:
            logger.error("Failed to fire cron trigger %s: %s", trigger.id, e)

    if fired:
        await db.commit()
        logger.info("Cron tick: fired %s trigger(s)", fired)

    return fired


# ── HELPERS ───────────────────────────────────────────────────────────────────


def _compute_next_fire(cron_expression: str, timezone_str: str) -> datetime | None:
    """Compute the next fire time from a cron expression."""
    from typing import Any

    try:
        from zoneinfo import ZoneInfo

        tz: Any = ZoneInfo(timezone_str)
    except Exception:
        tz = UTC

    now = datetime.now(tz)
    cron = croniter(cron_expression, now)
    next_fire = cron.get_next(datetime)
    # Ensure UTC-aware
    if next_fire.tzinfo is None:
        next_fire = next_fire.replace(tzinfo=UTC)
    return next_fire
