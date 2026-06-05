"""FLO-108: feedback_reports and feedback_patterns tables

Revision ID: flo108_feedback
Revises: flo79_user_custom_roles
Create Date: 2026-05-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers
revision = "flo108_feedback"
down_revision = "202605150100_add_security_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_reports",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("mission_id", UUID(as_uuid=False), sa.ForeignKey("missions.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("overall_score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("efficiency_score", sa.Float, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
        sa.Column("strengths", JSONB, nullable=True),
        sa.Column("weaknesses", JSONB, nullable=True),
        sa.Column("suggestions", JSONB, nullable=True),
        sa.Column("task_analysis", JSONB, nullable=True),
        sa.Column("error_summary", JSONB, nullable=True),
        sa.Column("token_efficiency", JSONB, nullable=True),
        sa.Column("synthesis_mode", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.create_table(
        "feedback_patterns",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("pattern_type", sa.String(50), nullable=False, index=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("frequency", sa.Integer, nullable=False, server_default="1"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("example_mission_ids", JSONB, nullable=True),
        sa.Column("suggested_fix", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("feedback_patterns")
    op.drop_table("feedback_reports")
