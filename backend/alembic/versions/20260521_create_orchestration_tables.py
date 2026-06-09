"""Create orchestration_agents, orchestration_teams, orchestration_tasks tables

Revision ID: 20260521_orchestration
Revises: 20260521_perf_indexes
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "20260521_orchestration"
down_revision = "20260521_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_agents",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("role", sa.String(50), server_default="WORKER"),
        sa.Column("status", sa.String(20), server_default="IDLE"),
        sa.Column("capabilities", JSON, nullable=True),
        sa.Column("config", JSON, nullable=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_table(
        "orchestration_teams",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("members", JSON, nullable=True),
        sa.Column("status", sa.String(20), server_default="ACTIVE"),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_table(
        "orchestration_tasks",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "assigned_agent_id",
            UUID(as_uuid=False),
            sa.ForeignKey("orchestration_agents.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("input", JSON, nullable=True),
        sa.Column("output", JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("orchestration_tasks")
    op.drop_table("orchestration_teams")
    op.drop_table("orchestration_agents")
