"""Add improvement knowledge graph tables (nodes + edges)

Revision ID: 20260526_knowledge_graph
Revises: 20260525_add_oauth_token_fields
Create Date: 2026-05-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260526_knowledge_graph"
down_revision = "20260525_add_oauth_token_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Improvement knowledge nodes
    op.create_table(
        "improvement_knowledge_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("node_type", sa.String(50), nullable=False),
        sa.Column("node_key", sa.String(255), nullable=False),
        sa.Column("properties", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
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

    # Compound unique index for node_type + node_key lookups
    op.create_index(
        "ix_improvement_knowledge_nodes_type_key",
        "improvement_knowledge_nodes",
        ["node_type", "node_key"],
        unique=True,
    )

    # Improvement knowledge edges
    op.create_table(
        "improvement_knowledge_edges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("improvement_knowledge_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.String(36),
            sa.ForeignKey("improvement_knowledge_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("edge_type", sa.String(50), nullable=False),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("properties", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Indexes for edge lookups by source/target
    op.create_index(
        "ix_improvement_knowledge_edges_source_id",
        "improvement_knowledge_edges",
        ["source_id"],
    )
    op.create_index(
        "ix_improvement_knowledge_edges_target_id",
        "improvement_knowledge_edges",
        ["target_id"],
    )
    # Compound index for (source_id, edge_type) pattern in get_outgoing_edges
    op.create_index(
        "ix_improvement_knowledge_edges_source_type",
        "improvement_knowledge_edges",
        ["source_id", "edge_type"],
    )
    # Compound index for (target_id, edge_type) pattern in get_incoming_edges
    op.create_index(
        "ix_improvement_knowledge_edges_target_type",
        "improvement_knowledge_edges",
        ["target_id", "edge_type"],
    )


def downgrade() -> None:
    op.drop_table("improvement_knowledge_edges")
    op.drop_table("improvement_knowledge_nodes")
