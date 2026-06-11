"""Blueprint + Run unified models — replaces Mission/Workflow/Flow/Orchestrator/Pipeline.

Two first-class objects:
- Blueprint = reusable, versioned work definition
- Run = one execution instance of a Blueprint

This collapses 14 execution tables → 4 tables + substrate_events.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin

# ── Enums ────────────────────────────────────────────────────────────────────


class BlueprintStatus(str, Enum):
    """Blueprint lifecycle states."""

    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class BlueprintType(str, Enum):
    """Blueprint execution types — maps 1:1 to WorkflowType."""

    SOLO = "solo"
    DAG = "dag"
    SWARM = "swarm"
    PIPELINE = "pipeline"
    GRAPH = "graph"
    META = "meta"
    LANGGRAPH = "langgraph"


class RunStatus(str, Enum):
    """Run lifecycle states."""

    PENDING = "pending"
    QUEUED = "queued"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


# ── Models ───────────────────────────────────────────────────────────────────


class Blueprint(Base, TimestampMixin):
    """Reusable, versioned definition of executable work.

    Replaces: Mission, Workflow/Graph, MissionTemplate.
    The `definition` JSONB column stores the Workflow-shaped data
    (nodes, edges, budget, config) as a declarative blueprint.
    """

    __tablename__ = "blueprints"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Identity
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Definition — THE key column
    blueprint_type: Mapped[str] = mapped_column(String(50), nullable=False, default="solo", index=True)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    input_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    # Metadata
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Usage stats (denormalized)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Run(Base, TimestampMixin):
    """Single execution instance of a Blueprint.

    Replaces: WorkflowExecution, OrchestratorExecution, SwarmPipeline.
    The `snapshot` column is an immutable copy of Blueprint.definition
    at run creation time — enables deterministic replay.
    """

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    blueprint_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("blueprints.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    # Execution state
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)

    # Immutable snapshot of Blueprint.definition at run time
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Results
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Budget tracking
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0.0")
    budget_limit_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Parent/child for sub-workflows (SUB_WORKFLOW NodeType)
    parent_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id"),
        nullable=True,
        index=True,
    )

    # Context
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Metadata (agent IDs, model IDs, etc.)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class BlueprintVersion(Base, TimestampMixin):
    """Versioned snapshot of a Blueprint's definition.

    Created on every `definition` change. Enables rollback, diffing,
    and success-rate analysis across blueprint versions.
    """

    __tablename__ = "blueprint_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    blueprint_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("blueprints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
