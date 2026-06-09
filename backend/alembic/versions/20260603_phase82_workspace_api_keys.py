"""Phase 8.2: Add workspace_id to user_api_keys.

Revision ID: phase82_workspace_api_keys
Revises: (latest)
"""

import sqlalchemy as sa

from alembic import op

revision = "phase82_workspace_api_keys"
down_revision = "phase6_hitl_cost_cb"
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_api_keys", sa.Column("workspace_id", sa.String(36), nullable=True)
    )
    op.create_index("ix_user_api_keys_workspace", "user_api_keys", ["workspace_id"])
    op.create_index(
        "ix_user_api_keys_workspace_user", "user_api_keys", ["workspace_id", "user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_api_keys_workspace_user", table_name="user_api_keys")
    op.drop_index("ix_user_api_keys_workspace", table_name="user_api_keys")
    op.drop_column("user_api_keys", "workspace_id")
