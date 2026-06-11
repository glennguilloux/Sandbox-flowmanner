"""Subscription Service — tier resolution, limit enforcement, and billing dashboard.

Phase 8.4: Wires SubscriptionTier limits to actual mission creation/execution
and API key generation.  Supports workspace-scoped tier resolution and a
post-expiration grace period where users retain read-only access.

Tier resolution order:
  1. UserSubscription (user-level, status=active)
  2. Workspace.subscription_tier_id (workspace-level)
  3. "free" tier fallback (always exists in DB)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.mission_models import Mission, MissionStatus
from app.models.subscription_models import SubscriptionTier, UserSubscription

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Grace period after subscription expiration before full downgrade
GRACE_PERIOD_DAYS = 7


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class TierLimits:
    """Resolved tier limits for a user/workspace."""

    tier_id: int | None = None
    tier_name: str = "free"
    display_name: str = "Free"
    missions_per_day: int = 5
    missions_per_month: int = 150
    max_concurrent_missions: int = 1
    has_priority_support: bool = False
    has_api_access: bool = False
    has_custom_models: bool = False
    price_monthly: float | None = None
    paypal_plan_id: str | None = None
    is_active_subscription: bool = False
    is_in_grace_period: bool = False
    grace_period_expires_at: datetime | None = None


@dataclass
class UsageSnapshot:
    """Current period usage counts for billing dashboard."""

    missions_today: int = 0
    missions_this_month: int = 0
    active_missions: int = 0
    api_keys_count: int = 0


@dataclass
class BillingDashboard:
    """Full billing dashboard response."""

    plan: TierLimits
    usage: UsageSnapshot
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    paypal_subscription_id: str | None = None


# ── Tier resolution ────────────────────────────────────────────────────────


async def resolve_user_tier(
    db: AsyncSession,
    user_id: int,
    workspace_id: str | None = None,
) -> TierLimits:
    """Resolve the effective subscription tier for a user.

    Checks user-level subscription first, then workspace, then free fallback.
    """
    # 1. User-level subscription
    result = await db.execute(
        select(UserSubscription, SubscriptionTier)
        .join(SubscriptionTier, UserSubscription.tier_id == SubscriptionTier.id)
        .where(
            UserSubscription.user_id == user_id,
            UserSubscription.status == "active",
        )
        .order_by(UserSubscription.id.desc())
        .limit(1)
    )
    row = result.first()
    if row:
        sub, tier = row
        return _tier_to_limits(tier, is_active=True)

    # Check for expired subscription (grace period)
    expired_result = await db.execute(
        select(UserSubscription, SubscriptionTier)
        .join(SubscriptionTier, UserSubscription.tier_id == SubscriptionTier.id)
        .where(
            UserSubscription.user_id == user_id,
            UserSubscription.status.in_(["active", "expired"]),
            UserSubscription.current_period_end.isnot(None),
        )
        .order_by(UserSubscription.id.desc())
        .limit(1)
    )
    expired_row = expired_result.first()
    if expired_row:
        sub, tier = expired_row
        if sub.current_period_end and sub.current_period_end > datetime.now(UTC):
            # Still within billing period — treat as active
            return _tier_to_limits(tier, is_active=True)

        grace_deadline = sub.current_period_end + timedelta(days=GRACE_PERIOD_DAYS)
        if datetime.now(UTC) < grace_deadline:
            # Within grace period — return tier with grace flag
            limits = _tier_to_limits(tier, is_active=False)
            limits.is_in_grace_period = True
            limits.grace_period_expires_at = grace_deadline
            return limits

    # 2. Workspace-level subscription
    if workspace_id:
        from app.models.workspace_models import Workspace

        ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        ws = ws_result.scalar_one_or_none()
        if ws and ws.subscription_tier_id:
            tier_result = await db.execute(
                select(SubscriptionTier).where(SubscriptionTier.id == ws.subscription_tier_id)
            )
            tier = tier_result.scalar_one_or_none()
            if tier:
                return _tier_to_limits(tier, is_active=True)

    # 3. Free fallback
    free_result = await db.execute(select(SubscriptionTier).where(SubscriptionTier.name == "free"))
    free_tier = free_result.scalar_one_or_none()
    if free_tier:
        return _tier_to_limits(free_tier, is_active=False)

    # Ultimate fallback — hardcoded defaults
    return TierLimits()


# ── Mission limit enforcement ──────────────────────────────────────────────


@dataclass
class LimitCheckResult:
    """Result of a limit check."""

    allowed: bool = True
    reason: str = ""
    current: int = 0
    limit: int = 0
    tier_name: str = "free"


async def check_mission_create_allowed(
    db: AsyncSession,
    user_id: int,
    workspace_id: str | None = None,
) -> LimitCheckResult:
    """Check if a user is allowed to create a new mission.

    Enforces:
      - Grace period (no mission creation)
      - Daily mission limit
      - Monthly mission limit
    """
    tier = await resolve_user_tier(db, user_id, workspace_id)

    # Grace period — read-only, no mission creation
    if tier.is_in_grace_period:
        return LimitCheckResult(
            allowed=False,
            reason=(
                f"Subscription expired. Grace period active until "
                f"{tier.grace_period_expires_at:%Y-%m-%d}. "
                f"Please renew your {tier.display_name} plan to create missions."
            ),
            tier_name=tier.tier_name,
        )

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Count missions created today
    daily_q = select(func.count(Mission.id)).where(
        Mission.user_id == user_id,
        Mission.created_at >= today_start,
        Mission.deleted_at.is_(None),
    )
    daily_count = (await db.execute(daily_q)).scalar() or 0

    if daily_count >= tier.missions_per_day:
        return LimitCheckResult(
            allowed=False,
            reason=(
                f"Daily mission limit reached ({daily_count}/{tier.missions_per_day}). "
                f"Upgrade your {tier.display_name} plan for higher limits."
            ),
            current=daily_count,
            limit=tier.missions_per_day,
            tier_name=tier.tier_name,
        )

    # Count missions created this month
    monthly_q = select(func.count(Mission.id)).where(
        Mission.user_id == user_id,
        Mission.created_at >= month_start,
        Mission.deleted_at.is_(None),
    )
    monthly_count = (await db.execute(monthly_q)).scalar() or 0

    if monthly_count >= tier.missions_per_month:
        return LimitCheckResult(
            allowed=False,
            reason=(
                f"Monthly mission limit reached ({monthly_count}/{tier.missions_per_month}). "
                f"Upgrade your {tier.display_name} plan for higher limits."
            ),
            current=monthly_count,
            limit=tier.missions_per_month,
            tier_name=tier.tier_name,
        )

    return LimitCheckResult(
        allowed=True,
        current=daily_count,
        limit=tier.missions_per_day,
        tier_name=tier.tier_name,
    )


async def check_mission_execute_allowed(
    db: AsyncSession,
    user_id: int,
    workspace_id: str | None = None,
) -> LimitCheckResult:
    """Check if a user is allowed to execute a mission.

    Enforces:
      - Grace period (no mission execution)
      - Concurrent mission limit
    """
    tier = await resolve_user_tier(db, user_id, workspace_id)

    # Grace period — read-only, no execution
    if tier.is_in_grace_period:
        return LimitCheckResult(
            allowed=False,
            reason=(
                f"Subscription expired. Grace period active until "
                f"{tier.grace_period_expires_at:%Y-%m-%d}. "
                f"Please renew your {tier.display_name} plan to execute missions."
            ),
            tier_name=tier.tier_name,
        )

    # Count active (concurrent) missions
    active_statuses = {
        MissionStatus.QUEUED,
        MissionStatus.RUNNING,
        MissionStatus.EXECUTING,
        MissionStatus.PLANNING,
    }
    active_q = select(func.count(Mission.id)).where(
        Mission.user_id == user_id,
        Mission.status.in_(active_statuses),
        Mission.deleted_at.is_(None),
    )
    active_count = (await db.execute(active_q)).scalar() or 0

    if active_count >= tier.max_concurrent_missions:
        return LimitCheckResult(
            allowed=False,
            reason=(
                f"Concurrent mission limit reached ({active_count}/{tier.max_concurrent_missions}). "
                f"Wait for a mission to finish or upgrade your {tier.display_name} plan."
            ),
            current=active_count,
            limit=tier.max_concurrent_missions,
            tier_name=tier.tier_name,
        )

    return LimitCheckResult(
        allowed=True,
        current=active_count,
        limit=tier.max_concurrent_missions,
        tier_name=tier.tier_name,
    )


# ── API key gating ─────────────────────────────────────────────────────────


async def check_api_key_allowed(
    db: AsyncSession,
    user_id: int,
    workspace_id: str | None = None,
) -> LimitCheckResult:
    """Check if a user can generate API keys.

    Requires has_api_access (pro+ tier). Free-tier users cannot create API keys.
    """
    tier = await resolve_user_tier(db, user_id, workspace_id)

    if tier.is_in_grace_period:
        return LimitCheckResult(
            allowed=False,
            reason=(
                f"Subscription expired. Grace period active until "
                f"{tier.grace_period_expires_at:%Y-%m-%d}. "
                f"Renew your plan to generate API keys."
            ),
            tier_name=tier.tier_name,
        )

    if not tier.has_api_access:
        return LimitCheckResult(
            allowed=False,
            reason=(
                "API key access requires a Pro plan or higher. "
                f"Your current plan ({tier.display_name}) does not include API access."
            ),
            tier_name=tier.tier_name,
        )

    return LimitCheckResult(allowed=True, tier_name=tier.tier_name)


# ── Billing dashboard ──────────────────────────────────────────────────────


async def get_billing_dashboard(
    db: AsyncSession,
    user_id: int,
    workspace_id: str | None = None,
) -> BillingDashboard:
    """Build the full billing dashboard for a user."""
    tier = await resolve_user_tier(db, user_id, workspace_id)

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Mission counts
    daily_q = select(func.count(Mission.id)).where(
        Mission.user_id == user_id,
        Mission.created_at >= today_start,
        Mission.deleted_at.is_(None),
    )
    missions_today = (await db.execute(daily_q)).scalar() or 0

    monthly_q = select(func.count(Mission.id)).where(
        Mission.user_id == user_id,
        Mission.created_at >= month_start,
        Mission.deleted_at.is_(None),
    )
    missions_this_month = (await db.execute(monthly_q)).scalar() or 0

    active_statuses = {
        MissionStatus.QUEUED,
        MissionStatus.RUNNING,
        MissionStatus.EXECUTING,
        MissionStatus.PLANNING,
    }
    active_q = select(func.count(Mission.id)).where(
        Mission.user_id == user_id,
        Mission.status.in_(active_statuses),
        Mission.deleted_at.is_(None),
    )
    active_missions = (await db.execute(active_q)).scalar() or 0

    # API key count
    from app.models.byok_models import UserAPIKey

    keys_q = select(func.count(UserAPIKey.id)).where(UserAPIKey.user_id == user_id)
    api_keys_count = (await db.execute(keys_q)).scalar() or 0

    usage = UsageSnapshot(
        missions_today=missions_today,
        missions_this_month=missions_this_month,
        active_missions=active_missions,
        api_keys_count=api_keys_count,
    )

    # Subscription period info
    sub_result = await db.execute(
        select(UserSubscription)
        .where(
            UserSubscription.user_id == user_id,
            UserSubscription.status.in_(["active", "expired"]),
        )
        .order_by(UserSubscription.id.desc())
        .limit(1)
    )
    sub = sub_result.scalar_one_or_none()

    return BillingDashboard(
        plan=tier,
        usage=usage,
        current_period_start=sub.current_period_start if sub else None,
        current_period_end=sub.current_period_end if sub else None,
        cancel_at_period_end=sub.cancel_at_period_end if sub else False,
        paypal_subscription_id=sub.paypal_subscription_id if sub else None,
    )


# ── Internals ──────────────────────────────────────────────────────────────


def _tier_to_limits(tier: SubscriptionTier, *, is_active: bool) -> TierLimits:
    """Convert a SubscriptionTier ORM object to a TierLimits dataclass."""
    return TierLimits(
        tier_id=tier.id,
        tier_name=tier.name,
        display_name=tier.display_name,
        missions_per_day=tier.missions_per_day,
        missions_per_month=tier.missions_per_month,
        max_concurrent_missions=tier.max_concurrent_missions,
        has_priority_support=tier.has_priority_support,
        has_api_access=tier.has_api_access,
        has_custom_models=tier.has_custom_models,
        price_monthly=tier.price_monthly,
        paypal_plan_id=tier.paypal_plan_id,
        is_active_subscription=is_active,
    )
