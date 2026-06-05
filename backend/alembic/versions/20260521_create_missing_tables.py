"""Create missing tables from models

Revision ID: 20260521_missing_tables
Revises: 20260521_memories
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "20260521_missing_tables"
down_revision = "20260521_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tenants
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("settings", JSON, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Tenant members
    op.create_table(
        "tenant_members",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True
        ),
        sa.Column("role", sa.String(50), server_default="member"),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Tenant invitations
    op.create_table(
        "tenant_invitations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="member"),
        sa.Column("invited_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Partners
    op.create_table(
        "partners",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Partner revenues
    op.create_table(
        "partner_revenues",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "partner_id",
            sa.Integer,
            sa.ForeignKey("partners.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD"),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Swarm pipelines
    op.create_table(
        "swarm_pipelines",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("config", JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Swarm agents
    op.create_table(
        "swarm_agents",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "pipeline_id",
            sa.Integer,
            sa.ForeignKey("swarm_pipelines.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("config", JSON, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Swarm tasks
    op.create_table(
        "swarm_tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "pipeline_id",
            sa.Integer,
            sa.ForeignKey("swarm_pipelines.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "agent_id", sa.Integer, sa.ForeignKey("swarm_agents.id"), nullable=True
        ),
        sa.Column("task_type", sa.String(100), nullable=False),
        sa.Column("input_data", JSON, nullable=True),
        sa.Column("output_data", JSON, nullable=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Swarm consensus rounds
    op.create_table(
        "swarm_consensus_rounds",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "pipeline_id",
            sa.Integer,
            sa.ForeignKey("swarm_pipelines.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("round_number", sa.Integer, nullable=False),
        sa.Column("consensus_data", JSON, nullable=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # Swarm profiles
    op.create_table(
        "swarm_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("config", JSON, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("swarm_profiles")
    op.drop_table("swarm_consensus_rounds")
    op.drop_table("swarm_tasks")
    op.drop_table("swarm_agents")
    op.drop_table("swarm_pipelines")
    op.drop_table("partner_revenues")
    op.drop_table("partners")
    op.drop_table("tenant_invitations")
    op.drop_table("tenant_members")
    op.drop_table("tenants")
