"""tool visibility default hidden

Revision ID: toolvis_001
Revises: contact_001
Create Date: 2026-07-07

Reconciles the tools_catalog.visibility column default from 'public' to
'hidden' to match the runtime ToolMetadata default (app/tools/base.py).

Existing rows are NOT modified: Gate 1 reads visibility from the in-memory
ToolMetadata, not the DB column, so pre-existing 'public' rows are inert.
Only the column DEFAULT changes.
"""

from alembic import op

revision = "toolvis_001"
down_revision = "contact_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tools_catalog ALTER COLUMN visibility SET DEFAULT 'hidden'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE tools_catalog ALTER COLUMN visibility SET DEFAULT 'public'"
    )
