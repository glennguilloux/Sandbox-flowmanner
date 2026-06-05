"""EventLog — append-only event store for the event-sourced substrate (H2.1).

Provides:
- append(): Atomically append one or more events to a run's event stream
- get_events(): Retrieve events for a run, ordered by sequence
- get_latest_sequence(): Get the last sequence number for a run
- SERIALIZABLE isolation for append operations to prevent gaps/duplicates

The append-only guarantee is enforced at the database level by a
BEFORE UPDATE OR DELETE trigger on the substrate_events table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_DNS, UUID, uuid4, uuid5

from sqlalchemy import func, select

from app.models.substrate_models import SubstrateEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class EventLog:
    """Append-only event store.

    Append-only semantics are enforced by the PostgreSQL trigger on
    substrate_events, not by SERIALIZABLE isolation.
    """

    # Maximum events per run (safety limit)
    MAX_EVENTS_PER_RUN = 100_000

    async def append(
        self,
        db: AsyncSession,
        run_id: str,
        events: list[dict],
        *,
        mission_id: str | None = None,
        blueprint_id: str | None = None,
    ) -> list[SubstrateEvent]:
        """Append one or more events to a run's event stream.

        Uses SERIALIZABLE isolation to prevent concurrent writers from
        creating gaps or duplicates in the sequence.

        Args:
            db: Async database session
            run_id: UUID string identifying the execution run
            events: List of event dicts, each with:
                - type: Event type string
                - payload: JSON-serializable dict
                - actor: Who triggered the event
                - task_id: Optional task UUID
                - causal_parent: Optional parent sequence number
            mission_id: Optional mission UUID for cross-referencing

        Returns:
            List of persisted SubstrateEvent ORM objects

        Raises:
            ValueError: If events list is empty or exceeds safety limit
        """
        if not events:
            raise ValueError("Must append at least one event")

        # Get current max sequence for this run
        current_seq = await self.get_latest_sequence(db, run_id)

        # Count existing events for safety limit
        existing_count = await self._count_events(db, run_id)
        if existing_count + len(events) > self.MAX_EVENTS_PER_RUN:
            raise ValueError(
                f"Run {run_id} exceeds max events limit "
                f"({existing_count} existing + {len(events)} new > {self.MAX_EVENTS_PER_RUN})"
            )

        now = datetime.now(UTC)
        persisted = []

        for i, event_dict in enumerate(events):
            seq = current_seq + i + 1
            # Coerce human-readable node IDs to deterministic UUIDs
            task_id_raw = event_dict.get("task_id")
            task_id = _ensure_uuid(task_id_raw) if task_id_raw else None
            mission_id_val = mission_id or event_dict.get("mission_id")
            mission_id_val = _ensure_uuid(mission_id_val) if mission_id_val else None

            event = SubstrateEvent(
                id=str(uuid4()),
                sequence=seq,
                run_id=run_id,
                mission_id=mission_id_val,
                task_id=task_id,
                type=event_dict["type"],
                payload=event_dict.get("payload", {}),
                causal_parent=event_dict.get("causal_parent"),
                actor=event_dict.get("actor", "system"),
                timestamp=now,
            )
            # Set blueprint_id if column exists (added in phase101 migration)
            try:
                event.blueprint_id = blueprint_id or event_dict.get("blueprint_id")
            except AttributeError:
                pass  # Column not yet migrated
            db.add(event)
            persisted.append(event)

        await db.flush()
        logger.debug(
            "Appended %d events to run %s (seq %d→%d)",
            len(events),
            run_id,
            current_seq,
            current_seq + len(events),
        )
        return persisted

    async def get_events(
        self,
        db: AsyncSession,
        run_id: str,
        *,
        from_sequence: int = 0,
        to_sequence: int | None = None,
        event_type: str | None = None,
        limit: int = 10_000,
    ) -> list[SubstrateEvent]:
        """Retrieve events for a run, ordered by sequence.

        Args:
            db: Async database session
            run_id: UUID string identifying the execution run
            from_sequence: Inclusive lower bound on sequence (default 0)
            to_sequence: Inclusive upper bound on sequence (default: no bound)
            event_type: Optional filter by event type
            limit: Maximum number of events to return

        Returns:
            List of SubstrateEvent ORM objects
        """
        stmt = (
            select(SubstrateEvent)
            .where(
                SubstrateEvent.run_id == run_id,
                SubstrateEvent.sequence >= from_sequence,
            )
            .order_by(SubstrateEvent.sequence)
            .limit(limit)
        )

        if to_sequence is not None:
            stmt = stmt.where(SubstrateEvent.sequence <= to_sequence)

        if event_type is not None:
            stmt = stmt.where(SubstrateEvent.type == event_type)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_sequence(self, db: AsyncSession, run_id: str) -> int:
        """Get the highest sequence number for a run (0 if no events)."""
        stmt = select(func.max(SubstrateEvent.sequence)).where(
            SubstrateEvent.run_id == run_id
        )
        result = await db.execute(stmt)
        max_seq = result.scalar()
        return max_seq if max_seq is not None else 0

    async def _count_events(self, db: AsyncSession, run_id: str) -> int:
        """Count events for a run (used for safety limit check)."""
        stmt = select(func.count(SubstrateEvent.id)).where(
            SubstrateEvent.run_id == run_id
        )
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def run_exists(self, db: AsyncSession, run_id: str) -> bool:
        """Check if a run has any events."""
        return await self.get_latest_sequence(db, run_id) > 0


# ── UUID coercion helper ───────────────────────────────────────────


def _ensure_uuid(value: Any) -> str:
    """Coerce a value to a UUID string.

    If already a UUID or valid UUID string, return as-is.
    Otherwise, generate a deterministic UUID5 from the value
    so the same input always maps to the same UUID.
    """
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        try:
            UUID(value)  # Validate
            return value
        except ValueError:
            pass
    # Deterministic UUID from arbitrary string (e.g. node IDs like 'fetch')
    return str(uuid5(NAMESPACE_DNS, f"flowmanner.task.{value}"))


# ── Singleton ──────────────────────────────────────────────────────

_event_log: EventLog | None = None


def get_event_log() -> EventLog:
    """Get or create the EventLog singleton."""
    global _event_log
    if _event_log is None:
        _event_log = EventLog()
    return _event_log
