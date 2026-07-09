"""MemoryDigestDelivery model (D30-60, T31 — daily digest).

Tracks every digest that has been delivered (or previewed) to a user.
A daily cron job (or the /memory/digest/preview endpoint) builds a
"Here's what I learned about you this week" digest from the user's
recent personal-memory claims, then writes a row here for audit +
dedup purposes.

Design notes (see plan §D30-60):

* ``workspace_id`` is NOT NULL on every row (workspace isolation
  guardrail, project-wide rule). ON DELETE CASCADE: deleting a
  workspace drops its deliveries.
* ``delivery_channel`` distinguishes the actual delivery target
  (``email``, ``in_app``, ``preview``). ``preview`` is for the
  /memory/digest/preview endpoint that builds the digest without
  sending it — the row is still persisted so analytics can see what
  users previewed.
* ``status`` follows a small state machine (delivered, failed,
  pending, previewed) — no enum iteration (sunder-name leak pitfall).
* ``claims_summary`` is a JSONB blob that stores pre-computed summary
  stats (top subjects, claim_type histogram, etc.) so the digest
  renderer doesn't have to recompute on every read.
* Composite indexes:
    - (user_id, workspace_id, sent_at) — fast user digest history
    - (user_id, workspace_id, delivery_channel) — fast filtered
      listing (e.g. "latest email digest")
    - (sent_at) — fast cleanup / retention sweeps
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin

# ── Value-set tuples for CHECK constraints ──────────────────────────────


# Hardcoded tuples — do NOT derive from enum iteration.
ALL_DELIVERY_CHANNELS: tuple[str, ...] = (
    "email",
    "in_app",
    "preview",
)
ALL_DELIVERY_STATUSES: tuple[str, ...] = (
    "pending",
    "delivered",
    "failed",
    "previewed",
)


# ── Model ────────────────────────────────────────────────────────────────


class MemoryDigestDelivery(Base, TimestampMixin):
    """A single daily-digest delivery (or preview) for a user.

    The atomic unit of the T31 digest surface. One row per delivery
    attempt — retries, previews, and successful sends each get their
    own row. The ``status`` field tracks the outcome.
    """

    __tablename__ = "memory_digest_deliveries"
    __table_args__ = (
        CheckConstraint(
            f"delivery_channel IN {ALL_DELIVERY_CHANNELS}",
            name="ck_memory_digest_delivery_channel_valid",
        ),
        CheckConstraint(
            f"status IN {ALL_DELIVERY_STATUSES}",
            name="ck_memory_digest_delivery_status_valid",
        ),
        # Composite indexes for the documented query patterns.
        Index(
            "ix_memory_digest_deliveries_user_ws_sent",
            "user_id",
            "workspace_id",
            "sent_at",
        ),
        Index(
            "ix_memory_digest_deliveries_user_ws_channel",
            "user_id",
            "workspace_id",
            "delivery_channel",
        ),
        Index("ix_memory_digest_deliveries_sent_at", "sent_at"),
    )

    # Primary key — UUID, auto-defaulted via uuid4.
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: uuid4(),
    )

    # Ownership + workspace isolation (workspace_id is NOT NULL per guardrail).
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # When the digest was queued (NOT when it was actually delivered —
    # that goes in delivered_at, which is NULL until the send
    # succeeds). For previewed digests, sent_at == delivered_at.
    sent_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Delivery channel — email, in-app, or preview.
    delivery_channel: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Status of this delivery attempt.
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # How many claims were in the digest. >= 0 (a digest of 0 claims
    # is valid: "nothing to share this week, see you next time").
    claims_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Pre-computed summary of the digest content (top subjects, type
    # histogram, etc.). NULL for "preview" rows that haven't been
    # finalised yet.
    claims_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Optional delivery target (email address for the email channel,
    # NULL for in_app / preview). Capped at 255 chars at the service
    # layer; the column is just a String with no DB-level CHECK.
    recipient: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # When the digest was actually delivered. NULL until status flips
    # to "delivered" (or "previewed", in which case delivered_at ==
    # sent_at).
    delivered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Free-text error message for failed deliveries. Capped at 2000
    # chars at the service layer.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
