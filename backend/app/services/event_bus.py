"""EventBus — durable event bus for inbound integration events.

Persists every inbound webhook event as an ``ExternalEvent`` row *before*
dispatching to consumers (trigger matching, audit, analytics, etc.).

This is the "ignition" that ChatGPT described: the bridge between the
world of external services and FlowManner's execution substrate.

Usage::

    from app.services.event_bus import get_event_bus

    bus = get_event_bus()
    event = await bus.publish(
        db,
        source="github",
        event_type="pull_request.opened",
        payload={...},
        delivery_id="abc-123",
    )
    # event.status is either "processed" (consumers ran) or "failed"

Design:
- ``publish()`` persists the ExternalEvent, then dispatches to registered
  consumers.  The caller owns the transaction (no internal commit).
- Idempotency: if ``delivery_id`` matches an existing row for the same
  source, the existing event is returned without re-processing.
- Consumers are registered via ``add_consumer()``.  The default consumer
  is the trigger-matching event router.
- The append-only guarantee is enforced at the DB level (PostgreSQL trigger).
  The only permitted UPDATE is the status transition (pending → processed/failed).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy import select

from app.models.external_event_model import ExternalEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Consumer protocol ─────────────────────────────────────────────────


class EventBusConsumer(Protocol):
    """Protocol for event bus consumers.

    A consumer is any async callable that processes an ExternalEvent.
    It receives the persisted event and the DB session (caller-owned transaction).
    """

    async def __call__(
        self,
        db: AsyncSession,
        event: ExternalEvent,
    ) -> None: ...


# ── EventBus ──────────────────────────────────────────────────────────


class EventBus:
    """Durable event bus for inbound integration events.

    Publishes events to the ``external_events`` table, then dispatches
    to registered consumers.  Designed for future extensibility: add
    consumers for audit logging, analytics, AI learning loop, etc.
    """

    def __init__(self) -> None:
        self._consumers: list[EventBusConsumer] = []
        self._on_failure: list[EventBusConsumer] = []

    def add_consumer(self, consumer: EventBusConsumer) -> None:
        """Register a consumer to receive all published events."""
        self._consumers.append(consumer)
        logger.info(
            "event_bus: registered consumer %s", consumer.__name__ if hasattr(consumer, "__name__") else consumer
        )

    def add_failure_handler(self, handler: EventBusConsumer) -> None:
        """Register a handler that runs ONLY when event processing fails.

        Called after all consumers have run and the event status has been
        set to "failed".  Useful for real-time alerting (Slack, PagerDuty).
        Failure handlers must not raise — exceptions are logged and swallowed.
        """
        self._on_failure.append(handler)
        logger.info(
            "event_bus: registered failure handler %s", handler.__name__ if hasattr(handler, "__name__") else handler
        )

    async def publish(
        self,
        db: AsyncSession,
        *,
        source: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        raw_body: dict[str, Any] | None = None,
        delivery_id: str | None = None,
        user_id: int | None = None,
    ) -> ExternalEvent:
        """Publish an inbound event and dispatch to consumers.

        Args:
            db: Database session (caller owns the transaction).
            source: Integration source slug (e.g. "github", "stripe").
            event_type: Normalized event type (e.g. "pull_request.opened").
            payload: Structured event data.
            raw_body: Raw webhook body for debugging.
            delivery_id: Idempotency key (e.g. Stripe event ID, GitHub delivery GUID).
            user_id: User ID if known from the webhook context.

        Returns:
            The persisted ExternalEvent.  If a duplicate ``delivery_id``
            was detected, returns the existing event without re-processing.
        """
        # ── Idempotency check ──────────────────────────────────────
        if delivery_id:
            existing = await self._find_existing(db, source, delivery_id)
            if existing is not None:
                logger.info(
                    "event_bus: duplicate delivery %s/%s — returning existing event %s",
                    source,
                    delivery_id,
                    existing.id,
                )
                return existing

        # ── Persist ─────────────────────────────────────────────────
        event = ExternalEvent(
            source=source,
            event_type=event_type,
            delivery_id=delivery_id,
            payload=payload,
            raw_body=raw_body,
            user_id=user_id,
            status="pending",
            received_at=datetime.now(UTC),
        )
        db.add(event)
        await db.flush()  # Assign ID, make visible in this transaction

        logger.info(
            "event_bus: persisted event %s (%s.%s, delivery=%s)",
            event.id,
            source,
            event_type,
            delivery_id or "none",
        )

        # ── Dispatch to consumers ──────────────────────────────────
        triggers_fired = 0
        error_messages: list[str] = []

        for consumer in self._consumers:
            try:
                await consumer(db, event)
                # If the consumer is the trigger router, it returns int via
                # a side-channel.  We count fires by inspecting the event
                # after all consumers run.  For now, we just log.
            except Exception as exc:
                msg = f"{consumer.__name__ if hasattr(consumer, '__name__') else consumer}: {exc}"
                error_messages.append(msg)
                logger.warning(
                    "event_bus: consumer failed for event %s: %s",
                    event.id,
                    msg,
                    exc_info=True,
                )

        # ── Update status ───────────────────────────────────────────
        now = datetime.now(UTC)
        if error_messages and not self._consumers:
            # No consumers registered — shouldn't happen, but handle gracefully
            event.status = "processed"
        elif error_messages:
            event.status = "failed"
            event.error_message = "; ".join(error_messages)
        else:
            event.status = "processed"

        event.processed_at = now
        # Note: we do NOT commit — the caller owns the transaction.

        # ── Post-processing: failure alerts ────────────────────────
        if event.status == "failed" and self._on_failure:
            for handler in self._on_failure:
                try:
                    await handler(db, event)
                except Exception:
                    logger.warning(
                        "event_bus: failure handler %s raised (event %s)",
                        handler.__name__ if hasattr(handler, "__name__") else handler,
                        event.id,
                        exc_info=True,
                    )

        return event

    async def replay(
        self,
        db: AsyncSession,
        event_id: str,
    ) -> ExternalEvent | None:
        """Replay a previously failed or pending event.

        Resets the event status to ``pending`` and re-dispatches to consumers.
        Useful for manual retry or automated recovery.
        """
        result = await db.execute(select(ExternalEvent).where(ExternalEvent.id == event_id))
        event = result.scalar_one_or_none()
        if event is None:
            return None

        event.status = "pending"
        event.error_message = None
        event.triggers_fired = 0
        event.processed_at = None
        await db.flush()

        # Re-dispatch
        error_messages: list[str] = []
        for consumer in self._consumers:
            try:
                await consumer(db, event)
            except Exception as exc:
                msg = f"{consumer.__name__ if hasattr(consumer, '__name__') else consumer}: {exc}"
                error_messages.append(msg)
                logger.warning(
                    "event_bus: replay consumer failed for event %s: %s",
                    event.id,
                    msg,
                    exc_info=True,
                )

        now = datetime.now(UTC)
        if error_messages:
            event.status = "failed"
            event.error_message = "; ".join(error_messages)
        else:
            event.status = "processed"

        event.processed_at = now
        return event

    @staticmethod
    async def _find_existing(
        db: AsyncSession,
        source: str,
        delivery_id: str,
    ) -> ExternalEvent | None:
        """Check for an existing event with the same source + delivery_id."""
        result = await db.execute(
            select(ExternalEvent).where(
                ExternalEvent.source == source,
                ExternalEvent.delivery_id == delivery_id,
            )
        )
        return result.scalar_one_or_none()


# ── Singleton ──────────────────────────────────────────────────────────

_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get or create the EventBus singleton.

    On first call, registers the trigger-matching consumer (event_router).
    Additional consumers can be registered via ``add_consumer()``.
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
        # Register the default consumer: trigger matching via event_router
        _register_default_consumers(_event_bus)
    return _event_bus


def reset_event_bus() -> None:
    """Reset the EventBus singleton (for testing)."""
    global _event_bus
    _event_bus = None


def _register_default_consumers(bus: EventBus) -> None:
    """Register the default set of consumers and failure handlers."""
    from app.services.event_bus_consumers import (
        audit_log_consumer,
        failure_alert_consumer,
        trigger_matching_consumer,
    )

    bus.add_consumer(trigger_matching_consumer)
    bus.add_consumer(audit_log_consumer)
    bus.add_failure_handler(failure_alert_consumer)
