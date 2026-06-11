"""auth_v3_init — sessions, api_keys, webhook subscriptions, OIDC configs

Revision ID: auth_v3_001
Revises: 9ebabc12fb98
Create Date: 2026-06-01
"""

import sqlalchemy as sa

from alembic import op

revision = "auth_v3_001"
down_revision = "9ebabc12fb98"
branch_labels = None
depends_on = None


def upgrade():
    # ── Table 1: auth_sessions (replaces implicit refresh_tokens session tracking) ──
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "refresh_token_hash",
            sa.String(64),
            nullable=False,
            comment="SHA-256 of the refresh token — never store plaintext",
        ),
        sa.Column("device_name", sa.String(255), nullable=True),
        sa.Column("device_os", sa.String(100), nullable=True),
        sa.Column("browser", sa.String(100), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Updated ONLY on token refresh, NOT on every access-token validation",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoke_reason",
            sa.String(100),
            nullable=True,
            comment="user_logout, password_change, admin_revoke, reuse_detected",
        ),
        sa.Column("family_id", sa.String(36), nullable=True, index=True),
        sa.Column("family_generation", sa.Integer(), default=0),
        sa.Index("ix_auth_sessions_user_active", "user_id", "is_active"),
    )

    # ── Table 2: auth_api_keys ──
    op.create_table(
        "auth_api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "key_prefix",
            sa.String(8),
            nullable=False,
            comment="First 8 chars of the full key — visible to user",
        ),
        sa.Column(
            "key_hash",
            sa.String(64),
            nullable=False,
            unique=True,
            comment="SHA-256 of full API key",
        ),
        sa.Column(
            "scopes",
            sa.Text(),
            nullable=True,
            comment='JSON array: ["missions:read", "missions:write"]',
        ),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index("ix_api_keys_user", "user_id", "is_active"),
    )

    # ── Table 3: auth_webhook_subscriptions ──
    op.create_table(
        "auth_webhook_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column(
            "secret",
            sa.String(64),
            nullable=False,
            comment="HMAC-SHA256 signing secret (64 hex chars)",
        ),
        sa.Column(
            "events",
            sa.Text(),
            nullable=False,
            comment='JSON array of event types: ["session.created", "session.revoked"]',
        ),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), default=0),
        sa.Index("ix_webhook_sub_workspace", "workspace_id", "is_active"),
    )

    # ── Table 4: oidc_provider_configs (workspace-scoped OIDC providers) ──
    # NOTE: existing oidc_providers table is system-level (in auth_models.py).
    # This new table is workspace-scoped for Enterprise SSO.
    op.create_table(
        "oidc_provider_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "provider_type",
            sa.String(50),
            nullable=False,
            comment="google, github, microsoft, okta, custom",
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("issuer_url", sa.String(500), nullable=True),
        sa.Column("client_id", sa.String(500), nullable=False),
        sa.Column(
            "client_secret_encrypted",
            sa.LargeBinary(),
            nullable=False,
            comment="AES-256 encrypted client secret",
        ),
        sa.Column("scopes", sa.String(500), default="openid email profile"),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Seed feature flags ──
    op.execute(
        """
        INSERT INTO feature_flags ("key", name, description, enabled_globally, created_at, updated_at)
        VALUES
            ('AUTH_V3_COOKIES', 'Auth v3 httpOnly Cookies',
             'Use httpOnly cookies for refresh tokens', false, NOW(), NOW()),
            ('AUTH_V3_SESSIONS', 'Auth v3 Session Management',
             'Enable session list and revoke endpoints', false, NOW(), NOW()),
            ('AUTH_V3_API_KEYS', 'Auth v3 API Keys',
             'Enable scoped API key CRUD', false, NOW(), NOW()),
            ('AUTH_V3_OIDC', 'Auth v3 OIDC Providers',
             'Enable workspace-scoped OIDC SSO', false, NOW(), NOW()),
            ('AUTH_V3_WEBHOOKS', 'Auth v3 Webhooks',
             'Enable auth event webhooks', false, NOW(), NOW()),
            ('AUTH_V3_SCOPES', 'Auth v3 Granular Scopes',
             'Enable scope-based authorization middleware', false, NOW(), NOW()),
            ('AUTH_V3_ENDPOINTS', 'Auth v3 Endpoints (Master)',
             'Master flag — gates ALL v3 auth endpoints', false, NOW(), NOW())
        ON CONFLICT ("key") DO NOTHING;
    """
    )


def downgrade():
    op.drop_table("auth_webhook_subscriptions")
    op.drop_table("auth_api_keys")
    op.drop_table("auth_sessions")
    op.drop_table("oidc_provider_configs")

    op.execute(
        """
        DELETE FROM feature_flags WHERE "key" IN (
            'AUTH_V3_COOKIES', 'AUTH_V3_SESSIONS', 'AUTH_V3_API_KEYS',
            'AUTH_V3_OIDC', 'AUTH_V3_WEBHOOKS', 'AUTH_V3_SCOPES', 'AUTH_V3_ENDPOINTS'
        );
    """
    )
