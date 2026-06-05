"""
OIDC, Custom Roles, Delegation, and Cross-Tenant models.

Tables: oidc_providers, user_oidc_accounts, custom_roles, role_permissions,
        role_delegations, user_tenants
"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin, UUIDMixin

# ---------------------------------------------------------------------------
# 1. OIDC Provider Config
# ---------------------------------------------------------------------------


class OIDCProvider(Base, UUIDMixin, TimestampMixin):
    """Configured OIDC identity provider (Okta, Google, Azure AD, …)."""

    __tablename__ = "oidc_providers"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issuer_url: Mapped[str] = mapped_column(String(500), nullable=False)
    client_id: Mapped[str] = mapped_column(String(500), nullable=False)
    # Stored encrypted at the application layer — DB column is just a blob.
    client_secret: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="App-layer encrypted"
    )
    scopes: Mapped[str | None] = mapped_column(
        String(500), nullable=True, default="openid email profile"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # relationships
    user_accounts: Mapped[list["UserOIDCAccount"]] = relationship(
        back_populates="provider", lazy="selectin"
    )


class UserOIDCAccount(Base, UUIDMixin):
    """Links a local user to an OIDC identity from a specific provider."""

    __tablename__ = "user_oidc_accounts"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("oidc_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="OIDC 'sub' claim"
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    id_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("provider_id", "subject", name="uq_oidc_provider_subject"),
        Index("ix_user_oidc_user_provider", "user_id", "provider_id"),
    )

    # relationships
    provider: Mapped["OIDCProvider"] = relationship(
        back_populates="user_accounts", lazy="selectin"
    )


# ---------------------------------------------------------------------------
# 2. Custom Roles
# ---------------------------------------------------------------------------


class CustomRole(Base, UUIDMixin, TimestampMixin):
    """Workspace-scoped role (system or custom). H4 Phase 3: renamed from tenant_id."""

    __tablename__ = "custom_roles"

    workspace_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Built-in roles cannot be deleted",
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_custom_role_ws_name"),
        Index("ix_custom_roles_ws", "workspace_id"),
    )

    # relationships
    permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", lazy="selectin", cascade="all, delete-orphan"
    )
    delegations: Mapped[list["RoleDelegation"]] = relationship(
        back_populates="role", lazy="selectin"
    )


class RolePermission(Base, UUIDMixin):
    """Single permission attached to a role (e.g. 'missions.create')."""

    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("custom_roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_key: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="e.g. missions.create, team.manage"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("role_id", "permission_key", name="uq_role_permission"),
    )

    # relationships
    role: Mapped["CustomRole"] = relationship(back_populates="permissions")


# ---------------------------------------------------------------------------
# 3. Delegation
# ---------------------------------------------------------------------------


class RoleDelegation(Base, UUIDMixin):
    """Temporary role elevation from one user to another within a workspace. H4 Phase 3: renamed from tenant_id."""

    __tablename__ = "role_delegations"

    delegator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delegatee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("custom_roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    audit_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_delegations_active", "workspace_id", "is_active"),)

    # relationships
    role: Mapped["CustomRole"] = relationship(back_populates="delegations")


# ---------------------------------------------------------------------------
# 4. Cross-tenant (many-to-many)
# ---------------------------------------------------------------------------


class UserTenant(Base, UUIDMixin):
    """Junction table linking users to multiple workspaces with a role. H4 Phase 3: renamed from tenant_id."""

    __tablename__ = "user_tenants"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="member",
        comment="Role name within this workspace (owner, admin, member, viewer)",
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_user_ws"),
        Index("ix_user_tenants_ws", "workspace_id"),
    )


# ---------------------------------------------------------------------------
# 5. User ↔ Custom Role assignment (junction)
# ---------------------------------------------------------------------------


class UserCustomRole(Base, UUIDMixin):
    """Assigns a custom role to a specific user within a workspace. H4 Phase 3: renamed from tenant_id."""

    __tablename__ = "user_custom_roles"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("custom_roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    assigned_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "role_id", "workspace_id", name="uq_user_custom_role_ws"
        ),
        Index("ix_user_custom_roles_ws", "workspace_id"),
    )

    # relationships
    role: Mapped["CustomRole"] = relationship(lazy="selectin")
