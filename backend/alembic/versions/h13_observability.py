"""H1.3: Add llm_call_records table + mission_logs append-only trigger.

Revision ID: h13_observability
Revises: 767ad7700db4
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "h13_observability"
down_revision: Union[str, None] = "767ad7700db4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── llm_call_records table (H1.3: LLM call observability) ─────────────
    op.create_table(
        "llm_call_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="true", index=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            index=True,
        ),
    )

    # ── mission_logs append-only trigger (H1.3: append-only enforcement) ────
    op.execute("""
        CREATE OR REPLACE FUNCTION mission_logs_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'mission_logs is append-only: DELETE not allowed';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                RAISE EXCEPTION 'mission_logs is append-only: UPDATE not allowed';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_mission_logs_append_only ON mission_logs")
    op.execute("""
        CREATE TRIGGER trg_mission_logs_append_only
        BEFORE DELETE OR UPDATE ON mission_logs
        FOR EACH ROW EXECUTE FUNCTION mission_logs_append_only();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_mission_logs_append_only ON mission_logs")
    op.execute("DROP FUNCTION IF EXISTS mission_logs_append_only()")
    op.drop_table("llm_call_records")
