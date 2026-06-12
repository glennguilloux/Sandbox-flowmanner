"""Add substrate_worker_leases table for worker task leasing.

Creates a durable lease table that lets the backend represent and query
active worker leases for execution runs.  This is the schema-only chunk;
heartbeat, stale-reclaimer, Celery wiring, and UnifiedExecutor integration
are deferred to later chunks.

Revision ID: worker_leases_001
Revises: align_playground_template_with_v1_api_001
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "worker_leases_001"
down_revision: str | None = "align_playground_template_with_v1_api_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create substrate_worker_leases table and index."""
    op.create_table(
        "substrate_worker_leases",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column("worker_id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "acquired_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("renewed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("generation", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index(
        "ix_substrate_worker_leases_expires",
        "substrate_worker_leases",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop substrate_worker_leases table and index."""
    op.drop_index("ix_substrate_worker_leases_expires", table_name="substrate_worker_leases")
    op.drop_table("substrate_worker_leases")
