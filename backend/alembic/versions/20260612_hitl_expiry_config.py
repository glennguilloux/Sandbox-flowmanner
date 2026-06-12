"""Add workspace_hitl_configs table for per-workspace HITL expiry config (Q1-B chunk 2).

Creates a table that lets each workspace configure:
- timeout_hours: how long before a HITL inbox item is considered stale
- auto_action: what to do on expiry (reject / approve / stay)

Also adds a CHECK constraint on auto_action to enforce valid values.

Revision ID: hitl_expiry_config_001
Revises: circuit_breaker_001
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hitl_expiry_config_001"
down_revision: str | None = "circuit_breaker_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create workspace_hitl_configs table."""
    op.create_table(
        "workspace_hitl_configs",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "timeout_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("24"),
        ),
        sa.Column(
            "auto_action",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'reject'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "auto_action IN ('reject', 'approve', 'stay')",
            name="ck_workspace_hitl_config_auto_action_valid",
        ),
        sa.CheckConstraint(
            "timeout_hours > 0",
            name="ck_workspace_hitl_config_timeout_positive",
        ),
        sa.UniqueConstraint("workspace_id", name="uq_workspace_hitl_config"),
    )


def downgrade() -> None:
    """Drop workspace_hitl_configs table."""
    op.drop_table("workspace_hitl_configs")
