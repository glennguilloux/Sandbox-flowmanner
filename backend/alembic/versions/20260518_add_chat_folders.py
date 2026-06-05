"""Add chat_folders table and folder_id to chat_threads

Revision ID: chat_folders_001
Revises: mission_advanced_001
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa

revision = "chat_folders_001"
down_revision = "mission_advanced_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_folders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.add_column("chat_threads", sa.Column("folder_id", sa.Integer, sa.ForeignKey("chat_folders.id"), nullable=True))
    op.create_index("ix_chat_threads_folder_id", "chat_threads", ["folder_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_threads_folder_id", table_name="chat_threads")
    op.drop_column("chat_threads", "folder_id")
    op.drop_table("chat_folders")
