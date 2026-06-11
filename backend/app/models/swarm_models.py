"""Orchestrator execution models — multi-agent goal tracking, task decomposition."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class OrchestratorExecution(Base, TimestampMixin):
    __tablename__ = "orchestrator_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, decomposing, dispatching, running, synthesizing, completed, failed
    strategy: Mapped[str] = mapped_column(String(50), default="parallel")  # parallel, sequential, debate
    synthesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    conflict_markers: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    agent_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tasks: Mapped[list["OrchestratorTask"]] = relationship(back_populates="execution", cascade="all, delete-orphan")


class OrchestratorTask(Base, TimestampMixin):
    __tablename__ = "orchestrator_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    execution_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("orchestrator_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, assigned, running, completed, failed, escalated
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    depends_on: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    execution: Mapped["OrchestratorExecution"] = relationship(back_populates="tasks")
