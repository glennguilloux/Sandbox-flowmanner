-- Create missing tables for Flowmanner backend
-- Run this on the homelab database: psql -U flowmanner -d flowmanner -f create_missing_tables.sql

-- Subscription tiers table
CREATE TABLE IF NOT EXISTS subscription_tiers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    price_monthly FLOAT,
    missions_per_day INTEGER NOT NULL DEFAULT 5,
    missions_per_month INTEGER NOT NULL DEFAULT 150,
    max_concurrent_missions INTEGER NOT NULL DEFAULT 1,
    has_priority_support BOOLEAN NOT NULL DEFAULT FALSE,
    has_api_access BOOLEAN NOT NULL DEFAULT FALSE,
    has_custom_models BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    paypal_plan_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User subscriptions table
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tier_id INTEGER NOT NULL REFERENCES subscription_tiers(id),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    paypal_subscription_id VARCHAR(100),
    current_period_start TIMESTAMP WITH TIME ZONE,
    current_period_end TIMESTAMP WITH TIME ZONE,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Marketplace listings table
CREATE TABLE IF NOT EXISTS marketplace_listings (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    owner_id VARCHAR(36) NOT NULL,
    category_id VARCHAR(255),
    listing_type VARCHAR(50) NOT NULL DEFAULT 'template',
    config TEXT,
    price FLOAT NOT NULL DEFAULT 0,
    rating FLOAT NOT NULL DEFAULT 0,
    download_count INTEGER NOT NULL DEFAULT 0,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Marketplace categories table
CREATE TABLE IF NOT EXISTS marketplace_categories (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    icon VARCHAR(100),
    color VARCHAR(50),
    listing_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Marketplace reviews table
CREATE TABLE IF NOT EXISTS marketplace_reviews (
    id VARCHAR(36) PRIMARY KEY,
    listing_id VARCHAR(36) NOT NULL REFERENCES marketplace_listings(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    is_approved BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User installations table
CREATE TABLE IF NOT EXISTS user_installations (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    listing_id VARCHAR(36) NOT NULL REFERENCES marketplace_listings(id) ON DELETE CASCADE,
    installed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Log entries table
CREATE TABLE IF NOT EXISTS log_entries (
    id VARCHAR(36) PRIMARY KEY,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    source VARCHAR(255),
    user_id VARCHAR(36),
    session_id VARCHAR(36),
    metadata_json TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Composed capabilities table
CREATE TABLE IF NOT EXISTS composed_capabilities (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    capability_ids TEXT,
    composition_strategy VARCHAR(100),
    config TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Agent reviews table
CREATE TABLE IF NOT EXISTS agent_reviews (
    id VARCHAR(36) PRIMARY KEY,
    agent_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    rating INTEGER NOT NULL,
    review TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed default subscription tiers
INSERT INTO subscription_tiers (name, display_name, description, price_monthly, missions_per_day, missions_per_month, max_concurrent_missions, has_priority_support, has_api_access, has_custom_models)
VALUES
    ('free', 'Free', 'Basic access to FlowManner', 0, 5, 150, 1, FALSE, FALSE, FALSE),
    ('pro', 'Pro', 'Professional features for power users', 29, 50, 1500, 5, TRUE, TRUE, FALSE),
    ('enterprise', 'Enterprise', 'Full access with custom models and priority support', 99, 999, 99999, 20, TRUE, TRUE, TRUE)
ON CONFLICT (name) DO NOTHING;

-- Seed default marketplace categories
INSERT INTO marketplace_categories (id, name, description, icon, color, listing_count)
VALUES
    ('cat-template', 'Templates', 'Pre-built workflow templates', 'Layout', '#3B82F6', 0),
    ('cat-automation', 'Automation', 'Automation tools and connectors', 'Zap', '#F59E0B', 0),
    ('cat-data', 'Data', 'Data processing and transformation', 'Database', '#10B981', 0),
    ('cat-integration', 'Integration', 'Third-party integrations', 'Plug', '#8B5CF6', 0),
    ('cat-ai', 'AI', 'AI and ML powered tools', 'Brain', '#EC4899', 0)
ON CONFLICT (name) DO NOTHING;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_id ON user_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_listings_owner_id ON marketplace_listings(owner_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_listings_category_id ON marketplace_listings(category_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_reviews_listing_id ON marketplace_reviews(listing_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_reviews_user_id ON marketplace_reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_user_installations_user_id ON user_installations(user_id);
CREATE INDEX IF NOT EXISTS idx_user_installations_listing_id ON user_installations(listing_id);
CREATE INDEX IF NOT EXISTS idx_log_entries_user_id ON log_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_log_entries_level ON log_entries(level);
