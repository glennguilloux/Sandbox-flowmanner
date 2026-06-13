"""Add community_comments table for threaded template comments.

Revision ID: add_community_comments
Revises: phase104_retarget_aux_tables
Create Date: 2026-06-10
"""

import sqlalchemy as sa

from alembic import context, op

revision = "add_community_comments"
down_revision = "phase103_drop_old_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        has_table = False
    else:
        bind = op.get_bind()
        has_table = bind.execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='community_comments')"
            )
        ).scalar()
    if has_table:
        return

    op.create_table(
        "community_comments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "template_id",
            sa.String(36),
            sa.ForeignKey("community_templates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("author_name", sa.String(100), nullable=False, server_default=""),
        sa.Column(
            "parent_id",
            sa.String(36),
            sa.ForeignKey("community_comments.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("community_comments")
