"""Playground sandbox models — anonymous, claimable sandboxes for the public playground.

Anonymous until claimed — user_id is NULL initially.
session_token proves ownership before claiming.
expires_at drives the auto-purge TTL (30 min anonymous, 24h claimed).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class PlaygroundSandboxStatus(str, Enum):
    """Lifecycle states for playground sandboxes."""

    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    PURGED = "purged"
    CLAIMED = "claimed"


class PlaygroundSandbox(Base, TimestampMixin):
    """Tracks sandboxd containers created via the public playground.

    Anonymous until claimed — user_id is NULL initially.
    session_token proves ownership before claiming.
    expires_at drives the 30-minute auto-purge TTL.
    """

    __tablename__ = "playground_sandboxes"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    sandbox_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="sandboxd container ID",
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_token: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
        comment="proves ownership before claiming",
    )
    workspace_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PlaygroundSandboxStatus.CREATING.value,
        server_default="creating",
    )
    template: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="python-img",
        server_default="python-img",
    )
    project_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    is_persistent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    anonymous_ip: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        index=True,
        comment="IPv4/IPv6 of anonymous creator for rate limiting",
    )

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    @property
    def is_anonymous(self) -> bool:
        return self.user_id is None
