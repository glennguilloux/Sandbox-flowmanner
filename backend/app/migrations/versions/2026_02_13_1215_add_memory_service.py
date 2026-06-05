"""Add memory service tables

Revision ID: 2026_02_13_1215
Revises: 2026_02_11_0000
Create Date: 2026-02-13 12:15:00

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "2026_02_13_1215"
down_revision = "2026_02_11_0000"
branch_labels = None
depends_on = None


def upgrade():
    # Create memory_namespaces table
    op.create_table(
        "memory_namespaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_memory_namespaces_name", "memory_namespaces", ["name"])

    # Create agent_memories table
    op.create_table(
        "agent_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "namespace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("memory_namespaces.id"),
            nullable=True,
        ),
        sa.Column("memory_type", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("importance_score", sa.Float, default=0.5),
        sa.Column("access_count", sa.Integer, default=0),
        sa.Column("last_accessed_at", sa.DateTime, nullable=True),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("priority", sa.String(20), default="normal"),
        sa.Column("status", sa.String(20), default="active"),
        sa.Column("source_type", sa.String(100), nullable=True),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("metadata", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_agent_memories_agent_id", "agent_memories", ["agent_id"])
    op.create_index("ix_agent_memories_memory_type", "agent_memories", ["memory_type"])
    op.create_index("ix_agent_memories_status", "agent_memories", ["status"])
    op.create_index("ix_agent_memories_expires_at", "agent_memories", ["expires_at"])
    op.create_index(
        "ix_agent_memories_importance", "agent_memories", ["importance_score"]
    )
    op.create_index(
        "ix_agent_memories_source", "agent_memories", ["source_type", "source_id"]
    )

    # Create memory_associations table
    op.create_table(
        "memory_associations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_memory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_memory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_memories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("association_type", sa.String(50), nullable=False),
        sa.Column("strength", sa.Float, default=1.0),
        sa.Column("metadata", postgresql.JSONB, default={}),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_memory_associations_source", "memory_associations", ["source_memory_id"]
    )
    op.create_index(
        "ix_memory_associations_target", "memory_associations", ["target_memory_id"]
    )
    op.create_index(
        "ix_memory_associations_type", "memory_associations", ["association_type"]
    )

    # Create memory_search_index table for vector search optimization
    op.create_table(
        "memory_search_index",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "memory_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_memories.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.String), default=[]),
        sa.Column("entities", postgresql.JSONB, default=[]),
        sa.Column("last_indexed_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_memory_search_hash", "memory_search_index", ["content_hash"])
    op.create_index(
        "ix_memory_search_keywords",
        "memory_search_index",
        ["keywords"],
        postgresql_using="gin",
    )


def downgrade():
    op.drop_table("memory_search_index")
    op.drop_table("memory_associations")
    op.drop_table("agent_memories")
    op.drop_table("memory_namespaces")
