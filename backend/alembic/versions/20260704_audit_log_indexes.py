"""Add missing indexes on audit_logs table.

Revision ID: audit_log_perf_001
Revises: byok_per_key_salt_001
Create Date: 2026-07-04
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "audit_log_perf_001"
down_revision = "byok_per_key_salt_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Audit logs — ORDER BY created_at DESC is the primary query pattern
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at)"
    )
    # Audit logs — user activity lookups (filter by user_id)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
