"""Modified User model with TOTP fields."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User model for authentication and profile."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="free", nullable=False)  # free, pro, enterprise, admin
    partner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("partners.id"), nullable=True, index=True)
    is_partner_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Profile
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Onboarding fields
    onboarding_step: Mapped[str | None] = mapped_column(String(50), nullable=True, default="welcome")
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_data: Mapped[str | None] = mapped_column(Text, nullable=True, default="{}")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 2FA TOTP fields
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_backup_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    api_keys: Mapped[list[UserAPIKey]] = relationship("UserAPIKey", back_populates="user", cascade="all, delete-orphan")

    # Partner relationship
    partner: Mapped[Partner | None] = relationship("Partner", back_populates="users")

    # Onboarding emails
    onboarding_emails: Mapped[list[OnboardingEmail]] = relationship("OnboardingEmail", back_populates="user", cascade="all, delete-orphan")


class OnboardingEmail(Base):
    """Tracks onboarding drip emails sent to users."""

    __tablename__ = "onboarding_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    email_type: Mapped[str] = mapped_column(String(50), nullable=False)  # welcome, day1, day3, day7
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship
    user: Mapped[User] = relationship("User", back_populates="onboarding_emails")
