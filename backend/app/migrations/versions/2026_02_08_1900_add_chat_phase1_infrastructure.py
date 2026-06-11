# mypy: disable-error-code=attr-defined
"""
Add Phase 1 Chat System Enhancement - Core Infrastructure

Phase 1: Chat System Enhancement Plan
- ChatThreadBranch: Branching hierarchy for conversation forking
- SharedLink: Public sharing system with expiration
- ChatModelSession: Track model switches per thread
- ContextSettings: User context preferences
- VoiceTranscription: Voice input history
- ExportToken: Export generation and access

Revision ID: 2026_02_08_1900
Revises: 2026_02_07_1600_add_external_model_support
Create Date: 2026-02-08 19:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "2026_02_08_1900"
down_revision = "2026_02_07_1600_add_external_model_support"
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade function to add Phase 1 chat infrastructure tables.

    Creates the following tables:
    - chat_thread_branches: Branching hierarchy for conversation forking
    - shared_links: Public sharing system with expiration
    - chat_model_sessions: Track model switches per thread
    - context_settings: User context preferences
    - voice_transcriptions: Voice input history
    - export_tokens: Export generation and access
    """

    # Create chat_thread_branches table
    # Stores branching hierarchy for conversation forking
    op.create_table(
        "chat_thread_branches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("branch_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("parent_thread_id", sa.Integer(), nullable=False, index=True),
        sa.Column("parent_message_id", sa.Integer(), nullable=True, index=True),
        sa.Column("branching_point_message_id", sa.Integer(), nullable=True),
        sa.Column("branch_title", sa.String(255), nullable=False),
        sa.Column("branch_description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True, index=True),
        sa.Column("is_active", sa.Boolean(), default=True, index=True),
        sa.Column("branch_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["parent_thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["branching_point_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )

    # Create indexes for chat_thread_branches
    op.create_index("idx_branches_branch_id", "chat_thread_branches", ["branch_id"], unique=True)
    op.create_index(
        "idx_branches_parent_thread",
        "chat_thread_branches",
        ["parent_thread_id"],
        unique=False,
    )
    op.create_index("idx_branches_created_by", "chat_thread_branches", ["created_by"], unique=False)
    op.create_index("idx_branches_active", "chat_thread_branches", ["is_active"], unique=False)

    # Create shared_links table
    # Stores public sharing links with expiration and permission levels
    op.create_table(
        "shared_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("share_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("thread_id", sa.Integer(), nullable=False, index=True),
        sa.Column("branch_id", sa.String(64), nullable=True, index=True),
        sa.Column("token", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("permission_level", sa.String(20), default="view", index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("created_by", sa.Integer(), nullable=True, index=True),
        sa.Column("view_count", sa.Integer(), default=0),
        sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, index=True),
        sa.Column("share_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["chat_thread_branches.branch_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )

    # Create indexes for shared_links
    op.create_index("idx_shared_share_id", "shared_links", ["share_id"], unique=True)
    op.create_index("idx_shared_token", "shared_links", ["token"], unique=True)
    op.create_index("idx_shared_thread", "shared_links", ["thread_id"], unique=False)
    op.create_index("idx_shared_expires", "shared_links", ["expires_at"], unique=False)
    op.create_index("idx_shared_active", "shared_links", ["is_active"], unique=False)

    # Create chat_model_sessions table
    # Tracks model switches within chat threads
    op.create_table(
        "chat_model_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("thread_id", sa.Integer(), nullable=False, index=True),
        sa.Column("model_name", sa.String(100), nullable=False, index=True),
        sa.Column("model_provider", sa.String(50), nullable=True),
        sa.Column("model_config", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_tokens", sa.Integer(), default=0),
        sa.Column("prompt_tokens", sa.Integer(), default=0),
        sa.Column("completion_tokens", sa.Integer(), default=0),
        sa.Column("cost_estimate", sa.Float(), default=0.0),
        sa.Column("is_active", sa.Boolean(), default=True, index=True),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
    )

    # Create indexes for chat_model_sessions
    op.create_index(
        "idx_model_sessions_session_id",
        "chat_model_sessions",
        ["session_id"],
        unique=True,
    )
    op.create_index("idx_model_sessions_thread", "chat_model_sessions", ["thread_id"], unique=False)
    op.create_index("idx_model_sessions_model", "chat_model_sessions", ["model_name"], unique=False)
    op.create_index("idx_model_sessions_active", "chat_model_sessions", ["is_active"], unique=False)

    # Create context_settings table
    # Stores user context preferences per thread
    op.create_table(
        "context_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("setting_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), nullable=False, index=True),
        sa.Column("thread_id", sa.Integer(), nullable=True, index=True),
        sa.Column("context_window_size", sa.Integer(), default=20),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("use_rag", sa.Boolean(), default=False),
        sa.Column("rag_collections", sa.JSON(), nullable=True),
        sa.Column("memory_enabled", sa.Boolean(), default=False),
        sa.Column("memory_important_messages", sa.JSON(), nullable=True),
        sa.Column("auto_truncate", sa.Boolean(), default=True),
        sa.Column("smart_compression", sa.Boolean(), default=False),
        sa.Column("preserve_important", sa.Boolean(), default=True),
        sa.Column("priority_messages", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
    )

    # Create indexes for context_settings
    op.create_index(
        "idx_context_settings_setting_id",
        "context_settings",
        ["setting_id"],
        unique=True,
    )
    op.create_index("idx_context_settings_user", "context_settings", ["user_id"], unique=False)
    op.create_index("idx_context_settings_thread", "context_settings", ["thread_id"], unique=False)

    # Create voice_transcriptions table
    # Stores voice input history and transcriptions
    op.create_table(
        "voice_transcriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("transcription_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("message_id", sa.Integer(), nullable=False, index=True),
        sa.Column("thread_id", sa.Integer(), nullable=True, index=True),
        sa.Column("user_id", sa.Integer(), nullable=True, index=True),
        sa.Column("audio_file_url", sa.String(512), nullable=True),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("audio_format", sa.String(20), nullable=True),
        sa.Column("transcription_text", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("language_code", sa.String(10), nullable=True),
        sa.Column("stt_provider", sa.String(50), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Create indexes for voice_transcriptions
    op.create_index(
        "idx_voice_transcription_id",
        "voice_transcriptions",
        ["transcription_id"],
        unique=True,
    )
    op.create_index("idx_voice_message", "voice_transcriptions", ["message_id"], unique=False)
    op.create_index("idx_voice_thread", "voice_transcriptions", ["thread_id"], unique=False)
    op.create_index("idx_voice_user", "voice_transcriptions", ["user_id"], unique=False)

    # Create export_tokens table
    # Tracks export generation and access
    op.create_table(
        "export_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("export_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("thread_id", sa.Integer(), nullable=False, index=True),
        sa.Column("branch_id", sa.String(64), nullable=True, index=True),
        sa.Column("created_by", sa.Integer(), nullable=True, index=True),
        sa.Column("export_format", sa.String(20), nullable=False),
        sa.Column("include_attachments", sa.Boolean(), default=False),
        sa.Column("include_metadata", sa.Boolean(), default=True),
        sa.Column("page_layout", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), default="pending", index=True),
        sa.Column("progress_percentage", sa.Integer(), default=0),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("file_url", sa.String(512), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_count", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["chat_thread_branches.branch_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )

    # Create indexes for export_tokens
    op.create_index("idx_export_export_id", "export_tokens", ["export_id"], unique=True)
    op.create_index("idx_export_thread", "export_tokens", ["thread_id"], unique=False)
    op.create_index("idx_export_status", "export_tokens", ["status"], unique=False)
    op.create_index("idx_export_expires", "export_tokens", ["expires_at"], unique=False)


def downgrade():
    """
    Downgrade function to remove Phase 1 chat infrastructure tables.
    Reverses all changes made in the upgrade function.
    """

    # Drop indexes and tables in reverse order

    # Drop export_tokens
    op.drop_index("idx_export_expires", table_name="export_tokens")
    op.drop_index("idx_export_status", table_name="export_tokens")
    op.drop_index("idx_export_thread", table_name="export_tokens")
    op.drop_index("idx_export_export_id", table_name="export_tokens")
    op.drop_table("export_tokens")

    # Drop voice_transcriptions
    op.drop_index("idx_voice_user", table_name="voice_transcriptions")
    op.drop_index("idx_voice_thread", table_name="voice_transcriptions")
    op.drop_index("idx_voice_message", table_name="voice_transcriptions")
    op.drop_index("idx_voice_transcription_id", table_name="voice_transcriptions")
    op.drop_table("voice_transcriptions")

    # Drop context_settings
    op.drop_index("idx_context_settings_thread", table_name="context_settings")
    op.drop_index("idx_context_settings_user", table_name="context_settings")
    op.drop_index("idx_context_settings_setting_id", table_name="context_settings")
    op.drop_table("context_settings")

    # Drop chat_model_sessions
    op.drop_index("idx_model_sessions_active", table_name="chat_model_sessions")
    op.drop_index("idx_model_sessions_model", table_name="chat_model_sessions")
    op.drop_index("idx_model_sessions_thread", table_name="chat_model_sessions")
    op.drop_index("idx_model_sessions_session_id", table_name="chat_model_sessions")
    op.drop_table("chat_model_sessions")

    # Drop shared_links
    op.drop_index("idx_shared_active", table_name="shared_links")
    op.drop_index("idx_shared_expires", table_name="shared_links")
    op.drop_index("idx_shared_thread", table_name="shared_links")
    op.drop_index("idx_shared_token", table_name="shared_links")
    op.drop_index("idx_shared_share_id", table_name="shared_links")
    op.drop_table("shared_links")

    # Drop chat_thread_branches
    op.drop_index("idx_branches_active", table_name="chat_thread_branches")
    op.drop_index("idx_branches_created_by", table_name="chat_thread_branches")
    op.drop_index("idx_branches_parent_thread", table_name="chat_thread_branches")
    op.drop_index("idx_branches_branch_id", table_name="chat_thread_branches")
    op.drop_table("chat_thread_branches")
