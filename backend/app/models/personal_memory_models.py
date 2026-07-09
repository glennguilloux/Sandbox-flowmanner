"""PersonalMemoryClaim model (D0-30, T18 — Personal Memory MVP).

A single durable, workspace-scoped claim about a user. Claims are the
atomic unit of personal memory — they store a (subject, predicate, object)
triple plus metadata about provenance, sensitivity, and TTL.

This module defines ONE table only: ``personal_memory_claims``. The other
tables of the personal memory MVP (entities, relations, sources,
user_actions) will arrive in T19+.

Design notes (see plan §D0-30):
- ``workspace_id`` is NOT NULL on every row (workspace isolation guardrail,
  project-wide rule). The DB enforces this; the application must scope all
  reads by workspace.
- Status / taxonomy columns are ``String(N)`` (not Python enums) to match
  the project's pattern (``Mission.status``, ``Episode.outcome``, etc.).
  The Python enums / hardcoded tuples are used for in-process validation
  only.
- All ``ALL_*`` tuples are HARDCODED (do NOT derive from enum iteration —
  ``str, Enum`` leaks ``_TRANSITIONS`` into iteration and corrupts the
  CHECK constraint SQL).
- Per-claim TTL: ``expires_at`` is nullable but is expected to be set by
  the writer; the personal-memory service rejects claims that would
  default to "never expire" (see plan §D0-30).
- Composite indexes:
    - (user_id, workspace_id, deleted_at) — fast active-scope lookup
    - (workspace_id, scope) — workspace-scoped recall by scope bucket
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
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
ALL_CLAIM_TYPES: tuple[str, ...] = (
    "fact",
    "preference",
    "observation",
    "sensitive",
    "constraint",
)
ALL_SCOPES: tuple[str, ...] = (
    "personal",
    "workspace",
    "program",
    "private",
)
ALL_SOURCE_TYPES: tuple[str, ...] = (
    "mission",
    "conversation",
    "user_explicit",
    "program_learning",
)
ALL_SENSITIVITIES: tuple[str, ...] = (
    "normal",
    "sensitive",
    "restricted",
)


# ── Model ─────────────────────────────────────────────────────────────────


class PersonalMemoryClaim(Base, TimestampMixin):
    """A single durable, workspace-scoped claim about a user.

    Stores a (subject, predicate, object) triple plus provenance, scope,
    sensitivity, and TTL. The atomic unit of personal memory.

    Workspace isolation: every row carries a non-null ``workspace_id`` and
    every read must be scoped to a workspace at the query layer.
    """

    __tablename__ = "personal_memory_claims"
    __table_args__ = (
        CheckConstraint(
            f"claim_type IN {ALL_CLAIM_TYPES}",
            name="ck_personal_memory_claim_claim_type_valid",
        ),
        CheckConstraint(
            f"scope IN {ALL_SCOPES}",
            name="ck_personal_memory_claim_scope_valid",
        ),
        CheckConstraint(
            f"source_type IN {ALL_SOURCE_TYPES}",
            name="ck_personal_memory_claim_source_type_valid",
        ),
        CheckConstraint(
            f"sensitivity IN {ALL_SENSITIVITIES}",
            name="ck_personal_memory_claim_sensitivity_valid",
        ),
        # Composite indexes for fast recall.
        Index(
            "ix_personal_memory_claims_user_ws_deleted",
            "user_id",
            "workspace_id",
            "deleted_at",
        ),
        Index(
            "ix_personal_memory_claims_workspace_scope",
            "workspace_id",
            "scope",
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
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Claim triple.
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    predicate: Mapped[str] = mapped_column(String(100), nullable=False)
    object: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Taxonomy columns (string, validated by CHECK constraints above).
    claim_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sensitivity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="normal",
    )

    # Numeric scoring + provenance fields.
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    source_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # TTL + soft delete (all nullable by design).
    last_used_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
