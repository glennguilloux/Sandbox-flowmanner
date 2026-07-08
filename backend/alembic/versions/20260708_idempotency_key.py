"""Add idempotency_key to substrate_events for dedup-on-write (Item #3).

Revision ID: 20260708_idem
Revises: 20260708_prov
Create Date: 2026-07-08
"""

from alembic import op
import sqlalchemy as sa

revision = "20260708_idem"
down_revision = "20260708_prov"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "substrate_events",
        sa.Column("idempotency_key", sa.String(256), nullable=True),
    )
    op.create_index(
        "ix_substrate_events_idempotency_key",
        "substrate_events",
        ["idempotency_key"],
        unique=False,
    )
    # Partial unique index: only enforce uniqueness when key is set
    op.execute(
        "CREATE UNIQUE INDEX uq_substrate_events_idempotency_key "
        "ON substrate_events(idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_substrate_events_idempotency_key")
    op.drop_index("ix_substrate_events_idempotency_key", table_name="substrate_events")
    op.drop_column("substrate_events", "idempotency_key")
