"""Add integration_manifests_v1 feature flag.

Seeds the feature flag that gates manifest-driven integration metadata.
Disabled by default — enable via admin toggle when ready to roll out.

Revision ID: integration_manifests_flag_001
Revises: 20260721_agent_protocol
Create Date: 2026-06-27
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "integration_manifests_flag_001"
down_revision: str | None = "20260721_agent_protocol"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Seed integration_manifests_v1 feature flag (idempotent, disabled by default)."""
    op.execute(
        """
        INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
        VALUES (
            'integration_manifests_v1',
            'Integration Manifests v1',
            'Serve integration metadata from JSON manifest files instead of the hardcoded AVAILABLE_INTEGRATIONS list.',
            false,
            NOW(),
            NOW()
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove integration_manifests_v1 feature flag row."""
    op.execute("DELETE FROM feature_flags WHERE key = 'integration_manifests_v1'")
