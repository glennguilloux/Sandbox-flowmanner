"""Add integrations and tags to marketplace_listings.

Revision ID: 20260521_marketplace_integrations_tags
Revises: 20260521_create_analytics_events
Create Date: 2026-05-21
"""

import sqlalchemy as sa

from alembic import op

revision = "20260521_marketplace_integrations_tags"
down_revision = "20260521_create_analytics_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("marketplace_listings")]

    if "integrations" not in columns:
        op.add_column(
            "marketplace_listings", sa.Column("integrations", sa.Text, nullable=True)
        )
    if "tags" not in columns:
        op.add_column("marketplace_listings", sa.Column("tags", sa.Text, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("marketplace_listings")]

    if "integrations" in columns:
        op.drop_column("marketplace_listings", "integrations")
    if "tags" in columns:
        op.drop_column("marketplace_listings", "tags")
