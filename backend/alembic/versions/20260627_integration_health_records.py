"""Add integration health records table + feature flag.

Creates the ``integration_health_records`` table used by the periodic
Celery health-check task, and seeds the ``integration_health_v1``
feature flag (disabled by default).

Revision ID: integration_health_records_001
Revises: 59bd8e5ea4b2
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "integration_health_records_001"
down_revision: str | None = "59bd8e5ea4b2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create integration_health_records table and seed feature flag."""
    op.create_table(
        "integration_health_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("integration_slug", sa.String(100), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
    op.create_index(
        "ix_integration_health_records_checked_at",
        "integration_health_records",
        ["checked_at"],
    )
    # Composite index for DISTINCT ON queries in get_all_latest()
    op.create_index(
        "ix_integration_health_records_slug_checked_at",
        "integration_health_records",
        ["integration_slug", "checked_at"],
    )

    # Seed the feature flag (idempotent, disabled by default).
    # NOTE: the literal below is a feature-flag name, not a credential.
    # gitleaks:allow
    op.execute(
        """
        INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
        VALUES (
            'integration_health_v1',
            'Integration Health v1',
            'Enable per-integration health checks, trust badges, and health status API endpoints.',
            false,
            NOW(),
            NOW()
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    """Drop integration_health_records table and remove feature flag."""
    op.execute("DELETE FROM feature_flags WHERE key = 'integration_health_v1'")
    op.drop_index("ix_integration_health_records_slug_checked_at", table_name="integration_health_records")
    op.drop_index("ix_integration_health_records_checked_at", table_name="integration_health_records")
    op.drop_table("integration_health_records")
