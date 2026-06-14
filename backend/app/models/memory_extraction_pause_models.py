"""MemoryExtractionPause model (D30-60, T30 — pause toggle).

A per-conversation toggle that suspends memory extraction (T20's
``PersonalMemoryExtractor`` will consult this table before extracting
any new claims from a conversation). Pauses are TTL-bound — never
permanent — and auto-expire on ``expires_at``.

Design notes (see plan §D30-60):

* ``workspace_id`` is NOT NULL on every row (workspace isolation
  guardrail, project-wide rule). ON DELETE CASCADE: deleting a
  workspace drops its pauses.
* ``conversation_id`` is a String(100) — duck-typed so it can hold a
  chat thread id, a mission id, or any future conversation-shaped
  reference. A future task may tighten this to a specific FK once
  the conversation model stabilises.
* ``expires_at`` is NOT NULL — pauses must always have a TTL. The
  extractor treats any pause with ``expires_at <= now()`` as inactive.
* No CHECK constraints on TTL bounds at the DB level (the service
  layer enforces a sane min/max — see
  ``MemoryExtractionPauseService.MIN_TTL_SECONDS`` /
  ``MAX_TTL_SECONDS``).
* Composite indexes:
    - (user_id, workspace_id, conversation_id, expires_at) — fast
      "is conversation X paused right now?" lookup
    - (expires_at) — fast cleanup-cron "delete all expired" sweep
"""
from __future__ import annotations

from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class MemoryExtractionPause(Base, TimestampMixin):
    """A TTL-bound pause of memory extraction for a specific conversation.

    The row is "active" while ``now() < expires_at``; once ``expires_at``
    passes the extractor ignores it. No soft-delete column — pauses
    are write-once-then-TTL'd; a fresh ``pause_conversation()`` call
    creates a new row, it doesn't resurrect an expired one.
    """

    __tablename__ = "memory_extraction_pauses"
    __table_args__ = (
        # Fast "is conversation X paused right now?" lookup.
        Index(
            "ix_memory_extraction_pauses_lookup",
            "user_id",
            "workspace_id",
            "conversation_id",
            "expires_at",
        ),
        # Fast cleanup-cron "delete all expired" sweep.
        Index("ix_memory_extraction_pauses_expires_at", "expires_at"),
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

    # The conversation being paused. Duck-typed String to support
    # multiple conversation models (chat threads, missions, etc.).
    conversation_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )

    # TTL — must always be set. The service layer enforces sane bounds
    # (MIN_TTL_SECONDS / MAX_TTL_SECONDS) at write time.
    expires_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Optional user-provided reason for the pause (e.g. "sensitive
    # topic" / "demo conversation"). Capped at 500 chars at the
    # service layer; CHECK constraint is intentionally not added at
    # the DB level (project rule: keep CHECK minimal).
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
