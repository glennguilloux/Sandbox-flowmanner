"""Add workflow_versions and execution_events tables.

Revision ID: 20260605_workflow_versions
Revises: 20260604_bindings
Create Date: 2026-06-05 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260605_workflow_versions"
down_revision: Union[str, Sequence[str], None] = "20260604_bindings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── workflow_versions ────────────────────────────────────────────
    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_wf_versions_workflow_id", "workflow_versions", ["workflow_id"])
    op.create_index(
        "ix_wf_versions_workflow_version",
        "workflow_versions",
        ["workflow_id", "version"],
        unique=True,
    )

    # ── execution_events ─────────────────────────────────────────────
    op.create_table(
        "execution_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflow_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("node_id", sa.String(255), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("level", sa.String(20), nullable=False, server_default="info"),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_exec_events_execution_id", "execution_events", ["execution_id"])
    op.create_index("ix_exec_events_event_type", "execution_events", ["event_type"])
    op.create_index(
        "ix_exec_events_exec_seq",
        "execution_events",
        ["execution_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("execution_events")
    op.drop_table("workflow_versions")
