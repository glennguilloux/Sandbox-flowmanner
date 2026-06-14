"""add personal_memory_claims

D0-30, T18 — Personal Memory MVP: durable, workspace-scoped claims about
a user. This is the first of the personal-memory tables; entities,
relations, sources, and user_actions arrive in T19+.

Table added:
- ``personal_memory_claims`` — atomic (subject, predicate, object) claim
  plus provenance, scope, sensitivity, and TTL.
  workspace_id is NOT NULL (workspace isolation guardrail, plan §D0-30).
  Per-claim TTL: expires_at is nullable but must be set by the writer;
  the service rejects claims that would default to "never expire".

Revision ID: 7a1c2d3e4f5b
Revises: 6bac5d9b7fd2
Create Date: 2026-06-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a1c2d3e4f5b"
down_revision: Union[str, Sequence[str], None] = "6bac5d9b7fd2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add personal_memory_claims table (plan §D0-30, T18)."""
    op.create_table(
        "personal_memory_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("predicate", sa.String(length=100), nullable=False),
        sa.Column("object", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("claim_type", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("sensitivity", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "claim_type IN ('fact', 'preference', 'observation', 'sensitive')",
            name="ck_personal_memory_claim_claim_type_valid",
        ),
        sa.CheckConstraint(
            "scope IN ('personal', 'workspace', 'program', 'private')",
            name="ck_personal_memory_claim_scope_valid",
        ),
        sa.CheckConstraint(
            "source_type IN ('mission', 'conversation', 'user_explicit', 'program_learning')",
            name="ck_personal_memory_claim_source_type_valid",
        ),
        sa.CheckConstraint(
            "sensitivity IN ('normal', 'sensitive', 'restricted')",
            name="ck_personal_memory_claim_sensitivity_valid",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_personal_memory_claims_user_id"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_personal_memory_claims_workspace_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_personal_memory_claims"),
    )
    # Single-column indexes (matching the mapped column indexes).
    op.create_index(
        "ix_personal_memory_claims_user_id",
        "personal_memory_claims",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_personal_memory_claims_workspace_id",
        "personal_memory_claims",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_personal_memory_claims_claim_type",
        "personal_memory_claims",
        ["claim_type"],
        unique=False,
    )
    op.create_index(
        "ix_personal_memory_claims_scope",
        "personal_memory_claims",
        ["scope"],
        unique=False,
    )
    op.create_index(
        "ix_personal_memory_claims_deleted_at",
        "personal_memory_claims",
        ["deleted_at"],
        unique=False,
    )
    # Composite indexes for the documented recall patterns.
    # (user_id, workspace_id, deleted_at) — fast active-scope lookup.
    op.create_index(
        "ix_personal_memory_claims_user_ws_deleted",
        "personal_memory_claims",
        ["user_id", "workspace_id", "deleted_at"],
        unique=False,
    )
    # (workspace_id, scope) — workspace-scoped recall by scope bucket.
    op.create_index(
        "ix_personal_memory_claims_workspace_scope",
        "personal_memory_claims",
        ["workspace_id", "scope"],
        unique=False,
    )


def downgrade() -> None:
    """Drop personal_memory_claims (and all its indexes)."""
    op.drop_index(
        "ix_personal_memory_claims_workspace_scope", table_name="personal_memory_claims"
    )
    op.drop_index(
        "ix_personal_memory_claims_user_ws_deleted", table_name="personal_memory_claims"
    )
    op.drop_index(
        "ix_personal_memory_claims_deleted_at", table_name="personal_memory_claims"
    )
    op.drop_index("ix_personal_memory_claims_scope", table_name="personal_memory_claims")
    op.drop_index(
        "ix_personal_memory_claims_claim_type", table_name="personal_memory_claims"
    )
    op.drop_index(
        "ix_personal_memory_claims_workspace_id", table_name="personal_memory_claims"
    )
    op.drop_index(
        "ix_personal_memory_claims_user_id", table_name="personal_memory_claims"
    )
    op.drop_table("personal_memory_claims")
