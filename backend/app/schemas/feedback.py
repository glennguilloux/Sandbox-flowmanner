"""Pydantic schemas for feedback synthesis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from datetime import datetime


class FeedbackReportResponse(BaseModel):
    id: str
    mission_id: str
    overall_score: float
    efficiency_score: float | None = None
    quality_score: float | None = None
    strengths: dict | None = None
    weaknesses: dict | None = None
    suggestions: dict | None = None
    task_analysis: dict | None = None
    error_summary: dict | None = None
    token_efficiency: dict | None = None
    synthesis_mode: str = "auto"
    status: str = "completed"
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SynthesizeRequest(BaseModel):
    mode: str = "auto"  # "auto" or "manual"
    include_task_analysis: bool = True
    include_patterns: bool = True


class FeedbackPatternResponse(BaseModel):
    id: str
    pattern_type: str
    description: str
    frequency: int
    severity: str
    example_mission_ids: dict | None = None
    suggested_fix: str | None = None
    status: str = "active"
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class FeedbackPatternUpdate(BaseModel):
    status: str | None = None  # "active", "resolved", "dismissed"
    suggested_fix: str | None = None


class FeedbackAnalyticsResponse(BaseModel):
    total_reports: int
    avg_overall_score: float
    avg_efficiency_score: float | None = None
    avg_quality_score: float | None = None
    top_patterns: list[dict] = []
    score_trend: list[dict] = []  # [{"date": ..., "score": ...}]


class BulkSynthesizeRequest(BaseModel):
    mission_ids: list[str]
    mode: str = "auto"


class FeedbackCompareResponse(BaseModel):
    missions: list[dict]  # per-mission summary
    score_delta: dict  # {"overall": float, "efficiency": float, "quality": float}
    improvements: list[str]
    regressions: list[str]
