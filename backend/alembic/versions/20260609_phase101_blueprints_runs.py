"""Phase 10.1: Create blueprints, runs, and blueprint_versions tables.

These tables unify the 5 overlapping execution concepts (Mission, Workflow/Graph,
Flow, OrchestratorExecution, SwarmPipeline) into two first-class objects:
- Blueprint = reusable, versioned work definition
- Run = one execution instance of a Blueprint

Revision ID: phase101_blueprints_runs
Revises: 20260603_phase96_plugin_security
Create Date: 2026-06-09
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "phase101_blueprints_runs"
down_revision = "20260603_phase96_plugin_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── blueprints ───────────────────────────────────────────────────
    op.create_table(
        "blueprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "blueprint_type", sa.String(50), nullable=False, server_default="solo"
        ),
        sa.Column("definition", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("input_schema", postgresql.JSONB, nullable=True),
        sa.Column("output_schema", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("run_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_blueprints_user_id", "blueprints", ["user_id"])
    op.create_index("ix_blueprints_workspace_id", "blueprints", ["workspace_id"])
    op.create_index("ix_blueprints_status", "blueprints", ["status"])
    op.create_index("ix_blueprints_blueprint_type", "blueprints", ["blueprint_type"])
    op.create_index("ix_blueprints_deleted_at", "blueprints", ["deleted_at"])
    op.create_index("ix_blueprints_title", "blueprints", ["title"])

    # ── runs ─────────────────────────────────────────────────────────
    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "blueprint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("blueprints.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("snapshot", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("output_data", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("budget_limit_usd", sa.Float, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "parent_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("runs.id"),
            nullable=True,
        ),
        sa.Column("input_data", postgresql.JSONB, nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_runs_blueprint_id", "runs", ["blueprint_id"])
    op.create_index("ix_runs_user_id", "runs", ["user_id"])
    op.create_index("ix_runs_workspace_id", "runs", ["workspace_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_parent_run_id", "runs", ["parent_run_id"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])

    # ── blueprint_versions ───────────────────────────────────────────
    op.create_table(
        "blueprint_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "blueprint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("blueprints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("snapshot", postgresql.JSONB, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_blueprint_versions_blueprint_id", "blueprint_versions", ["blueprint_id"]
    )

    # ── substrate_events: add blueprint_id column ─────────────────────
    op.add_column(
        "substrate_events",
        sa.Column(
            "blueprint_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_substrate_events_blueprint_id",
        "substrate_events",
        ["blueprint_id"],
    )
    op.create_foreign_key(
        "fk_substrate_events_blueprint_id",
        "substrate_events",
        "blueprints",
        ["blueprint_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_substrate_events_blueprint_id", "substrate_events", type_="foreignkey"
    )
    op.drop_index("ix_substrate_events_blueprint_id", table_name="substrate_events")
    op.drop_column("substrate_events", "blueprint_id")

    op.drop_index("ix_blueprint_versions_blueprint_id", table_name="blueprint_versions")
    op.drop_table("blueprint_versions")

    op.drop_index("ix_runs_created_at", table_name="runs")
    op.drop_index("ix_runs_parent_run_id", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_workspace_id", table_name="runs")
    op.drop_index("ix_runs_user_id", table_name="runs")
    op.drop_index("ix_runs_blueprint_id", table_name="runs")
    op.drop_table("runs")

    op.drop_index("ix_blueprints_title", table_name="blueprints")
    op.drop_index("ix_blueprints_deleted_at", table_name="blueprints")
    op.drop_index("ix_blueprints_blueprint_type", table_name="blueprints")
    op.drop_index("ix_blueprints_status", table_name="blueprints")
    op.drop_index("ix_blueprints_workspace_id", table_name="blueprints")
    op.drop_index("ix_blueprints_user_id", table_name="blueprints")
    op.drop_table("blueprints")
