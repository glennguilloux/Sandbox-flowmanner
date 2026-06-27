"""Add integration_onboarding_v1 feature flag.

Seeds the feature flag that gates the integration onboarding wizard
(TTFC optimization — template workflows and guided setup).
Disabled by default — enable via admin toggle when ready to roll out.

Revision ID: integration_onboarding_flag_001
Revises: integration_status_page_001
Create Date: 2026-06-27
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "integration_onboarding_flag_001"
down_revision: str | None = "integration_status_page_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Seed integration_onboarding_v1 feature flag (idempotent, disabled by default)."""
    op.execute(
        """
        INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
        VALUES (
            'integration_onboarding_v1',
            'Integration Onboarding v1',
            'Guided onboarding wizard with template workflows to reduce Time to First Connection to under 5 minutes.',
            false,
            NOW(),
            NOW()
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove integration_onboarding_v1 feature flag row."""
    op.execute("DELETE FROM feature_flags WHERE key = 'integration_onboarding_v1'")
