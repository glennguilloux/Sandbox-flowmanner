"""Add rejection_reason column to scaffold_proposals (AutoMem Phase 2 fix).

Revision ID: 20260705_scaffold_rejection_reason
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260705_scaffold_rejection_reason"
down_revision = "20260705_scaffold_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scaffold_proposals",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scaffold_proposals", "rejection_reason")
