"""add_idempotency_tables

Revision ID: 2c8ebb094375
Revises: 20260521_orchestration
Create Date: 2026-05-21 07:51:10.489496

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2c8ebb094375"
down_revision: Union[str, Sequence[str], None] = "20260521_orchestration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create idempotency tables."""
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("is_processing", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column(
            "response_headers", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "response_body", postgresql.JSON(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cache_hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_idempotency_keys_idempotency_key",
        "idempotency_keys",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_idempotency_keys_user_id", "idempotency_keys", ["user_id"], unique=False
    )
    op.create_index(
        "ix_idempotency_keys_expires_at",
        "idempotency_keys",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "idempotency_request_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("was_cached", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_idempotency_request_logs_idempotency_key",
        "idempotency_request_logs",
        ["idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    """Drop idempotency tables."""
    op.drop_index(
        "ix_idempotency_request_logs_idempotency_key",
        table_name="idempotency_request_logs",
    )
    op.drop_table("idempotency_request_logs")
    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_user_id", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_idempotency_key", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
