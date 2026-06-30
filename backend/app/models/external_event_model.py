"""ExternalEvent model — durable, append-only event bus for inbound integration events.

Every webhook delivery from an external service (GitHub, Stripe, Sentry, Slack, etc.)
is persisted as an ``ExternalEvent`` *before* any side-effects (trigger matching,
agent dispatch, audit logging) occur.  This gives FlowManner:

- **Durability** — events survive process crashes; replay is always possible.
- **Idempotency** — duplicate webhook deliveries are detected via ``delivery_id``
  and silently ignored (the existing row is returned).
- **Observability** — a single query shows every inbound event, its source,
  processing status, and any error.
- **Replay** — re-process an event by resetting its status to ``pending``.
- **Extensibility** — future consumers (analytics, AI learning loop, audit log)
  can subscribe to the same durable stream.

The append-only guarantee is enforced by a PostgreSQL ``BEFORE UPDATE OR DELETE``
trigger (see migration ``20260630_external_events``).  The *only* permitted
UPDATE is the status transition (``pending`` → ``processed`` / ``failed``),
which is exempted from the trigger.

Design follows the ``SubstrateEvent`` / ``EventLog`` pattern already established
in the execution substrate (H2.1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class ExternalEvent(Base, TimestampMixin):
    """Durable, append-only record of an inbound integration event.

    One row per webhook delivery.  ``delivery_id`` provides idempotency:
    if a webhook is retried (e.g. Stripe's automatic retries), the duplicate
    is detected and the existing row is returned instead of creating a new one.
    """

    __tablename__ = "external_events"
    __table_args__ = (
        Index(
            "ix_external_events_delivery_id",
            "source",
            "delivery_id",
            unique=True,
        ),
        Index("ix_external_events_status", "status"),
        Index("ix_external_events_source_type", "source", "event_type"),
        Index("ix_external_events_received_at", "received_at"),
        Index("ix_external_events_user_id", "user_id"),
    )

    # ── Identity ────────────────────────────────────────────────────

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: uuid4(),
    )

    # ── Source ──────────────────────────────────────────────────────

    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Integration slug, e.g. 'github', 'stripe', 'sentry'",
    )
    event_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Normalized event type, e.g. 'pull_request.opened', 'charge.failed'",
    )
    delivery_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Webhook delivery ID for idempotency (e.g. Stripe event ID, GitHub delivery GUID)",
    )

    # ── Payload ─────────────────────────────────────────────────────

    payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Structured, source-normalized event data",
    )
    raw_body: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Raw webhook request body (for debugging / replay)",
    )

    # ── Routing context ─────────────────────────────────────────────

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="User ID if known from the webhook context",
    )

    # ── Processing status ───────────────────────────────────────────

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="'pending' | 'processed' | 'failed'",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error details if processing failed",
    )
    triggers_fired: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Number of triggers that were fired for this event",
    )

    # ── Timestamps ──────────────────────────────────────────────────

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When the webhook was received",
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When processing completed (success or failure)",
    )
