"""Add materialization_state table — Postgres-native cache sync tracking.

Revision ID: 20260603_materialization_state
Revises: 20260603_tools_capabilities
Create Date: 2026-06-03 23:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260603_materialization_state"
down_revision: str | Sequence[str] | None = "20260603_tools_capabilities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "materialization_state",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "object_type",
            sa.String(100),
            nullable=False,
            comment="'tool', 'capability', 'agent_template', 'memory', 'topology'",
        ),
        sa.Column(
            "object_id",
            sa.String(36),
            nullable=False,
            comment="UUID of the object in its canonical table",
        ),
        sa.Column(
            "target",
            sa.String(50),
            nullable=False,
            comment="'redis', 'qdrant', 'inproc', 'all'",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="pending",
            comment="'pending', 'materializing', 'materialized', 'stale', 'failed'",
        ),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("last_materialized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Unique constraint on (object_type, object_id, target) — one state row per triple
    op.create_index(
        "ix_mat_state_object_type_id_target",
        "materialization_state",
        ["object_type", "object_id", "target"],
        unique=True,
    )
    op.create_index(
        "ix_mat_state_status",
        "materialization_state",
        ["status"],
    )
    op.create_index(
        "ix_mat_state_object_type",
        "materialization_state",
        ["object_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_mat_state_object_type", table_name="materialization_state")
    op.drop_index("ix_mat_state_status", table_name="materialization_state")
    op.drop_index(
        "ix_mat_state_object_type_id_target", table_name="materialization_state"
    )
    op.drop_table("materialization_state")
