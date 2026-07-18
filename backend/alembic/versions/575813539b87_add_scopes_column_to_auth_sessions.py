"""add scopes column to auth_sessions

Adds an OAuth-style ``scopes`` JSONB column to ``auth_sessions`` so that
``require_scope`` (app/api/deps.py) can gate routes on per-session scopes.
Nullable — an existing session with no scopes reads as ``None`` (→ 403 from
``require_scope``), preserving current behavior for rows created before this
migration.

Hand-authored: alembic autogenerate swept in unrelated pre-existing model/DB
drift (table drops, index churn on other tables). This migration is scoped to
the single intended change only.

Revision ID: 575813539b87
Revises: 20260717_changelog
Create Date: 2026-07-18
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "575813539b87"
down_revision: Union[str, Sequence[str], None] = "20260717_changelog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="OAuth-style scopes granted to this session; None = no scopes assigned",
        ),
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "scopes")
