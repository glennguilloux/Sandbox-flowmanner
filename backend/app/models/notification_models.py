from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class NotificationSettings(Base, TimestampMixin):
    """User notification settings stored in DB."""

    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    # Channel toggles
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Event toggles
    event_mission_completed: Mapped[bool] = mapped_column(Boolean, default=True)
    event_mission_failed: Mapped[bool] = mapped_column(Boolean, default=True)
    event_mention: Mapped[bool] = mapped_column(Boolean, default=True)
    event_system: Mapped[bool] = mapped_column(Boolean, default=True)
    # Digest settings
    digest_mode: Mapped[str] = mapped_column(String(20), default="realtime")
    digest_time_utc: Mapped[str | None] = mapped_column(String(5), nullable=True)
    digest_day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Contact info
    email_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    push_enabled_channels: Mapped[str | None] = mapped_column(String, nullable=True)


class PushSubscription(Base, TimestampMixin):
    """Web Push subscription stored in DB.

    Replaces the in-memory `_push_subscriptions` dict.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh_key: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_key: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def to_push_dict(self) -> dict:
        """Return dict suitable for pywebpush."""
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.p256dh_key,
                "auth": self.auth_key,
            },
        }


class Notification(Base, TimestampMixin):
    """Persistent notification items stored in DB.

    Replaces the in-memory `_notifications` dict.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), default="info", nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)
