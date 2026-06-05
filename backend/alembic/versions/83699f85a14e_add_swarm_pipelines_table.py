"""add swarm_pipelines table

Revision ID: 83699f85a14e
Revises:
Create Date: 2026-04-15 12:10:43.024497

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


revision: str = "83699f85a14e"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "swarm_pipelines",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("swarm_id", sa.String(64), sa.ForeignKey("swarm_profiles.swarm_id"), nullable=False, index=True),
        sa.Column("objective", sa.Text, nullable=False),
        sa.Column("current_phase", sa.String(50), server_default="pending"),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("config", JSON, nullable=True),
        sa.Column("result", JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("phase_history", JSON, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("swarm_pipelines")
