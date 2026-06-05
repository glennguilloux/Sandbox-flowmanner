"""Phase 9.6: Plugin security review and runtime monitoring columns.

Revision ID: 20260603_phase96_plugin_security
Revises: 20260603_phase91_plugins
Create Date: 2026-06-03
"""

from alembic import op
import sqlalchemy as sa

revision = "20260603_phase96_plugin_security"
down_revision = "20260603_phase91_plugins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Security review columns
    op.add_column("installed_plugins", sa.Column("review_status", sa.String(20), nullable=False, server_default="pending"))
    op.create_index("ix_installed_plugins_review_status", "installed_plugins", ["review_status"])
    op.add_column("installed_plugins", sa.Column("scan_risk_score", sa.Integer, server_default="0"))
    op.add_column("installed_plugins", sa.Column("scan_result_json", sa.Text, nullable=True))
    op.add_column("installed_plugins", sa.Column("reviewed_by", sa.String(36), nullable=True))
    op.add_column("installed_plugins", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("installed_plugins", sa.Column("rejection_reason", sa.Text, nullable=True))

    # Runtime monitoring columns
    op.add_column("installed_plugins", sa.Column("p99_latency_ms", sa.Float, server_default="0"))
    op.add_column("installed_plugins", sa.Column("crash_count", sa.Integer, server_default="0"))
    op.add_column("installed_plugins", sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("installed_plugins", "last_health_check_at")
    op.drop_column("installed_plugins", "crash_count")
    op.drop_column("installed_plugins", "p99_latency_ms")
    op.drop_index("ix_installed_plugins_review_status", table_name="installed_plugins")
    op.drop_column("installed_plugins", "rejection_reason")
    op.drop_column("installed_plugins", "reviewed_at")
    op.drop_column("installed_plugins", "reviewed_by")
    op.drop_column("installed_plugins", "scan_result_json")
    op.drop_column("installed_plugins", "scan_risk_score")
    op.drop_column("installed_plugins", "review_status")
