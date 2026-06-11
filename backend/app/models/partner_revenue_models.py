from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Partner(Base, TimestampMixin):
    """Partner organization that receives revenue share."""

    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    revenue_share_percent: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    stripe_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    revenues: Mapped[list[PartnerRevenue]] = relationship(
        "PartnerRevenue", back_populates="partner", cascade="all, delete-orphan"
    )
    users: Mapped[list[User]] = relationship("User", back_populates="partner")


class PartnerRevenue(Base, TimestampMixin):
    """Tracks revenue generated for partners from missions."""

    __tablename__ = "partner_revenues"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    partner_id: Mapped[int] = mapped_column(ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    mission_volume: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    revenue_amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    period_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    partner: Mapped[Partner] = relationship("Partner", back_populates="revenues")
