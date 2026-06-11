"""Auth v3 models — sessions, API keys, webhook subscriptions, OIDC provider configs.

Replaces implicit refresh_tokens session tracking with explicit auth_sessions table.
API keys are AES-256 encrypted at rest. Webhooks deliver auth events to subscribers.
OIDC provider configs are workspace-scoped (Enterprise SSO), distinct from the
system-level oidc_providers table in auth_models.py.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, UUIDMixin

# ──────────────────────────────────────────────────────────────
# AuthSession — explicit session tracking (replaces refresh_tokens)
# ──────────────────────────────────────────────────────────────


class AuthSession(Base, UUIDMixin, TimestampMixin):
    """A user login session tracked explicitly with device metadata and token hashing.

    v2 used refresh_tokens for implicit session tracking.
    v3 uses auth_sessions for explicit session management (list, revoke, audit).
    """

    __tablename__ = "auth_sessions"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 of the refresh token — never store plaintext",
    )
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_os: Mapped[str | None] = mapped_column(String(100), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Updated ONLY on token refresh, NOT on every access-token validation",
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="user_logout, password_change, admin_revoke, reuse_detected",
    )
    family_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    family_generation: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("ix_auth_sessions_user_active", "user_id", "is_active"),)

    # Relationship — the user this session belongs to
    user: Mapped[User] = relationship("User", lazy="selectin")

    @staticmethod
    def make_refresh_token_hash(token: str) -> str:
        """SHA-256 the refresh token for storage. Never store plaintext."""
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def generate_refresh_token() -> str:
        """Generate a cryptographically random refresh token (64 hex chars = 256 bits)."""
        return secrets.token_hex(32)


# ──────────────────────────────────────────────────────────────
# ApiKey — scoped, expirable API keys for programmatic access
# ──────────────────────────────────────────────────────────────


class ApiKey(Base, UUIDMixin):
    """User-created API key with granular scopes, stored encrypted at rest.

    The full key is returned ONCE on creation. Only the SHA-256 hash is indexed.
    The key_prefix (first 8 chars) lets users identify keys in the list view.
    """

    __tablename__ = "auth_api_keys"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment="First 8 chars of the full key — visible to user",
    )
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, comment="SHA-256 of full API key")
    scopes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment='JSON array: ["missions:read", "missions:write"]'
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (Index("ix_api_keys_user", "user_id", "is_active"),)

    # Relationship
    user: Mapped[User] = relationship("User", lazy="selectin")

    @staticmethod
    def generate_api_key() -> tuple[str, str, str]:
        """Generate a new API key. Returns (full_key, prefix, hash).

        full_key:   "fm_" + 40 hex chars (user-visible, shown ONCE)
        prefix:     "fm_" + first 6 hex chars (shown in list view)
        hash:       SHA-256 of full_key (stored in DB, indexed for lookup)
        """
        raw = secrets.token_hex(20)  # 40 hex chars = 160 bits
        full_key = f"fm_{raw}"
        prefix = full_key[:8]  # "fm_" + 6 hex chars
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        return full_key, prefix, key_hash

    @staticmethod
    def hash_key(key: str) -> str:
        """SHA-256 a full API key for storage comparison."""
        return hashlib.sha256(key.encode()).hexdigest()


# ──────────────────────────────────────────────────────────────
# AuthWebhookSubscription — auth event webhook delivery targets
# ──────────────────────────────────────────────────────────────


class AuthWebhookSubscription(Base, UUIDMixin):
    """Webhook subscription for auth events (login, logout, session revoked, etc.).

    Each subscription has an HMAC-SHA256 secret for payload signing so the
    receiver can verify the webhook came from Flowmanner.
    """

    __tablename__ = "auth_webhook_subscriptions"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    secret: Mapped[str] = mapped_column(String(64), nullable=False, comment="HMAC-SHA256 signing secret (64 hex chars)")
    events: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment='JSON array of event types: ["session.created", "session.revoked"]',
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (Index("ix_webhook_sub_workspace", "workspace_id", "is_active"),)

    @staticmethod
    def generate_secret() -> str:
        """Generate an HMAC-SHA256 signing secret (64 hex chars = 256 bits)."""
        return secrets.token_hex(32)


# ──────────────────────────────────────────────────────────────
# OIDCProviderConfig — workspace-scoped OIDC SSO configuration
# ──────────────────────────────────────────────────────────────


class OIDCProviderConfig(Base, UUIDMixin):
    """Workspace-scoped OIDC identity provider for Enterprise SSO.

    Distinct from the system-level oidc_providers table in auth_models.py.
    The client_secret is AES-256 encrypted at the application layer.
    """

    __tablename__ = "oidc_provider_configs"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="google, github, microsoft, okta, custom"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    issuer_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    client_id: Mapped[str] = mapped_column(String(500), nullable=False)
    client_secret_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary(), nullable=False, comment="AES-256 encrypted client secret"
    )
    scopes: Mapped[str] = mapped_column(String(500), default="openid email profile")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
