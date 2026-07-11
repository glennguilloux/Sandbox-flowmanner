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

# ── Source priority (Epic 2.3 E23-A) ──────────────────────────────────────
#
# Precedence map used by the lexicographic ranking comparator (E23-B) and by
# the conflict-resolution policy. Encodes the provenance authority of each
# ``source_type``: a human-authored, deliberate fact outranks a
# human-stated preference which outranks a reviewer/background inference.
# Higher int = higher authority. ``user_explicit`` (a user typing a fact
# directly) is the strongest signal; ``program_learning`` (the reviewer /
# background path) is the weakest because it is gated by human approval and
# must never silently override a human-stated claim.
#
# Stored denormalized on the claim as ``source_priority`` (int) so recall can
# ORDER BY it at the SQL layer (Q1/Q2/Q5 depend on SQL-level ordering). The
# migration seeds it from ``source_type``; writes keep it in sync via
# ``SOURCE_PRIORITY``. This is the single source of truth for the mapping.
SOURCE_PRIORITY: dict[str, int] = {
    "user_explicit": 4,
    "conversation": 3,
    "mission": 2,
    "program_learning": 1,
}
# Sentinel for any unknown / future source_type not in the map above.
# Defaults the claim to the lowest authority rather than crashing ranking.
SOURCE_PRIORITY_DEFAULT: int = 0

# ── Recency half-life bands (Epic 2.3 E23-B) ──────────────────────────────
#
# Recency of write is the second axis of the lexicographic comparator. To keep
# ranking *deterministic and cross-machine reproducible*, tiny absolute time
# deltas must NOT flip the ordering between two claims — a 3-second difference
# in ``created_at`` should not move a claim above another. We bucket
# ``created_at`` into half-life bands (in days): newer = higher band = ranks
# first. Bands are contiguous and deterministic. ``RECENCY_BANDS_DAYS`` is the
# single source of truth for band boundaries (see Q1-Q6 decomposition §9.4).
RECENCY_BANDS_DAYS: tuple[float, ...] = (1.0, 7.0, 30.0, 90.0)
# band 0 = >90d (oldest), band 4 = <1d (newest). Higher band number ranks first.


def recency_half_life_band(created_at: object) -> int:
    """Return the recency half-life band [0..len(RECENCY_BANDS_DAYS)] for a
    claim's ``created_at``.

    Higher band = more recent = ranks first. Pure + deterministic (no
    ``now()`` dependency) so the reported band is stable regardless of when
    the comparator runs, which is what makes cross-machine replay
    reproducible. ``None`` (no timestamp) maps to the oldest band (0).
    """
    if created_at is None:
        return 0
    try:
        from datetime import UTC, datetime

        if isinstance(created_at, datetime):
            now = datetime.now(UTC)
            # Naive timestamp: assume UTC to keep behaviour deterministic.
            c = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at
            age_days = (now - c).total_seconds() / 86400.0
            if age_days < 0:
                # Future-dated claim: treat as newest (< 1d band).
                return len(RECENCY_BANDS_DAYS)
            for i, threshold in enumerate(RECENCY_BANDS_DAYS):
                if age_days < threshold:
                    return len(RECENCY_BANDS_DAYS) - i
            return 0
    except Exception:  # pragma: no cover - defensive: unknown type never ranks high
        return 0
    return 0


def source_priority_for(source_type: str | None) -> int:
    """Resolve the integer source priority for a ``source_type`` string."""
    if source_type is None:
        return SOURCE_PRIORITY_DEFAULT
    return SOURCE_PRIORITY.get(source_type, SOURCE_PRIORITY_DEFAULT)


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

    # Epic 2.3 E23-A — denormalized source priority (int) derived from
    # ``source_type`` via ``SOURCE_PRIORITY``. Stored (not derived at read
    # time) so recall() can ORDER BY it at the SQL layer, which Q1/Q2/Q5
    # ranking depend on. Seeded by the E23-A migration; kept in sync on
    # every write. NOT NULL with a server default so existing rows are
    # populated by the migration and the column is consistent thereafter.
    source_priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=source_priority_for,
        server_default="0",
        index=True,
    )

    # Epic 2.3 E23-D — provenance of the *authoring agent* for a claim.
    # NULL = human-authored (highest trust), mirroring skill_models.agent_id.
    # Enables Q5 multi-agent memory sharing: an agent can read claims it
    # authored and human-authored (NULL) claims, but not another agent's
    # private inferences unless explicitly shared. Read-only column add —
    # no behavior change; existing rows are NULL (backfilled as NULL = the
    # strongest trust signal). Indexed for per-agent recall scans.
    agent_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
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

    # Denormalized governance metadata (JSONB). Carries the retroactive
    # poison-scan verdict (``meta["poison_scan"]``) plus the
    # ``retro_sweep_flagged`` idempotency marker written by
    # ``retroactive_memory_sweep``. Null until a sweep flags the row.
    # Added in t_9bb4df81 — persisted the FULL severity/provenance verdict
    # that the sweep previously dropped (it only logged it).
    meta: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
