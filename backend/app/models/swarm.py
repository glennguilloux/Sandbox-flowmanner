"""Swarm models aligned to actual PostgreSQL schema.

Verified against information_schema 2026-04-14.
Tables: swarm_profiles, swarm_agents, swarm_tasks, swarm_consensus_rounds
"""

from datetime import datetime

from sqlalchemy import (
    Double,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class SwarmProfile(Base):
    __tablename__ = "swarm_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    swarm_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    swarm_name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    task_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    consensus_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    consensus_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    daily_limit: Mapped[float | None] = mapped_column(Double, nullable=True)
    monthly_limit: Mapped[float | None] = mapped_column(Double, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    dissolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)


class SwarmAgent(Base):
    __tablename__ = "swarm_agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_instance_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    swarm_id: Mapped[str] = mapped_column(String(64), ForeignKey("swarm_profiles.swarm_id"), nullable=False)
    agent_template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_templates.template_id"), nullable=True
    )
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    specializations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assigned_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    load: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrent_tasks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating_avg: Mapped[float | None] = mapped_column(Double, nullable=True)
    rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(default=datetime.utcnow)
    cost_tracking: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    performance_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SwarmTask(Base):
    __tablename__ = "swarm_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    swarm_id: Mapped[str] = mapped_column(String(64), ForeignKey("swarm_profiles.swarm_id"), nullable=False)
    parent_task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("swarm_tasks.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("swarm_agents.agent_instance_id"), nullable=True
    )
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.utcnow)
    assigned_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_retries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dependencies: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SwarmConsensusRound(Base):
    __tablename__ = "swarm_consensus_rounds"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    swarm_id: Mapped[str] = mapped_column(String(64), ForeignKey("swarm_profiles.swarm_id"), nullable=False)
    proposal: Mapped[dict] = mapped_column(JSON, nullable=False)
    initiator_agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    votes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    strategy_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
