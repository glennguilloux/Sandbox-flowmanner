"""v3 Workspace Billing — subscription and usage data for a workspace.

H4.1: Now reads subscription_tier_id and billing_customer_id from Workspace
(migrated from the Tenant model).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v3.base import ok
from app.database import get_db
from app.models.subscription_models import SubscriptionTier
from app.models.workspace_models import Workspace, WorkspaceMember

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/workspaces", tags=["v3-workspace-billing"])


async def _require_billing_enabled(db: AsyncSession) -> None:
    from sqlalchemy import text

    result = await db.execute(text("SELECT enabled_globally FROM feature_flags WHERE key = 'WORKSPACES_V3_BILLING'"))
    if not result.scalar():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")


@router.get("/{workspace_id}/billing", status_code=status.HTTP_200_OK)
async def get_billing(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_billing_enabled(db)

    membership = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if not membership.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # H4.1: Resolve subscription tier details from Workspace
    tier = None
    if ws.subscription_tier_id:
        tier_result = await db.execute(select(SubscriptionTier).where(SubscriptionTier.id == ws.subscription_tier_id))
        tier = tier_result.scalar_one_or_none()

    return ok(
        {
            "workspace_id": ws.id,
            "plan": ws.plan,
            "plan_display_name": ws.plan.title(),
            "member_limit": ws.member_limit or 5,
            "storage_limit_bytes": 1073741824,
            "storage_used_bytes": ws.storage_used_bytes or 0,
            # H4.1: Subscription & billing from Workspace (migrated from Tenant)
            "subscription": (
                {
                    "tier_id": ws.subscription_tier_id,
                    "tier_name": tier.name if tier else None,
                    "tier_display": tier.display_name if tier else None,
                    "missions_per_day": tier.missions_per_day if tier else 5,
                    "missions_per_month": tier.missions_per_month if tier else 150,
                    "has_api_access": tier.has_api_access if tier else False,
                    "has_custom_models": tier.has_custom_models if tier else False,
                }
                if ws.subscription_tier_id
                else None
            ),
            "billing_customer_id": ws.billing_customer_id,
        }
    )
