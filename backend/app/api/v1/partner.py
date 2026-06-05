from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.partner_revenue_models import Partner, PartnerRevenue
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/partner", tags=["Partner"])


class RevenueResponse(BaseModel):
    current_month_revenue: float
    total_mission_volume: int
    total_referrals: int
    pending_payout: float
    revenue_trend: list[dict]  # Last 6 months
    currency: str = "USD"


class PayoutRequest(BaseModel):
    amount: float | None = None  # If None, pay all pending


class PayoutResponse(BaseModel):
    success: bool
    amount: float
    currency: str = "USD"
    payout_id: str | None = None
    message: str


@router.get("/dashboard", response_model=RevenueResponse)
async def get_partner_dashboard(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        """
        Get partner revenue dashboard.
        Implements Story 3.5 (FR31, FR32, FR33) - View Revenue Share Reports.
        """
        # Verify user is a partner admin
        if not getattr(user, "is_partner_admin", False):
            raise HTTPException(status_code=403, detail="Partner admin access required")

        partner_id = getattr(user, "partner_id", None)
        if not partner_id:
            raise HTTPException(
                status_code=400, detail="No partner associated with this account"
            )

        # Get partner
        result = await db.execute(select(Partner).where(Partner.id == partner_id))
        partner = result.scalars().first()
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")

        # Current month revenue
        current_month = datetime.now().strftime("%Y-%m")
        result = await db.execute(
            select(func.sum(PartnerRevenue.revenue_amount)).where(
                PartnerRevenue.partner_id == partner_id,
                PartnerRevenue.period_month == current_month,
            )
        )
        current_month_revenue = result.scalar() or 0.0

        # Total mission volume (all time)
        result = await db.execute(
            select(func.sum(PartnerRevenue.mission_volume)).where(
                PartnerRevenue.partner_id == partner_id
            )
        )
        total_volume = result.scalar() or 0

        # Total referrals (users who upgraded to Pro/Enterprise)
        result = await db.execute(
            select(func.count(User.id)).where(
                User.partner_id == partner_id,
                User.role.in_(["pro", "enterprise"]),
            )
        )
        total_referrals = result.scalar() or 0

        # Pending payout (unpaid revenues)
        result = await db.execute(
            select(func.sum(PartnerRevenue.revenue_amount)).where(
                PartnerRevenue.partner_id == partner_id,
                PartnerRevenue.is_paid == False,
            )
        )
        pending_payout = result.scalar() or 0.0

        # Revenue trend (last 6 months)
        trend = []
        for i in range(6):
            date = datetime.now() - timedelta(days=30 * i)
            month_str = date.strftime("%Y-%m")
            result = await db.execute(
                select(func.sum(PartnerRevenue.revenue_amount)).where(
                    PartnerRevenue.partner_id == partner_id,
                    PartnerRevenue.period_month == month_str,
                )
            )
            amount = result.scalar() or 0.0
            trend.append(
                {
                    "month": month_str,
                    "revenue": amount,
                }
            )
        trend.reverse()  # Oldest first

        return {
            "current_month_revenue": current_month_revenue,
            "total_mission_volume": total_volume,
            "total_referrals": total_referrals,
            "pending_payout": pending_payout,
            "revenue_trend": trend,
            "currency": "USD",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/revenues")
async def list_revenues(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    month: str | None = None,
):
    try:
        """List revenue records for the partner."""
        if not getattr(user, "is_partner_admin", False):
            raise HTTPException(status_code=403, detail="Partner admin access required")

        query = select(PartnerRevenue).where(
            PartnerRevenue.partner_id == getattr(user, "partner_id", None)
        )
        if month:
            query = query.where(PartnerRevenue.period_month == month)

        result = await db.execute(query.order_by(PartnerRevenue.period_month.desc()))
        revenues = result.scalars().all()

        return [
            {
                "id": r.id,
                "mission_id": r.mission_id,
                "mission_volume": r.mission_volume,
                "revenue_amount": r.revenue_amount,
                "period_month": r.period_month,
                "is_paid": r.is_paid,
                "paid_at": r.paid_at.isoformat() if r.paid_at else None,
            }
            for r in revenues
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/request-payout", response_model=PayoutResponse)
async def request_payout(
    payout_request: PayoutRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Request a payout to the partner's Stripe account.
    Implements Story 3.5 (FR33) - Request Payout via Stripe Transfer.
    """
    try:
        # Verify user is a partner admin
        if not getattr(user, "is_partner_admin", False):
            raise HTTPException(status_code=403, detail="Partner admin access required")

        partner_id = getattr(user, "partner_id", None)
        if not partner_id:
            raise HTTPException(
                status_code=400, detail="No partner associated with this account"
            )

        # Get partner
        result = await db.execute(select(Partner).where(Partner.id == partner_id))
        partner = result.scalars().first()
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")

        # Check if partner has Stripe account connected
        if not partner.stripe_account_id:
            raise HTTPException(
                status_code=400,
                detail="No Stripe account connected. Please connect your Stripe account first.",
            )

        # Calculate pending payout amount
        result = await db.execute(
            select(func.sum(PartnerRevenue.revenue_amount)).where(
                PartnerRevenue.partner_id == partner_id,
                PartnerRevenue.is_paid == False,
            )
        )
        pending_amount = result.scalar() or 0.0

        if pending_amount <= 0:
            raise HTTPException(status_code=400, detail="No pending payout available")

        # Use requested amount or pay all pending
        payout_amount = (
            payout_request.amount
            if payout_request and payout_request.amount
            else pending_amount
        )

        if payout_amount > pending_amount:
            raise HTTPException(
                status_code=400,
                detail=f"Requested amount exceeds pending payout ({pending_amount})",
            )

        # Configure Stripe API key from environment
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

        # Create Stripe transfer
        try:
            if stripe.api_key:
                transfer = stripe.Transfer.create(
                    amount=int(payout_amount * 100),  # Stripe expects cents
                    currency="usd",
                    destination=partner.stripe_account_id,
                    description=f"Partner payout for {datetime.now().strftime('%Y-%m')}",
                )
                payout_id = transfer.id
            else:
                logger.error(
                    "STRIPE_SECRET_KEY is not configured — cannot process real payout. "
                    "Set STRIPE_SECRET_KEY in environment for Stripe transfers."
                )
                raise HTTPException(
                    status_code=502,
                    detail="Stripe is not configured: STRIPE_SECRET_KEY is not set. "
                    "Please configure Stripe payments before requesting payouts.",
                )

            # Mark revenues as paid
            result = await db.execute(
                select(PartnerRevenue)
                .where(
                    PartnerRevenue.partner_id == partner_id,
                    PartnerRevenue.is_paid == False,
                )
                .limit(1000)  # Safety limit
            )
            unpaid_revenues = result.scalars().all()

            total_marked = 0.0
            for revenue in unpaid_revenues:
                if total_marked + revenue.revenue_amount <= payout_amount:
                    revenue.is_paid = True
                    revenue.paid_at = datetime.now()
                    total_marked += revenue.revenue_amount

                    # Stop if we've marked enough
                    if total_marked >= payout_amount:
                        break

            await db.commit()

            return PayoutResponse(
                success=True,
                amount=payout_amount,
                payout_id=payout_id,
                message=f"Payout of ${payout_amount:.2f} initiated successfully",
            )

        except Exception as stripe_error:
            logger.error("Stripe transfer failed for partner %s: %s", partner_id, stripe_error)
            raise HTTPException(
                status_code=500, detail=f"Stripe transfer failed: {stripe_error!s}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
