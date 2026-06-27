"""Create integration_incidents table and seed status page feature flag.

Revision ID: integration_status_page_001
Revises: integration_playground_flag_001
"""

from alembic import op
import sqlalchemy as sa

revision: str = "integration_status_page_001"
down_revision: str | None = "integration_playground_flag_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create integration_incidents table and seed feature flag."""
    op.create_table(
        "integration_incidents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("integration_slug", sa.String(100), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
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
        "ix_integration_incidents_slug_status",
        "integration_incidents",
        ["integration_slug", "status"],
    )
    op.create_index(
        "ix_integration_incidents_created_at",
        "integration_incidents",
        ["created_at"],
    )

    # Seed feature flag
    op.execute(
        """
        INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
        VALUES (
            'integration_status_page_v1',
            'Integration Status Page',
            'Public status page showing per-integration health, uptime, and recent incidents.',
            false,
            NOW(),
            NOW()
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    """Drop integration_incidents table and remove feature flag."""
    op.execute("DELETE FROM feature_flags WHERE key = 'integration_status_page_v1'")
    op.drop_index("ix_integration_incidents_created_at", table_name="integration_incidents")
    op.drop_index("ix_integration_incidents_slug_status", table_name="integration_incidents")
    op.drop_table("integration_incidents")
