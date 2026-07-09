"""Merge GOV-1.1 head with the blog head into a single linear head.

Revision ID: gov11_merge_blog_gov11
Revises: 20260709_blog, gov11_inbox_items_nullable_mission
Create Date: 2026-07-09 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "gov11_merge_blog_gov11"
down_revision: str | Sequence[str] | None = (
    "20260709_blog",
    "gov11_inbox_items_nullable_mission",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Both branches are already applied; this only unifies the graph."""
    pass


def downgrade() -> None:
    """No schema changes to revert; splits the head again."""
    pass
