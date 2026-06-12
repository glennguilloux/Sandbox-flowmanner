"""Add per-workspace+provider circuit breaker tables (Q1-A chunk 5).

Creates two tables:
- circuit_breaker_state: Per-(workspace, provider) circuit breaker state
- provider_fallbacks: Per-(workspace, primary_provider) fallback chain config

Uses the COALESCE unique index trick to enforce uniqueness on nullable
workspace_id columns (Postgres treats NULL as not-equal in UNIQUE constraints).

Revision ID: circuit_breaker_001
Revises: worker_leases_001
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "circuit_breaker_001"
down_revision: str | None = "worker_leases_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

# Sentinel UUID used in COALESCE to make NULL workspace_id rows unique.
# This is a well-known PG idiom: since UNIQUE treats NULLs as distinct,
# we coalesce NULL to a fixed sentinel so the index enforces uniqueness
# across both per-workspace and global (NULL) rows.
_NULL_WORKSPACE_SENTINEL = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    """Create circuit_breaker_state and provider_fallbacks tables."""
    # ── circuit_breaker_state ────────────────────────────────────────
    op.create_table(
        "circuit_breaker_state",
        # BIGSERIAL PK — faster for SELECT FOR UPDATE locking; these rows
        # are not distributed so UUID uniqueness is not needed.
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column(
            "state",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'closed'"),
        ),
        # CHECK constraint enforces valid states at the DB level
        sa.CheckConstraint(
            "state IN ('closed', 'open', 'half_open')",
            name="ck_circuit_breaker_state_valid",
        ),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("probe_in_flight", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("failure_threshold", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "failure_count >= 0",
            name="ck_circuit_breaker_failure_count_non_negative",
        ),
    )

    # Unique index using COALESCE to handle NULL workspace_id.
    # Without COALESCE, Postgres UNIQUE treats (NULL, 'openai') and
    # (NULL, 'openai') as distinct, allowing duplicate global rows.
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_circuit_breaker_state_ws_provider
        ON circuit_breaker_state (
            COALESCE(workspace_id, '{_NULL_WORKSPACE_SENTINEL}'::uuid),
            provider_id
        )
        """
    )

    # ── provider_fallbacks ───────────────────────────────────────────
    op.create_table(
        "provider_fallbacks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("primary_provider", sa.Text(), nullable=False),
        sa.Column("fallback_provider", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Same COALESCE trick for provider_fallbacks unique index
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_provider_fallbacks_ws_primary_priority
        ON provider_fallbacks (
            COALESCE(workspace_id, '{_NULL_WORKSPACE_SENTINEL}'::uuid),
            primary_provider,
            priority
        )
        """
    )


def downgrade() -> None:
    """Drop circuit breaker tables and indexes."""
    op.drop_index("uq_provider_fallbacks_ws_primary_priority", table_name="provider_fallbacks")
    op.drop_table("provider_fallbacks")
    op.drop_index("uq_circuit_breaker_state_ws_provider", table_name="circuit_breaker_state")
    op.drop_table("circuit_breaker_state")
