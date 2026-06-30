"""MissionProgram + ProgramRun models (Phase: Mission Programs, T1).

Standing, repeatable missions that accumulate outcome intelligence across
runs and inject that learning into the planner prompt.

Models:
- ``ProgramStatus`` — typed lifecycle states for a program (active/paused/archived).
- ``ProgramRunStatus`` — typed lifecycle states for a single program run.
- ``MissionProgram`` — durable program definition (one per workflow).
- ``ProgramRun`` — a single execution of a program (one per mission).

Design notes (see plan §T1):
- ``workspace_id`` is NOT NULL on ``MissionProgram`` (workspace isolation guardrail).
- Status columns are ``String(20)`` (not the enum) to match the project's
  pattern (``Mission.status`` etc.) — the Python enum is used for
  in-process validation only.
- All ``ALL_*_STATUSES`` tuples are HARDCODED (do NOT derive from enum
  iteration — ``str, Enum`` leaks ``_TRANSITIONS`` into iteration and
  corrupts the CHECK constraint SQL).
"""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003
from enum import Enum, nonmember
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin

# ── Enums ─────────────────────────────────────────────────────────────────


class ProgramStatus(str, Enum):
    """Lifecycle states for a MissionProgram.

    ACTIVE — program is eligible to be fired.
    PAUSED — program is temporarily disabled (no new fires; in-flight runs continue).
    ARCHIVED — terminal; program is soft-deleted / historical only.
    """

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"

    # Valid transitions from each state (use enum members, not strings).
    # WRAPPED in enum.nonmember() to prevent Python 3.11+ Enum metaclass
    # from treating _TRANSITIONS as a regular enum member (which would
    # corrupt iteration, by-class lookup, and CHECK constraint generation).
    _TRANSITIONS: dict[ProgramStatus, set[ProgramStatus]] = nonmember(  # type: ignore[assignment]
        {
            ACTIVE: {PAUSED, ARCHIVED},  # type: ignore[arg-type, dict-item]
            PAUSED: {ACTIVE, ARCHIVED},  # type: ignore[arg-type, dict-item]
            ARCHIVED: set(),  # type: ignore[arg-type, dict-item]  # terminal
        }
    )

    @property
    def is_terminal(self) -> bool:
        """Return True if this status is a terminal/final state."""
        return not self._TRANSITIONS.get(self, set())

    @property
    def is_active(self) -> bool:
        """Return True if the program is currently active (not terminal, not paused)."""
        # "active" in business sense: status is ACTIVE specifically.
        return self == ProgramStatus.ACTIVE

    def can_transition_to(self, target: ProgramStatus) -> bool:
        """Return True if transitioning from self to target is valid."""
        allowed = self._TRANSITIONS.get(self, set())
        return target in allowed


class ProgramRunStatus(str, Enum):
    """Lifecycle states for a single ProgramRun.

    RUNNING — execution in flight.
    COMPLETED — execution finished successfully.
    FAILED — execution finished with error.
    ABORTED — execution was cancelled mid-flight.
    """

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"

    # Valid transitions from each state. See _TRANSITIONS note on
    # ProgramStatus for why this is wrapped in nonmember().
    _TRANSITIONS: dict[ProgramRunStatus, set[ProgramRunStatus]] = nonmember(  # type: ignore[assignment]
        {
            RUNNING: {COMPLETED, FAILED, ABORTED},  # type: ignore[arg-type, dict-item]
            COMPLETED: set(),  # type: ignore[arg-type, dict-item]  # terminal
            FAILED: set(),  # type: ignore[arg-type, dict-item]  # terminal
            ABORTED: set(),  # type: ignore[arg-type, dict-item]  # terminal
        }
    )

    @property
    def is_terminal(self) -> bool:
        """Return True if this status is a terminal/final state."""
        return not self._TRANSITIONS.get(self, set())

    @property
    def is_active(self) -> bool:
        """Return True if the run is currently in flight (not terminal)."""
        return not self.is_terminal

    def can_transition_to(self, target: ProgramRunStatus) -> bool:
        """Return True if transitioning from self to target is valid."""
        allowed = self._TRANSITIONS.get(self, set())
        return target in allowed


# ── Status tuples for CHECK constraints ──────────────────────────────────

# Hardcoded tuples — do NOT derive from enum iteration because
# ProgramStatus(str, Enum) leaks the _TRANSITIONS class attribute
# into iteration, corrupting the CHECK constraint SQL.
ALL_PROGRAM_STATUSES: tuple[str, ...] = (
    "active",
    "paused",
    "archived",
)
ALL_PROGRAM_RUN_STATUSES: tuple[str, ...] = (
    "running",
    "completed",
    "failed",
    "aborted",
)


# ── Models ────────────────────────────────────────────────────────────────


class MissionProgram(Base, TimestampMixin):
    """Durable definition of a standing mission program.

    A ``MissionProgram`` is the long-lived template; each fire creates a
    child ``Mission`` + ``ProgramRun`` pair. The program holds the
    baseline configuration (constraints, context, trigger) and the
    accumulated learning brief used by the planner.
    """

    __tablename__ = "mission_programs"
    __table_args__ = (
        CheckConstraint(
            f"status IN {ALL_PROGRAM_STATUSES}",
            name="ck_mission_program_status_valid",
        ),
    )

    # Primary key — UUID, auto-defaulted via uuid4.
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: uuid4(),
    )

    # Ownership + workspace isolation (workspace_id is NOT NULL per guardrail).
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Human-readable metadata.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mission_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Base mission configuration (copied onto each fired Mission).
    base_constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    base_context_files: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    base_context_urls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Trigger configuration (SUBSUMED — no FK to mission_triggers).
    # Shape: {type: "cron", expression, timezone}
    #    OR {type: "webhook", secret, path}
    #    OR {type: "manual"}
    trigger_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Learning brief (consolidated across runs).
    # Documented sub-keys:
    #   total_runs: int
    #   success_rate: float
    #   avg_cost_usd: float
    #   avg_tokens: int
    #   common_failures: [{pattern, count, mitigation}]
    #   effective_tools: [str]
    #   ineffective_tools: [str]
    #   hitl_history: [{outcome, count}]
    #   plan_adjustments: str
    #   last_consolidated_at: ISO-8601 string
    #   user_notes: str (user-controlled; consolidation MUST NOT overwrite)
    learning_brief: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Lifecycle status (string column, default "active"; project pattern).
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        index=True,
    )

    # Per-run + monthly budget caps (USD). Independent of workspace budget.
    per_run_budget_usd: Mapped[float | None] = mapped_column(Double, nullable=True)
    monthly_budget_usd: Mapped[float | None] = mapped_column(Double, nullable=True)

    # Cron scheduling: next computed fire time (mirrors MissionTrigger.next_fire_at).
    next_fire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ProgramRun(Base, TimestampMixin):
    """A single execution instance of a MissionProgram.

    One ``ProgramRun`` per fired mission. Tracks outcome metrics used by
    ``consolidate_learning()`` to build the next-run learning brief.
    """

    __tablename__ = "program_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN {ALL_PROGRAM_RUN_STATUSES}",
            name="ck_program_run_status_valid",
        ),
    )

    # Primary key — UUID, auto-defaulted via uuid4.
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: uuid4(),
    )

    # Foreign keys to the parent program and the fired mission.
    program_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mission_programs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mission_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # What triggered this run: cron | webhook | manual.
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Lifecycle status (string column, default "running"; project pattern).
    status: Mapped[str] = mapped_column(
        String(20),
        default="running",
        index=True,
    )

    # Outcome metrics (filled in on completion).
    cost_usd: Mapped[float | None] = mapped_column(Double, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Double, nullable=True)
    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
