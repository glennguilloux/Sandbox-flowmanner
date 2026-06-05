"""Add avatar_url to users table

Revision ID: 20260521_avatar
Revises: 20260521_marketplace
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa

revision = "20260521_avatar"
down_revision = "20260521_create_teams_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
