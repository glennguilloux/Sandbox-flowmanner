"""H4.1 — Add subscription_tier_id and billing_customer_id to workspaces.

Migrates billing/subscription fields from the Tenant model to Workspace
as part of the Tenant → Workspace consolidation (H4.1 Phase 1).

Adds:
- subscription_tier_id (FK → subscription_tiers.id, nullable)
- billing_customer_id (String/100, nullable)
"""

revision = "h4_1_workspace_billing"
down_revision = "h2_substrate_init"
branch_labels = None
depends_on = None

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "subscription_tier_id",
            sa.Integer(),
            sa.ForeignKey("subscription_tiers.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "workspaces",
        sa.Column(
            "billing_customer_id",
            sa.String(100),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_workspaces_subscription_tier",
        "workspaces",
        ["subscription_tier_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workspaces_subscription_tier", table_name="workspaces")
    op.drop_column("workspaces", "billing_customer_id")
    op.drop_column("workspaces", "subscription_tier_id")
