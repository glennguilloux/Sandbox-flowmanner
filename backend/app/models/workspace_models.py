"""DB-backed Workspace, Team, and Invitation models."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class Workspace(Base, TimestampMixin):
    """Workspace organization for multi-user collaboration.

    H4.1: Added subscription_tier_id and billing_customer_id (migrated from Tenant).
    """

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    settings: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, server_default="{}"
    )
    member_limit: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="5"
    )
    storage_used_bytes: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, server_default="0"
    )
    # H4.1: Subscription & billing (migrated from Tenant model)
    subscription_tier_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscription_tiers.id", ondelete="SET NULL"), nullable=True
    )
    billing_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, server_default="1"
    )

    # Relationships
    owner: Mapped[User] = relationship("User", foreign_keys=[owner_id])
    subscription_tier: Mapped[SubscriptionTier | None] = relationship(
        "SubscriptionTier", lazy="selectin"
    )
    members: Mapped[list[WorkspaceMember]] = relationship(
        "WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan"
    )
    teams: Mapped[list[Team]] = relationship(
        "Team", back_populates="workspace", cascade="all, delete-orphan"
    )
    invitations: Mapped[list[WorkspaceInvitation]] = relationship(
        "WorkspaceInvitation", back_populates="workspace", cascade="all, delete-orphan"
    )


class WorkspaceMember(Base, TimestampMixin):
    """Member of a workspace with role-based access."""

    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="members")
    user: Mapped[User] = relationship("User")


class Team(Base, TimestampMixin):
    """Team within a workspace for grouping members."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    workspace: Mapped[Workspace] = relationship("Workspace", back_populates="teams")
    members: Mapped[list[TeamMember]] = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )


class TeamMember(Base, TimestampMixin):
    """Member of a team."""

    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relationships
    team: Mapped[Team] = relationship("Team", back_populates="members")
    user: Mapped[User] = relationship("User")


class WorkspaceInvitation(Base, TimestampMixin):
    """Pending invitation to join a workspace."""

    __tablename__ = "workspace_invitations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    invited_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invitation_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    workspace: Mapped[Workspace] = relationship(
        "Workspace", back_populates="invitations"
    )
    inviter: Mapped[User] = relationship("User", foreign_keys=[invited_by])


class WorkspaceVersion(Base, TimestampMixin):
    """Immutable version snapshot of a Workspace.

    Each time workspace settings change, a new version row is created.
    Enables rollback, diffing, and audit trails.
    """

    __tablename__ = "workspace_versions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkspaceShare(Base, TimestampMixin):
    """Cross-workspace permission grant for a specific entity.

    Allows workspace A to grant read/write access to a specific
    mission, workflow, or chat thread owned by workspace B.
    """

    __tablename__ = "workspace_shares"
    __table_args__ = (
        UniqueConstraint(
            "source_workspace_id",
            "target_workspace_id",
            "entity_type",
            "entity_id",
            name="uq_workspace_share",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    source_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # mission, workflow, chat_thread
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(
        String(20), default="read", nullable=False
    )  # read, write
    granted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    source_workspace: Mapped[Workspace] = relationship(
        "Workspace", foreign_keys=[source_workspace_id]
    )
    target_workspace: Mapped[Workspace] = relationship(
        "Workspace", foreign_keys=[target_workspace_id]
    )
    granter: Mapped[User | None] = relationship("User", foreign_keys=[granted_by])


class WorkspaceMessage(Base, TimestampMixin):
    """Persistent direct message between workspace members."""

    __tablename__ = "workspace_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    workspace: Mapped[Workspace] = relationship("Workspace")
    sender: Mapped[User] = relationship("User", foreign_keys=[sender_id])
    recipient: Mapped[User] = relationship("User", foreign_keys=[recipient_id])
