"""LLM Evaluation models — golden datasets, test cases, and eval runs."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class GoldenDataset(Base, TimestampMixin):
    __tablename__ = "golden_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # code, review, rag, agent, creative
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    test_cases: Mapped[list["GoldenTestCase"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")
    eval_runs: Mapped[list["EvalRun"]] = relationship(back_populates="dataset", cascade="all, delete-orphan")


class GoldenTestCase(Base, TimestampMixin):
    __tablename__ = "golden_test_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("golden_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    input_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    expected_behavior: Mapped[str] = mapped_column(Text, nullable=False)  # description of what good output looks like
    task_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # code_generation, rag_accuracy, agent_reasoning, creative
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")  # easy, medium, hard
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    rubric: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # scoring criteria: accuracy, completeness, relevance, safety (weighted)

    dataset: Mapped["GoldenDataset"] = relationship(back_populates="test_cases")


class EvalRun(Base, TimestampMixin):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("golden_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_config_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # hash of system prompt, temperature, etc.
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, running, completed, failed
    aggregate_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scores_by_category: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    per_case_scores: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Comment 10: cost-per-correct-answer tracking for model rollout (Opus).
    # total_cost_usd is the summed cost of every model generation call in the
    # run (judge calls excluded unless judge_model is the same); total_latency_ms
    # is the summed generation latency; routed_provider is the dominant provider
    # observed across cases.
    total_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    routed_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Pass/correct rate derived from the rubric threshold (Comment 10).
    pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    correct_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    langfuse_trace_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dataset: Mapped["GoldenDataset"] = relationship(back_populates="eval_runs")
