"""Add episodes table for sparse episodic memory.

Revision ID: episodic_memory_001
Revises: auth_v3_feature_flag_001
Create Date: 2026-06-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "episodic_memory_001"
down_revision: str | Sequence[str] | None = "auth_v3_feature_flag_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create episodes table with indexes for hybrid BM25+vector search."""
    op.create_table(
        "episodes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mission_id",
            postgresql.UUID(as_uuid=False),
            nullable=False,
        ),
        sa.Column("step_type", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("cost_bucket", sa.String(20), nullable=False),
        sa.Column("hitl_outcome", sa.String(20), nullable=True),
        sa.Column("retrieval_text", sa.Text(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(64), nullable=True),
        sa.Column(
            "embedding_model",
            sa.String(100),
            nullable=False,
            server_default="all-MiniLM-L6-v2",
        ),
        sa.Column(
            "retrieval_vector",
            postgresql.TSVECTOR(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Composite index for the common retrieval query:
    # WHERE workspace_id = ? AND user_id = ? ORDER BY created_at DESC
    op.create_index(
        "ix_episodes_ws_user_created",
        "episodes",
        ["workspace_id", "user_id", sa.text("created_at DESC")],
    )

    # Partial index on mission_id for lookups by mission
    op.execute(
        "CREATE INDEX ix_episodes_mission ON episodes (mission_id) "
        "WHERE mission_id IS NOT NULL"
    )

    # GIN index on tsvector for full-text search
    op.execute(
        "CREATE INDEX ix_episodes_tsvector ON episodes USING gin (retrieval_vector)"
    )

    # Trigger to auto-update tsvector on INSERT/UPDATE
    op.execute("""
        CREATE OR REPLACE FUNCTION episodes_tsvector_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.retrieval_vector := to_tsvector('english', NEW.retrieval_text);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER episodes_tsvector_update
        BEFORE INSERT OR UPDATE ON episodes
        FOR EACH ROW EXECUTE FUNCTION episodes_tsvector_trigger();
    """)


def downgrade() -> None:
    """Drop episodes table and related objects."""
    op.execute("DROP TRIGGER IF EXISTS episodes_tsvector_update ON episodes")
    op.execute("DROP FUNCTION IF EXISTS episodes_tsvector_trigger()")
    op.drop_index("ix_episodes_tsvector", table_name="episodes")
    op.drop_index("ix_episodes_mission", table_name="episodes")
    op.drop_index("ix_episodes_ws_user_created", table_name="episodes")
    op.drop_table("episodes")
