"""
Migration: add_user_api_keys_table

Adds the user_api_keys table for encrypted API key storage.
"""

from datetime import datetime

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision = "2026_02_11_0000"
down_revision = "2026_02_08_2200"  # Points to the last migration
branch_labels = None
depends_on = None


def upgrade():
    # Create user_api_keys table
    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("key_name", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), default=datetime.utcnow),
        sa.Column("updated_at", sa.DateTime(), onupdate=datetime.utcnow),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_user_provider", "user_id", "provider"),
    )

    # Add api_keys relationship column to users table is handled by ORM, not migration
    # The relationship is defined in models.py but doesn't require a DB column


def downgrade():
    op.drop_table("user_api_keys")
