"""Add integration usage logs table + feature flag.

Creates the ``integration_usage_logs`` table used by the usage analytics
service, and seeds the ``integration_usage_v1`` feature flag (disabled
by default).

Revision ID: integration_usage_logs_001
Revises: integration_health_records_001
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "integration_usage_logs_001"
down_revision: str | None = "integration_health_records_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create integration_usage_logs table and seed feature flag."""
    op.create_table(
        "integration_usage_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("integration_slug", sa.String(100), nullable=False, index=True),
        sa.Column("action", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Composite index for per-user, per-slug usage queries
    op.create_index(
        "ix_integration_usage_logs_user_slug_created",
        "integration_usage_logs",
        ["user_id", "integration_slug", "created_at"],
    )
    # Index for retention cleanup
    op.create_index(
        "ix_integration_usage_logs_created_at",
        "integration_usage_logs",
        ["created_at"],
    )

    # Seed the feature flag (idempotent, disabled by default).
    op.execute(
        """
        INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
        VALUES (
            'integration_usage_v1',
            'Integration Usage v1',
            'Enable per-integration usage analytics: call counts, success rates, latency, and top actions.',
            false,
            NOW(),
            NOW()
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    """Drop integration_usage_logs table and remove feature flag."""
    op.execute("DELETE FROM feature_flags WHERE key = 'integration_usage_v1'")
    op.drop_index("ix_integration_usage_logs_created_at", table_name="integration_usage_logs")
    op.drop_index("ix_integration_usage_logs_user_slug_created", table_name="integration_usage_logs")
    op.drop_table("integration_usage_logs")
