"""Scaffold models — AutoMem Phase 2: Meta-LLM Review Loop.

Two tables:
- scaffold_proposals: proposals from the meta-LLM to improve agent prompts
- scaffold_versions: versioned agent prompts with is_active flag

The meta-LLM reviews episode traces and proposes prompt improvements.
Proposals go through validation → approval → apply. Only one version
is active per agent_id at a time. Rollback = flip is_active to a
previous version.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin

# ── Status constants ─────────────────────────────────────────────────


class ScaffoldProposalStatus:
    """Lifecycle states for scaffold proposals."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


ALL_SCAFFOLD_PROPOSAL_STATUSES = (
    ScaffoldProposalStatus.PENDING,
    ScaffoldProposalStatus.APPROVED,
    ScaffoldProposalStatus.REJECTED,
    ScaffoldProposalStatus.APPLIED,
)


# ── ORM Models ───────────────────────────────────────────────────────


class ScaffoldProposal(Base, TimestampMixin):
    """A proposal from the meta-LLM to improve an agent's scaffold.

    Created by the meta-review Celery task. Sits in pending state
    until an admin approves or rejects it. On approval, the proposed
    prompt is written to scaffold_versions and becomes active.
    """

    __tablename__ = "scaffold_proposals"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    agent_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    current_prompt_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hex of the current prompt when proposal was created",
    )
    proposed_prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    reasoning: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    changes_summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    expected_impact: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    validation_metrics: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="LLM-as-judge scores: confidence, soundness, risk_level",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ScaffoldProposalStatus.PENDING,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    applied_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("scaffold_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    trace_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of episode traces used for this review",
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Reason for rejection, set by admin on reject",
    )
    meta_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="llamacpp-qwen3.6-27b",
    )

    __table_args__ = (
        Index(
            "ix_scaffold_proposals_agent_status",
            "agent_id",
            "status",
        ),
        Index(
            "ix_scaffold_proposals_status_created",
            "status",
            "created_at",
        ),
    )


class ScaffoldVersion(Base, TimestampMixin):
    """A versioned agent prompt.

    Only one version is active per agent_id at a time.
    Rollback = set is_active=True on a previous version.
    """

    __tablename__ = "scaffold_versions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    agent_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    prompt_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    source_proposal_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("scaffold_proposals.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_version_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("scaffold_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "ix_scaffold_versions_agent_active",
            "agent_id",
            "is_active",
            postgresql_where=text("is_active = true"),
        ),
        Index(
            "ix_scaffold_versions_agent_version",
            "agent_id",
            "version",
            unique=True,
        ),
    )
