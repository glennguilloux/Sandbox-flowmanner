"""Add integration_playground_v1 feature flag.

Revision ID: integration_playground_flag_001
Revises: integration_usage_logs_001
Create Date: 2026-06-27
"""

from alembic import op

# revision identifiers
revision: str = "integration_playground_flag_001"
down_revision: str | None = "integration_usage_logs_001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
        VALUES (
            'integration_playground_v1',
            'Integration Playground',
            'Try before you connect — execute demo actions with sandbox credentials without connecting your account.',
            false,
            NOW(),
            NOW()
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_flags WHERE key = 'integration_playground_v1'")
