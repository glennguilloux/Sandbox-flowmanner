"""Topology models — Postgres-native graph topology storage.

Replaces the filesystem ``graph.json`` as the canonical source of truth
for topology data.  The existing ``TopologyManager`` will be updated
(Phase 2.4) to read from these tables instead of the file.

Phase 1.1f of the Postgres-native migration plan.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class TopologySnapshot(Base, TimestampMixin):
    """A versioned snapshot of the full topology graph.

    Each computation or import produces a new snapshot.  The latest
    snapshot is the current topology.  Old snapshots are retained for
    history and rollback.
    """

    __tablename__ = "topology_snapshots"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_count: Mapped[int] = mapped_column(Integer, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, default=0)
    community_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(
        String(50),
        default="computed",
        comment="'computed', 'imported', 'manual'",
    )
    snapshot_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full topology graph (nodes + edges) as JSON",
    )


class TopologyNode(Base):
    """A single node in a topology snapshot.

    Nodes represent agents, capabilities, workflows, or other entities
    in the system graph.  ``derived_from_*`` columns provide lineage
    back to canonical tables.
    """

    __tablename__ = "topology_nodes"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Node ID as it appears in the graph (may differ from PK)",
    )
    label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    node_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="'agent', 'capability', 'workflow', 'tool', etc.",
    )
    community_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )
    # Lineage: where this node came from
    derived_from_agent_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="FK to agents.id — set when this node represents an agent",
    )
    derived_from_capability_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="FK to capabilities_catalog.id — set when this node represents a capability",
    )
    derived_from_workflow_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="FK to workflows.id — set when this node represents a workflow",
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (Index("ix_topo_nodes_snapshot", "snapshot_id"),)


class TopologyEdge(Base):
    """A directed edge between two nodes in a topology snapshot.

    Edges represent relationships (calls, depends-on, data-flow, etc.)
    between entities in the system graph.
    """

    __tablename__ = "topology_edges"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    source_node_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )
    target_node_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(
        String(100),
        default="calls",
        comment="'calls', 'depends-on', 'data-flow', etc.",
    )
    confidence: Mapped[str] = mapped_column(
        String(50),
        default="INFERRED",
        comment="'INFERRED', 'OBSERVED', 'DECLARED'",
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    __table_args__ = (Index("ix_topo_edges_snapshot", "snapshot_id"),)
