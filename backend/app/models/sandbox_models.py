"""MissionSandbox model — tracks sandboxd sandboxes scoped to missions.

Each mission can have at most one active sandbox. The sandbox lifecycle
(create → stop → purge) maps to the mission lifecycle via SandboxService.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class MissionSandbox(Base, TimestampMixin):
    __tablename__ = "mission_sandboxes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=lambda: uuid4()
    )
    mission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    sandbox_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="sandboxd container ULID",
    )
    project_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="maps to sandboxd project.id",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="creating",
        server_default="creating",
        index=True,
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    purged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, comment="arbitrary sandbox config/env"
    )
