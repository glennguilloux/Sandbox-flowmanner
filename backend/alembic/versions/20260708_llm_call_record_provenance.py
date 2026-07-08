"""add provider-fallback provenance columns to llm_call_records (Item #6)

Revision ID: 20260708_prov
Revises: d30_60_2a3
Create Date: 2026-07-08 00:00:00.000000

Item #6 from the Opus 4.8 Design-QA plan: every LLM call now carries
provenance metadata so callers know which model was requested vs served,
and whether a fallback (provider-level or model-level) occurred.

Adds three nullable columns to ``llm_call_records``:
- ``requested_model``: The model originally requested by the caller.
- ``substituted_from``: When a model-level fallback fired, the originally
  requested model_id.  NULL when no substitution occurred.
- ``degraded``: True when a fallback resulted in a different provider/model
  than requested (e.g. cloud→local).
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260708_prov"
down_revision: str | Sequence[str] | None = "d30_60_2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add provenance columns to llm_call_records."""
    op.add_column(
        "llm_call_records",
        sa.Column("requested_model", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_llm_call_records_requested_model",
        "llm_call_records",
        ["requested_model"],
        unique=False,
    )
    op.add_column(
        "llm_call_records",
        sa.Column("substituted_from", sa.Text(), nullable=True),
    )
    op.add_column(
        "llm_call_records",
        sa.Column("degraded", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index(
        "ix_llm_call_records_degraded",
        "llm_call_records",
        ["degraded"],
        unique=False,
    )


def downgrade() -> None:
    """Remove provenance columns from llm_call_records."""
    op.drop_index("ix_llm_call_records_degraded", table_name="llm_call_records")
    op.drop_column("llm_call_records", "degraded")
    op.drop_column("llm_call_records", "substituted_from")
    op.drop_index("ix_llm_call_records_requested_model", table_name="llm_call_records")
    op.drop_column("llm_call_records", "requested_model")
