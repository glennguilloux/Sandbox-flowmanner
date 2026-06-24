"""SQLAlchemy ORM models for the improvement knowledge graph.

These models map to the ``improvement_knowledge_nodes`` and
``improvement_knowledge_edges`` tables created by the
``20260526_add_knowledge_graph_tables`` migration.

The tables are primarily accessed via raw SQL in
:mod:`app.services.improvement.knowledge_graph`, but ORM models
are provided for type safety, relationship navigation, and future
query-building.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class KnowledgeNode(Base):
    """A node in the improvement knowledge graph.

    Represents a failure, strategy, pattern, knob, outcome, agent,
    mission, or success_pattern.
    """

    __tablename__ = "improvement_knowledge_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    node_key: Mapped[str] = mapped_column(String(255), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    outgoing_edges: Mapped[list[KnowledgeEdge]] = relationship(
        "KnowledgeEdge",
        foreign_keys="KnowledgeEdge.source_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[list[KnowledgeEdge]] = relationship(
        "KnowledgeEdge",
        foreign_keys="KnowledgeEdge.target_id",
        back_populates="target_node",
        cascade="all, delete-orphan",
    )


class KnowledgeEdge(Base):
    """An edge (relationship) in the improvement knowledge graph."""

    __tablename__ = "improvement_knowledge_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("improvement_knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("improvement_knowledge_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    source_node: Mapped[KnowledgeNode] = relationship(
        "KnowledgeNode", foreign_keys=[source_id], back_populates="outgoing_edges"
    )
    target_node: Mapped[KnowledgeNode] = relationship(
        "KnowledgeNode", foreign_keys=[target_id], back_populates="incoming_edges"
    )
