"""Per-step cost attribution: add cost_category, tool_name, embedding_tokens.

Adds columns to llm_call_records that support the 6 cost categories
(llm_tokens, tool_execution, embedding, external_api, storage, browser)
and per-step drill-down queries.

Revision ID: cost_attribution_001
Revises: hitl_expiry_config_001
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cost_attribution_001"
down_revision: str | None = "hitl_expiry_config_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add cost_category, tool_name, and embedding_tokens columns."""
    op.add_column(
        "llm_call_records",
        sa.Column(
            "cost_category",
            sa.String(30),
            nullable=False,
            server_default="llm_tokens",
        ),
    )
    op.add_column(
        "llm_call_records",
        sa.Column(
            "tool_name",
            sa.String(100),
            nullable=True,
        ),
    )
    op.add_column(
        "llm_call_records",
        sa.Column(
            "embedding_tokens",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_llmcr_cost_category",
        "llm_call_records",
        ["cost_category"],
        unique=False,
    )
    # Backfill existing rows (all LLM calls default to llm_tokens).
    # The server_default handles new rows; this handles existing rows.
    op.execute(
        "UPDATE llm_call_records SET cost_category = 'llm_tokens' "
        "WHERE cost_category IS NULL"
    )


def downgrade() -> None:
    """Remove cost_category, tool_name, and embedding_tokens columns."""
    op.drop_index("ix_llmcr_cost_category", table_name="llm_call_records")
    op.drop_column("llm_call_records", "embedding_tokens")
    op.drop_column("llm_call_records", "tool_name")
    op.drop_column("llm_call_records", "cost_category")
