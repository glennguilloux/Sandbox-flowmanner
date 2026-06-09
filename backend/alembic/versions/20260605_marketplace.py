"""Normalize marketplace_listings — artifact references + category FK.

Adds:
- ``artifact_type`` column (enum-like: 'tool', 'capability', 'agent_template', 'workflow')
- ``artifact_id`` — FK to the canonical catalog table row
- ``artifact_version_id`` — FK to the version snapshot row
- ``slug`` column on marketplace_categories
- Proper FK on ``category_id`` → ``marketplace_categories.id``

Handles existing marketplace_categories table which has columns:
id, name, description, icon, color, listing_count, created_at, updated_at.
Existing category IDs: cat-template, cat-automation, cat-data, cat-integration, cat-ai.
Existing listing category_ids are freeform strings like 'AI/ML', 'Automation', etc.

Revision ID: 20260605_marketplace
Revises: 20260605_workflow_versions
Create Date: 2026-06-05 12:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260605_marketplace"
down_revision: str | Sequence[str] | None = "20260605_workflow_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Existing category IDs from the DB
CATEGORY_MAP = {
    "AI/ML": "cat-ai",
    "AI": "cat-ai",
    "Automation": "cat-automation",
    "Data": "cat-data",
    "Integration": "cat-integration",
    "Integrations": "cat-integration",
    "Templates": "cat-template",
    "Template": "cat-template",
    "Agents": "cat-ai",
    "Tools": "cat-integration",
    "DevOps": "cat-automation",
    "Workflow": "cat-automation",
    "Workflows": "cat-automation",
}


def upgrade() -> None:
    # ── marketplace_categories: add slug column ─────────────────────
    op.add_column(
        "marketplace_categories",
        sa.Column(
            "slug",
            sa.String(255),
            nullable=True,
        ),
    )
    # Backfill slug from name
    op.execute(
        """
        UPDATE marketplace_categories
        SET slug = LOWER(REPLACE(REPLACE(name, ' ', '-'), '_', '-'))
        WHERE slug IS NULL
    """
    )
    op.create_unique_constraint("uq_mc_slug", "marketplace_categories", ["slug"])

    # ── marketplace_listings: add new columns ───────────────────────
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "artifact_type",
            sa.String(50),
            nullable=True,
            comment="'tool', 'capability', 'agent_template', 'workflow'",
        ),
    )
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "artifact_id",
            sa.String(36),
            nullable=True,
            comment="FK to the canonical catalog table row",
        ),
    )
    op.add_column(
        "marketplace_listings",
        sa.Column(
            "artifact_version_id",
            sa.String(36),
            nullable=True,
            comment="FK to the version snapshot row",
        ),
    )

    # ── Indexes on new columns ──────────────────────────────────────
    op.create_index("ix_ml_artifact_type", "marketplace_listings", ["artifact_type"])
    op.create_index("ix_ml_artifact_id", "marketplace_listings", ["artifact_id"])

    # ── Normalize category_id to match existing category IDs ────────
    for freeform, target_id in CATEGORY_MAP.items():
        op.execute(
            sa.text(
                "UPDATE marketplace_listings SET category_id = :target WHERE LOWER(category_id) = LOWER(:freeform)"
            ).bindparams(target=target_id, freeform=freeform)
        )

    # Catch remaining unknown values and NULLs → cat-ai as default
    op.execute(
        sa.text(
            """
        UPDATE marketplace_listings
        SET category_id = 'cat-ai'
        WHERE category_id IS NULL
           OR category_id NOT IN (
            SELECT id FROM marketplace_categories
        )
    """
        )
    )

    # ── Add FK constraint on category_id ────────────────────────────
    op.create_foreign_key(
        "fk_ml_category",
        "marketplace_listings",
        "marketplace_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_ml_category", "marketplace_listings", type_="foreignkey")
    op.drop_index("ix_ml_artifact_id", table_name="marketplace_listings")
    op.drop_index("ix_ml_artifact_type", table_name="marketplace_listings")
    op.drop_column("marketplace_listings", "artifact_version_id")
    op.drop_column("marketplace_listings", "artifact_id")
    op.drop_column("marketplace_listings", "artifact_type")
    op.drop_constraint("uq_mc_slug", "marketplace_categories", type_="unique")
    op.drop_column("marketplace_categories", "slug")
