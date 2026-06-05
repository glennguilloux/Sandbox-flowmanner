"""add roadmap tables

Revision ID: roadmap_001
Revises: flo118_triggers
Create Date: 2026-05-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "roadmap_001"
down_revision = "flo118_triggers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roadmap_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="under_review"
        ),
        sa.Column("category", sa.String(64), nullable=False, server_default="general"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("vote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(128), nullable=False),
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

    op.create_table(
        "roadmap_votes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("roadmap_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("vote_type", sa.String(8), nullable=False, server_default="up"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_roadmap_votes_item_user",
        "roadmap_votes",
        ["item_id", "user_id"],
        unique=True,
    )

    op.create_table(
        "roadmap_comments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "roadmap_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("roadmap_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), nullable=True),
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

    # Seed some initial roadmap items
    op.execute(
        """
        INSERT INTO roadmap_items (id, title, description, status, category, sort_order, is_public, vote_count, created_by)
        VALUES
            (gen_random_uuid(), 'Mobile App', 'Native mobile application for iOS and Android', 'planned', 'platform', 1, true, 0, 'system'),
            (gen_random_uuid(), 'Team Collaboration', 'Real-time collaboration features for teams', 'under_review', 'feature', 2, true, 0, 'system'),
            (gen_random_uuid(), 'Custom AI Models', 'Support for custom fine-tuned AI models', 'planned', 'ai', 3, true, 0, 'system'),
            (gen_random_uuid(), 'API v2', 'Redesigned REST API with GraphQL support', 'under_review', 'platform', 4, true, 0, 'system'),
            (gen_random_uuid(), 'Workflow Marketplace', 'Community-driven workflow template marketplace', 'in_progress', 'feature', 5, true, 0, 'system')
    """
    )


def downgrade() -> None:
    op.drop_table("roadmap_comments")
    op.drop_index("ix_roadmap_votes_item_user", table_name="roadmap_votes")
    op.drop_table("roadmap_votes")
    op.drop_table("roadmap_items")
