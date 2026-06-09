"""Marketplace v2 — workspace scoping, versioning, publish workflow.

Adds to marketplace_listings:
- workspace_id (FK → workspaces.id, nullable, indexed)
- status column (draft/published/deprecated, replaces is_published boolean)
- version string (e.g. '1.0.0')
- published_at timestamp

Adds to marketplace_reviews:
- title column for review headlines

Revision ID: marketplace_v2_001
Revises: ws_shares_001
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "marketplace_v2_001"
down_revision = "ws_shares_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── marketplace_listings: new columns ───────────────────────────
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "workspace_id",
            sa.String(36),
            nullable=True,
            index=True,
        ),
    )
    op.create_foreign_key(
        "fk_ml_workspace",
        "marketplace_listings",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
        ),
    )
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "version",
            sa.String(20),
            nullable=True,
            server_default="1.0.0",
        ),
    )
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index("ix_ml_status", "marketplace_listings", ["status"])
    op.create_index("ix_ml_workspace", "marketplace_listings", ["workspace_id"])

    # Backfill status from is_published boolean
    op.execute(
        """
        UPDATE marketplace_listings
        SET status = 'published', published_at = created_at
        WHERE is_published = true
    """
    )
    op.execute(
        """
        UPDATE marketplace_listings
        SET status = 'draft'
        WHERE is_published = false
    """
    )

    # ── marketplace_listings: add review_count column ──────────────
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "review_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )

    # ── marketplace_reviews: add title column ───────────────────────
    op.add_column(
        "marketplace_reviews",
        sa.Column(
            "title",
            sa.String(255),
            nullable=True,
        ),
    )

    # ── Backfill review_count from existing reviews ─────────────────
    op.execute(
        """
        UPDATE marketplace_listings ml
        SET review_count = COALESCE(sub.cnt, 0)
        FROM (
            SELECT listing_id, COUNT(*) AS cnt
            FROM marketplace_reviews
            GROUP BY listing_id
        ) sub
        WHERE ml.id = sub.listing_id
    """
    )


def downgrade() -> None:
    op.drop_column("marketplace_reviews", "title")
    op.drop_index("ix_ml_workspace", table_name="marketplace_listings")
    op.drop_index("ix_ml_status", table_name="marketplace_listings")
    op.drop_constraint("fk_ml_workspace", "marketplace_listings", type_="foreignkey")
    op.drop_column("marketplace_listings", "published_at")
    op.drop_column("marketplace_listings", "version")
    op.drop_column("marketplace_listings", "status")
    op.drop_column("marketplace_listings", "workspace_id")
