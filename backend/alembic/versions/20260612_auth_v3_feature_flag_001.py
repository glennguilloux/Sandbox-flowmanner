"""Enable AUTH_V3_ENDPOINTS feature flag.

Ensures the v3 auth endpoints are enabled across all environments
(dev, staging, production) without requiring a manual DB update.

Uses INSERT ... ON CONFLICT to be idempotent — safe to run multiple times.

Revision ID: auth_v3_feature_flag_001
Revises: cost_attribution_001
Create Date: 2026-06-12
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "auth_v3_feature_flag_001"
down_revision: str | None = "cost_attribution_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Enable AUTH_V3_ENDPOINTS feature flag (idempotent)."""
    op.execute(
        """
        INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
        VALUES (
            'AUTH_V3_ENDPOINTS',
            'Auth v3 Endpoints',
            'Enable /api/v3/auth/* endpoints (session management, API keys, OIDC, webhooks)',
            true,
            NOW(),
            NOW()
        )
        ON CONFLICT (key) DO UPDATE SET
            enabled_globally = true,
            updated_at = NOW()
        """
    )


def downgrade() -> None:
    """Disable AUTH_V3_ENDPOINTS feature flag (do not delete the row)."""
    op.execute(
        """
        UPDATE feature_flags
        SET enabled_globally = false, updated_at = NOW()
        WHERE key = 'AUTH_V3_ENDPOINTS'
        """
    )
