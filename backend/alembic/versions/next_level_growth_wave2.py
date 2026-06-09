"""Add http_integration_configs and http_integration_logs tables.

Revision ID: next_level_growth_wave2
Revises: next_level_growth_wave1
Create Date: 2026-06-03 13:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "next_level_growth_wave2"
down_revision: str | Sequence[str] | None = "next_level_growth_wave1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "http_integration_configs",
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
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("default_headers", postgresql.JSONB(), nullable=True),
        sa.Column("auth_type", sa.String(20), nullable=True),
        sa.Column("auth_config_encrypted", sa.Text(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
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
        "ix_http_integration_configs_user_id",
        "http_integration_configs",
        ["user_id"],
    )

    op.create_table(
        "http_integration_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("http_integration_configs.id"),
            nullable=False,
        ),
        sa.Column(
            "mission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("missions.id"),
            nullable=True,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("request_method", sa.String(10), nullable=False),
        sa.Column("request_url", sa.String(4096), nullable=False),
        sa.Column("request_headers", postgresql.JSONB(), nullable=True),
        sa.Column("request_body_preview", sa.Text(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_headers", postgresql.JSONB(), nullable=True),
        sa.Column("response_body_preview", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        "ix_http_integration_logs_integration_id",
        "http_integration_logs",
        ["integration_id"],
    )
    op.create_index(
        "ix_http_integration_logs_mission_id",
        "http_integration_logs",
        ["mission_id"],
    )
    op.create_index(
        "ix_http_integration_logs_timestamp",
        "http_integration_logs",
        ["timestamp"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_http_integration_logs_timestamp", table_name="http_integration_logs"
    )
    op.drop_index(
        "ix_http_integration_logs_mission_id", table_name="http_integration_logs"
    )
    op.drop_index(
        "ix_http_integration_logs_integration_id", table_name="http_integration_logs"
    )
    op.drop_table("http_integration_logs")
    op.drop_index(
        "ix_http_integration_configs_user_id", table_name="http_integration_configs"
    )
    op.drop_table("http_integration_configs")
