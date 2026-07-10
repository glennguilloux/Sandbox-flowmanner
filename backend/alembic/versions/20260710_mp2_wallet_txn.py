# mypy: disable-error-code=attr-defined
"""MARKETPLACE-2 — internal wallet + transaction lifecycle tables.

Implements the buyer-side marketplace transaction lifecycle on an internal
credit wallet (NO external PSP). Two new tables:

  * ``marketplace_wallets``   — per-user USD balance
  * ``marketplace_transactions`` — audit log of purchases/refunds, full
    state machine: pending -> completed|failed; completed -> refunded.

Chains from the current head ``20260710_e43_agent_id``.

Revision ID: 20260710_mp2_wallet_txn
Revises:     20260710_e43_agent_id
Create Date: 2026-07-10 22:30:00

Forward + reversible: ``downgrade()`` drops both tables (and their indexes).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260710_mp2_wallet_txn"
down_revision = "20260710_e43_agent_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_wallets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False, unique=True),
        sa.Column("balance", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_marketplace_wallets_user_id", "marketplace_wallets", ["user_id"])

    op.create_table(
        "marketplace_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("listing_id", sa.String(36), nullable=False),
        sa.Column("amount", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("payment_ref", sa.String(128), nullable=True),
        sa.Column("refunded_from", sa.String(36), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_marketplace_transactions_user_id", "marketplace_transactions", ["user_id"]
    )
    op.create_index(
        "ix_marketplace_transactions_listing_id",
        "marketplace_transactions",
        ["listing_id"],
    )
    op.create_index(
        "ix_marketplace_transactions_refunded_from",
        "marketplace_transactions",
        ["refunded_from"],
    )


def downgrade() -> None:
    op.drop_index("ix_marketplace_transactions_refunded_from", table_name="marketplace_transactions")
    op.drop_index("ix_marketplace_transactions_listing_id", table_name="marketplace_transactions")
    op.drop_index("ix_marketplace_transactions_user_id", table_name="marketplace_transactions")
    op.drop_table("marketplace_transactions")

    op.drop_index("ix_marketplace_wallets_user_id", table_name="marketplace_wallets")
    op.drop_table("marketplace_wallets")
