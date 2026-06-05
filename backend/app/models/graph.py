from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class Workflow(Base, TimestampMixin):
    """Workflow definition (consolidated from GraphWorkflow + Flow, H4.2).

    Migration h5_rename_graph_tables has been applied. Tablename updated
    from "graph_workflows" to "workflows".
    """
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True,
    )


class WorkflowExecution(Base, TimestampMixin):
    """Execution instance of a Workflow (renamed from GraphExecution, H4.2).

    Migration h5_rename_graph_tables applied. Tablename and FK references
    updated from graph_* to workflow_*.
    """
    __tablename__ = "workflow_executions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True,
    )


class WorkflowState(Base, TimestampMixin):
    """Per-node state during workflow execution (renamed from GraphState, H4.2).

    Migration h5_rename_graph_tables applied. Tablename and FK references
    updated from graph_* to workflow_*.
    """
    __tablename__ = "workflow_states"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=True
    )
    workflow_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=True
    )
    state_data: Mapped[dict] = mapped_column(JSONB, nullable=False)


# ── Backward-compat aliases (H4.2 migration) ──────────────────────

GraphWorkflow = Workflow
GraphExecution = WorkflowExecution
GraphState = WorkflowState
