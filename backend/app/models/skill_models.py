"""Skill model — Q3 dedicated skills table (C3 correction).

A minimal, purpose-built table for reviewer-authored *skills* (reusable
procedural knowledge, distinct from personal-memory *claims*). Skills are
NOT stored in ``MemoryEntry`` — ``MemoryEntry`` has no governance columns
(provenance / trust_tier / confidence / approval) and is a KV/episodic
store, not a structured skill registry. See
``.sisyphus/plans/Q1-Q6-IMPLEMENTATION-DECOMPOSITION.md`` §0 C3 and §5.

Design follows the project's conventions:
- ``workspace_id`` is NOT NULL on every row (workspace-isolation guardrail).
- Value-set columns are plain ``String`` (not Python enums), matching the
  ``PersonalMemoryClaim`` / ``Mission`` pattern; the ``ALL_*`` tuples are
  hardcoded (never derived from enum iteration) and used for in-process
  validation only.
- ``version int`` + ``provenance`` give us Q3-F rollback/audit lineage.

Runtime imports are NOT hidden under ``TYPE_CHECKING`` — the E23-B recency
fix taught us that column imports referenced at runtime must be top-level,
or mypy/SQLAlchemy metadata registration breaks.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin

# ── Value-set tuples (hardcoded; used for validation only) ────────────────

# Skill provenance — where the skill came from. Mirrors the memory
# source_type vocabulary so the governance gate (GOV-1.2) treats skills
# the same way it treats claims.
ALL_SKILL_PROVENANCE: tuple[str, ...] = (
    "agent",  # the reviewing agent distilled it from this mission
    "fetched",  # pulled from an external doc/site
    "tool_output",  # derived from a tool's output
    "third_party",  # supplied by another user/agent (HITL-forced)
    "user",  # authored directly by a human in the workspace
)

# Trust tiers. Lower tiers are routed to human approval (GOV-1.2).
ALL_SKILL_TRUST_TIERS: tuple[str, ...] = (
    "unverified",  # default for agent/third_party-derived skills
    "reviewed",  # a human approved it
    "curated",  # owner/blessed, highest trust
)

DEFAULT_SKILL_TRUST_TIER = "unverified"


class Skill(Base, TimestampMixin):
    """A reviewer-authored skill: reusable procedural knowledge.

    Distinct from ``MemoryEntry`` (KV/episodic) and ``PersonalMemoryClaim``
    (subject-predicate-object). A skill has a *name* (class-level, stable),
    a *body* (the procedure), and *frontmatter* (structured metadata:
    description, triggers, tags, etc.). Versioning is append-only-ish:
    each accepted PATCH bumps ``version`` and the prior body is retained in
    ``meta.history`` by the service (Q3-F) so we can roll back.
    """

    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    # Class-level, stable, unique per workspace. The PATCH>ADD>CREATE guard
    # keys off this (Q3-E): a new body for an existing name is a PATCH, not
    # a CREATE.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured metadata: description, triggers, tags, model hints, etc.
    frontmatter: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trust_tier: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DEFAULT_SKILL_TRUST_TIER,
    )
    # Monotonic. PATCH bumps it; CREATE starts at 1.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provenance: Mapped[str] = mapped_column(String(50), nullable=False)
    # Workspace isolation guardrail.
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # NULL = human-authored (highest trust), mirroring PersonalMemoryClaim.
    agent_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        # A skill name is unique *within* a workspace (class-level names).
        Index(
            "ix_skills_workspace_name",
            "workspace_id",
            "name",
            unique=True,
        ),
    )
