"""evaluation tables

Revision ID: eval_001
Revises:
Create Date: 2026-05-21

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "eval_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "golden_datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("category", sa.String(50), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_table(
        "golden_test_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("golden_datasets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("input_prompt", sa.Text, nullable=False),
        sa.Column("expected_behavior", sa.Text, nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False, index=True),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("rubric", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "dataset_id",
            sa.String(36),
            sa.ForeignKey("golden_datasets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_config_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("aggregate_score", sa.Float, nullable=True),
        sa.Column("scores_by_category", postgresql.JSONB, nullable=True),
        sa.Column("per_case_scores", postgresql.JSONB, nullable=True),
        sa.Column("langfuse_trace_id", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_index("ix_eval_runs_status", "eval_runs", ["status"])
    op.create_index("ix_eval_runs_model_name", "eval_runs", ["model_name"])


def downgrade() -> None:
    op.drop_table("eval_runs")
    op.drop_table("golden_test_cases")
    op.drop_table("golden_datasets")
