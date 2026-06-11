from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.subscription_models import SubscriptionTier, UserSubscription
from app.services.paypal_service import paypal_client
from app.services.subscription_service import get_billing_dashboard

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscription", tags=["Subscription"])


class TierResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: str | None
    price_monthly: float | None
    missions_per_day: int
    missions_per_month: int
    max_concurrent_missions: int
    has_priority_support: bool
    has_api_access: bool
    has_custom_models: bool


@router.get("/tiers", response_model=list[TierResponse])
async def list_tiers(db: AsyncSession = Depends(get_db)):
    try:
        """List all active subscription tiers."""
        result = await db.execute(select(SubscriptionTier).where(SubscriptionTier.is_active == True))
        tiers = result.scalars().all()
        return [
            {
                "id": t.id,
                "name": t.name,
                "display_name": t.display_name,
                "description": t.description,
                "price_monthly": t.price_monthly,
                "missions_per_day": t.missions_per_day,
                "missions_per_month": t.missions_per_month,
                "max_concurrent_missions": t.max_concurrent_missions,
                "has_priority_support": t.has_priority_support,
                "has_api_access": t.has_api_access,
                "has_custom_models": t.has_custom_models,
            }
            for t in tiers
        ]
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


class UpgradeRequest(BaseModel):
    tier_name: str  # "pro" or "enterprise"
    success_url: str | None = None
    cancel_url: str | None = None


@router.post("/upgrade", status_code=status.HTTP_200_OK)
async def initiate_upgrade(
    data: UpgradeRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate subscription upgrade using PayPal.
    Implements Story 3.3 (FR34) with PayPal instead of Stripe.
    """
    # Verify tier exists
    result = await db.execute(
        select(SubscriptionTier).where(
            SubscriptionTier.name == data.tier_name.lower(),
            SubscriptionTier.is_active == True,
        )
    )
    tier = result.scalars().first()

    if not tier:
        raise HTTPException(status_code=404, detail=f"Tier '{data.tier_name}' not found")

    # If tier has no price (enterprise), handle differently
    if tier.price_monthly is None or not tier.paypal_plan_id:
        return {
            "success": True,
            "message": "Enterprise plan requires manual setup",
            "contact_sales": True,
        }

    # Create PayPal subscription
    try:
        paypal_response = await paypal_client.create_subscription(
            plan_id=tier.paypal_plan_id,
            subscriber_email=user.email,
        )

        # Find the approval URL
        approval_url = None
        for link in paypal_response.get("links", []):
            if link.get("rel") == "approve":
                approval_url = link.get("href")
                break

        return {
            "success": True,
            "subscription_id": paypal_response.get("id"),
            "checkout_url": approval_url,
            "tier": tier.name,
            "price_monthly": tier.price_monthly,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PayPal error: {e!s}")


@router.get("/my-subscription")
async def get_my_subscription(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        """Get current user's subscription details from the database."""
        # Query real subscription from UserSubscription + SubscriptionTier
        result = await db.execute(
            select(UserSubscription, SubscriptionTier)
            .join(SubscriptionTier, UserSubscription.tier_id == SubscriptionTier.id)
            .where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
            )
        )
        row = result.first()

        if row:
            sub, tier = row
            return {
                "tier": {
                    "name": tier.name,
                    "missions_per_day": tier.missions_per_day,
                    "missions_per_month": tier.missions_per_month,
                },
                "status": sub.status,
                "current_period_end": (sub.current_period_end.isoformat() if sub.current_period_end else None),
            }

        # Fall back to free tier if no active subscription found
        free_tier_result = await db.execute(select(SubscriptionTier).where(SubscriptionTier.name == "free"))
        free_tier = free_tier_result.scalars().first()

        if free_tier:
            return {
                "tier": {
                    "name": free_tier.name,
                    "missions_per_day": free_tier.missions_per_day,
                    "missions_per_month": free_tier.missions_per_month,
                },
                "status": "free",
            }

        # Ultimate fallback if no free tier configured in DB
        return {
            "tier": {"name": "free", "missions_per_day": 5, "missions_per_month": 150},
            "status": "free",
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# PayPal webhook/return endpoints
@router.get("/paypal/return")
async def paypal_return(subscription_id: str, user=Depends(get_current_user)):
    try:
        """Handle successful PayPal subscription return."""
        return {
            "success": True,
            "message": "Subscription activated successfully",
            "subscription_id": subscription_id,
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/paypal/cancel")
async def paypal_cancel():
    try:
        """Handle cancelled PayPal subscription."""
        return {
            "success": False,
            "message": "Subscription cancelled by user",
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ── PayPal Webhook (Phase 8.4) ─────────────────────────────────────────────


@router.post("/paypal/webhook")
async def paypal_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle PayPal webhook events for subscription lifecycle.

    Processes:
      - BILLING.SUBSCRIPTION.ACTIVATED  → activate subscription, link to user
      - BILLING.SUBSCRIPTION.CANCELLED  → mark cancelled
      - BILLING.SUBSCRIPTION.SUSPENDED  → mark suspended
      - BILLING.SUBSCRIPTION.PAYMENT.FAILED → mark payment failed
      - BILLING.SUBSCRIPTION.EXPIRED    → mark expired

    Expects the webhook ID to be set in PAYPAL_WEBHOOK_ID env var.
    """
    body = await request.body()
    headers = dict(request.headers)

    # Verify webhook signature via PayPal API
    webhook_id = getattr(settings, "PAYPAL_WEBHOOK_ID", "")
    if webhook_id:
        is_valid = await paypal_client.verify_webhook_signature_api(
            webhook_id=webhook_id,
            body=body,
            headers=headers,
        )
        if not is_valid:
            logger.warning("PayPal webhook signature verification failed")
            raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("event_type", "")
    resource = event.get("resource", {})
    paypal_sub_id = resource.get("id", "")

    if not paypal_sub_id:
        logger.warning("PayPal webhook missing subscription id: %s", event_type)
        return {"status": "ignored"}

    logger.info("PayPal webhook: %s subscription=%s", event_type, paypal_sub_id)

    # Find the UserSubscription linked to this PayPal subscription
    result = await db.execute(select(UserSubscription).where(UserSubscription.paypal_subscription_id == paypal_sub_id))
    sub = result.scalar_one_or_none()

    if not sub:
        logger.warning("PayPal webhook for unknown subscription: %s", paypal_sub_id)
        return {"status": "unknown_subscription"}

    now = datetime.now(UTC)

    if event_type == "BILLING.SUBSCRIPTION.ACTIVATED":
        sub.status = "active"
        # Update period dates from the resource
        billing_info = resource.get("billing_info", {})
        last_payment = billing_info.get("last_payment", {})
        if last_payment.get("time"):
            sub.current_period_start = datetime.fromisoformat(last_payment["time"].replace("Z", "+00:00"))
        next_billing = billing_info.get("next_billing_time", "")
        if next_billing:
            sub.current_period_end = datetime.fromisoformat(next_billing.replace("Z", "+00:00"))
        sub.cancel_at_period_end = False

    elif event_type == "BILLING.SUBSCRIPTION.CANCELLED":
        sub.status = "cancelled"
        sub.cancel_at_period_end = True

    elif event_type == "BILLING.SUBSCRIPTION.SUSPENDED":
        sub.status = "suspended"

    elif event_type == "BILLING.SUBSCRIPTION.PAYMENT.FAILED":
        sub.status = "payment_failed"

    elif event_type == "BILLING.SUBSCRIPTION.EXPIRED":
        sub.status = "expired"

    else:
        logger.debug("Unhandled PayPal event type: %s", event_type)
        return {"status": "unhandled", "event_type": event_type}

    await db.commit()
    logger.info(
        "Subscription %s updated to status=%s via PayPal webhook",
        paypal_sub_id,
        sub.status,
    )
    return {"status": "processed", "event_type": event_type, "new_status": sub.status}


# ── Activate after approval (Phase 8.4) ────────────────────────────────────


@router.post("/paypal/activate")
async def paypal_activate(
    subscription_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Activate a PayPal subscription after the user has approved it.

    This is called from the frontend after the PayPal approval redirect.
    It verifies the subscription with PayPal, activates it, and links
    the UserSubscription to the user.
    """
    # Verify with PayPal that the subscription is in APPROVED state
    try:
        pp_sub = await paypal_client.get_subscription(subscription_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PayPal verification failed: {e}")

    pp_status = pp_sub.get("status", "")
    if pp_status not in ("APPROVED", "ACTIVE"):
        raise HTTPException(
            status_code=400,
            detail=f"Subscription is in '{pp_status}' state, expected APPROVED",
        )

    # Activate with PayPal if approved (not yet active)
    if pp_status == "APPROVED":
        try:
            await paypal_client.activate_subscription(subscription_id)
        except Exception as e:
            logger.warning("PayPal activation call failed: %s", e)
            # Continue — PayPal may have already activated it

    # Find the tier from the PayPal plan ID
    plan_id = pp_sub.get("plan_id", "")
    tier_result = await db.execute(
        select(SubscriptionTier).where(
            SubscriptionTier.paypal_plan_id == plan_id,
            SubscriptionTier.is_active == True,
        )
    )
    tier = tier_result.scalar_one_or_none()

    if not tier:
        raise HTTPException(status_code=400, detail=f"No tier found for PayPal plan {plan_id}")

    # Create or update UserSubscription
    existing_result = await db.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user.id,
            UserSubscription.paypal_subscription_id == subscription_id,
        )
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        existing.status = "active"
        existing.tier_id = tier.id
    else:
        new_sub = UserSubscription(
            user_id=user.id,
            tier_id=tier.id,
            status="active",
            paypal_subscription_id=subscription_id,
        )
        db.add(new_sub)

    await db.commit()

    return {
        "success": True,
        "tier": tier.name,
        "display_name": tier.display_name,
        "status": "active",
    }


# ── Billing Dashboard (Phase 8.4) ─────────────────────────────────────────


@router.get("/billing")
async def billing_dashboard(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Billing dashboard — current plan, usage vs limits, next billing date.

    Shows:
      - Current plan tier and limits
      - Today's and this month's mission usage vs limits
      - Active (concurrent) mission count
      - API key count
      - Grace period status (if subscription expired)
      - Billing period dates
    """
    try:
        dashboard = await get_billing_dashboard(db, user.id)

        return {
            "plan": {
                "name": dashboard.plan.tier_name,
                "display_name": dashboard.plan.display_name,
                "missions_per_day_limit": dashboard.plan.missions_per_day,
                "missions_per_month_limit": dashboard.plan.missions_per_month,
                "max_concurrent_missions": dashboard.plan.max_concurrent_missions,
                "has_api_access": dashboard.plan.has_api_access,
                "has_custom_models": dashboard.plan.has_custom_models,
                "has_priority_support": dashboard.plan.has_priority_support,
                "price_monthly": dashboard.plan.price_monthly,
            },
            "usage": {
                "missions_today": dashboard.usage.missions_today,
                "missions_this_month": dashboard.usage.missions_this_month,
                "active_missions": dashboard.usage.active_missions,
                "api_keys_count": dashboard.usage.api_keys_count,
            },
            "limits": {
                "missions_today_remaining": max(
                    0,
                    dashboard.plan.missions_per_day - dashboard.usage.missions_today,
                ),
                "missions_this_month_remaining": max(
                    0,
                    dashboard.plan.missions_per_month - dashboard.usage.missions_this_month,
                ),
                "concurrent_remaining": max(
                    0,
                    dashboard.plan.max_concurrent_missions - dashboard.usage.active_missions,
                ),
            },
            "subscription": {
                "is_active": dashboard.plan.is_active_subscription,
                "is_in_grace_period": dashboard.plan.is_in_grace_period,
                "grace_period_expires_at": (
                    dashboard.plan.grace_period_expires_at.isoformat()
                    if dashboard.plan.grace_period_expires_at
                    else None
                ),
                "current_period_start": (
                    dashboard.current_period_start.isoformat() if dashboard.current_period_start else None
                ),
                "current_period_end": (
                    dashboard.current_period_end.isoformat() if dashboard.current_period_end else None
                ),
                "cancel_at_period_end": dashboard.cancel_at_period_end,
                "paypal_subscription_id": dashboard.paypal_subscription_id,
            },
        }
    except Exception as e:
        logger.exception("Billing dashboard error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
