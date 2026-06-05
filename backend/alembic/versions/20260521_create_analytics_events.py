"""Create analytics_events table.

Revision ID: 20260521_create_analytics_events
Revises: fix_notifications_columns
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa

revision = "20260521_create_analytics_events"
down_revision = "fix_notifications_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String, nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("properties", sa.JSON, default={}),
        sa.Column("session_id", sa.String),
    )
    op.create_index("idx_analytics_user_type", "analytics_events", ["user_id", "event_type"])
    op.create_index("idx_analytics_timestamp", "analytics_events", ["timestamp"])
    op.create_index("idx_analytics_event_type", "analytics_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("analytics_events")
