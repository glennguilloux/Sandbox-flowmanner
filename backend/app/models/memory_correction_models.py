"""MemoryCorrectionEvent model (D30-60, T29 — privacy-compliance audit trail).

A ``MemoryCorrectionEvent`` is one row per view/edit/delete/forget/inspect
action a user (or the system) takes on a personal-memory claim. The table
is the durable record required by the release gate "no privacy incidents"
— every interaction with a user's personal memory must be auditable so
we can answer "who saw this claim, when, from where, and why?".

Design notes (see plan §D30-60 / release gate):
- ``workspace_id`` is NOT NULL on every row (workspace isolation guardrail,
  project-wide rule). ON DELETE CASCADE: deleting a workspace drops its
  audit rows along with its claims.
- ``claim_id`` is NULLABLE and ON DELETE SET NULL: the audit row must
  survive a hard-delete of the claim (privacy: a "forget" event still
  proves the user exercised the right to be forgotten, even if the
  claim itself is gone).
- ``event_type`` and ``actor`` are ``String(N)`` (not Python enums) to
  match the project pattern (``Mission.status``,
  ``PersonalMemoryClaim.claim_type``, ``Critique.critic_kind``). The
  Python tuples ``ALL_EVENT_TYPES`` / ``ALL_ACTORS`` are used for
  in-process validation AND to build the CHECK constraints.
- All ``ALL_*`` tuples are HARDCODED (do NOT derive from enum iteration
  — ``str, Enum`` leaks ``_TRANSITIONS`` into iteration and corrupts the
  CHECK constraint SQL).
- ``details`` is JSONB — extra context (old_value, new_value, reason,
  ip_address, user_agent, etc.) that varies per event type.
- Composite indexes:
    - (user_id, workspace_id, created_at) — fast user audit listing
    - (claim_id) — fast per-claim provenance query
    - (user_id, workspace_id, event_type) — fast filtered listing
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


# ── Value-set tuples for CHECK constraints ────────────────────────────────

# Hardcoded tuples — do NOT derive from enum iteration.
ALL_EVENT_TYPES: tuple[str, ...] = (
    "view",
    "edit",
    "delete",
    "forget",
    "create",
    "inspect",
    "export",
    "pause",
    "resume",
)
ALL_ACTORS: tuple[str, ...] = (
    "user",
    "system",
    "admin",
)


# ── Model ─────────────────────────────────────────────────────────────────


class MemoryCorrectionEvent(Base, TimestampMixin):
    """A single auditable action on a personal-memory claim.

    Records (user_id, workspace_id, claim_id?, event_type, actor,
    source?, details?) plus the auto-managed created_at / updated_at
    timestamps from ``TimestampMixin``.

    Workspace isolation: every row carries a non-null ``workspace_id``
    and every read must be scoped to a workspace at the query layer.

    Privacy: ``claim_id`` is nullable + ON DELETE SET NULL so the audit
    row survives a hard-delete of the claim. A "forget" event therefore
    serves as durable evidence that the user exercised the right to be
    forgotten, even after the claim is gone.
    """

    __tablename__ = "memory_correction_events"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN {ALL_EVENT_TYPES}",
            name="ck_memory_correction_event_event_type_valid",
        ),
        CheckConstraint(
            f"actor IN {ALL_ACTORS}",
            name="ck_memory_correction_event_actor_valid",
        ),
        # Composite indexes for the documented recall patterns.
        # (user_id, workspace_id, created_at) — fast user audit listing.
        Index(
            "ix_memory_correction_events_user_ws_created",
            "user_id",
            "workspace_id",
            "created_at",
        ),
        # (claim_id) — fast per-claim provenance query.
        Index(
            "ix_memory_correction_events_claim_id",
            "claim_id",
        ),
        # (user_id, workspace_id, event_type) — fast filtered listing.
        Index(
            "ix_memory_correction_events_user_ws_event_type",
            "user_id",
            "workspace_id",
            "event_type",
        ),
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
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Claim anchor — NULLABLE and ON DELETE SET NULL: the audit row must
    # survive a hard-delete of the claim. See the class docstring.
    claim_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personal_memory_claims.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Action taxonomy (string, validated by CHECK constraints above).
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="user",
    )

    # Provenance hint + arbitrary extra context (old/new value, reason,
    # ip_address, user_agent, etc.). Both nullable: the wire-up may
    # simply not have a source label, and some events carry no details.
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
