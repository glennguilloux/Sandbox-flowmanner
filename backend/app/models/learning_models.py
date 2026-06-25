"""Learning & Adaptation models for the improvement loop."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class AdaptationRuleDB(Base, TimestampMixin):
    __tablename__ = "adaptation_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=lambda: str(uuid4()))
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    condition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class LearningFeedbackDB(Base, TimestampMixin):
    __tablename__ = "learning_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    mission_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
