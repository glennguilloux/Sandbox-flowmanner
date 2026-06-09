"""Add missing columns to notifications table

The notifications table was created manually before the alembic migration
existed. This migration adds the columns that the model expects but the
table is missing.

Revision ID: fix_notifications_columns
Revises: push_subscriptions_001
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa

revision = "fix_notifications_columns"
down_revision = "push_subscriptions_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("notifications")]

    if "entity_type" not in columns:
        op.add_column(
            "notifications", sa.Column("entity_type", sa.String(50), nullable=True)
        )
    if "entity_id" not in columns:
        op.add_column(
            "notifications", sa.Column("entity_id", sa.String(50), nullable=True)
        )
    if "meta" not in columns:
        op.add_column("notifications", sa.Column("meta", sa.Text, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("notifications")]

    if "entity_type" in columns:
        op.drop_column("notifications", "entity_type")
    if "entity_id" in columns:
        op.drop_column("notifications", "entity_id")
    if "meta" in columns:
        op.drop_column("notifications", "meta")
