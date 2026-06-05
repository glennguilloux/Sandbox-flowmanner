"""Add notifications table (DB-backed replacement for in-memory store)

Revision ID: notifications_table_001
Revises: 66697531c2da
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa

revision = "notifications_table_001"
down_revision = "66697531c2da"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text, default="", nullable=False),
        sa.Column("notification_type", sa.String(50), default="info", nullable=False),
        sa.Column("severity", sa.String(20), default="info", nullable=False),
        sa.Column("is_read", sa.Boolean, default=False, nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.String(50), nullable=True),
        sa.Column("meta", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("notifications")
