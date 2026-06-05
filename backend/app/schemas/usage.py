from datetime import datetime

from pydantic import BaseModel


class UsageRecord(BaseModel):
    user_id: str
    model_id: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost: float
    timestamp: datetime


class UsageByModel(BaseModel):
    model_id: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost: float


class UsageSummaryResponse(BaseModel):
    total_tokens: int
    total_cost: float
    period: str
    breakdown: list[UsageByModel]
