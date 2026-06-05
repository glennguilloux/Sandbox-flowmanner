from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.schemas.usage import UsageSummaryResponse
from app.services.usage_service import UsageService, get_usage_service

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/v1/usage", tags=["usage"])

# Map API period params to service period keys
_PERIOD_MAP: dict[str, str] = {
    "7d": "week",
    "30d": "month",
    "90d": "month",  # service has no 90d; map to month as best-effort
    "day": "day",
    "week": "week",
    "month": "month",
}
_VALID_PERIODS = {"7d", "30d", "90d"}


class UsageTimeseriesPoint(BaseModel):
    timestamp: str
    tokens: int
    cost: float
    request_count: int


class UsageBreakdown(BaseModel):
    model: str
    provider: str
    requests: int
    tokens: int
    cost: float


@router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    period: Annotated[str, Query(description="Time period: 7d, 30d, 90d")] = "30d",
    current_user: User = Depends(get_current_user),
    usage_service: UsageService = Depends(get_usage_service),
) -> UsageSummaryResponse:
    service_period = _PERIOD_MAP.get(period, "month")
    return usage_service.get_summary(
        user_id=str(current_user.id), period=service_period
    )


@router.get("/timeseries", response_model=list[UsageTimeseriesPoint])
async def get_usage_timeseries(
    period: Annotated[str, Query(description="Time period: 7d, 30d, 90d")] = "30d",
    current_user: User = Depends(get_current_user),
    usage_service: UsageService = Depends(get_usage_service),
) -> list[UsageTimeseriesPoint]:
    service_period = _PERIOD_MAP.get(period, "month")
    granularity = "hour" if period == "7d" else "day"
    points = usage_service.get_timeseries(
        user_id=str(current_user.id),
        period=service_period,
        granularity=granularity,
    )
    return [UsageTimeseriesPoint(**p) for p in points]


@router.get("/breakdown", response_model=list[UsageBreakdown])
async def get_usage_breakdown(
    period: Annotated[str, Query(description="Time period: 7d, 30d, 90d")] = "30d",
    provider: str | None = Query(default=None, description="Filter by provider"),
    current_user: User = Depends(get_current_user),
    usage_service: UsageService = Depends(get_usage_service),
) -> list[UsageBreakdown]:
    service_period = _PERIOD_MAP.get(period, "month")
    summary = usage_service.get_summary(
        user_id=str(current_user.id), period=service_period
    )
    breakdown = summary.breakdown

    if provider:
        breakdown = [b for b in breakdown if b.provider.lower() == provider.lower()]

    return [
        UsageBreakdown(
            model=b.model_id,
            provider=b.provider,
            requests=0,  # UsageByModel doesn't track request counts; default to 0
            tokens=b.prompt_tokens + b.completion_tokens,
            cost=b.cost,
        )
        for b in breakdown
    ]
