"""Reusable auditing concern for program command handlers.

Every mutating program operation emits a structured ``structlog`` event
(action, actor_id, program_id, request_id, metadata, timestamp).  The
audit trail lives in the application log stream — no dedicated
``program_audit_log`` table is required for the T4 skeleton.

Failure policy: audit failures are logged and swallowed — they MUST
NOT silently break the business flow.

DI-friendly: command handlers receive an optional ``ProgramAudit`` via
constructor injection rather than a hard global.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class ProgramAudit:
    """Writes structured audit events via ``structlog``.

    Auditing is optional: command handlers that don't need it simply
    don't inject a ``ProgramAudit``.  When present, every mutation
    emits a log event.  Failures are logged and swallowed — auditing is
    never allowed to break the business operation.
    """

    def __init__(self, session: AsyncSession) -> None:
        # Session is unused for structlog-only audits, but the signature
        # mirrors ``AuditService`` so it can be swapped out later if a
        # dedicated table is added.
        self._session = session

    def record(
        self,
        *,
        action: str,
        actor_id: int,
        program_id: uuid.UUID | str,
        request_id: str | None = None,
        old_status: str | None = None,
        new_status: str | None = None,
        metadata: dict[str, Any] | None = None,
        level: str = "info",
    ) -> None:
        """Emit a single audit event to the structlog stream.

        Args:
            action: snake_case action name (e.g. ``"program.create"``).
            actor_id: ID of the user performing the action.
            program_id: Program UUID.
            request_id: Optional ``X-Request-ID`` for tracing.
            old_status: Previous program status (nil for creates).
            new_status: New program status (nil for deletes).
            metadata: Arbitrary key-value payload.
            level: Log level (info, warning, error).
        """
        try:
            payload: dict[str, Any] = {
                "action": action,
                "actor_id": actor_id,
                "actor": "user",
                "program_id": str(program_id),
                "timestamp": datetime.now(UTC).isoformat(),
            }
            if request_id:
                payload["request_id"] = request_id
            if old_status is not None:
                payload["old_status"] = old_status
            if new_status is not None:
                payload["new_status"] = new_status
            if metadata:
                payload["metadata"] = metadata

            message = f"audit: {action}"
            if old_status and new_status:
                message += f" ({old_status} → {new_status})"

            log_fn = getattr(logger, level, logger.info)
            log_fn(message, **payload)
        except Exception:
            # Audit MUST NOT break the business operation.
            logger.warning(
                "program_audit_write_failed",
                action=action,
                actor_id=actor_id,
                program_id=str(program_id),
                exc_info=True,
            )

    # ── Convenience helpers for common actions ────────────────────────────

    def program_created(
        self,
        program_id: uuid.UUID,
        actor_id: int,
        request_id: str | None = None,
        **meta: Any,
    ) -> None:
        self.record(
            action="program.create",
            actor_id=actor_id,
            program_id=program_id,
            request_id=request_id,
            new_status="active",
            metadata=meta or None,
        )

    def program_updated(
        self,
        program_id: uuid.UUID,
        actor_id: int,
        old_status: str,
        new_status: str | None,
        request_id: str | None = None,
        **meta: Any,
    ) -> None:
        self.record(
            action="program.update",
            actor_id=actor_id,
            program_id=program_id,
            request_id=request_id,
            old_status=old_status,
            new_status=new_status,
            metadata=meta or None,
        )

    def program_deleted(
        self,
        program_id: uuid.UUID,
        actor_id: int,
        old_status: str,
        request_id: str | None = None,
    ) -> None:
        self.record(
            action="program.delete",
            actor_id=actor_id,
            program_id=program_id,
            request_id=request_id,
            old_status=old_status,
            new_status=None,
            level="warning",
        )

    def program_fired(
        self,
        program_id: uuid.UUID,
        actor_id: int,
        trigger_type: str,
        request_id: str | None = None,
        **meta: Any,
    ) -> None:
        self.record(
            action="program.fire",
            actor_id=actor_id,
            program_id=program_id,
            request_id=request_id,
            metadata={"trigger_type": trigger_type, **(meta or {})},
        )

    def program_consolidated(
        self,
        program_id: uuid.UUID,
        actor_id: int,
        consolidated_runs: int,
        request_id: str | None = None,
        **meta: Any,
    ) -> None:
        self.record(
            action="program.consolidate",
            actor_id=actor_id,
            program_id=program_id,
            request_id=request_id,
            metadata={
                "consolidated_runs": consolidated_runs,
                **(meta or {}),
            },
        )
