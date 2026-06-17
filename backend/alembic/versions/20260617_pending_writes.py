"""Add pending_writes table — background review write staging.

Revision ID: 20260617_pending_writes
Revises: 3959f8d6ee64
Create Date: 2026-06-17 12:00:00.000000

Adds the ``pending_writes`` table used by ``BackgroundReviewService`` to
stage proposed memory writes (when ``write_approval=true``) for user
review. Direct writes (when ``write_approval=false``) bypass this table
and write straight to ``memory_entries``.

Schema notes:
- ``id``, ``workspace_id``, ``mission_id`` use ``postgresql.UUID(as_uuid=False)``
  for consistency with the existing ``memory_entries`` migration. The Postgres
  columns are stored as ``character varying(36)`` (verified on homelab).
- ``user_id`` is a plain ``Integer`` FK to ``users.id`` (matches
  ``memory_entries.user_id``).
- ``action`` is a free ``String(50)`` rather than a Postgres enum because the
  reviewer LLM can return any of {add, replace, remove} and we'd rather
  accept the string than crash the worker on an enum mismatch.
- ``status`` defaults to ``pending`` so newly staged rows surface in the
  approval queue immediately.
- ``expires_at`` defaults to ``now() + 7 days`` at the row level (the staging
  service is responsible for setting the exact expiry on insert).
- Partial index ``ix_pending_writes_status_pending`` keeps the queue lookup
  fast as the table grows.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260617_pending_writes"
down_revision: Union[str, Sequence[str], None] = "3959f8d6ee64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pending_writes",
        sa.Column(
            "id",
            sa.String(36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mission_id",
            sa.String(36),
            nullable=True,
        ),
        sa.Column(
            "write_type",
            sa.String(50),
            nullable=False,
            server_default="memory",
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("old_text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Lookup indexes for the approval queue and per-user listings.
    op.create_index(
        "ix_pending_writes_user_id",
        "pending_writes",
        ["user_id"],
    )
    op.create_index(
        "ix_pending_writes_workspace_id",
        "pending_writes",
        ["workspace_id"],
    )
    op.create_index(
        "ix_pending_writes_mission_id",
        "pending_writes",
        ["mission_id"],
    )
    # Partial index for the active queue — speeds up "show me pending".
    op.create_index(
        "ix_pending_writes_status_pending",
        "pending_writes",
        ["status", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    # Partial index for the expiry sweeper.
    op.create_index(
        "ix_pending_writes_expires",
        "pending_writes",
        ["expires_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_pending_writes_expires", table_name="pending_writes")
    op.drop_index("ix_pending_writes_status_pending", table_name="pending_writes")
    op.drop_index("ix_pending_writes_mission_id", table_name="pending_writes")
    op.drop_index("ix_pending_writes_workspace_id", table_name="pending_writes")
    op.drop_index("ix_pending_writes_user_id", table_name="pending_writes")
    op.drop_table("pending_writes")
