# mypy: disable-error-code=attr-defined
"""
Add Phase 4 Chat System Enhancement - Sharing & Export System

Phase 4: Sharing & Export System
- Public links: Time-limited access tokens
- Permission levels: view, comment, full access
- Expiration management: Configurable TTL
- Share analytics: View count, engagement tracking
- Revoke access: Instant access removal
- Export system: PDF, Markdown, JSON formats
- Real-time generation: Background processing
- Export progress: Status tracking UI

Revision ID: 2026_02_08_2200
Revises: 2026_02_08_2100_add_chat_phase3_branching
Create Date: 2026-02-08 22:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "2026_02_08_2200"
down_revision = "2026_02_08_2100_add_chat_phase3_branching"
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade function to add Phase 4 sharing and export system.

    Creates the following:
    - shared_links: Public sharing links with time-limited access
    - export_tokens: Export generation tracking
    - share_analytics: Share link view and engagement tracking
    - export_analytics: Export generation statistics

    Additional features:
    - Share password protection
    - Custom share URLs
    - Export templates
    - Batch export capabilities
    """

    # Create shared_links table
    # Public sharing links with time-limited access
    op.create_table(
        "shared_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("share_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("thread_id", sa.Integer(), nullable=False, index=True),
        sa.Column("branch_id", sa.String(64), nullable=True, index=True),
        sa.Column("token", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("permission_level", sa.String(20), default="view", index=True),  # view, comment, full
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("created_by", sa.Integer(), nullable=True, index=True),
        sa.Column("view_count", sa.Integer(), default=0),
        sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, index=True),
        sa.Column("share_metadata", sa.JSON(), nullable=True),  # Additional share settings
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["chat_thread_branches.branch_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )

    # Create indexes for shared_links
    op.create_index("idx_shared_links_share_id", "shared_links", ["share_id"], unique=True)
    op.create_index("idx_shared_links_token", "shared_links", ["token"], unique=True)
    op.create_index("idx_shared_links_thread", "shared_links", ["thread_id"], unique=False)
    op.create_index("idx_shared_links_expires", "shared_links", ["expires_at"], unique=False)
    op.create_index("idx_shared_links_active", "shared_links", ["is_active"], unique=False)

    # Create share_analytics table
    # Track view and engagement metrics for shared links
    op.create_table(
        "share_analytics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analytics_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("share_id", sa.String(64), nullable=False, index=True),
        sa.Column("event_type", sa.String(30), nullable=False, index=True),  # view, access, download, share
        sa.Column("viewer_info", sa.JSON(), nullable=True),  # IP, user agent, location
        sa.Column("access_duration", sa.Integer(), nullable=True),  # Time spent in seconds
        sa.Column("messages_viewed", sa.Integer(), default=0),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["share_id"], ["shared_links.share_id"], ondelete="CASCADE"),
    )

    # Create indexes for share_analytics
    op.create_index(
        "idx_share_analytics_analytics_id",
        "share_analytics",
        ["analytics_id"],
        unique=True,
    )
    op.create_index("idx_share_analytics_share", "share_analytics", ["share_id"], unique=False)
    op.create_index("idx_share_analytics_event", "share_analytics", ["event_type"], unique=False)
    op.create_index("idx_share_analytics_recorded", "share_analytics", ["recorded_at"], unique=False)

    # Create export_tokens table
    # Export generation tracking for PDF, Markdown, JSON formats
    op.create_table(
        "export_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("export_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("thread_id", sa.Integer(), nullable=False, index=True),
        sa.Column("branch_id", sa.String(64), nullable=True, index=True),
        sa.Column("created_by", sa.Integer(), nullable=True, index=True),
        sa.Column("export_format", sa.String(20), nullable=False, index=True),  # pdf, markdown, json
        sa.Column("include_attachments", sa.Boolean(), default=False),
        sa.Column("include_metadata", sa.Boolean(), default=True),
        sa.Column("page_layout", sa.String(20), default="default"),  # default, compact, detailed
        sa.Column("status", sa.String(20), default="pending", index=True),  # pending, processing, completed, failed
        sa.Column("progress_percentage", sa.Integer(), default=0),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("file_url", sa.String(512), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),  # Size in bytes
        sa.Column("checksum", sa.String(64), nullable=True),  # MD5/SHA256 hash
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("download_count", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["chat_thread_branches.branch_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )

    # Create indexes for export_tokens
    op.create_index("idx_export_tokens_export_id", "export_tokens", ["export_id"], unique=True)
    op.create_index("idx_export_tokens_thread", "export_tokens", ["thread_id"], unique=False)
    op.create_index("idx_export_tokens_format", "export_tokens", ["export_format"], unique=False)
    op.create_index("idx_export_tokens_status", "export_tokens", ["status"], unique=False)
    op.create_index("idx_export_tokens_expires", "export_tokens", ["expires_at"], unique=False)
    op.create_index("idx_export_tokens_created", "export_tokens", ["created_at"], unique=False)

    # Create export_analytics table
    # Export generation statistics and performance tracking
    op.create_table(
        "export_analytics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("analytics_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("export_id", sa.String(64), nullable=False, index=True),
        sa.Column("event_type", sa.String(30), nullable=False, index=True),  # start, progress, complete, fail, download
        sa.Column("progress_detail", sa.JSON(), nullable=True),  # Detailed progress information
        sa.Column("duration_ms", sa.Integer(), nullable=True),  # Processing duration
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["export_id"], ["export_tokens.export_id"], ondelete="CASCADE"),
    )

    # Create indexes for export_analytics
    op.create_index(
        "idx_export_analytics_analytics_id",
        "export_analytics",
        ["analytics_id"],
        unique=True,
    )
    op.create_index("idx_export_analytics_export", "export_analytics", ["export_id"], unique=False)
    op.create_index("idx_export_analytics_event", "export_analytics", ["event_type"], unique=False)
    op.create_index(
        "idx_export_analytics_recorded",
        "export_analytics",
        ["recorded_at"],
        unique=False,
    )

    # Add share settings columns to chat_threads for default sharing
    op.add_column("chat_threads", sa.Column("default_share_enabled", sa.Boolean(), default=False))
    op.add_column(
        "chat_threads",
        sa.Column("default_share_token", sa.String(64), nullable=True, unique=True),
    )
    op.add_column(
        "chat_threads",
        sa.Column("default_share_permission", sa.String(20), default="view"),
    )
    op.add_column(
        "chat_threads",
        sa.Column("default_share_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create index for default_share_token
    op.create_index(
        "idx_threads_default_share_token",
        "chat_threads",
        ["default_share_token"],
        unique=True,
    )


def downgrade():
    """
    Downgrade function to remove Phase 4 sharing and export system.
    Reverses all changes made in the upgrade function.
    """

    # Remove indexes and columns from chat_threads
    op.drop_index("idx_threads_default_share_token", table_name="chat_threads")
    op.drop_column("chat_threads", "default_share_expires_at")
    op.drop_column("chat_threads", "default_share_permission")
    op.drop_column("chat_threads", "default_share_token")
    op.drop_column("chat_threads", "default_share_enabled")

    # Drop export_analytics table
    op.drop_index("idx_export_analytics_recorded", table_name="export_analytics")
    op.drop_index("idx_export_analytics_event", table_name="export_analytics")
    op.drop_index("idx_export_analytics_export", table_name="export_analytics")
    op.drop_index("idx_export_analytics_analytics_id", table_name="export_analytics")
    op.drop_table("export_analytics")

    # Drop export_tokens table
    op.drop_index("idx_export_tokens_created", table_name="export_tokens")
    op.drop_index("idx_export_tokens_expires", table_name="export_tokens")
    op.drop_index("idx_export_tokens_status", table_name="export_tokens")
    op.drop_index("idx_export_tokens_format", table_name="export_tokens")
    op.drop_index("idx_export_tokens_thread", table_name="export_tokens")
    op.drop_index("idx_export_tokens_export_id", table_name="export_tokens")
    op.drop_table("export_tokens")

    # Drop share_analytics table
    op.drop_index("idx_share_analytics_recorded", table_name="share_analytics")
    op.drop_index("idx_share_analytics_event", table_name="share_analytics")
    op.drop_index("idx_share_analytics_share", table_name="share_analytics")
    op.drop_index("idx_share_analytics_analytics_id", table_name="share_analytics")
    op.drop_table("share_analytics")

    # Drop shared_links table
    op.drop_index("idx_shared_links_active", table_name="shared_links")
    op.drop_index("idx_shared_links_expires", table_name="shared_links")
    op.drop_index("idx_shared_links_thread", table_name="shared_links")
    op.drop_index("idx_shared_links_token", table_name="shared_links")
    op.drop_index("idx_shared_links_share_id", table_name="shared_links")
    op.drop_table("shared_links")
