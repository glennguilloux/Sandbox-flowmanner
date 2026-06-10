"""Add mission_sandboxes table for sandboxd integration.

Tracks sandboxd Docker sandboxes scoped to missions (one sandbox per mission).
Sandbox lifecycle (create → stop → purge) maps to mission lifecycle via SandboxService.

Revision ID: mission_sandboxes_001
Revises: hotfix_sql_fixes
Create Date: 2026-06-15
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "mission_sandboxes_001"
down_revision = "hotfix_sql_fixes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_sandboxes",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "mission_id",
            UUID(as_uuid=True),
            sa.ForeignKey("missions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "sandbox_id",
            sa.String(64),
            nullable=False,
            unique=True,
            comment="sandboxd container ULID",
        ),
        sa.Column(
            "project_id",
            sa.String(128),
            nullable=False,
            comment="maps to sandboxd project.id",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="creating",
        ),
        sa.Column(
            "stopped_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "purged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            JSONB,
            nullable=True,
            comment="arbitrary sandbox config/env",
        ),
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

    # Index for filtering by status (e.g. reaper queries: WHERE status = 'creating')
    op.create_index(
        "ix_mission_sandboxes_status",
        "mission_sandboxes",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_mission_sandboxes_status", table_name="mission_sandboxes")
    op.drop_table("mission_sandboxes")
