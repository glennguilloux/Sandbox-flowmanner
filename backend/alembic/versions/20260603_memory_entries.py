"""Add memory_entries table — canonical Postgres-native memory store.

Revision ID: 20260603_memory_entries
Revises: next_level_growth_wave3_oauth
Create Date: 2026-06-03 20:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260603_memory_entries"
down_revision: Union[str, Sequence[str], None] = "next_level_growth_wave3_oauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column(
            "namespace",
            sa.String(255),
            nullable=False,
            server_default="default",
        ),
        sa.Column("key", sa.String(500), nullable=True),
        sa.Column(
            "memory_type",
            sa.String(100),
            nullable=False,
            server_default="episodic",
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "importance",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.5"),
        ),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=False),
            nullable=True,
        ),
        sa.Column("source_mission_id", sa.String(100), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Indexes
    op.create_index(
        "ix_memory_entries_user_id", "memory_entries", ["user_id"]
    )
    op.create_index(
        "ix_memory_entries_agent_id", "memory_entries", ["agent_id"]
    )
    op.create_index(
        "ix_memory_entries_session_id", "memory_entries", ["session_id"]
    )
    op.create_index(
        "ix_memory_entries_workspace_id", "memory_entries", ["workspace_id"]
    )
    op.create_index(
        "ix_memory_entries_agent_type",
        "memory_entries",
        ["agent_id", "memory_type"],
    )
    op.create_index(
        "ix_memory_entries_namespace_key",
        "memory_entries",
        ["namespace", "key"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_entries_namespace_key", table_name="memory_entries")
    op.drop_index("ix_memory_entries_agent_type", table_name="memory_entries")
    op.drop_index("ix_memory_entries_workspace_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_session_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_agent_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_user_id", table_name="memory_entries")
    op.drop_table("memory_entries")
