# mypy: disable-error-code=attr-defined
"""
Add Phase 3 Chat System Enhancement - Branching System

Phase 3: Chat Branching System
- Branch merging: Merge branches back together
- Branch comparison: Compare different branches
- Branch hierarchy: Parent-child branch relationships
- Branch analytics: Usage and performance tracking per branch

Revision ID: 2026_02_08_2100
Revises: 2026_02_08_2000_add_chat_phase2_multimodel
Create Date: 2026-02-08 21:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "2026_02_08_2100"
down_revision = "2026_02_08_2000_add_chat_phase2_multimodel"
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade function to add Phase 3 branching system enhancements.

    Creates the following:
    - chat_branch_merges: Track branch merge history
    - chat_branch_comparisons: Store branch comparison snapshots
    - chat_branch_hierarchy: Parent-child branch relationships
    - chat_branch_analytics: Usage and performance tracking per branch

    Adds columns:
    - chat_thread_branches: merge_status, merge_destination_id, branch_order
    - chat_messages: branch_id (to track which branch a message belongs to)
    """

    # Create chat_branch_merges table
    # Tracks branch merge history and operations
    op.create_table(
        "chat_branch_merges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("merge_id", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("source_branch_id", sa.String(64), nullable=False, index=True),
        sa.Column("destination_branch_id", sa.String(64), nullable=False, index=True),
        sa.Column("merged_by", sa.Integer(), nullable=True, index=True),
        sa.Column(
            "merge_strategy", sa.String(20), default="linear", index=True
        ),  # linear, interleaved, newest
        sa.Column(
            "conflict_resolution", sa.JSON(), nullable=True
        ),  # Conflict resolution data
        sa.Column(
            "merge_status", sa.String(20), default="pending", index=True
        ),  # pending, in_progress, completed, failed
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("merge_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_branch_id"], ["chat_thread_branches.branch_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["destination_branch_id"],
            ["chat_thread_branches.branch_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["merged_by"], ["users.id"], ondelete="SET NULL"),
    )

    # Create indexes for chat_branch_merges
    op.create_index(
        "idx_branch_merges_merge_id", "chat_branch_merges", ["merge_id"], unique=True
    )
    op.create_index(
        "idx_branch_merges_source",
        "chat_branch_merges",
        ["source_branch_id"],
        unique=False,
    )
    op.create_index(
        "idx_branch_merges_destination",
        "chat_branch_merges",
        ["destination_branch_id"],
        unique=False,
    )
    op.create_index(
        "idx_branch_merges_status", "chat_branch_merges", ["merge_status"], unique=False
    )

    # Create chat_branch_comparisons table
    # Stores branch comparison snapshots for analysis
    op.create_table(
        "chat_branch_comparisons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "comparison_id", sa.String(64), unique=True, nullable=False, index=True
        ),
        sa.Column("branch_a_id", sa.String(64), nullable=False, index=True),
        sa.Column("branch_b_id", sa.String(64), nullable=False, index=True),
        sa.Column("compared_by", sa.Integer(), nullable=True, index=True),
        sa.Column(
            "comparison_type", sa.String(30), default="full", index=True
        ),  # full, messages, metrics
        sa.Column(
            "comparison_result", sa.JSON(), nullable=False
        ),  # Detailed comparison data
        sa.Column(
            "similarity_score", sa.Float(), nullable=True
        ),  # 0-1 similarity score
        sa.Column(
            "divergence_point", sa.Integer(), nullable=True
        ),  # Message ID where branches diverged
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["branch_a_id"], ["chat_thread_branches.branch_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["branch_b_id"], ["chat_thread_branches.branch_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["compared_by"], ["users.id"], ondelete="SET NULL"),
    )

    # Create indexes for chat_branch_comparisons
    op.create_index(
        "idx_branch_comparisons_comparison_id",
        "chat_branch_comparisons",
        ["comparison_id"],
        unique=True,
    )
    op.create_index(
        "idx_branch_comparisons_branch_a",
        "chat_branch_comparisons",
        ["branch_a_id"],
        unique=False,
    )
    op.create_index(
        "idx_branch_comparisons_branch_b",
        "chat_branch_comparisons",
        ["branch_b_id"],
        unique=False,
    )
    op.create_index(
        "idx_branch_comparisons_type",
        "chat_branch_comparisons",
        ["comparison_type"],
        unique=False,
    )

    # Create chat_branch_hierarchy table
    # Manages parent-child relationships between branches
    op.create_table(
        "chat_branch_hierarchy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "hierarchy_id", sa.String(64), unique=True, nullable=False, index=True
        ),
        sa.Column("parent_branch_id", sa.String(64), nullable=False, index=True),
        sa.Column("child_branch_id", sa.String(64), nullable=False, index=True),
        sa.Column("hierarchy_level", sa.Integer(), default=1),  # Depth in the tree
        sa.Column("branch_order", sa.Integer(), default=0),  # Order among siblings
        sa.Column(
            "relationship_type", sa.String(20), default="direct", index=True
        ),  # direct, merged, copied
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["parent_branch_id"], ["chat_thread_branches.branch_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["child_branch_id"], ["chat_thread_branches.branch_id"], ondelete="CASCADE"
        ),
    )

    # Create indexes for chat_branch_hierarchy
    op.create_index(
        "idx_branch_hierarchy_hierarchy_id",
        "chat_branch_hierarchy",
        ["hierarchy_id"],
        unique=True,
    )
    op.create_index(
        "idx_branch_hierarchy_parent",
        "chat_branch_hierarchy",
        ["parent_branch_id"],
        unique=False,
    )
    op.create_index(
        "idx_branch_hierarchy_child",
        "chat_branch_hierarchy",
        ["child_branch_id"],
        unique=False,
    )
    op.create_index(
        "idx_branch_hierarchy_level",
        "chat_branch_hierarchy",
        ["hierarchy_level"],
        unique=False,
    )

    # Create chat_branch_analytics table
    # Usage and performance tracking per branch
    op.create_table(
        "chat_branch_analytics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "analytics_id", sa.String(64), unique=True, nullable=False, index=True
        ),
        sa.Column("branch_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "metric_type", sa.String(30), nullable=False, index=True
        ),  # views, messages, duration, cost
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["chat_thread_branches.branch_id"], ondelete="CASCADE"
        ),
    )

    # Create indexes for chat_branch_analytics
    op.create_index(
        "idx_branch_analytics_analytics_id",
        "chat_branch_analytics",
        ["analytics_id"],
        unique=True,
    )
    op.create_index(
        "idx_branch_analytics_branch",
        "chat_branch_analytics",
        ["branch_id"],
        unique=False,
    )
    op.create_index(
        "idx_branch_analytics_type",
        "chat_branch_analytics",
        ["metric_type"],
        unique=False,
    )
    op.create_index(
        "idx_branch_analytics_recorded",
        "chat_branch_analytics",
        ["recorded_at"],
        unique=False,
    )

    # Add enhanced columns to chat_thread_branches
    op.add_column(
        "chat_thread_branches",
        sa.Column("merge_status", sa.String(20), default="none", index=True),
    )  # none, pending, merged
    op.add_column(
        "chat_thread_branches",
        sa.Column("merge_destination_id", sa.String(64), nullable=True, index=True),
    )
    op.add_column(
        "chat_thread_branches", sa.Column("branch_order", sa.Integer(), default=0)
    )
    op.add_column(
        "chat_thread_branches", sa.Column("branch_color", sa.String(7), nullable=True)
    )  # Hex color for visualization
    op.add_column(
        "chat_thread_branches", sa.Column("message_count", sa.Integer(), default=0)
    )
    op.add_column(
        "chat_thread_branches",
        sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=True),
    )

    # Add index for merge_status
    op.create_index(
        "idx_branches_merge_status",
        "chat_thread_branches",
        ["merge_status"],
        unique=False,
    )

    # Add branch_id column to chat_messages to track which branch a message belongs to
    op.add_column(
        "chat_messages",
        sa.Column("branch_id", sa.String(64), nullable=True, index=True),
    )
    op.create_index(
        "idx_chat_messages_branch", "chat_messages", ["branch_id"], unique=False
    )


def downgrade():
    """
    Downgrade function to remove Phase 3 branching system enhancements.
    Reverses all changes made in the upgrade function.
    """

    # Remove indexes and columns from chat_messages
    op.drop_index("idx_chat_messages_branch", table_name="chat_messages")
    op.drop_column("chat_messages", "branch_id")

    # Remove indexes and columns from chat_thread_branches
    op.drop_index("idx_branches_merge_status", table_name="chat_thread_branches")
    op.drop_column("chat_thread_branches", "last_accessed")
    op.drop_column("chat_thread_branches", "message_count")
    op.drop_column("chat_thread_branches", "branch_color")
    op.drop_column("chat_thread_branches", "branch_order")
    op.drop_column("chat_thread_branches", "merge_destination_id")
    op.drop_column("chat_thread_branches", "merge_status")

    # Drop chat_branch_analytics table
    op.drop_index("idx_branch_analytics_recorded", table_name="chat_branch_analytics")
    op.drop_index("idx_branch_analytics_type", table_name="chat_branch_analytics")
    op.drop_index("idx_branch_analytics_branch", table_name="chat_branch_analytics")
    op.drop_index(
        "idx_branch_analytics_analytics_id", table_name="chat_branch_analytics"
    )
    op.drop_table("chat_branch_analytics")

    # Drop chat_branch_hierarchy table
    op.drop_index("idx_branch_hierarchy_level", table_name="chat_branch_hierarchy")
    op.drop_index("idx_branch_hierarchy_child", table_name="chat_branch_hierarchy")
    op.drop_index("idx_branch_hierarchy_parent", table_name="chat_branch_hierarchy")
    op.drop_index(
        "idx_branch_hierarchy_hierarchy_id", table_name="chat_branch_hierarchy"
    )
    op.drop_table("chat_branch_hierarchy")

    # Drop chat_branch_comparisons table
    op.drop_index("idx_branch_comparisons_type", table_name="chat_branch_comparisons")
    op.drop_index(
        "idx_branch_comparisons_branch_b", table_name="chat_branch_comparisons"
    )
    op.drop_index(
        "idx_branch_comparisons_branch_a", table_name="chat_branch_comparisons"
    )
    op.drop_index(
        "idx_branch_comparisons_comparison_id", table_name="chat_branch_comparisons"
    )
    op.drop_table("chat_branch_comparisons")

    # Drop chat_branch_merges table
    op.drop_index("idx_branch_merges_status", table_name="chat_branch_merges")
    op.drop_index("idx_branch_merges_destination", table_name="chat_branch_merges")
    op.drop_index("idx_branch_merges_source", table_name="chat_branch_merges")
    op.drop_index("idx_branch_merges_merge_id", table_name="chat_branch_merges")
    op.drop_table("chat_branch_merges")
