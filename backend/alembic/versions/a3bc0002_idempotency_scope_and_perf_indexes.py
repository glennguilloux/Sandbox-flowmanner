"""idempotency_scope_and_perf_indexes

Revision ID: a3bc0002
Revises: a3bc0001
Create Date: 2026-06-02 14:00:00.000000

1. Adds method column to idempotency_keys for scoped lookup
2. Replaces unique index on idempotency_key with composite scoped unique index
   on (user_id, method, endpoint, idempotency_key)
3. Adds performance indexes for hot mission/task queries (B4)
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "a3bc0002"
down_revision: str | Sequence[str] | None = "a3bc0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Idempotency scope ─────────────────────────────────────────────────
    op.add_column(
        "idempotency_keys",
        sa.Column("method", sa.String(length=10), nullable=True),
    )

    # Drop old unique index on idempotency_key alone
    op.drop_index("ix_idempotency_keys_idempotency_key", table_name="idempotency_keys")
    # Create composite scoped unique index
    op.create_index(
        "ix_idempotency_keys_scoped",
        "idempotency_keys",
        ["user_id", "method", "endpoint", "idempotency_key"],
        unique=True,
    )

    # ── Performance indexes (B4) ──────────────────────────────────────────
    # Hot path: missions by user + status (for list_active, active_missions)
    op.create_index(
        "ix_missions_user_status_not_deleted",
        "missions",
        ["user_id", "status"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Hot path: mission_tasks by mission_id + status (for progress queries)
    op.create_index(
        "ix_mission_tasks_mission_status",
        "mission_tasks",
        ["mission_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mission_tasks_mission_status", table_name="mission_tasks")
    op.drop_index("ix_missions_user_status_not_deleted", table_name="missions")
    op.drop_index("ix_idempotency_keys_scoped", table_name="idempotency_keys")
    op.create_index(
        "ix_idempotency_keys_idempotency_key",
        "idempotency_keys",
        ["idempotency_key"],
        unique=True,
    )
    op.drop_column("idempotency_keys", "method")
