"""Marketplace purchase / transaction lifecycle + internal credit wallet.

Design decision (MARKETPLACE-2): NO external payment service provider.
Purchases are settled atomically against the buyer's internal wallet balance.
The transaction table is the audit log and records the full lifecycle:

    purchase():
        pending  ->  completed   (balance >= price, funds debited)
        pending  ->  failed      (insufficient balance or listing unavailable)
    refund():
        completed -> refunded    (funds credited back to wallet)

A "pending" state is retained (rather than written straight to completed) so a
real PSP can later be slotted in: the external charge stays `pending` until a
webhook confirms, then flips to `completed`/`failed`. Today, with an internal
wallet, the debit is synchronous so pending is momentary — but the column and
state machine already support the async path.

Payout to listing authors is explicitly OUT OF SCOPE (deferred to a later
ticket); only the buyer-side lifecycle + wallet are implemented here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class TransactionStatus:
    """Allowed lifecycle states for a marketplace transaction."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    REFUND_FAILED = "refund_failed"

    @classmethod
    def all(cls) -> list[str]:
        return [cls.PENDING, cls.COMPLETED, cls.FAILED, cls.REFUNDED, cls.REFUND_FAILED]


class MarketplaceWalletModel(Base, TimestampMixin):
    """Per-user internal credit wallet (no external PSP)."""

    __tablename__ = "marketplace_wallets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")


class MarketplaceTransactionModel(Base, TimestampMixin):
    """A single purchase (or refund) in the marketplace transaction lifecycle."""

    __tablename__ = "marketplace_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: f"txn:{uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    listing_id: Mapped[str] = mapped_column(String(36), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(20), default=TransactionStatus.PENDING)
    # Internal settlement reference (wallet debit/refund id). Reserved for a
    # real PSP charge/payment_intent id when one is introduced.
    payment_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # For refunds: the transaction this refund settles.
    refunded_from: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
