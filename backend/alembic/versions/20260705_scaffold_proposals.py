"""scaffold_proposals + scaffold_versions tables (AutoMem Phase 2).

Revision ID: 20260705_scaffold_proposals
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID

# revision identifiers, used by Alembic.
revision = "20260705_scaffold_proposals"
down_revision = "20260704_memory_action_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create both tables WITHOUT cross-FKs first ──────────────────
    # Circular FK: scaffold_versions.source_proposal_id → scaffold_proposals.id
    #              scaffold_proposals.applied_version_id → scaffold_versions.id
    # Solution: create both tables with only self-referencing FKs, then
    # add the cross-FKs via op.create_foreign_key().

    op.create_table(
        "scaffold_versions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_proposal_id", UUID(as_uuid=False), nullable=True),
        sa.Column("parent_version_id", UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        # Only self-ref FK now; cross-FK added below
        sa.ForeignKeyConstraint(["parent_version_id"], ["scaffold_versions.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "scaffold_proposals",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("agent_id", sa.String(255), nullable=False),
        sa.Column("current_prompt_hash", sa.String(64), nullable=False),
        sa.Column("proposed_prompt", sa.Text(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("changes_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("expected_impact", sa.Text(), nullable=False, server_default=""),
        sa.Column("validation_metrics", JSONB, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_version_id", UUID(as_uuid=False), nullable=True),
        sa.Column("trace_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("meta_model", sa.String(100), nullable=False, server_default="'llamacpp-qwen3.6-27b'"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        # Cross-FK added below
    )

    # ── Now add the cross-FKs ───────────────────────────────────────
    op.create_foreign_key(
        "fk_scaffold_versions_source_proposal",
        "scaffold_versions",
        "scaffold_proposals",
        ["source_proposal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_scaffold_proposals_applied_version",
        "scaffold_proposals",
        "scaffold_versions",
        ["applied_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── Indexes ─────────────────────────────────────────────────────
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_scaffold_versions_agent_version "
        "ON scaffold_versions (agent_id, version)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scaffold_versions_agent_active "
        "ON scaffold_versions (agent_id, is_active) WHERE is_active = true"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scaffold_proposals_agent_status "
        "ON scaffold_proposals (agent_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scaffold_proposals_status_created "
        "ON scaffold_proposals (status, created_at)"
    )


def downgrade() -> None:
    # Drop cross-FKs first, then tables (reverse of upgrade order)
    op.drop_constraint("fk_scaffold_proposals_applied_version", "scaffold_proposals", type_="foreignkey")
    op.drop_constraint("fk_scaffold_versions_source_proposal", "scaffold_versions", type_="foreignkey")
    op.drop_table("scaffold_proposals")
    op.drop_table("scaffold_versions")
