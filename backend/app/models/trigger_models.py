"""Mission Trigger and Trigger Log models (FLO-118).

Provides cron scheduling and inbound webhook triggers for mission execution.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class MissionTrigger(Base, TimestampMixin):
    __tablename__ = "mission_triggers"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "cron" | "webhook"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # "active" | "paused" | "disabled"

    # Cron fields
    cron_expression: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cron_timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Webhook fields
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhook_path: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Extra config passed to mission executor
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Tracking
    fire_count: Mapped[int] = mapped_column(Integer, default=0)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_fire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    logs: Mapped[list["TriggerLog"]] = relationship("TriggerLog", back_populates="trigger", lazy="selectin")


class TriggerLog(Base):
    __tablename__ = "trigger_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    trigger_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mission_triggers.id"),
        nullable=False,
        index=True,
    )
    mission_run_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # "success" | "failure" | "pending"
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    webhook_signature_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)

    # Relationships
    trigger: Mapped["MissionTrigger"] = relationship("MissionTrigger", back_populates="logs")
