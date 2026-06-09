"""
Knowledge Graph Storage for Autonomous Self-Improvement System.

This module provides persistent graph storage for relationships between
failures, strategies, patterns, and outcomes using PostgreSQL.

Phase 6B of the Autonomous Self-Improvement Architecture.
"""

import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Import from previous phases
from .causal_decomposer import StrategyType
from .failure_types import FailureType

# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================


class NodeType(str, Enum):
    """Types of nodes in the knowledge graph."""

    FAILURE = "failure"
    STRATEGY = "strategy"
    PATTERN = "pattern"
    KNOB = "knob"
    OUTCOME = "outcome"
    AGENT = "agent"
    MISSION = "mission"
    SUCCESS_PATTERN = "success_pattern"


class EdgeType(str, Enum):
    """Types of edges (relationships) in the knowledge graph."""

    CAUSES = "causes"  # failure → failure
    FIXES = "fixes"  # strategy → failure
    CORRELATES_WITH = "correlates_with"  # pattern → outcome
    PRECEDED_BY = "preceded_by"  # failure → failure (temporal)
    AMPLIFIES = "amplifies"  # knob → pattern
    LEARNED_FROM = "learned_from"  # pattern → mission
    APPLIED_TO = "applied_to"  # strategy → agent
    SUCCEEDED_BY = "succeeded_by"  # failure → strategy (when strategy worked)
    FAILED_BY = "failed_by"  # failure → strategy (when strategy failed)
    SIMILAR_TO = "similar_to"  # pattern → pattern
    DEPENDS_ON = "depends_on"  # strategy → strategy
    RECOMMENDS = "recommends"  # pattern → knob


@dataclass
class KnowledgeNode:
    """A node in the knowledge graph."""

    id: str
    node_type: NodeType
    node_key: str  # e.g., 'TOOL_TIMEOUT', 'ADD_RETRY', pattern_id
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "node_key": self.node_key,
            "properties": self.properties,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class KnowledgeEdge:
    """An edge (relationship) in the knowledge graph."""

    id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "properties": self.properties,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class GraphPath:
    """A path through the knowledge graph."""

    nodes: list[KnowledgeNode]
    edges: list[KnowledgeEdge]
    total_weight: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "total_weight": self.total_weight,
        }


# ============================================================================
# KNOWLEDGE GRAPH
# ============================================================================


class KnowledgeGraph:
    """
    In-memory knowledge graph with optional database persistence.

    This class manages nodes and edges representing relationships
    between failures, strategies, patterns, and outcomes.
    """

    def __init__(self, db_session=None):
        """
        Initialize the knowledge graph.

        Args:
            db_session: Optional database session for persistence
        """
        self.db_session = db_session
        self._nodes: dict[str, KnowledgeNode] = {}
        self._edges: dict[str, KnowledgeEdge] = {}
        self._node_index: dict[NodeType, dict[str, str]] = defaultdict(
            dict
        )  # type -> key -> id
        self._outgoing_edges: dict[str, set[str]] = defaultdict(
            set
        )  # node_id -> edge_ids
        self._incoming_edges: dict[str, set[str]] = defaultdict(
            set
        )  # node_id -> edge_ids

        # Configuration
        self.max_path_length = 5

    # ========================================================================
    # NODE OPERATIONS
    # ========================================================================

    async def add_node(
        self,
        node_type: NodeType,
        node_key: str,
        properties: dict[str, Any] | None = None,
        node_id: str | None = None,
    ) -> KnowledgeNode:
        """
        Add a node to the graph.

        Args:
            node_type: Type of the node
            node_key: Key identifier (e.g., 'TOOL_TIMEOUT')
            properties: Optional properties
            node_id: Optional specific ID (generated if not provided)

        Returns:
            The created or existing node
        """
        # Check if node already exists
        existing_id = self._node_index[node_type].get(node_key)
        if existing_id:
            node = self._nodes[existing_id]
            if properties:
                node.properties.update(properties)
                node.updated_at = datetime.now(UTC)
            return node

        # Create new node
        node_id = node_id or str(uuid.uuid4())
        node = KnowledgeNode(
            id=node_id,
            node_type=node_type,
            node_key=node_key,
            properties=properties or {},
        )

        # Store in memory
        self._nodes[node_id] = node
        self._node_index[node_type][node_key] = node_id

        # Persist to database if available
        if self.db_session:
            await self._persist_node(node)

        logger.debug('Added node %s (%s/%s)', node_id, node_type.value, node_key)
        return node

    def get_node(self, node_id: str) -> KnowledgeNode | None:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def get_node_by_key(
        self,
        node_type: NodeType,
        node_key: str,
    ) -> KnowledgeNode | None:
        """Get a node by type and key."""
        node_id = self._node_index[node_type].get(node_key)
        if node_id:
            return self._nodes.get(node_id)
        return None

    async def update_node(
        self,
        node_id: str,
        properties: dict[str, Any],
    ) -> KnowledgeNode | None:
        """Update a node's properties."""
        node = self._nodes.get(node_id)
        if not node:
            return None

        node.properties.update(properties)
        node.updated_at = datetime.now(UTC)

        if self.db_session:
            await self._persist_node(node)

        return node

    async def delete_node(self, node_id: str) -> bool:
        """Delete a node and its edges."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        # Delete all connected edges
        edge_ids = self._outgoing_edges[node_id] | self._incoming_edges[node_id]
        for edge_id in edge_ids:
            await self.delete_edge(edge_id)

        # Remove from indices
        del self._nodes[node_id]
        if node.node_key in self._node_index[node.node_type]:
            del self._node_index[node.node_type][node.node_key]

        # Remove from edge indices
        if node_id in self._outgoing_edges:
            del self._outgoing_edges[node_id]
        if node_id in self._incoming_edges:
            del self._incoming_edges[node_id]

        # Persist deletion to database
        if self.db_session:
            try:
                from sqlalchemy import text

                await self.db_session.execute(
                    text("DELETE FROM improvement_knowledge_nodes WHERE id = :id"),
                    {"id": node_id},
                )
                await self.db_session.commit()
            except Exception as e:
                logger.warning("Failed to delete node %s from DB: %s", node_id, e)
                await self.db_session.rollback()

        return True

    # ========================================================================
    # EDGE OPERATIONS
    # ========================================================================

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        weight: float = 1.0,
        properties: dict[str, Any] | None = None,
        edge_id: str | None = None,
    ) -> KnowledgeEdge | None:
        """
        Add an edge between two nodes.

        Args:
            source_id: Source node ID
            target_id: Target node ID
            edge_type: Type of relationship
            weight: Edge weight (importance)
            properties: Optional properties
            edge_id: Optional specific ID

        Returns:
            The created edge, or None if nodes don't exist
        """
        # Verify nodes exist
        if source_id not in self._nodes or target_id not in self._nodes:
            logger.warning('Cannot add edge: nodes %s or %s not found', source_id, target_id)
            return None

        # Check for duplicate edge
        for existing_id in self._outgoing_edges[source_id]:
            edge = self._edges.get(existing_id)
            if edge and edge.target_id == target_id and edge.edge_type == edge_type:
                # Update existing edge
                edge.weight = (edge.weight + weight) / 2  # Average weight
                if properties:
                    edge.properties.update(properties)
                # Persist the updated weight/properties
                if self.db_session:
                    await self._persist_edge(edge)
                return edge

        # Create new edge
        edge_id = edge_id or str(uuid.uuid4())
        edge = KnowledgeEdge(
            id=edge_id,
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            properties=properties or {},
        )

        # Store in memory
        self._edges[edge_id] = edge
        self._outgoing_edges[source_id].add(edge_id)
        self._incoming_edges[target_id].add(edge_id)

        # Persist to database if available
        if self.db_session:
            await self._persist_edge(edge)

        logger.debug('Added edge %s (%s -%s-> %s)', edge_id, source_id, edge_type.value, target_id)
        return edge

    def get_edge(self, edge_id: str) -> KnowledgeEdge | None:
        """Get an edge by ID."""
        return self._edges.get(edge_id)

    async def delete_edge(self, edge_id: str) -> bool:
        """Delete an edge."""
        edge = self._edges.get(edge_id)
        if not edge:
            return False

        del self._edges[edge_id]
        self._outgoing_edges[edge.source_id].discard(edge_id)
        self._incoming_edges[edge.target_id].discard(edge_id)

        # Persist deletion to database
        if self.db_session:
            try:
                from sqlalchemy import text

                await self.db_session.execute(
                    text("DELETE FROM improvement_knowledge_edges WHERE id = :id"),
                    {"id": edge_id},
                )
                await self.db_session.commit()
            except Exception as e:
                logger.warning("Failed to delete edge %s from DB: %s", edge_id, e)
                await self.db_session.rollback()

        return True

    # ========================================================================
    # QUERY OPERATIONS
    # ========================================================================

    def get_outgoing_edges(
        self,
        node_id: str,
        edge_type: EdgeType | None = None,
    ) -> list[KnowledgeEdge]:
        """Get all outgoing edges from a node."""
        edge_ids = self._outgoing_edges.get(node_id, set())
        edges = [self._edges[eid] for eid in edge_ids if eid in self._edges]

        if edge_type:
            edges = [e for e in edges if e.edge_type == edge_type]

        return edges

    def get_incoming_edges(
        self,
        node_id: str,
        edge_type: EdgeType | None = None,
    ) -> list[KnowledgeEdge]:
        """Get all incoming edges to a node."""
        edge_ids = self._incoming_edges.get(node_id, set())
        edges = [self._edges[eid] for eid in edge_ids if eid in self._edges]

        if edge_type:
            edges = [e for e in edges if e.edge_type == edge_type]

        return edges

    def get_neighbors(
        self,
        node_id: str,
        edge_type: EdgeType | None = None,
        direction: str = "both",
    ) -> list[KnowledgeNode]:
        """
        Get neighboring nodes.

        Args:
            node_id: The node ID
            edge_type: Optional edge type filter
            direction: 'incoming', 'outgoing', or 'both'

        Returns:
            List of neighboring nodes
        """
        neighbors = []

        if direction in ("outgoing", "both"):
            for edge in self.get_outgoing_edges(node_id, edge_type):
                neighbor = self._nodes.get(edge.target_id)
                if neighbor:
                    neighbors.append(neighbor)

        if direction in ("incoming", "both"):
            for edge in self.get_incoming_edges(node_id, edge_type):
                neighbor = self._nodes.get(edge.source_id)
                if neighbor:
                    neighbors.append(neighbor)

        return neighbors

    async def find_paths(
        self,
        start_node_id: str,
        end_node_id: str,
        max_depth: int = 5,
        edge_types: list[EdgeType] | None = None,
    ) -> list[GraphPath]:
        """
        Find all paths between two nodes.

        Args:
            start_node_id: Starting node ID
            end_node_id: Target node ID
            max_depth: Maximum path length
            edge_types: Optional edge types to follow

        Returns:
            List of paths sorted by total weight
        """
        if start_node_id not in self._nodes or end_node_id not in self._nodes:
            return []

        paths = []
        visited = set()

        async def dfs(
            current_id: str,
            path_nodes: list[str],
            path_edges: list[str],
            total_weight: float,
        ):
            if len(path_nodes) > max_depth:
                return

            if current_id == end_node_id:
                # Found a path
                nodes = [self._nodes[nid] for nid in path_nodes]
                edges = [self._edges[eid] for eid in path_edges]
                paths.append(
                    GraphPath(
                        nodes=nodes,
                        edges=edges,
                        total_weight=total_weight,
                    )
                )
                return

            if current_id in visited:
                return

            visited.add(current_id)

            for edge in self.get_outgoing_edges(current_id):
                if edge_types and edge.edge_type not in edge_types:
                    continue

                if edge.target_id not in visited:
                    await dfs(
                        edge.target_id,
                        [*path_nodes, edge.target_id],
                        [*path_edges, edge.id],
                        total_weight + edge.weight,
                    )

            visited.discard(current_id)

        await dfs(start_node_id, [start_node_id], [], 0.0)

        # Sort by weight (lower is better)
        paths.sort(key=lambda p: p.total_weight)

        return paths

    async def query(
        self,
        start_type: NodeType,
        start_key: str | None = None,
        edge_types: list[EdgeType] | None = None,
        target_type: NodeType | None = None,
        max_depth: int = 2,
    ) -> list[tuple[KnowledgeNode, list[KnowledgeEdge]]]:
        """
        Query the graph starting from nodes of a specific type.

        Args:
            start_type: Type of starting nodes
            start_key: Optional specific key to start from
            edge_types: Optional edge types to follow
            target_type: Optional target node type filter
            max_depth: Maximum traversal depth

        Returns:
            List of (target_node, path_edges) tuples
        """
        results = []

        # Get starting nodes
        if start_key:
            start_node = self.get_node_by_key(start_type, start_key)
            start_nodes = [start_node] if start_node else []
        else:
            start_nodes = [
                self._nodes[nid] for nid in self._node_index[start_type].values()
            ]

        for start_node in start_nodes:
            visited = set()

            async def traverse(
                current: KnowledgeNode,
                depth: int,
                path: list[KnowledgeEdge],
            ):
                if depth > max_depth:
                    return

                if current.id in visited:
                    return

                visited.add(current.id)

                # Check if this is a target
                if target_type is None or current.node_type == target_type:
                    if current != start_node:  # Don't include start node
                        results.append((current, path.copy()))

                # Traverse outgoing edges
                for edge in self.get_outgoing_edges(current.id):
                    if edge_types and edge.edge_type not in edge_types:
                        continue

                    neighbor = self._nodes.get(edge.target_id)
                    if neighbor and neighbor.id not in visited:
                        path.append(edge)
                        await traverse(neighbor, depth + 1, path)
                        path.pop()

                visited.discard(current.id)

            await traverse(start_node, 0, [])

        return results

    # ========================================================================
    # SPECIALIZED QUERIES
    # ========================================================================

    async def get_strategies_for_failure(
        self,
        failure_type: FailureType,
    ) -> list[tuple[KnowledgeNode, float]]:
        """
        Get strategies that have been used to fix a failure type.

        Args:
            failure_type: The failure type

        Returns:
            List of (strategy_node, success_rate) tuples
        """
        # Get failure node
        failure_node = self.get_node_by_key(NodeType.FAILURE, failure_type.value)
        if not failure_node:
            return []

        results = []

        # Find strategies that fix this failure
        for edge in self.get_incoming_edges(failure_node.id, EdgeType.FIXES):
            strategy_node = self._nodes.get(edge.source_id)
            if strategy_node:
                # Calculate success rate from properties
                success_rate = edge.properties.get("success_rate", 0.5)
                results.append((strategy_node, success_rate))

        # Sort by success rate
        results.sort(key=lambda x: x[1], reverse=True)

        return results

    async def get_failure_predecessors(
        self,
        failure_type: FailureType,
    ) -> list[tuple[KnowledgeNode, float]]:
        """
        Get failures that often precede a given failure.

        Args:
            failure_type: The failure type

        Returns:
            List of (predecessor_node, frequency) tuples
        """
        failure_node = self.get_node_by_key(NodeType.FAILURE, failure_type.value)
        if not failure_node:
            return []

        results = []

        for edge in self.get_incoming_edges(failure_node.id, EdgeType.PRECEDED_BY):
            predecessor = self._nodes.get(edge.source_id)
            if predecessor:
                frequency = edge.properties.get("frequency", 1.0)
                results.append((predecessor, frequency))

        results.sort(key=lambda x: x[1], reverse=True)

        return results

    async def get_effective_knobs(
        self,
        strategy_type: StrategyType,
    ) -> list[tuple[KnowledgeNode, float]]:
        """
        Get knobs that amplify a strategy's effectiveness.

        Args:
            strategy_type: The strategy type

        Returns:
            List of (knob_node, amplification) tuples
        """
        strategy_node = self.get_node_by_key(NodeType.STRATEGY, strategy_type.value)
        if not strategy_node:
            return []

        results = []

        for edge in self.get_incoming_edges(strategy_node.id, EdgeType.AMPLIFIES):
            knob_node = self._nodes.get(edge.source_id)
            if knob_node:
                amplification = edge.weight
                results.append((knob_node, amplification))

        results.sort(key=lambda x: x[1], reverse=True)

        return results

    async def record_strategy_outcome(
        self,
        failure_type: FailureType,
        strategy_type: StrategyType,
        success: bool,
        agent_id: str | None = None,
    ) -> None:
        """
        Record the outcome of applying a strategy to a failure.

        Args:
            failure_type: The failure type
            strategy_type: The strategy type
            success: Whether the strategy succeeded
            agent_id: Optional agent ID
        """
        # Ensure nodes exist
        failure_node = await self.add_node(
            NodeType.FAILURE,
            failure_type.value,
        )

        strategy_node = await self.add_node(
            NodeType.STRATEGY,
            strategy_type.value,
        )

        # Add or update edge
        edge_type = EdgeType.SUCCEEDED_BY if success else EdgeType.FAILED_BY

        # Find existing edge
        existing_edge = None
        for edge in self.get_outgoing_edges(failure_node.id, edge_type):
            if edge.target_id == strategy_node.id:
                existing_edge = edge
                break

        if existing_edge:
            # Update counts
            count = existing_edge.properties.get("count", 0) + 1
            existing_edge.properties["count"] = count
            existing_edge.weight = count
        else:
            # Create new edge
            await self.add_edge(
                failure_node.id,
                strategy_node.id,
                edge_type,
                weight=1.0,
                properties={"count": 1, "agent_id": agent_id},
            )

        # Also update FIXES edge with success rate
        fixes_edge = None
        for edge in self.get_outgoing_edges(strategy_node.id, EdgeType.FIXES):
            if edge.target_id == failure_node.id:
                fixes_edge = edge
                break

        if fixes_edge:
            # Update success rate
            total = fixes_edge.properties.get("total", 0) + 1
            successes = fixes_edge.properties.get("successes", 0) + (
                1 if success else 0
            )
            fixes_edge.properties["total"] = total
            fixes_edge.properties["successes"] = successes
            fixes_edge.properties["success_rate"] = successes / total
        else:
            # Create new edge
            await self.add_edge(
                strategy_node.id,
                failure_node.id,
                EdgeType.FIXES,
                weight=1.0,
                properties={
                    "total": 1,
                    "successes": 1 if success else 0,
                    "success_rate": 1.0 if success else 0.0,
                },
            )

    # ========================================================================
    # STATISTICS
    # ========================================================================

    def get_statistics(self) -> dict[str, Any]:
        """Get graph statistics."""
        node_counts = defaultdict(int)
        for node in self._nodes.values():
            node_counts[node.node_type.value] += 1

        edge_counts = defaultdict(int)
        for edge in self._edges.values():
            edge_counts[edge.edge_type.value] += 1

        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "nodes_by_type": dict(node_counts),
            "edges_by_type": dict(edge_counts),
        }

    # ========================================================================
    # PERSISTENCE
    # ========================================================================

    async def _persist_node(self, node: KnowledgeNode) -> None:
        """Persist a node to the database."""
        if not self.db_session:
            return

        try:
            from sqlalchemy import text

            await self.db_session.execute(
                text(
                    """
                    INSERT INTO improvement_knowledge_nodes (id, node_type, node_key, properties, created_at, updated_at)
                    VALUES (:id, :node_type, :node_key, :properties, :created_at, :updated_at)
                    ON CONFLICT (id) DO UPDATE SET
                        properties = EXCLUDED.properties,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": node.id,
                    "node_type": node.node_type.value,
                    "node_key": node.node_key,
                    "properties": json.dumps(node.properties),
                    "created_at": node.created_at,
                    "updated_at": node.updated_at,
                },
            )
            await self.db_session.commit()
        except Exception as e:
            logger.warning("Failed to persist node %s: %s", node.id, e)
            await self.db_session.rollback()

    async def _persist_edge(self, edge: KnowledgeEdge) -> None:
        """Persist an edge to the database."""
        if not self.db_session:
            return

        try:
            from sqlalchemy import text

            await self.db_session.execute(
                text(
                    """
                    INSERT INTO improvement_knowledge_edges (id, source_id, target_id, edge_type, weight, properties, created_at)
                    VALUES (:id, :source_id, :target_id, :edge_type, :weight, :properties, :created_at)
                    ON CONFLICT (id) DO UPDATE SET
                        weight = EXCLUDED.weight,
                        properties = EXCLUDED.properties
                    """
                ),
                {
                    "id": edge.id,
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "edge_type": edge.edge_type.value,
                    "weight": edge.weight,
                    "properties": json.dumps(edge.properties),
                    "created_at": edge.created_at,
                },
            )
            await self.db_session.commit()
        except Exception as e:
            logger.warning("Failed to persist edge %s: %s", edge.id, e)
            await self.db_session.rollback()

    async def load_from_database(self) -> None:
        """Load the graph from the database."""
        if not self.db_session:
            return

        try:
            from sqlalchemy import text

            # Load nodes
            node_result = await self.db_session.execute(
                text(
                    "SELECT id, node_type, node_key, properties, created_at, updated_at FROM improvement_knowledge_nodes"
                )
            )
            for row in node_result:
                props = row.properties if isinstance(row.properties, dict) else {}
                node = KnowledgeNode(
                    id=row.id,
                    node_type=NodeType(row.node_type),
                    node_key=row.node_key,
                    properties=props,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                self._nodes[node.id] = node
                self._node_index[node.node_type][node.node_key] = node.id

            # Load edges
            edge_result = await self.db_session.execute(
                text(
                    "SELECT id, source_id, target_id, edge_type, weight, properties, created_at FROM improvement_knowledge_edges"
                )
            )
            for row in edge_result:
                props = row.properties if isinstance(row.properties, dict) else {}
                edge = KnowledgeEdge(
                    id=row.id,
                    source_id=row.source_id,
                    target_id=row.target_id,
                    edge_type=EdgeType(row.edge_type),
                    weight=row.weight,
                    properties=props,
                    created_at=row.created_at,
                )
                self._edges[edge.id] = edge
                self._outgoing_edges[edge.source_id].add(edge.id)
                self._incoming_edges[edge.target_id].add(edge.id)

            logger.info(
                "Loaded %d nodes and %d edges from database",
                len(self._nodes),
                len(self._edges),
            )
        except Exception as e:
            logger.warning("Failed to load graph from database: %s", e)

    async def save_to_database(self) -> None:
        """Save the entire graph to the database."""
        if not self.db_session:
            return

        for node in self._nodes.values():
            await self._persist_node(node)

        for edge in self._edges.values():
            await self._persist_edge(edge)


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_knowledge_graph: KnowledgeGraph | None = None


def get_knowledge_graph() -> KnowledgeGraph:
    """Get the singleton knowledge graph instance."""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraph()
    return _knowledge_graph


def initialize_knowledge_graph(db_session=None) -> KnowledgeGraph:
    """Initialize the knowledge graph with a database session."""
    global _knowledge_graph
    _knowledge_graph = KnowledgeGraph(db_session)
    return _knowledge_graph
