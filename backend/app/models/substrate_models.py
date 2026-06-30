"""Substrate models — event-sourced execution substrate (H2.1).

The Event table is the source of truth for all mission state transitions.
It is genuinely append-only: a PostgreSQL trigger prevents UPDATE or DELETE.

Event columns:
- sequence: Monotonically increasing sequence number (per run)
- run_id: Groups events belonging to one mission execution
- type: Event type (e.g., "task.started", "task.completed", "mission.aborted")
- payload: JSONB event payload
- causal_parent: Sequence number of the event that caused this one
- actor: Who/what triggered this event (e.g., "mission_executor", "user", "system")
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class SubstrateEvent(Base):
    """Append-only event log entry for the event-sourced execution substrate.

    One row per state transition.  The relational Mission / MissionTask tables
    remain as *projections* of the event log — they can be rebuilt from the
    event stream at any time.

    The append-only guarantee is enforced by a PostgreSQL trigger
    (see migration h2_substrate_init) that raises on any UPDATE or DELETE.
    """

    __tablename__ = "substrate_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    mission_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    causal_parent: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
    blueprint_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )


# ── Known event types ──────────────────────────────────────────────


class SubstrateEventType:
    """Well-known event types for the substrate event stream.

    Phase 10: Constant names renamed from MISSION_* → RUN_* and TASK_* → NODE_*
    to reflect the unified Blueprint + Run model.
    **String values remain unchanged** for backward compatibility with
    existing data in the substrate_events table.
    """

    # Run lifecycle (was MISSION_*)
    RUN_STARTED = "mission.started"
    RUN_COMPLETED = "mission.completed"
    RUN_FAILED = "mission.failed"
    RUN_ABORTED = "mission.aborted"
    RUN_PAUSED = "mission.paused"
    RUN_RESUMED = "mission.resumed"

    # Node lifecycle (was TASK_*)
    NODE_STARTED = "task.started"
    NODE_COMPLETED = "task.completed"
    NODE_FAILED = "task.failed"
    NODE_RETRYING = "task.retrying"
    NODE_SKIPPED = "task.skipped"

    LLM_CALL = "llm.call"
    LLM_RESPONSE = "llm.response"

    TOOL_CALL = "tool.call"
    TOOL_RESPONSE = "tool.response"

    CHECKPOINT = "substrate.checkpoint"
    BUDGET_EXHAUSTED = "substrate.budget_exhausted"
    ERROR = "substrate.error"

    # Phase 6: HITL events
    HUMAN_INTERRUPT_RAISED = "human_interrupt.raised"
    HUMAN_INTERRUPT_RESOLVED = "human_interrupt.resolved"

    # Phase 6: Circuit breaker events
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker.triggered"
    CIRCUIT_BREAKER_BROKEN = "circuit_breaker.broken"
    CIRCUIT_BREAKER_RESET = "circuit_breaker.reset"

    # Q1-A: Worker lease events
    LEASE_CLAIMED = "run.lease.claimed"
    LEASE_RENEWED = "run.lease.renewed"
    LEASE_RELEASED = "run.lease.released"

    # Q1-A chunk 4: Resume validation event
    RUN_RESUME_VALIDATED = "run.resumed"

    # Q1-A chunk 5: Per-workspace+provider circuit breaker events
    CIRCUIT_BREAKER_OPENED = "circuit_breaker.opened"
    PROVIDER_FALLBACK_INVOKED = "provider.fallback_invoked"

    # Q1-B chunk 1: HITL resume event
    HITL_RESUMED = "hitl.resumed"

    # Q2-Q3 Chunk 3: Tool routing events
    TOOL_ROUTE_DECIDED = "tool_route.decided"

    # Q2-Q3 Chunk 4: Adaptive reasoning depth events
    DEPTH_DECIDED = "depth.decided"

    # Q2-Q3 Chunk 5: Multi-agent handoff events
    HANDOFF_INITIATED = "handoff.initiated"
    HANDOFF_ACCEPTED = "handoff.accepted"
    HANDOFF_COMPLETED = "handoff.completed"
    HANDOFF_FAILED = "handoff.failed"
    HANDOFF_BUDGET_EXHAUSTED = "handoff.budget_exhausted"
    HANDOFF_LEASE_LOST = "handoff.lease_lost"

    # Q2-Q3 Chunk 6: Self-correction events
    SELF_CORRECTION_ATTEMPTED = "self_correction.attempted"
    SELF_CORRECTION_COMPLETED = "self_correction.completed"
    SELF_CORRECTION_ABORTED = "self_correction.aborted"

    # Cost-aware plan selection
    PLAN_SELECTED = "plan.selected"

    # Phase 3: Sandbox events
    SANDBOX_CREATED = "sandbox.created"
    SANDBOX_FILES_WRITTEN = "sandbox.files_written"
    SANDBOX_TASK_SUBMITTED = "sandbox.task_submitted"
    SANDBOX_TASK_PROGRESS = "sandbox.task_progress"
    SANDBOX_TASK_COMPLETED = "sandbox.task_completed"
    SANDBOX_TASK_FAILED = "sandbox.task_failed"
    SANDBOX_SNAPSHOT_CREATED = "sandbox.snapshot_created"

    # Backward-compat aliases (deprecated — use RUN_* / NODE_* instead)
    MISSION_STARTED = RUN_STARTED
    MISSION_COMPLETED = RUN_COMPLETED
    MISSION_FAILED = RUN_FAILED
    MISSION_ABORTED = RUN_ABORTED
    MISSION_PAUSED = RUN_PAUSED
    MISSION_RESUMED = RUN_RESUMED
    TASK_STARTED = NODE_STARTED
    TASK_COMPLETED = NODE_COMPLETED
    TASK_FAILED = NODE_FAILED
    TASK_RETRYING = NODE_RETRYING
    TASK_SKIPPED = NODE_SKIPPED


# ── RunState projection ────────────────────────────────────────────


class SubstrateRunState:
    """In-memory projection of a run's current state, built from events.

    This is NOT persisted — it is rebuilt on worker restart by replaying
    the event log from the database.
    """

    __slots__ = (
        "completed_tasks",
        "current_sequence",
        "error_message",
        "failed_tasks",
        "last_event_at",
        "mission_id",
        "run_id",
        "started_at",
        "status",
        "task_states",  # task_id -> task_status
        "total_cost_usd",
        "total_tokens",
    )

    def __init__(self, run_id: str, mission_id: str | None = None):
        self.run_id = run_id
        self.mission_id = mission_id
        self.status = "pending"
        self.current_sequence = 0
        self.task_states: dict[str, dict] = {}
        self.completed_tasks: set[str] = set()
        self.failed_tasks: set[str] = set()
        self.total_tokens = 0
        self.total_cost_usd = 0.0
        self.error_message: str | None = None
        self.started_at: datetime | None = None
        self.last_event_at: datetime | None = None

    def apply(self, event: "SubstrateEvent") -> None:
        """Apply a single event to update the run state."""
        self.current_sequence = max(self.current_sequence, event.sequence)
        self.last_event_at = event.timestamp

        payload = event.payload or {}

        match event.type:
            case SubstrateEventType.MISSION_STARTED:
                self.status = "executing"
                self.started_at = event.timestamp

            case SubstrateEventType.MISSION_COMPLETED:
                self.status = "completed"

            case SubstrateEventType.MISSION_FAILED:
                self.status = "failed"
                self.error_message = payload.get("error")

            case SubstrateEventType.MISSION_ABORTED:
                self.status = "aborted"
                self.error_message = payload.get("reason", "Aborted")

            case SubstrateEventType.MISSION_PAUSED:
                self.status = "paused"

            case SubstrateEventType.MISSION_RESUMED:
                self.status = "executing"

            case SubstrateEventType.TASK_STARTED:
                task_id = payload.get("task_id", "")
                self.task_states[task_id] = {
                    "status": "running",
                    "started_at": event.timestamp,
                }

            case SubstrateEventType.TASK_COMPLETED:
                task_id = payload.get("task_id", "")
                self.task_states[task_id] = {
                    "status": "completed",
                    "completed_at": event.timestamp,
                }
                self.completed_tasks.add(task_id)
                self.total_tokens += payload.get("tokens", 0)
                self.total_cost_usd += payload.get("cost_usd", 0.0)

            case SubstrateEventType.TASK_FAILED:
                task_id = payload.get("task_id", "")
                self.task_states[task_id] = {
                    "status": "failed",
                    "error": payload.get("error"),
                    "completed_at": event.timestamp,
                }
                self.failed_tasks.add(task_id)

            case SubstrateEventType.TASK_RETRYING:
                task_id = payload.get("task_id", "")
                self.task_states[task_id] = {
                    "status": "retrying",
                    "attempt": payload.get("attempt", 1),
                }

            case SubstrateEventType.BUDGET_EXHAUSTED:
                self.status = "failed"
                self.error_message = f"Budget exhausted: {payload.get('budget_type', 'unknown')}"

            # Phase 3: Sandbox events are informational — no state change needed
            case _ if event.type.startswith("sandbox."):
                pass

            case _:
                pass  # Unknown event types are silently applied (no state change)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "mission_id": self.mission_id,
            "status": self.status,
            "sequence": self.current_sequence,
            "completed_tasks": len(self.completed_tasks),
            "failed_tasks": len(self.failed_tasks),
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_event_at": (self.last_event_at.isoformat() if self.last_event_at else None),
        }
