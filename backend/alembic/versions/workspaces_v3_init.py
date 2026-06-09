"""workspaces_v3_init — workspace settings, billing fields, team top-level support

Revision ID: workspaces_v3_001
Revises: auth_v3_001
Create Date: 2026-06-08
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "workspaces_v3_001"
down_revision = "auth_v3_001"
branch_labels = None
depends_on = None


def upgrade():
    # ── Add columns to workspaces ──
    op.add_column("workspaces", sa.Column("logo_url", sa.String(500), nullable=True))
    op.add_column(
        "workspaces",
        sa.Column(
            "settings", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "member_limit", sa.Integer(), nullable=True, server_default=sa.text("5")
        ),
    )  # Free tier: 5 members
    op.add_column(
        "workspaces",
        sa.Column(
            "storage_used_bytes",
            sa.BigInteger(),
            nullable=True,
            server_default=sa.text("0"),
        ),
    )

    # ── Add columns to workspace_invitations ──
    op.add_column(
        "workspace_invitations",
        sa.Column(
            "invitation_message", sa.Text(), nullable=True, server_default=sa.text("''")
        ),
    )

    # ── Add workspace_activity_log table ──
    op.create_table(
        "workspace_activity_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column(
            "metadata", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Index("ix_activity_log_workspace_time", "workspace_id", "created_at"),
    )

    # ── Seed feature flags ──
    op.execute(
        """
        INSERT INTO feature_flags ("key", name, description, enabled_globally, created_at, updated_at)
        VALUES
            ('WORKSPACES_V3_ENDPOINTS', 'Workspaces v3 Endpoints',
             'Enable v3 workspace routes (invitations, billing, audit, top-level teams)',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_INVITES', 'Workspaces v3 Email Invitations',
             'Enable email invitation send/accept flow',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_BILLING', 'Workspaces v3 Billing',
             'Enable subscription and billing endpoints',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_TEAMS_TOPLEVEL', 'Workspaces v3 Top-Level Teams',
             'Serve teams at /api/v3/teams instead of nested under workspaces',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_AUDIT', 'Workspaces v3 Audit Log',
             'Enable workspace activity audit log endpoints',
             false, NOW(), NOW()),
            ('WORKSPACES_V3_ROLES', 'Workspaces v3 Extended Roles',
             'Support viewer role and custom workspace roles',
             false, NOW(), NOW())
        ON CONFLICT ("key") DO NOTHING;
    """
    )

    # ── Data backfill: set member_limit for existing workspaces ──
    op.execute(
        """
        UPDATE workspaces
        SET member_limit = 5
        WHERE member_limit IS NULL;
    """
    )


def downgrade():
    op.drop_table("workspace_activity_log")
    op.drop_column("workspaces", "logo_url")
    op.drop_column("workspaces", "settings")
    op.drop_column("workspaces", "member_limit")
    op.drop_column("workspaces", "storage_used_bytes")
    op.drop_column("workspace_invitations", "invitation_message")

    op.execute(
        """
        DELETE FROM feature_flags WHERE "key" IN (
            'WORKSPACES_V3_ENDPOINTS', 'WORKSPACES_V3_INVITES', 'WORKSPACES_V3_BILLING',
            'WORKSPACES_V3_TEAMS_TOPLEVEL', 'WORKSPACES_V3_AUDIT', 'WORKSPACES_V3_ROLES'
        );
    """
    )
