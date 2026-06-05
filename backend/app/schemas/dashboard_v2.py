"""Dashboard v2 schemas — execution history, cost analytics, logs, stats."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MissionHistoryItem(BaseModel):
    """Single mission in the execution history list."""

    id: str
    title: str
    status: str
    mission_type: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    actual_cost: float | None = None
    tokens_used: int | None = None
    task_count: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    error_message: str | None = None

    model_config = {"from_attributes": True}


class MissionHistoryResponse(BaseModel):
    """Paginated mission history response."""

    items: list[MissionHistoryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    pages: int = 0


class CostByAgent(BaseModel):
    """Cost breakdown for a single agent."""

    agent_id: str
    cost_usd: float = 0.0


class CostByModel(BaseModel):
    """Cost breakdown for a single model."""

    model_id: str
    cost_usd: float = 0.0


class CostAnalyticsResponse(BaseModel):
    """Aggregated cost analytics for a user."""

    total_cost: float = 0.0
    previous_period_cost: float | None = None
    trend_pct: float | None = None
    by_agent: list[CostByAgent] = Field(default_factory=list)
    by_model: list[CostByModel] = Field(default_factory=list)


class LogEntry(BaseModel):
    """Single mission log entry."""

    id: str
    mission_id: str
    task_id: str | None = None
    mission_title: str | None = None
    task_title: str | None = None
    level: str = "info"
    message: str
    timestamp: str
    data: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class LogSearchResponse(BaseModel):
    """Paginated log search results."""

    items: list[LogEntry] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    pages: int = 0


class DashboardStats(BaseModel):
    """Aggregate dashboard statistics for a user."""

    total_missions: int = 0
    completed_missions: int = 0
    failed_missions: int = 0
    success_rate: float = 0.0
    avg_duration_seconds: float = 0.0
    total_cost: float = 0.0
    total_tokens: int = 0
