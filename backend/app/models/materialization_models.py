"""Materialization state model — Postgres-native cache sync tracking.

Tracks which objects (tools, capabilities, agent templates, memories,
topology) have been materialized to which targets (Redis, Qdrant,
in-process registries).  Used by the startup hydration pipeline to
determine what needs re-syncing after a restart.

Phase 1.1e of the Postgres-native migration plan.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class MaterializationState(Base, TimestampMixin):
    """Track materialization status of an object to a specific target.

    Each row represents one ``(object_type, object_id, target)`` triple.
    The hydration pipeline reads this table to decide which objects
    need to be (re-)pushed to caches on startup.
    """

    __tablename__ = "materialization_state"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    object_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="'tool', 'capability', 'agent_template', 'memory', 'topology'",
    )
    object_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        comment="UUID of the object in its canonical table",
    )
    target: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="'redis', 'qdrant', 'inproc', 'all'",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        comment="'pending', 'materializing', 'materialized', 'stale', 'failed'",
    )
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 of the object's canonical JSON, used for staleness detection",
    )
    last_materialized_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    __table_args__ = (
        Index(
            "ix_mat_state_object_type_id_target",
            "object_type",
            "object_id",
            "target",
            unique=True,
        ),
        Index("ix_mat_state_status", "status"),
        Index("ix_mat_state_object_type", "object_type"),
    )
