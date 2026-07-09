"""Memory Action Event models — AutoMem Phase 1.

Tracks explicit memory operations (observe, recall, consolidate, etc.)
as structured events for episode tracing and memory proficiency scoring.

Follows the pattern from tool_routing_models.py for Pydantic payloads
and memory_models.py for the SQLAlchemy ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin

# ── Action type constants ──────────────────────────────────────────────


class MemoryActionType:
    """Memory action type constants (no DB enum — validated at application layer)."""

    LOG_OBSERVATION = "log_observation"
    LOG_TOOL_RESULT = "log_tool_result"
    RECALL_EPISODIC = "recall_episodic"
    RECALL_SEMANTIC = "recall_semantic"
    CONSOLIDATE = "consolidate"
    FORGET_LOW_QUALITY = "forget_low_quality"
    PROMOTE = "promote"


ALL_MEMORY_ACTION_TYPES = (
    MemoryActionType.LOG_OBSERVATION,
    MemoryActionType.LOG_TOOL_RESULT,
    MemoryActionType.RECALL_EPISODIC,
    MemoryActionType.RECALL_SEMANTIC,
    MemoryActionType.CONSOLIDATE,
    MemoryActionType.FORGET_LOW_QUALITY,
    MemoryActionType.PROMOTE,
)


# ── ORM Model ─────────────────────────────────────────────────────────


class MemoryActionEvent(Base, TimestampMixin):
    """A single memory action event recorded during an agent episode.

    Each event captures what memory operation was attempted, what came back,
    and how long it took. This enables:
    - Episode tracing (all memory actions for a mission)
    - Memory proficiency scoring (success rate, latency, type distribution)
    - Future meta-LLM review (Phase 2 — needs traces first)
    """

    __tablename__ = "memory_action_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mission_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    action_input: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
    action_result: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
    action_latency_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    action_success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    agent_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_mem_actions_ws_user_created",
            "workspace_id",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_mem_actions_mission",
            "mission_id",
            postgresql_where=text("mission_id IS NOT NULL"),
        ),
        Index(
            "ix_mem_actions_type",
            "action_type",
        ),
    )
