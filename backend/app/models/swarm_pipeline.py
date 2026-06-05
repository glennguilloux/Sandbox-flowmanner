"""Swarm Pipeline models aligned to actual PostgreSQL schema.

Verified against Alembic migrations:
- 83699f85a14e: create swarm_pipelines table
- 20249800e422: add analytics columns (phase_durations, total_duration, task_count, error_count)
"""

from datetime import datetime

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class SwarmPipeline(Base):
    __tablename__ = "swarm_pipelines"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    swarm_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    current_phase: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    phase_history: Mapped[list | None] = mapped_column(JSON, nullable=True)
    phase_durations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total_duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    task_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class NexusPipeline(SwarmPipeline):
    """Extension point for Nexus-type pipeline configurations.

    Currently uses the same swarm_pipelines table with a type discriminator.
    Can be promoted to its own table if Nexus pipelines diverge.
    """

    __mapper_args__ = {
        'polymorphic_identity': 'nexus',
    }
