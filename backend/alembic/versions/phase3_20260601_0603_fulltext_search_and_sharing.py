"""Full-text search, shared links, usage records

Revision ID: phase3_20260601_0603
Revises: "c3d4e5f6a7b8"
Create Date: 2026-06-01T06:03:52.029135
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase3_20260601_0603"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Full-text search: tsvector column + GIN index on chat_messages
    op.add_column(
        "chat_messages",
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
    )
    op.create_index(
        "ix_chat_messages_search_vector",
        "chat_messages",
        ["search_vector"],
        postgresql_using="gin",
    )
    # Trigger to auto-update search_vector
    op.execute(
        """
        CREATE OR REPLACE FUNCTION chat_messages_search_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """
    )
    op.execute(
        """
        CREATE TRIGGER trg_chat_messages_search_vector
        BEFORE INSERT OR UPDATE ON chat_messages
        FOR EACH ROW EXECUTE FUNCTION chat_messages_search_update();
    """
    )
    op.execute(
        "UPDATE chat_messages "
        "SET search_vector = to_tsvector('english', COALESCE(content, ''))"
    )

    # Shared links table
    op.create_table(
        "shared_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "thread_id", sa.Integer(), sa.ForeignKey("chat_threads.id"), nullable=False
        ),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("token", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_shared_links_thread_id", "shared_links", ["thread_id"])
    op.create_index("ix_shared_links_token", "shared_links", ["token"])

    # Shared with column on chat_threads
    op.add_column(
        "chat_threads", sa.Column("shared_with", postgresql.JSONB(), nullable=True)
    )

    # Usage records table
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=True
        ),
        sa.Column(
            "thread_id", sa.Integer(), sa.ForeignKey("chat_threads.id"), nullable=True
        ),
        sa.Column("model", sa.String(150), nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer(), server_default=sa.text("0")),
        sa.Column("total_tokens", sa.Integer(), server_default=sa.text("0")),
        sa.Column("cost_usd", sa.Float(), server_default=sa.text("0.0")),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_usage_records_user_id", "usage_records", ["user_id"])
    op.create_index("ix_usage_records_thread_id", "usage_records", ["thread_id"])
    op.create_index("ix_usage_records_created_at", "usage_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_records_created_at")
    op.drop_index("ix_usage_records_thread_id")
    op.drop_index("ix_usage_records_user_id")
    op.drop_table("usage_records")
    op.drop_column("chat_threads", "shared_with")
    op.drop_index("ix_shared_links_token")
    op.drop_index("ix_shared_links_thread_id")
    op.drop_table("shared_links")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_chat_messages_search_vector ON chat_messages"
    )
    op.execute("DROP FUNCTION IF EXISTS chat_messages_search_update()")
    op.drop_index("ix_chat_messages_search_vector")
    op.drop_column("chat_messages", "search_vector")
