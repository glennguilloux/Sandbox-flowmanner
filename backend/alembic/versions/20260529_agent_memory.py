"""Create agent_memory table

Revision ID: 20260529_agent_memory
Revises: 20260526_add_knowledge_graph_tables
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "20260529_agent_memory"
down_revision = "20260526_knowledge_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_memory",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False, index=True),
        sa.Column("agent_id", sa.String(255), nullable=False, index=True, server_default="default"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="note"),
        sa.Column("metadata", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("agent_memory")
