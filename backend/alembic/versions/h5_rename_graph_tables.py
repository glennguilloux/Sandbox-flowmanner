"""Rename graph tables to workflow tables (H4.2 consolidation).

Revision ID: h5_rename_graph_tables
Revises: h4_6_drop_cancelled_status
Create Date: 2026-06-02

Renames:
  graph_workflows    → workflows
  graph_executions   → workflow_executions
  graph_states       → workflow_states

All ForeignKey constraints are automatically updated by PostgreSQL
when tables are renamed via ALTER TABLE ... RENAME TO.

DEPLOYMENT ORDER:
  1. Run this migration FIRST (alembic upgrade head)
  2. THEN deploy code that uses the new __tablename__ values
"""
from alembic import op


revision = "h5_rename_graph_tables"
down_revision = "h4_6_drop_cancelled_status"
branch_labels = None
depends_on = None


def upgrade():
    """Rename graph-prefixed tables to workflow-prefixed names."""
    op.rename_table("graph_workflows", "workflows")
    op.rename_table("graph_executions", "workflow_executions")
    op.rename_table("graph_states", "workflow_states")


def downgrade():
    """Rename workflow-prefixed tables back to graph-prefixed names."""
    op.rename_table("workflow_states", "graph_states")
    op.rename_table("workflow_executions", "graph_executions")
    op.rename_table("workflows", "graph_workflows")
