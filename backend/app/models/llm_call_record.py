"""LLMCallRecord model — dedicated observability table for H1.3.

Records every LLM API call made during mission execution:
- model_id, provider
- prompt_tokens, completion_tokens
- cost_usd, latency_ms
- success/error
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class LLMCallRecord(Base):
    __tablename__ = "llm_call_records"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    mission_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 6.3: Cost attribution columns
    agent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
    # Q1-B Chunk 4: Per-step cost attribution columns
    cost_category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="llm_tokens",
        index=True,
    )
    tool_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    embedding_tokens: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=0,
    )
