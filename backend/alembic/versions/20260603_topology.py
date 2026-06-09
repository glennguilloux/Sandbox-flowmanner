"""Add topology_snapshots, topology_nodes, topology_edges tables.

Moves topology from filesystem graph.json to Postgres-native storage.
The existing TopologyManager will be updated (Phase 2.4) to read
from these tables.

Revision ID: 20260603_topology
Revises: 20260603_materialization_state
Create Date: 2026-06-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260603_topology"
down_revision: Union[str, Sequence[str], None] = "20260603_materialization_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── topology_snapshots ───────────────────────────────────────────
    op.create_table(
        "topology_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("node_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("edge_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("community_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column(
            "source",
            sa.String(50),
            server_default="computed",
            comment="'computed', 'imported', 'manual'",
        ),
        sa.Column(
            "snapshot_data",
            postgresql.JSONB(),
            nullable=False,
            comment="Full topology graph (nodes + edges) as JSON",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── topology_nodes ──────────────────────────────────────────────
    op.create_table(
        "topology_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("label", sa.String(500), nullable=True),
        sa.Column(
            "node_type",
            sa.String(100),
            nullable=True,
            comment="'agent', 'capability', 'workflow', 'tool', etc.",
        ),
        sa.Column("community_id", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "derived_from_agent_id",
            sa.String(36),
            nullable=True,
            comment="FK to agents.id",
        ),
        sa.Column(
            "derived_from_capability_id",
            sa.String(36),
            nullable=True,
            comment="FK to capabilities_catalog.id",
        ),
        sa.Column(
            "derived_from_workflow_id",
            sa.String(36),
            nullable=True,
            comment="FK to workflows.id",
        ),
        sa.Column("confidence", sa.Float(), server_default=sa.text("1.0")),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_topo_nodes_snapshot", "topology_nodes", ["snapshot_id"])

    # ── topology_edges ──────────────────────────────────────────────
    op.create_table(
        "topology_edges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_id", sa.String(36), nullable=False),
        sa.Column("source_node_id", sa.String(36), nullable=False),
        sa.Column("target_node_id", sa.String(36), nullable=False),
        sa.Column(
            "relation",
            sa.String(100),
            server_default="calls",
            comment="'calls', 'depends-on', 'data-flow', etc.",
        ),
        sa.Column(
            "confidence",
            sa.String(50),
            server_default="INFERRED",
            comment="'INFERRED', 'OBSERVED', 'DECLARED'",
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_topo_edges_snapshot", "topology_edges", ["snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_topo_edges_snapshot", table_name="topology_edges")
    op.drop_table("topology_edges")
    op.drop_index("ix_topo_nodes_snapshot", table_name="topology_nodes")
    op.drop_table("topology_nodes")
    op.drop_table("topology_snapshots")
