"""Memory and memory session models for the memory API.

Contains three models:
- Memory: Session-scoped memory entries (existing)
- MemorySession: Grouping for Memory entries (existing)
- MemoryEntry: Canonical unified memory store (Postgres-native, Phase 1)

MemoryEntry is the new canonical table for all agent/user memory.
It replaces Redis as the source of truth — Redis becomes an optional
read-through cache.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class Memory(Base, TimestampMixin):
    """An individual memory entry extracted from a session or mission."""

    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("memory_sessions.id"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    source_mission_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    session: Mapped[MemorySession] = relationship(
        "MemorySession", back_populates="memories"
    )


class MemorySession(Base, TimestampMixin):
    """A session that groups related memories."""

    __tablename__ = "memory_sessions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False, default="Untitled Session"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    memories: Mapped[list[Memory]] = relationship(
        "Memory", back_populates="session", cascade="all, delete-orphan"
    )


class MemoryEntry(Base, TimestampMixin):
    """Canonical unified memory store — Postgres is the source of truth.

    Replaces Redis as the durable memory substrate. Redis becomes an
    optional read-through cache for hot entries.

    Supports both simple KV (via namespace + key) and agent memory
    (via agent_id + content + memory_type + importance).
    """

    __tablename__ = "memory_entries"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    workspace_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    namespace: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="default",
    )
    key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    memory_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="episodic",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    supersedes_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
    )
    source_mission_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index("ix_memory_entries_agent_type", "agent_id", "memory_type"),
        Index("ix_memory_entries_namespace_key", "namespace", "key"),
    )
