"""Add integrations and tags to marketplace_listings.

Revision ID: 20260521_marketplace_integrations_tags
Revises: 20260521_create_analytics_events
Create Date: 2026-05-21
"""

import sqlalchemy as sa

from alembic import context, op

revision = "20260521_marketplace_integrations_tags"
down_revision = "20260521_create_analytics_events"
branch_labels = None
depends_on = None


def _marketplace_listing_columns(conn):
    if context.is_offline_mode():
        return []

    return [column["name"] for column in sa.inspect(conn).get_columns("marketplace_listings")]


def _offline_marketplace_listing_columns():
    return ["integrations", "tags"]


def upgrade() -> None:
    conn = op.get_bind()
    columns = _marketplace_listing_columns(conn)

    if "integrations" not in columns:
        op.add_column("marketplace_listings", sa.Column("integrations", sa.Text, nullable=True))
    if "tags" not in columns:
        op.add_column("marketplace_listings", sa.Column("tags", sa.Text, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    columns = (
        _offline_marketplace_listing_columns()
        if context.is_offline_mode()
        else _marketplace_listing_columns(conn)
    )

    if "integrations" in columns:
        op.drop_column("marketplace_listings", "integrations")
    if "tags" in columns:
        op.drop_column("marketplace_listings", "tags")
