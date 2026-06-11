"""Add user_oauth_apps and user_oauth_connections tables.

Revision ID: next_level_growth_wave3_oauth
Revises: merge_wave2_heads
Create Date: 2026-06-03 15:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "next_level_growth_wave3_oauth"
down_revision: str | Sequence[str] | None = "merge_wave2_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_oauth_apps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("encrypted_client_id", sa.Text(), nullable=False),
        sa.Column("encrypted_client_secret", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_oauth_apps_user_id",
        "user_oauth_apps",
        ["user_id"],
    )
    op.create_index(
        "ix_user_oauth_apps_provider",
        "user_oauth_apps",
        ["provider"],
    )

    op.create_table(
        "user_oauth_connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column(
            "app_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_oauth_apps.id"),
            nullable=False,
        ),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_type", sa.String(50), nullable=True, server_default="Bearer"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_account_id", sa.String(255), nullable=True),
        sa.Column("provider_account_name", sa.String(255), nullable=True),
        sa.Column("scopes", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_oauth_connections_user_id",
        "user_oauth_connections",
        ["user_id"],
    )
    op.create_index(
        "ix_user_oauth_connections_app_id",
        "user_oauth_connections",
        ["app_id"],
    )
    op.create_index(
        "ix_user_oauth_connections_provider",
        "user_oauth_connections",
        ["provider"],
    )
    op.create_index(
        "ix_user_oauth_connections_status",
        "user_oauth_connections",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_oauth_connections_status", table_name="user_oauth_connections")
    op.drop_index("ix_user_oauth_connections_provider", table_name="user_oauth_connections")
    op.drop_index("ix_user_oauth_connections_app_id", table_name="user_oauth_connections")
    op.drop_index("ix_user_oauth_connections_user_id", table_name="user_oauth_connections")
    op.drop_table("user_oauth_connections")
    op.drop_index("ix_user_oauth_apps_provider", table_name="user_oauth_apps")
    op.drop_index("ix_user_oauth_apps_user_id", table_name="user_oauth_apps")
    op.drop_table("user_oauth_apps")
