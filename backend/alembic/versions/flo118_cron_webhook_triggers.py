"""FLO-118: mission_triggers and trigger_logs tables

Revision ID: flo118_triggers
Revises: flo108_feedback
Create Date: 2026-05-16
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers
revision = "flo118_triggers"
down_revision = "flo108_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mission_triggers",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column(
            "mission_id",
            UUID(as_uuid=True),
            sa.ForeignKey("missions.id"),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("cron_expression", sa.String(100), nullable=True),
        sa.Column("cron_timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("webhook_path", sa.String(255), nullable=True, unique=True),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("fire_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_mission_triggers_status", "mission_triggers", ["status"])
    op.create_index("ix_mission_triggers_next_fire_at", "mission_triggers", ["next_fire_at"])

    op.create_table(
        "trigger_logs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "trigger_id",
            UUID(as_uuid=True),
            sa.ForeignKey("mission_triggers.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("mission_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("webhook_signature_valid", sa.Boolean, nullable=True),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_trigger_logs_fired_at", "trigger_logs", ["fired_at"])


def downgrade() -> None:
    op.drop_table("trigger_logs")
    op.drop_table("mission_triggers")
