"""Enable integration_onboarding_v1 feature flag.

Turns on the TTFC-optimization onboarding wizard flag that was seeded
disabled in integration_onboarding_flag_001. Reversible via downgrade
(which sets enabled_globally=false without dropping the row).

Revision ID: integration_onboarding_flag_001_enable
Revises: integration_onboarding_flag_001
Create Date: 2026-06-27
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "integration_onboarding_flag_001_enable"
down_revision: str | None = "integration_onboarding_flag_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Enable integration_onboarding_v1 feature flag."""
    op.execute(
        """
        UPDATE feature_flags
        SET enabled_globally = true,
            updated_at = NOW()
        WHERE key = 'integration_onboarding_v1'
        """
    )


def downgrade() -> None:
    """Disable integration_onboarding_v1 feature flag (keeps the row)."""
    op.execute(
        """
        UPDATE feature_flags
        SET enabled_globally = false,
            updated_at = NOW()
        WHERE key = 'integration_onboarding_v1'
        """
    )