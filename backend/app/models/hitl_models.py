"""HITL (Human-in-the-Loop) models — Phase 6.2.

Provides:
- InboxItem: Persistent inbox items for human interrupts (approval, clarification, escalation)
- HumanInterruptType: Enum of interrupt types
- InboxItemStatus: Enum of item statuses

Design decisions:
- DB-backed (not in-memory/Redis) for durability and multi-instance support
- Workspace-scoped via mission→workspace relationship
- Soft-resolve: items are resolved, not deleted
- Resolution payload carries the human's response
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Identity, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class HumanInterruptType(str, Enum):
    """Types of human interrupts."""

    APPROVAL = "approval"
    CLARIFICATION = "clarification"
    ESCALATION = "escalation"
    # GOV-1.1: memory write approvals are drained into the inbox as a
    # SEPARATE filter from mission action approvals (no SLA contention)
    # and must never pause/abort a mission.
    MEMORY_APPROVAL = "memory_approval"


class InboxItemStatus(str, Enum):
    """Lifecycle states for inbox items."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLARIFIED = "clarified"
    ESCALATED = "escalated"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class InboxItem(Base, TimestampMixin):
    """Persistent inbox item for human-in-the-loop interrupts.

    Created when an executor node requires human approval, clarification,
    or escalation.  Resolved when the human responds via the Inbox API.

    The item is linked to a mission and optionally to a specific task/node.
    When resolved, the executor resumes from the point it paused.
    """

    __tablename__ = "inbox_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    # GOV-1.1: memory write approvals (MEMORY_APPROVAL) are not bound to a
    # mission, so mission_id is nullable. Action approvals still require one.
    mission_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    node_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )

    # Interrupt details
    interrupt_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_action: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Status and resolution
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=InboxItemStatus.PENDING.value,
        server_default="pending",
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resolved_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )
    resolution_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Expiration
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class HumanInterrupt(Exception):
    """Exception raised by the executor to pause execution for human input.

    This is caught by the UnifiedExecutor, which persists the interrupt
    to the inbox_items table and signals the mission as paused.

    Args:
        interrupt_type: Type of interrupt (approval, clarification, escalation)
        title: Human-readable summary of what needs attention
        description: Detailed explanation
        proposed_action: What the agent wants to do (structured data)
        context: Additional context for the human
        task_id: Optional task UUID where the interrupt occurred
        node_id: Optional node UUID where the interrupt occurred
        expires_at: Optional expiration time
    """

    def __init__(
        self,
        interrupt_type: HumanInterruptType,
        title: str,
        *,
        description: str | None = None,
        proposed_action: dict | None = None,
        context: dict | None = None,
        task_id: str | None = None,
        node_id: str | None = None,
        expires_at: datetime | None = None,
    ):
        self.interrupt_type = interrupt_type
        self.title = title
        self.description = description
        self.proposed_action = proposed_action
        self.context = context
        self.task_id = task_id
        self.node_id = node_id
        self.expires_at = expires_at
        super().__init__(f"[{interrupt_type.value}] {title}")


class WorkspaceHITLConfig(Base, TimestampMixin):
    """Per-workspace HITL configuration.

    Controls auto-action behaviour when inbox items expire.
    Each workspace gets one row; absence means "use system defaults".
    """

    __tablename__ = "workspace_hitl_configs"
    __table_args__ = (UniqueConstraint("workspace_id", name="uq_workspace_hitl_config"),)

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timeout_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="24",
    )
    auto_action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="reject",
    )
    # CHECK constraint enforces valid auto-action values at DB level
    # (enforced via migration, not declaratively here, for consistency with
    # other models in this file that use plain String columns)

    # Relationship back to workspace
    workspace = relationship("Workspace", foreign_keys=[workspace_id], lazy="selectin")
