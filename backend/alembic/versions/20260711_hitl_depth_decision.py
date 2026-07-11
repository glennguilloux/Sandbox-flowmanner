# mypy: disable-error-code=attr-defined
"""HITL inbox — add depth_decision JSONB column (GOLD t_002875da).

Carries the adaptive-reasoning-depth policy decision (level/reason/
hitl_reason) on each inbox item so the HITL inbox UI can show *why* a
human interrupt was raised.  The column is nullable — existing inbox
rows simply report ``depth_decision = NULL`` and the UI falls back to
no reasoning.  No backfill/sentinel UPDATE is required.

Forward + reversible: ``downgrade()`` drops the column.

Chains from the current live head ``20260710_mp2_wallet_txn``.

Revision ID: 20260711_hitl_depth_decision
Revises:     20260710_mp2_wallet_txn
Create Date: 2026-07-11 18:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260711_hitl_depth_decision"
down_revision = "20260710_mp2_wallet_txn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbox_items",
        sa.Column(
            "depth_decision",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Adaptive-reasoning-depth decision that motivated the "
                "interrupt: {level, reason, escalate_to_hitl, hitl_reason, "
                "policy_version, estimated_reflection_iterations}. "
                "Mirrors app.models.depth_models.DepthDecision."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("inbox_items", "depth_decision")
