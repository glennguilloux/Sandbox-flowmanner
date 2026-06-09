"""Mission and MissionTask models (separate from mission.py for services/learning_service.py)."""

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class AbortReason(str, Enum):
    """Typed reasons for aborting a mission."""

    USER_REQUESTED = "user_requested"
    BUDGET_EXCEEDED = "budget_exceeded"
    TIMEOUT = "timeout"
    ERROR_CASCADE = "error_cascade"
    DEPENDENCY_FAILURE = "dependency_failure"
    MANUAL_INTERVENTION = "manual_intervention"


class MissionStatus(str, Enum):
    """Typed mission lifecycle states with validated transitions.

    External (user-visible): draft, pending, queued, running, completed, approved, failed, paused, aborted
    Internal (executor phases): planning, planned, executing
    Deprecated alias: cancelled (mapped to aborted)
    """

    DRAFT = "draft"
    PENDING = "pending"
    PLANNING = "planning"
    PLANNED = "planned"
    QUEUED = "queued"
    EXECUTING = "executing"
    RUNNING = "running"
    COMPLETED = "completed"
    APPROVED = "approved"
    FAILED = "failed"
    PAUSED = "paused"
    ABORTED = "aborted"
    CANCELLED = "aborted"  # deprecated alias for ABORTED — same value

    # Valid transitions from each state (use enum members, not strings)
    _TRANSITIONS: dict["MissionStatus", set["MissionStatus"]] = {
        DRAFT: {PENDING, ABORTED},  # type: ignore[arg-type]
        PENDING: {PLANNING, QUEUED, ABORTED},  # type: ignore[arg-type]
        PLANNING: {PLANNED, ABORTED},  # type: ignore[arg-type]
        PLANNED: {EXECUTING, ABORTED},  # type: ignore[arg-type]
        EXECUTING: {RUNNING, ABORTED},  # type: ignore[arg-type]
        QUEUED: {RUNNING, ABORTED},  # type: ignore[arg-type]
        RUNNING: {COMPLETED, APPROVED, FAILED, PAUSED, ABORTED},  # type: ignore[arg-type]
        PAUSED: {RUNNING, ABORTED},  # type: ignore[arg-type]
        COMPLETED: {APPROVED},  # type: ignore[arg-type]  # completed can be promoted to approved
        APPROVED: set(),  # type: ignore[arg-type]  # terminal
        FAILED: set(),  # type: ignore[arg-type]  # terminal
        ABORTED: set(),  # type: ignore[arg-type]  # terminal
    }

    @property
    def is_terminal(self) -> bool:
        """Return True if this status is a terminal/final state."""
        return not self._TRANSITIONS.get(self, set())

    @property
    def is_active(self) -> bool:
        """Return True if the mission is currently active (not terminal)."""
        return not self.is_terminal

    def can_transition_to(self, target: "MissionStatus") -> bool:
        """Return True if transitioning from self to target is valid."""
        allowed = self._TRANSITIONS.get(self, set())
        return target in allowed


class MissionTaskStatus(str, Enum):
    """Typed task lifecycle states with validated transitions."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    # Valid transitions from each state (use enum members, not strings)
    _TRANSITIONS: dict["MissionTaskStatus", set["MissionTaskStatus"]] = {
        PENDING: {RUNNING},  # type: ignore[arg-type]
        RUNNING: {COMPLETED, FAILED},  # type: ignore[arg-type]
        FAILED: {PENDING},  # type: ignore[arg-type]  # allow retry
        COMPLETED: set(),  # type: ignore[arg-type]  # terminal
    }

    @property
    def is_terminal(self) -> bool:
        """Return True if this status is a terminal/final state."""
        return not self._TRANSITIONS.get(self, set())

    @property
    def is_active(self) -> bool:
        """Return True if the task is currently active (not terminal)."""
        return not self.is_terminal

    def can_transition_to(self, target: "MissionTaskStatus") -> bool:
        """Return True if transitioning from self to target is valid."""
        allowed = self._TRANSITIONS.get(self, set())
        return target in allowed


# ── Models ───────────────────────────────────────────────────────────────────

# Hardcoded tuples — do NOT derive from enum iteration because
# MissionStatus(str, Enum) leaks the _TRANSITIONS class attribute
# into iteration, corrupting the CHECK constraint SQL.
ALL_MISSION_STATUSES: tuple[str, ...] = (
    "draft",
    "pending",
    "planning",
    "planned",
    "queued",
    "executing",
    "running",
    "completed",
    "approved",
    "failed",
    "paused",
    "aborted",
)
ALL_TASK_STATUSES: tuple[str, ...] = ("pending", "running", "completed", "failed")


class Mission(Base, TimestampMixin):
    __tablename__ = "missions"
    __table_args__ = (
        CheckConstraint(
            f"status IN {ALL_MISSION_STATUSES}",
            name="ck_mission_status_valid",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=lambda: uuid4()
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mission_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    context_files: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    context_urls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[MissionStatus] = mapped_column(
        String(20),
        default=MissionStatus.PENDING,
        index=True,
    )
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_files: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    feedback_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Double, nullable=True)
    actual_cost: Mapped[float | None] = mapped_column(Double, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_mission_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True
    )
    integration_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, server_default="1"
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )


class MissionTask(Base, TimestampMixin):
    __tablename__ = "mission_tasks"
    __table_args__ = (
        CheckConstraint(
            f"status IN {ALL_TASK_STATUSES}",
            name="ck_mission_task_status_valid",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=lambda: uuid4()
    )
    mission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id"), nullable=False, index=True
    )
    parent_task_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mission_tasks.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    assigned_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[MissionTaskStatus] = mapped_column(
        String(20),
        default=MissionTaskStatus.PENDING,
        index=True,
    )
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dependencies: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approval_required: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Double, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MissionLog(Base):
    __tablename__ = "mission_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=lambda: uuid4()
    )
    mission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    level: Mapped[str | None] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class MissionImprovement(Base, TimestampMixin):
    __tablename__ = "mission_improvements"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=lambda: uuid4()
    )
    mission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id"), nullable=False, index=True
    )
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    failure_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_context: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Model-level transition validation via SQLAlchemy events ──────────────────


def _validate_mission_transition(mission: Mission, new_status_value: str) -> None:
    """Raise ValueError if the transition is not allowed."""
    old_status = mission.status
    if old_status is None:
        return
    try:
        old = MissionStatus(old_status) if isinstance(old_status, str) else old_status
        new = (
            MissionStatus(new_status_value)
            if isinstance(new_status_value, str)
            else new_status_value
        )
    except ValueError:
        return

    if not old.can_transition_to(new):
        raise ValueError(
            f"Invalid mission status transition: {old.value} → {new.value}"
        )


def _validate_task_transition(task: MissionTask, new_status_value: str) -> None:
    """Raise ValueError if the transition is not allowed."""
    old_status = task.status
    if old_status is None:
        return
    try:
        old = (
            MissionTaskStatus(old_status) if isinstance(old_status, str) else old_status
        )
        new = (
            MissionTaskStatus(new_status_value)
            if isinstance(new_status_value, str)
            else new_status_value
        )
    except ValueError:
        return

    if not old.can_transition_to(new):
        raise ValueError(f"Invalid task status transition: {old.value} → {new.value}")


@event.listens_for(Mission.status, "set", retval=True)
def _on_mission_status_set(target: Mission, value, oldvalue, initiator):
    if value is not None:
        _validate_mission_transition(target, value)
    return value


@event.listens_for(MissionTask.status, "set", retval=True)
def _on_task_status_set(target: MissionTask, value, oldvalue, initiator):
    if value is not None:
        _validate_task_transition(target, value)
    return value
