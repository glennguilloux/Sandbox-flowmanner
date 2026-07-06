"""add contact_submissions

Revision ID: contact_001
Revises: 20260706_prompt_versions
Create Date: 2026-07-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "contact_001"
down_revision = "20260706_prompt_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_submissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("subject", sa.String(100), nullable=False, server_default="Sales"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="new", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("contact_submissions")
