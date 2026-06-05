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
import uuid

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from app.models.mission_models import MissionLog, MissionStatus

if TYPE_CHECKING:

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
        """Write a single audit event to MissionLog.

        Args:
            action: snake_case action name (e.g. "mission.create", "mission.abort").
            actor_id: ID of the user performing the action.
            mission_id: Mission UUID.
            request_id: Optional X-Request-ID for tracing.
            old_status: Previous mission status (nil for creates).
            new_status: New mission status (nil for deletes).
            metadata: Arbitrary key-value payload.
            level: Log level (info, warning, error).
        """
        try:
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
            self._session.add(log_entry)
            # NOTE: no flush/commit here — the command handler's transaction
            # boundary commits or rolls back the entire batch atomically.
        except Exception:
            logger.warning(
                "audit_write_failed",
                action=action,
                actor_id=actor_id,
                mission_id=str(mission_id),
                exc_info=True,
            )

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
