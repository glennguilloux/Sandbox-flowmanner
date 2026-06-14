"""add mission_programs and program_runs

Mission Programs: durable, repeatable missions that accumulate outcome
intelligence across runs and inject that learning into the planner prompt.

Tables added:
- ``mission_programs`` — durable program definition (one per workflow).
  workspace_id is NOT NULL (workspace isolation guardrail, plan §T1).
- ``program_runs`` — a single execution of a program (one per mission).

Revision ID: 6bac5d9b7fd2
Revises: handoff_packets_001
Create Date: 2026-06-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6bac5d9b7fd2"
down_revision: Union[str, Sequence[str], None] = "handoff_packets_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add mission_programs + program_runs tables (plan §T1)."""
    op.create_table(
        "mission_programs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("mission_type", sa.String(length=50), nullable=True),
        sa.Column("base_constraints", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("base_context_files", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("base_context_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trigger_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("learning_brief", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("per_run_budget_usd", sa.Double(), nullable=True),
        sa.Column("monthly_budget_usd", sa.Double(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'archived')",
            name="ck_mission_program_status_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_mission_programs_user_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
            name="fk_mission_programs_workspace_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mission_programs"),
    )
    op.create_index("ix_mission_programs_status", "mission_programs", ["status"], unique=False)
    op.create_index("ix_mission_programs_user_id", "mission_programs", ["user_id"], unique=False)
    op.create_index(
        "ix_mission_programs_workspace_id", "mission_programs", ["workspace_id"], unique=False
    )

    op.create_table(
        "program_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger_type", sa.String(length=20), nullable=False),
        sa.Column("trigger_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("cost_usd", sa.Double(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Double(), nullable=True),
        sa.Column("outcome_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'aborted')",
            name="ck_program_run_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"], ["missions.id"], ondelete="CASCADE", name="fk_program_runs_mission_id"
        ),
        sa.ForeignKeyConstraint(
            ["program_id"],
            ["mission_programs.id"],
            ondelete="CASCADE",
            name="fk_program_runs_program_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_program_runs"),
    )
    op.create_index("ix_program_runs_program_id", "program_runs", ["program_id"], unique=False)
    op.create_index("ix_program_runs_mission_id", "program_runs", ["mission_id"], unique=False)
    op.create_index("ix_program_runs_status", "program_runs", ["status"], unique=False)


def downgrade() -> None:
    """Drop program_runs first (FK dependency), then mission_programs."""
    op.drop_index("ix_program_runs_status", table_name="program_runs")
    op.drop_index("ix_program_runs_mission_id", table_name="program_runs")
    op.drop_index("ix_program_runs_program_id", table_name="program_runs")
    op.drop_table("program_runs")

    op.drop_index("ix_mission_programs_workspace_id", table_name="mission_programs")
    op.drop_index("ix_mission_programs_user_id", table_name="mission_programs")
    op.drop_index("ix_mission_programs_status", table_name="mission_programs")
    op.drop_table("mission_programs")
