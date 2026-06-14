"""Critique model (D30-60, T24 — Critic Agent + Memory Correction UX).

A ``Critique`` is one row per critic run — the durable record of a single
adversarial / red-team / plan-improvement pass over a mission. Future tasks
(T25–T28) build the service layer and the surface-UI on top of this table.

Design notes (see plan §D30-60):
- ``workspace_id`` is NOT NULL on every row (workspace isolation guardrail,
  project-wide rule). ON DELETE CASCADE: deleting a workspace drops its
  critiques.
- ``critic_kind`` is ``String(30)`` (not Python enum) to match the project's
  pattern (``Mission.status``, ``PersonalMemoryClaim.claim_type``, etc.).
  The Python ``ALL_CRITIC_KINDS`` tuple is used for in-process validation
  AND to build the CHECK constraint.
- All ``ALL_*`` tuples are HARDCODED (do NOT derive from enum iteration —
  ``str, Enum`` leaks ``_TRANSITIONS`` into iteration and corrupts the
  CHECK constraint SQL).
- ``score_overall`` is nullable but bounded 0.0-1.0 by a CHECK constraint
  (the writer is expected to set it on a complete run; partial runs may
  leave it NULL).
- JSONB columns ``misses``, ``risks``, ``improvements``, ``alternatives``
  default to ``[]`` so consumers can read them unconditionally.
- ``raw_response`` and ``model_id`` are audit/replay fields: they let
  us re-derive a critique from the LLM response without a second model
  call.
- Composite indexes:
    - (user_id, workspace_id, created_at) — fast active-scope lookup
    - (mission_id) — fast mission-scoped recall
    - (program_id) — fast program-scoped recall
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
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


# ── Value-set tuples for CHECK constraints ────────────────────────────────

# Hardcoded tuples — do NOT derive from enum iteration.
ALL_CRITIC_KINDS: tuple[str, ...] = (
    "red_team",
    "critic",
    "improvement_generator",
)


# ── Model ─────────────────────────────────────────────────────────────────


class Critique(Base, TimestampMixin):
    """A single critic run against a mission (or program).

    Stores the critic's verdict: scores, summary, missed items, risks,
    improvement suggestions, alternative plan outlines, and an optional
    raw LLM response for audit/replay. The atomic unit of the D30-60
    critic stack.

    Workspace isolation: every row carries a non-null ``workspace_id`` and
    every read must be scoped to a workspace at the query layer.
    """

    __tablename__ = "critiques"
    __table_args__ = (
        CheckConstraint(
            f"critic_kind IN {ALL_CRITIC_KINDS}",
            name="ck_critique_critic_kind_valid",
        ),
        # score_overall bounded 0.0-1.0 when set. The other score_* columns
        # are NOT constrained at the DB level (app-level guards are
        # sufficient and the project rule is to keep CHECK constraints
        # minimal).
        CheckConstraint(
            "score_overall IS NULL OR (score_overall >= 0.0 AND score_overall <= 1.0)",
            name="ck_critique_score_overall_range",
        ),
        # Composite indexes for the documented recall patterns.
        # (user_id, workspace_id, created_at) — fast active-scope lookup.
        # Note: single-column indexes on mission_id and program_id are
        # auto-created by ``index=True`` on the mapped_column below
        # (named ``ix_critiques_mission_id`` / ``ix_critiques_program_id``
        # by SQLAlchemy's default). They are NOT re-declared here to
        # avoid duplicate-index errors at the snapshot validation gate
        # (the project pattern: rely on the column-level ``index=True``
        # for single-column indexes, use ``__table_args__`` for
        # composite or named indexes).
        Index(
            "ix_critiques_user_ws_created",
            "user_id",
            "workspace_id",
            "created_at",
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

    # Anchors — every critique is tied to a mission; program_id is optional
    # (a critic run can target a mission outside any program).
    mission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    program_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mission_programs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Critic taxonomy (string, validated by CHECK constraint above).
    critic_kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    # Scores (nullable; bounded 0.0-1.0 for score_overall only at the DB level).
    score_overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_alignment: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_safety: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_completeness: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Verdict text + structured findings.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    misses: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )  # list[str]
    risks: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )  # list[str]
    improvements: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )  # list[dict]
    alternatives: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )  # list[dict]
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # LLM provenance / cost telemetry.
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
