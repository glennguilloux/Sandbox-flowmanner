"""Create memory_sessions and memories tables

Revision ID: 20260521_memories
Revises: 20260521_avatar
Create Date: 2026-05-21
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

from alembic import op

revision = "20260521_memories"
down_revision = "20260521_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_sessions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True
        ),
        sa.Column(
            "title", sa.String(500), nullable=False, server_default="Untitled Session"
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_table(
        "memories",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=False),
            sa.ForeignKey("memory_sessions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", JSON, nullable=True),
        sa.Column("metadata", JSON, nullable=True),
        sa.Column("source_mission_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("memories")
    op.drop_table("memory_sessions")
