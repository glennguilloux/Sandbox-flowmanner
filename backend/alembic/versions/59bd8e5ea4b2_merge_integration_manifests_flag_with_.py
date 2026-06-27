"""merge integration_manifests_flag with fix_playground_ws_fk_type

Revision ID: 59bd8e5ea4b2
Revises: integration_manifests_flag_001, fix_playground_ws_fk_type
Create Date: 2026-06-27 10:12:27.286836

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "59bd8e5ea4b2"
down_revision: str | Sequence[str] | None = ("integration_manifests_flag_001", "fix_playground_ws_fk_type")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
