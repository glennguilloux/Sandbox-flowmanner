"""Add performance indexes for frequently queried tables

Revision ID: 20260521_perf_indexes
Revises: 20260521_missing_tables
Create Date: 2026-05-21
"""

from alembic import op

revision = "20260521_perf_indexes"
down_revision = "20260521_missing_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Agents — queried by owner
    op.create_index("ix_agents_owner_id", "agents", ["owner_id"])

    # Graph executions — queried by workflow and status
    op.create_index("ix_graph_executions_workflow_id", "graph_executions", ["workflow_id"])
    op.create_index("ix_graph_executions_status", "graph_executions", ["status"])
    op.create_index("ix_graph_executions_user_id", "graph_executions", ["user_id"])

    # Graph states — queried by workflow
    op.create_index("ix_graph_states_workflow_id", "graph_states", ["workflow_id"])

    # Graph workflows — queried by owner
    op.create_index("ix_graph_workflows_user_id", "graph_workflows", ["user_id"])

    # Roadmap items — queried by status
    op.create_index("ix_roadmap_items_status", "roadmap_items", ["status"])

    # Roadmap comments — queried by item
    op.create_index("ix_roadmap_comments_roadmap_item_id", "roadmap_comments", ["roadmap_item_id"])

    # Agent reviews — queried by agent
    op.create_index("ix_agent_reviews_agent_id", "agent_reviews", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_reviews_agent_id")
    op.drop_index("ix_roadmap_comments_roadmap_item_id")
    op.drop_index("ix_roadmap_items_status")
    op.drop_index("ix_graph_workflows_user_id")
    op.drop_index("ix_graph_states_workflow_id")
    op.drop_index("ix_graph_executions_user_id")
    op.drop_index("ix_graph_executions_status")
    op.drop_index("ix_graph_executions_workflow_id")
    op.drop_index("ix_agents_owner_id")
