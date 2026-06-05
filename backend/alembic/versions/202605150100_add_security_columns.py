"""Database migration: Add TOTP columns to users table and device tracking to refresh_tokens."""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "202605150100_add_security_columns"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    # Add TOTP columns to users table
    op.add_column("users", sa.Column("totp_secret", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean(), nullable=True, server_default="false"),
    )
    op.add_column("users", sa.Column("totp_backup_codes", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Add device tracking columns to refresh_tokens table
    op.add_column(
        "refresh_tokens", sa.Column("device_name", sa.String(255), nullable=True)
    )
    op.add_column(
        "refresh_tokens", sa.Column("ip_address", sa.String(45), nullable=True)
    )
    op.add_column("refresh_tokens", sa.Column("user_agent", sa.Text(), nullable=True))
    op.add_column(
        "refresh_tokens",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refresh_tokens", sa.Column("location", sa.String(255), nullable=True)
    )

    # Add family_id for refresh token reuse detection
    op.add_column(
        "refresh_tokens", sa.Column("family_id", sa.String(36), nullable=True)
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("family_generation", sa.Integer(), nullable=True, server_default="0"),
    )

    # Create audit_logs table if it doesn't exist
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            action VARCHAR(100) NOT NULL,
            details TEXT,
            ip_address VARCHAR(45),
            user_id INTEGER,
            user_email VARCHAR(255),
            endpoint VARCHAR(255),
            method VARCHAR(10),
            user_agent TEXT,
            success BOOLEAN DEFAULT true,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """
    )

    # Create indexes for audit_logs
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_logs_user_action
        ON audit_logs(user_id, action, timestamp DESC)
    """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
        ON audit_logs(timestamp DESC)
    """
    )

    # Create index for refresh token family detection
    op.create_index("idx_refresh_tokens_family", "refresh_tokens", ["family_id"])


def downgrade():
    # Remove TOTP columns
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_backup_codes")
    op.drop_column("users", "totp_verified_at")

    # Remove device tracking columns
    op.drop_column("refresh_tokens", "device_name")
    op.drop_column("refresh_tokens", "ip_address")
    op.drop_column("refresh_tokens", "user_agent")
    op.drop_column("refresh_tokens", "last_used_at")
    op.drop_column("refresh_tokens", "location")
    op.drop_column("refresh_tokens", "family_id")
    op.drop_column("refresh_tokens", "family_generation")

    # Drop indexes
    op.drop_index("idx_refresh_tokens_family", table_name="refresh_tokens")

    # Note: We don't drop audit_logs table in downgrade to preserve data
