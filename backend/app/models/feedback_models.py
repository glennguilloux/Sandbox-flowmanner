"""Feedback synthesis models — FeedbackReport and FeedbackPattern."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class FeedbackReport(Base, TimestampMixin):
    """Synthesized feedback for a mission execution."""

    __tablename__ = "feedback_reports"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    mission_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("missions.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Scores
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    efficiency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Analysis
    strengths: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"items": [...]}
    weaknesses: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"items": [...]}
    suggestions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"items": [...]}
    task_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # per-task breakdown
    error_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"errors": [...]}
    token_efficiency: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"total_tokens, cost_estimate, ...}"

    # Metadata
    synthesis_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")

    # Relationships
    mission = relationship("Mission", foreign_keys=[mission_id], lazy="selectin")


class FeedbackPattern(Base, TimestampMixin):
    """Recurring feedback patterns across missions."""

    __tablename__ = "feedback_patterns"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    pattern_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "error", "efficiency", "quality"
    description: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium"
    )  # "low", "medium", "high", "critical"
    example_mission_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {"mission_ids": [...]}
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # "active", "resolved", "dismissed"
