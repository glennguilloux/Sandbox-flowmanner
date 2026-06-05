"""Unified Agent models — consolidated from 5 files (H4.3).

Covers:
- Agent + AgentTemplate (runtime instances and template definitions)
- AgentRegistration (self-registering agent registry)
- AgentCapability (capability profiles with embeddings)
- AgentMemory (session-scoped memory entries)
- AgentProtocol (inter-agent messages, debates, handoffs, escalations)

State machine: DEFINED → REGISTERED → CAPABILITY_GRANTED → ACTIVE → SUSPENDED → RETIRED

All models from the original 5 files are preserved as-is, just consolidated
into a single module. The state machine is a new Pydantic enum for the canonical
agent lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin

# ── State machine (H4.3) ───────────────────────────────────────────

class AgentState(str, Enum):
    """Canonical agent lifecycle state machine."""
    DEFINED = "defined"                 # Template exists, not yet registered
    REGISTERED = "registered"           # Registered in agent registry
    CAPABILITY_GRANTED = "capability_granted"  # Capabilities assigned
    ACTIVE = "active"                   # Ready to receive tasks
    SUSPENDED = "suspended"             # Temporarily paused
    RETIRED = "retired"                 # Permanently decommissioned


# ── Agent + AgentTemplate (from original agent.py) ─────────────────

class Agent(Base, TimestampMixin):
    """Runtime agent instance."""
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: __import__("uuid").uuid4().__str__(),
    )
    name: Mapped[str] = mapped_column(String(255))
    owner_id: Mapped[str] = mapped_column(String(36))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text(), nullable=True)
    model_preference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config: Mapped[str | None] = mapped_column(Text(), nullable=True)
    state: Mapped[str] = mapped_column(
        String(30), default=AgentState.DEFINED.value, nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default="1")
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )


class AgentVersion(Base, TimestampMixin):
    """Immutable version snapshot of an Agent instance.

    Each time an agent's configuration changes, a new version row is
    created.  Enables rollback, diffing, and audit trails.
    """

    __tablename__ = "agent_versions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: __import__("uuid").uuid4().__str__(),
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentTemplate(Base, TimestampMixin):
    """Template definition for creating agents."""
    __tablename__ = "agent_templates"

    template_id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: __import__("uuid").uuid4().__str__(),
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    agent_type: Mapped[str] = mapped_column(String(50), default="domain")
    system_prompt: Mapped[str | None] = mapped_column(Text(), nullable=True)
    model_config: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean(), default=True)
    state: Mapped[str] = mapped_column(
        String(30), default=AgentState.DEFINED.value, nullable=False,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )


# ── AgentRegistration (from original agent_models.py) ──────────────

class AgentRegistration(Base, TimestampMixin):
    """Self-registering agent entry in the agent registry."""
    __tablename__ = "agent_registrations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()),
    )
    agent_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    capabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    discovered_tools: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    state: Mapped[str] = mapped_column(
        String(30), default=AgentState.REGISTERED.value, nullable=False,
    )


# ── AgentCapability (from original agent_capability.py) ─────────────

class AgentCapability(Base, TimestampMixin):
    """Capability profile for an agent with embeddings."""
    __tablename__ = "agent_capabilities"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: __import__("uuid").uuid4().__str__(),
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tools: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    embedding_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


# ── AgentMemory (from original agent_memory.py) ────────────────────

class AgentMemory(Base, TimestampMixin):
    """A memory entry saved by an agent for recall across sessions.

    Each entry is scoped to a user + agent_id pair so agents operating
    in different workspaces or personas maintain separate memory stores.
    """
    __tablename__ = "agent_memory"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()),
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, default="default",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(100), nullable=False, default="note",
    )
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


# ── AgentProtocol (from original agent_protocol.py) ────────────────

class AgentMessage(Base, TimestampMixin):
    """Inter-agent message with sender, recipient, type, payload, and priority."""
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4()),
    )
    sender_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sub_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    priority: Mapped[int] = mapped_column(Integer, default=0)
    correlation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
    )
    parent_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_messages.id", ondelete="SET NULL"), nullable=True,
    )
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="delivered", index=True)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)


class DebateRound(Base, TimestampMixin):
    """One round in a multi-agent debate."""
    __tablename__ = "debate_rounds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    debate_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)

    topic: Mapped[str] = mapped_column(Text, nullable=False)
    criteria: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    position_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    position_b: Mapped[str | None] = mapped_column(Text, nullable=True)
    rebuttal_a: Mapped[str | None] = mapped_column(Text, nullable=True)
    rebuttal_b: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent_a_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agent_b_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    judge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    judge_score_a: Mapped[float | None] = mapped_column(nullable=True)
    judge_score_b: Mapped[float | None] = mapped_column(nullable=True)
    judge_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_verdict: Mapped[str | None] = mapped_column(String(50), nullable=True)

    consensus_reached: Mapped[bool] = mapped_column(default=False)
    consensus_synthesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    consensus_score: Mapped[float | None] = mapped_column(nullable=True)

    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


class HandoffRecord(Base, TimestampMixin):
    """Records a structured subtask delegation from one agent to another."""
    __tablename__ = "handoff_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))

    from_agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    from_agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    to_agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)

    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    parent_handoff_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("handoff_records.id", ondelete="SET NULL"), nullable=True,
    )
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


class EscalationRecord(Base, TimestampMixin):
    """Records an escalation from a failed task up the chain."""
    __tablename__ = "escalation_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))

    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_description: Mapped[str] = mapped_column(Text, nullable=False)

    level: Mapped[int] = mapped_column(Integer, default=0)
    attempted_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempted_agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    escalated_to_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    escalated_to_agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    resolved: Mapped[bool] = mapped_column(default=False)
    resolution_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    max_retries_per_level: Mapped[int] = mapped_column(Integer, default=2)
    retries_at_level: Mapped[int] = mapped_column(Integer, default=0)
    escalation_policy: Mapped[str] = mapped_column(String(50), default="default")

    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
