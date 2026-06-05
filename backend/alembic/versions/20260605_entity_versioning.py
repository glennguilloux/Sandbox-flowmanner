"""Entity versioning — Phase 3.1.

Adds version columns to agents, workspaces, missions tables.
Creates agent_versions and workspace_versions tables.
Normalizes mission_versions (version_number → version, adds unique index + FK cascade).

Revision ID: 20260605_entity_versioning
Revises: 20260605_marketplace
Create Date: 2026-06-05 15:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260605_entity_versioning"
down_revision: Union[str, Sequence[str], None] = "20260605_marketplace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Add missing columns to agents ──────────────────────────────
    # The Agent model defines 'state' but the original agents table
    # was created before the H4.3 consolidation.  Add it if missing.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'state'
            ) THEN
                ALTER TABLE agents ADD COLUMN state VARCHAR(30) NOT NULL DEFAULT 'defined';
            END IF;
        END $$;
    """
    )

    op.add_column(
        "agents",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # ── Create agent_versions table ────────────────────────────────
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_agent_versions_agent_id", "agent_versions", ["agent_id"])
    op.create_index(
        "ix_agent_versions_agent_version",
        "agent_versions",
        ["agent_id", "version"],
        unique=True,
    )

    # ── Add version column to workspaces ───────────────────────────
    op.add_column(
        "workspaces",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # ── Create workspace_versions table ────────────────────────────
    op.create_table(
        "workspace_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_workspace_versions_workspace_id", "workspace_versions", ["workspace_id"]
    )
    op.create_index(
        "ix_workspace_versions_ws_version",
        "workspace_versions",
        ["workspace_id", "version"],
        unique=True,
    )

    # ── Add version column to missions ─────────────────────────────
    op.add_column(
        "missions",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    # ── Normalize mission_versions ─────────────────────────────────
    # Rename version_number → version for consistency with all other
    # version tables (tool_versions, capability_versions, etc.)
    op.alter_column(
        "mission_versions",
        "version_number",
        new_column_name="version",
        existing_type=sa.Integer(),
    )

    # Add cascade to mission_id FK (was missing)
    op.drop_constraint(
        "mission_versions_mission_id_fkey",
        "mission_versions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "mission_versions_mission_id_fkey",
        "mission_versions",
        "missions",
        ["mission_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Add unique composite index on (mission_id, version)
    op.create_index(
        "ix_mission_versions_mission_version",
        "mission_versions",
        ["mission_id", "version"],
        unique=True,
    )


def downgrade() -> None:
    # ── agents: remove state column if it was added by this migration ──
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'agents' AND column_name = 'state'
            ) THEN
                ALTER TABLE agents DROP COLUMN state;
            END IF;
        END $$;
    """
    )

    # ── mission_versions ───────────────────────────────────────────
    op.drop_index("ix_mission_versions_mission_version", table_name="mission_versions")
    op.drop_constraint(
        "mission_versions_mission_id_fkey",
        "mission_versions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "mission_versions_mission_id_fkey",
        "mission_versions",
        "missions",
        ["mission_id"],
        ["id"],
    )
    op.alter_column(
        "mission_versions",
        "version",
        new_column_name="version_number",
        existing_type=sa.Integer(),
    )

    # ── missions ───────────────────────────────────────────────────
    op.drop_column("missions", "version")

    # ── workspace_versions ─────────────────────────────────────────
    op.drop_index("ix_workspace_versions_ws_version", table_name="workspace_versions")
    op.drop_index("ix_workspace_versions_workspace_id", table_name="workspace_versions")
    op.drop_table("workspace_versions")
    op.drop_column("workspaces", "version")

    # ── agent_versions ─────────────────────────────────────────────
    op.drop_index("ix_agent_versions_agent_version", table_name="agent_versions")
    op.drop_index("ix_agent_versions_agent_id", table_name="agent_versions")
    op.drop_table("agent_versions")
    op.drop_column("agents", "version")
