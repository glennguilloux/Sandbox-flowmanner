"""Human-in-the-loop interrupt primitives (H5.2).

Provides:
- ``HumanInterrupt`` dataclass (approval | clarification | escalation)
- Persistence model ``HumanInterruptRecord`` for the interrupt inbox
- ``HITLManager`` with raise/poll/resolve + event-bus adapter boundary
- Integration hook for mission executor ``approval_required_for`` checks

No RabbitMQ dependency — the event-bus signal is an adapter boundary
(a simple async callback list).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, select
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── SQLAlchemy model for interrupt inbox ───────────────────────────


class HumanInterruptRecord(Base, TimestampMixin):
    """Persistent row for every raised interrupt."""

    __tablename__ = "human_interrupts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    mission_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("missions.id"),
        nullable=False,
        index=True,
    )
    interrupt_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # approval | clarification | escalation
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    proposed_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
    )  # pending | approved | rejected | expired
    resolved_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# ── Dataclass (in-memory representation) ───────────────────────────


@dataclass
class HumanInterrupt:
    mission_id: str
    interrupt_type: str  # approval | clarification | escalation
    context: dict[str, Any] = field(default_factory=dict)
    proposed_action: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    deadline: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "interrupt_type": self.interrupt_type,
            "context": self.context,
            "proposed_action": self.proposed_action,
            "confidence": self.confidence,
            "deadline": self.deadline.isoformat() if self.deadline else None,
        }


# ── Manager ────────────────────────────────────────────────────────


class HITLManager:
    """Orchestrates interrupt lifecycle: raise → persist → signal → resolve.

    The event-bus adapter is a simple list of async callbacks.
    Replace with Redis pub/sub or WebSocket broadcast in production.
    """

    def __init__(self) -> None:
        self._listeners: list[Callable] = []

    def on_interrupt_raised(self, callback: Callable) -> None:
        """Register an async callback to be fired when an interrupt is raised.

        Callback signature: ``async def callback(signal_name: str, interrupt: HumanInterrupt)``
        """
        self._listeners.append(callback)

    async def raise_interrupt(
        self,
        db: AsyncSession,
        interrupt: HumanInterrupt,
    ) -> str:
        """Persist interrupt and fire all registered listeners.

        Returns the DB record ID.
        """
        record = HumanInterruptRecord(
            id=str(uuid4()),
            mission_id=interrupt.mission_id,
            interrupt_type=interrupt.interrupt_type,
            context=interrupt.context,
            proposed_action=interrupt.proposed_action,
            confidence=interrupt.confidence,
            deadline=interrupt.deadline,
            status="pending",
        )
        db.add(record)
        await db.commit()

        # Fire listeners (adapter boundary for WebSocket / event bus)
        for listener in self._listeners:
            try:
                await listener("HUMAN_INTERRUPT_RAISED", interrupt)
            except Exception as exc:
                logger.warning(
                    "HITL listener failed (non-fatal): %s",
                    exc,
                )

        logger.info(
            "Interrupt raised: mission=%s type=%s id=%s",
            interrupt.mission_id,
            interrupt.interrupt_type,
            record.id,
        )
        return record.id

    async def resolve_interrupt(
        self,
        db: AsyncSession,
        interrupt_id: str,
        resolution: str,  # approved | rejected
        resolved_by: str = "system",
    ) -> bool:
        """Resolve a pending interrupt by ID."""
        result = await db.execute(
            select(HumanInterruptRecord).where(
                HumanInterruptRecord.id == interrupt_id,
            ),
        )
        record = result.scalars().first()
        if record is None:
            return False
        if record.status != "pending":
            logger.debug("Interrupt %s already resolved: %s", interrupt_id, record.status)
            return False

        record.status = resolution
        record.resolved_by = resolved_by
        record.resolved_at = datetime.now(UTC)
        await db.commit()
        logger.info(
            "Interrupt %s resolved: %s by %s",
            interrupt_id,
            resolution,
            resolved_by,
        )
        return True

    async def list_pending(
        self,
        db: AsyncSession,
        mission_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all pending interrupts, optionally filtered by mission."""
        stmt = select(HumanInterruptRecord).where(
            HumanInterruptRecord.status == "pending",
        )
        if mission_id:
            stmt = stmt.where(HumanInterruptRecord.mission_id == mission_id)

        result = await db.execute(stmt)
        records = result.scalars().all()
        return [
            {
                "id": r.id,
                "mission_id": r.mission_id,
                "interrupt_type": r.interrupt_type,
                "context": r.context,
                "proposed_action": r.proposed_action,
                "confidence": r.confidence,
                "deadline": r.deadline.isoformat() if r.deadline else None,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

    @staticmethod
    def approval_required_for(
        action_type: str,
        confidence: float = 1.0,
        *,
        destructive_actions: set[str] | None = None,
    ) -> bool:
        """Determine if the given action requires human approval.

        Returns True if:
        - ``action_type`` starts with ``destructive_``
        - ``action_type`` is in the ``destructive_actions`` set
        - confidence is below 0.7
        """
        if confidence < 0.7:
            return True
        if action_type.startswith("destructive_"):
            return True
        return bool(destructive_actions and action_type in destructive_actions)


# ── Singleton ──────────────────────────────────────────────────────

_manager: HITLManager | None = None


def get_hitl_manager() -> HITLManager:
    global _manager
    if _manager is None:
        _manager = HITLManager()
    return _manager
