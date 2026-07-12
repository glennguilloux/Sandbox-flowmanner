"""Reusable auditing concern for mission command handlers.

Every mutating mission operation writes a structured audit event (action,
actor_id, mission_id, old/new status when relevant, request_id, metadata,
timestamp) via the existing MissionLog model.

Failure policy: audit failures are logged and swallowed — they MUST NOT
silently break the business flow.

DI-friendly: command handlers receive an optional AuditService via
constructor injection rather than a hard global.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from app.models.mission_models import MissionLog, MissionStatus

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class AuditService:
    """Writes structured audit events to MissionLog.

    Auditing is optional: command handlers that don't need it simply don't
    inject an AuditService.  When present, every mutation writes an audit
    event.  Failures are logged and swallowed — auditing is never allowed to
    break the business operation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def record(
        self,
        *,
        action: str,
        actor_id: int,
        mission_id: uuid.UUID | str,
        request_id: str | None = None,
        old_status: str | None = None,
        new_status: str | None = None,
        metadata: dict[str, Any] | None = None,
        level: str = "info",
    ) -> None:
        """Write a single audit event to MissionLog in the HANDLER session.

        NOTE: this method shares ``self._session`` with the command handler.
        If the handler's transaction ROLLS BACK (e.g. on a
        ``PermanentMissionError``), the audit row written here is rolled
        back WITH it — exactly when forensics are needed (FM-2).  For
        forensic-critical audit that MUST survive rollback, use
        :meth:`record_async` instead.
        """
        try:
            self._record_into(
                self._session, action, actor_id, mission_id, request_id, old_status, new_status, metadata, level
            )
        except Exception:
            logger.warning(
                "audit_write_failed",
                action=action,
                actor_id=actor_id,
                mission_id=str(mission_id),
                exc_info=True,
            )

    async def record_async(
        self,
        *,
        action: str,
        actor_id: int,
        mission_id: uuid.UUID | str,
        request_id: str | None = None,
        old_status: str | None = None,
        new_status: str | None = None,
        metadata: dict[str, Any] | None = None,
        level: str = "info",
    ) -> None:
        """Forensic-critical audit in its OWN autonomous transaction (GC4).

        Opens a fresh :func:`fresh_session` and commits independently, so the
        audit row SURVIVES a rollback of the calling handler's transaction
        (FM-2). ``MissionLog.mission_id`` is a SOFT reference (no FK), so
        the write never depends on the mission row's isolation. Any failure is
        swallowed and out-of-band-alerted, never re-raised.
        """
        from app.database import fresh_session

        try:
            async with fresh_session() as s:
                self._record_into(
                    s,
                    action,
                    actor_id,
                    mission_id,
                    request_id,
                    old_status,
                    new_status,
                    metadata,
                    level,
                )
        except Exception as exc:
            # Out-of-band alert: the audit trace is the forensic record;
            # its loss must be visible to operators, not silent.
            logger.error(
                "audit_write_failed_async",
                action=action,
                actor_id=actor_id,
                mission_id=str(mission_id),
                exc_info=exc,
            )
            self._alert_audit_failure(action, actor_id, mission_id, exc)

    @staticmethod
    def _alert_audit_failure(action, actor_id, mission_id, exc) -> None:
        """Out-of-band alert for an audit-write failure.

        Kept as a separate hook so operators can wire a pager/Slack without
        touching the write path. Failures here are themselves swallowed.
        """
        try:
            # Hook point: send_audit_failure_alert(action, actor_id, mission_id)
            pass
        except Exception:
            logger.debug("audit_failure_alert_hook_errored", exc_info=True)

    @staticmethod
    def _record_into(
        session,
        action: str,
        actor_id: int,
        mission_id: uuid.UUID | str,
        request_id,
        old_status,
        new_status,
        metadata,
        level: str,
    ) -> None:
        data: dict[str, Any] = {
            "action": action,
            "actor_id": actor_id,
            "actor": "user",
        }
        if request_id:
            data["request_id"] = request_id
        if old_status is not None:
            data["old_status"] = old_status
        if new_status is not None:
            data["new_status"] = new_status
        if metadata:
            data["metadata"] = metadata

        message = f"audit: {action}"
        if old_status and new_status:
            message += f" ({old_status} → {new_status})"

        log_entry = MissionLog(
            mission_id=str(mission_id),
            level=level,
            message=message,
            data=data,
            timestamp=datetime.now(UTC),
        )
        session.add(log_entry)

    # ── Convenience helpers for common actions ────────────────────────────

    def mission_created(
        self,
        mission_id: uuid.UUID,
        actor_id: int,
        request_id: str | None = None,
        **meta: Any,
    ) -> None:
        self.record(
            action="mission.create",
            actor_id=actor_id,
            mission_id=mission_id,
            request_id=request_id,
            new_status=MissionStatus.PENDING.value,
            metadata=meta or None,
        )

    def mission_updated(
        self,
        mission_id: uuid.UUID,
        actor_id: int,
        old_status: str,
        new_status: str | None,
        request_id: str | None = None,
        **meta: Any,
    ) -> None:
        self.record(
            action="mission.update",
            actor_id=actor_id,
            mission_id=mission_id,
            request_id=request_id,
            old_status=old_status,
            new_status=new_status,
            metadata=meta or None,
        )

    def mission_deleted(
        self,
        mission_id: uuid.UUID,
        actor_id: int,
        old_status: str,
        request_id: str | None = None,
    ) -> None:
        self.record(
            action="mission.delete",
            actor_id=actor_id,
            mission_id=mission_id,
            request_id=request_id,
            old_status=old_status,
            new_status=None,
            level="warning",
        )

    def mission_executed(
        self,
        mission_id: uuid.UUID,
        actor_id: int,
        old_status: str,
        new_status: str,
        request_id: str | None = None,
        **meta: Any,
    ) -> None:
        self.record(
            action="mission.execute",
            actor_id=actor_id,
            mission_id=mission_id,
            request_id=request_id,
            old_status=old_status,
            new_status=new_status,
            metadata=meta or None,
        )

    def mission_aborted(
        self,
        mission_id: uuid.UUID,
        actor_id: int,
        old_status: str,
        abort_reason: str,
        request_id: str | None = None,
    ) -> None:
        self.record(
            action="mission.abort",
            actor_id=actor_id,
            mission_id=mission_id,
            request_id=request_id,
            old_status=old_status,
            new_status=MissionStatus.ABORTED.value,
            level="warning",
            metadata={"abort_reason": abort_reason},
        )

    def mission_paused(
        self,
        mission_id: uuid.UUID,
        actor_id: int,
        old_status: str,
        request_id: str | None = None,
    ) -> None:
        self.record(
            action="mission.pause",
            actor_id=actor_id,
            mission_id=mission_id,
            request_id=request_id,
            old_status=old_status,
            new_status=MissionStatus.PAUSED.value,
        )

    def mission_resumed(
        self,
        mission_id: uuid.UUID,
        actor_id: int,
        old_status: str,
        request_id: str | None = None,
    ) -> None:
        self.record(
            action="mission.resume",
            actor_id=actor_id,
            mission_id=mission_id,
            request_id=request_id,
            old_status=old_status,
            new_status=MissionStatus.QUEUED.value,
        )

    def mission_retried(
        self,
        mission_id: uuid.UUID,
        actor_id: int,
        old_status: str,
        request_id: str | None = None,
    ) -> None:
        self.record(
            action="mission.retry",
            actor_id=actor_id,
            mission_id=mission_id,
            request_id=request_id,
            old_status=old_status,
            new_status=MissionStatus.PENDING.value,
        )
