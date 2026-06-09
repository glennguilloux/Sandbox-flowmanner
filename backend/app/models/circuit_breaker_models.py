"""Circuit Breaker models — Phase 6.4.

Provides:
- MissionCircuitBreaker: Per-mission execution limits and state
- CircuitBreakerState: Enum of breaker states

Design decisions:
- One-to-one with Mission (FK, cascade delete)
- Separate from Mission model to avoid schema pollution
- Limits are configurable per-mission; defaults from workspace settings
- State transitions: ARMED → TRIGGERED → CIRCUIT_BROKEN
- The executor checks the breaker before each tool/LLM call
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class CircuitBreakerState(str, Enum):
    """States for circuit breaker lifecycle."""

    ARMED = "armed"  # Normal operation, limits not yet exceeded
    TRIGGERED = "triggered"  # A limit was hit; mission paused, can resume
    CIRCUIT_BROKEN = "circuit_broken"  # Permanent stop; requires manual reset


class MissionCircuitBreaker(Base, TimestampMixin):
    """Per-mission circuit breaker with configurable limits.

    Created alongside the mission (or lazily on first check).
    The executor checks limits before every LLM call and tool call.
    When any limit is exceeded, the breaker transitions to TRIGGERED,
    which pauses the mission.  Repeated triggers escalate to
    CIRCUIT_BROKEN, which requires manual intervention.

    Destructive action policy: if `destructive_actions_require_approval`
    is True, tool calls flagged as destructive will raise a
    HumanInterrupt before execution.
    """

    __tablename__ = "mission_circuit_breakers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    mission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    # ── Configurable limits ──────────────────────────────────────────
    max_llm_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
    )
    max_cost_usd: Mapped[float] = mapped_column(
        nullable=False,
        default=10.0,
    )
    max_duration_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3600,
    )
    max_tool_calls: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=200,
    )
    destructive_actions_require_approval: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # ── Current counters ─────────────────────────────────────────────
    llm_calls_made: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    tool_calls_made: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    cost_accumulated_usd: Mapped[float] = mapped_column(
        nullable=False,
        default=0.0,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── State ────────────────────────────────────────────────────────
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CircuitBreakerState.ARMED.value,
        server_default="armed",
        index=True,
    )
    trigger_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    trigger_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    # ── Destructive action list ──────────────────────────────────────
    destructive_actions: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="List of tool/action names that require approval when destructive_actions_require_approval=True",
    )

    def check_limits(self) -> tuple[bool, str]:
        """Check if any limit has been exceeded.

        Returns:
            (is_broken, reason_string) — True if a limit was hit.
        """
        if self.state == CircuitBreakerState.CIRCUIT_BROKEN.value:
            return True, "Circuit breaker is permanently broken — manual reset required"

        llm_made = self.llm_calls_made or 0
        tool_made = self.tool_calls_made or 0
        cost_acc = self.cost_accumulated_usd or 0.0

        if self.max_llm_calls > 0 and llm_made >= self.max_llm_calls:
            return True, f"LLM call limit reached ({llm_made}/{self.max_llm_calls})"

        if self.max_tool_calls > 0 and tool_made >= self.max_tool_calls:
            return True, f"Tool call limit reached ({tool_made}/{self.max_tool_calls})"

        if self.max_cost_usd > 0 and cost_acc >= self.max_cost_usd:
            return (
                True,
                f"Cost limit reached (${cost_acc:.4f}/${self.max_cost_usd:.2f})",
            )

        if self.max_duration_seconds > 0 and self.started_at:
            elapsed = (datetime.now(UTC) - self.started_at).total_seconds()
            if elapsed >= self.max_duration_seconds:
                return (
                    True,
                    f"Duration limit reached ({elapsed:.0f}s/{self.max_duration_seconds}s)",
                )

        return False, ""

    def should_approve(self, action_name: str) -> bool:
        """Check if a specific action requires human approval."""
        if not self.destructive_actions_require_approval:
            return False
        destructive: list[str] = self.destructive_actions or []  # type: ignore[assignment]
        return action_name in destructive
