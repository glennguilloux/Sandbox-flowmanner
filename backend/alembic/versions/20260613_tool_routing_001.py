"""Add tool_routing_decisions audit table.

Revision ID: tool_routing_001
Revises: episodic_memory_001
Create Date: 2026-06-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "tool_routing_001"
down_revision: str | Sequence[str] | None = "episodic_memory_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create tool_routing_decisions audit table with indexes."""
    op.create_table(
        "tool_routing_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "mission_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        sa.Column("task_text_hash", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("top_score", sa.Float(), nullable=False),
        sa.Column("candidates_considered", sa.Integer(), nullable=False),
        sa.Column("candidates_returned", sa.Integer(), nullable=False),
        sa.Column(
            "selected_tool_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Composite index for the common query: per-user routing history
    op.create_index(
        "ix_tool_routing_ws_user_created",
        "tool_routing_decisions",
        ["workspace_id", "user_id", sa.text("created_at DESC")],
    )

    # Partial index on mission_id for mission-scoped lookups
    # NB: single-statement op.execute() — asyncpg cannot batch multi-statement SQL
    op.execute(
        "CREATE INDEX ix_tool_routing_mission "
        "ON tool_routing_decisions (mission_id) "
        "WHERE mission_id IS NOT NULL"
    )


def downgrade() -> None:
    """Drop tool_routing_decisions table and indexes."""
    op.drop_index("ix_tool_routing_mission", table_name="tool_routing_decisions")
    op.drop_index("ix_tool_routing_ws_user_created", table_name="tool_routing_decisions")
    op.drop_table("tool_routing_decisions")
