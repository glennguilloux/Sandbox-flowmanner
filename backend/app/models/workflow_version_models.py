"""Workflow versioning and execution event models — Phase 2.6.

Adds version snapshots for workflow definitions (matching the pattern
used by tool_versions, capability_versions, agent_template_versions)
and an append-only execution event log for observability.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class WorkflowVersion(Base, TimestampMixin):
    """Immutable version snapshot of a workflow definition.

    Each time a workflow's ``graph_definition`` changes, a new version
    row is created.  This enables rollback, diffing, and audit trails.
    """

    __tablename__ = "workflow_versions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    workflow_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExecutionEvent(Base, TimestampMixin):
    """Append-only event log for workflow executions.

    Records lifecycle transitions, node-level events, errors, and
    side-effects during a workflow run.  Never updated or deleted —
    the event stream is the authoritative execution history.
    """

    __tablename__ = "execution_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    execution_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="'started', 'node_started', 'node_completed', 'node_failed', "
        "'completed', 'failed', 'paused', 'resumed', 'side_effect'",
    )
    node_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="ID of the workflow node this event relates to (if any)",
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    level: Mapped[str] = mapped_column(
        String(20),
        default="info",
        nullable=False,
        comment="'debug', 'info', 'warn', 'error'",
    )
    sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Monotonically increasing sequence within the execution",
    )
