"""Stub subscription endpoints — placeholders so the frontend /api/subscription/*
calls stop 404ing. No real billing logic, no PayPal/Stripe side effects."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.subscription_models import SubscriptionTier, UserSubscription
from app.models.user import User

router = APIRouter(prefix="/subscription", tags=["subscription"])

_PLACEHOLDER_TIERS = [
    {
        "id": 0,
        "name": "free",
        "display_name": "Free",
        "price_monthly": 0.0,
        "interval": "month",
    },
]


@router.get("/tiers")
async def list_tiers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List subscription tiers. Falls back to a hardcoded placeholder if none seeded."""
    result = await db.execute(
        select(SubscriptionTier).where(SubscriptionTier.is_active.is_(True))
    )
    tiers = result.scalars().all()
    if not tiers:
        return _PLACEHOLDER_TIERS
    return [
        {
            "id": t.id,
            "name": t.name,
            "display_name": t.display_name,
            "price_monthly": t.price_monthly,
            "interval": "month",
        }
        for t in tiers
    ]


@router.get("/my-subscription")
async def my_subscription(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the user's current subscription (joined tier name), or {} if none."""
    result = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
    )
    sub = result.scalars().first()
    if not sub:
        return {}
    return {
        "id": sub.id,
        "user_id": sub.user_id,
        "tier_id": sub.tier_id,
        "status": sub.status,
        "current_period_start": sub.current_period_start,
        "current_period_end": sub.current_period_end,
        "cancel_at_period_end": sub.cancel_at_period_end,
    }


@router.post("/upgrade")
async def upgrade_subscription(
    payload: dict | None = None,
    user: User = Depends(get_current_user),
):
    """Stub upgrade — accepts an optional tier_id and ignores it. No DB write."""
    return {
        "status": "accepted",
        "detail": "subscription upgrade is a stub — no charge performed",
    }


@router.get("/billing")
async def billing_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Placeholder billing summary for the current user."""
    result = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
    )
    sub = result.scalars().first()
    if not sub:
        return {"plan": "free", "subscription": None, "billing_customer_id": None}
    return {
        "plan": "paid",
        "subscription": {
            "id": sub.id,
            "tier_id": sub.tier_id,
            "status": sub.status,
            "current_period_end": sub.current_period_end,
            "cancel_at_period_end": sub.cancel_at_period_end,
        },
        "billing_customer_id": sub.paypal_subscription_id,
    }


@router.get("/paypal/cancel")
@router.post("/paypal/cancel")
async def paypal_cancel(
    user: User = Depends(get_current_user),
):
    """Stub PayPal cancel acknowledgement — no PayPal API call made."""
    return {
        "status": "ok",
        "detail": "paypal cancel stub — no PayPal API call made",
    }


@router.get("/paypal/return")
@router.post("/paypal/return")
async def paypal_return(
    user: User = Depends(get_current_user),
):
    """Stub PayPal return acknowledgement — no PayPal API call made."""
    return {
        "status": "ok",
        "detail": "paypal return stub — no PayPal API call made",
    }
