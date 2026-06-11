"""add_missing_tables

Revision ID: add_missing_tables_001
Revises:
Create Date: 2026-05-18

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_missing_tables_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Subscription tiers table
    op.create_table(
        "subscription_tiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("price_monthly", sa.Float(), nullable=True),
        sa.Column("missions_per_day", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("missions_per_month", sa.Integer(), nullable=False, server_default="150"),
        sa.Column("max_concurrent_missions", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("has_priority_support", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_api_access", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("has_custom_models", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("paypal_plan_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscription_tiers_name", "subscription_tiers", ["name"])

    # User subscriptions table
    op.create_table(
        "user_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tier_id",
            sa.Integer(),
            sa.ForeignKey("subscription_tiers.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("paypal_subscription_id", sa.String(100), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"])

    # Marketplace listings table
    op.create_table(
        "marketplace_listings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("category_id", sa.String(255), nullable=True),
        sa.Column("listing_type", sa.String(50), nullable=False, server_default="template"),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rating", sa.Float(), nullable=False, server_default="0"),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketplace_listings_name", "marketplace_listings", ["name"])
    op.create_index("ix_marketplace_listings_owner_id", "marketplace_listings", ["owner_id"])

    # Marketplace categories table
    op.create_table(
        "marketplace_categories",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(100), nullable=True),
        sa.Column("color", sa.String(50), nullable=True),
        sa.Column("listing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # Marketplace reviews table
    op.create_table(
        "marketplace_reviews",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column(
            "listing_id",
            sa.String(36),
            sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marketplace_reviews_listing_id", "marketplace_reviews", ["listing_id"])
    op.create_index("ix_marketplace_reviews_user_id", "marketplace_reviews", ["user_id"])

    # User installations table
    op.create_table(
        "user_installations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(
            "listing_id",
            sa.String(36),
            sa.ForeignKey("marketplace_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("installed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_installations_user_id", "user_installations", ["user_id"])
    op.create_index("ix_user_installations_listing_id", "user_installations", ["listing_id"])

    # Log entries table
    op.create_table(
        "log_entries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_log_entries_level", "log_entries", ["level"])
    op.create_index("ix_log_entries_user_id", "log_entries", ["user_id"])

    # Composed capabilities table
    op.create_table(
        "composed_capabilities",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("capability_ids", sa.Text(), nullable=True),
        sa.Column("composition_strategy", sa.String(100), nullable=True),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_composed_capabilities_name", "composed_capabilities", ["name"])

    # Agent reviews table
    op.create_table(
        "agent_reviews",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # Seed default subscription tiers
    op.execute(
        """
        INSERT INTO subscription_tiers (name, display_name, description, price_monthly, missions_per_day, missions_per_month, max_concurrent_missions, has_priority_support, has_api_access, has_custom_models)
        VALUES
            ('free', 'Free', 'Basic access to FlowManner', 0, 5, 150, 1, FALSE, FALSE, FALSE),
            ('pro', 'Pro', 'Professional features for power users', 29, 50, 1500, 5, TRUE, TRUE, FALSE),
            ('enterprise', 'Enterprise', 'Full access with custom models and priority support', 99, 999, 99999, 20, TRUE, TRUE, TRUE)
        ON CONFLICT (name) DO NOTHING;
    """
    )

    # Seed default marketplace categories
    op.execute(
        """
        INSERT INTO marketplace_categories (id, name, description, icon, color, listing_count)
        VALUES
            ('cat-template', 'Templates', 'Pre-built workflow templates', 'Layout', '#3B82F6', 0),
            ('cat-automation', 'Automation', 'Automation tools and connectors', 'Zap', '#F59E0B', 0),
            ('cat-data', 'Data', 'Data processing and transformation', 'Database', '#10B981', 0),
            ('cat-integration', 'Integration', 'Third-party integrations', 'Plug', '#8B5CF6', 0),
            ('cat-ai', 'AI', 'AI and ML powered tools', 'Brain', '#EC4899', 0)
        ON CONFLICT (name) DO NOTHING;
    """
    )


def downgrade() -> None:
    op.drop_table("agent_reviews")
    op.drop_table("composed_capabilities")
    op.drop_table("log_entries")
    op.drop_table("user_installations")
    op.drop_table("marketplace_reviews")
    op.drop_table("marketplace_categories")
    op.drop_table("marketplace_listings")
    op.drop_table("user_subscriptions")
    op.drop_table("subscription_tiers")
