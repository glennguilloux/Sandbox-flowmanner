from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class SubscriptionTier(Base, TimestampMixin):
    """Defines available subscription tiers (Free, Pro, Enterprise)."""

    __tablename__ = "subscription_tiers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    price_monthly: Mapped[float | None] = mapped_column(nullable=True)
    missions_per_day: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    missions_per_month: Mapped[int] = mapped_column(
        Integer, default=150, nullable=False
    )
    max_concurrent_missions: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    has_priority_support: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    has_api_access: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_custom_models: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    paypal_plan_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class UserSubscription(Base, TimestampMixin):
    """Tracks user's current subscription."""

    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_tiers.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    paypal_subscription_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
