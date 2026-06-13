"""Add missing columns to notifications table

The notifications table was created manually before the alembic migration
existed. This migration adds the columns that the model expects but the
table is missing.

Revision ID: fix_notifications_columns
Revises: push_subscriptions_001
Create Date: 2026-05-20
"""

import sqlalchemy as sa

from alembic import context, op

revision = "fix_notifications_columns"
down_revision = "push_subscriptions_001"
branch_labels = None
depends_on = None


def _notification_columns(conn):
    if context.is_offline_mode():
        return []

    return [column["name"] for column in sa.inspect(conn).get_columns("notifications")]


def _offline_notification_columns():
    return ["entity_id", "entity_type", "meta"]


def upgrade() -> None:
    conn = op.get_bind()
    columns = _notification_columns(conn)

    if "entity_type" not in columns:
        op.add_column("notifications", sa.Column("entity_type", sa.String(50), nullable=True))
    if "entity_id" not in columns:
        op.add_column("notifications", sa.Column("entity_id", sa.String(50), nullable=True))
    if "meta" not in columns:
        op.add_column("notifications", sa.Column("meta", sa.Text, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    columns = _offline_notification_columns() if context.is_offline_mode() else _notification_columns(conn)

    if "entity_type" in columns:
        op.drop_column("notifications", "entity_type")
    if "entity_id" in columns:
        op.drop_column("notifications", "entity_id")
    if "meta" in columns:
        op.drop_column("notifications", "meta")
