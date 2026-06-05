import json
import logging
from datetime import UTC
from pathlib import Path

logger = logging.getLogger(__name__)


class TopologyManager:
    def __init__(self, graph_path: str = "/mnt/workflows/workflows/graphify-out/graph.json"):
        self.graph_path = Path(graph_path)
        self.G = None
        self.communities: dict[int, list[str]] | None = None
        self.embeddings: dict[int, dict] | None = None

    async def build(self, data: dict | None = None) -> dict:
        if data is None:
            if not self.graph_path.exists():
                return {"nodes": [], "edges": []}
            data = json.loads(self.graph_path.read_text())
        try:
            from graphify.build import build_from_json
            self.G = build_from_json(data)
        except ImportError:
            import networkx as nx
            self.G = nx.DiGraph()
            for node in data.get("nodes", []):
                self.G.add_node(node["id"], **node)
            for edge in data.get("links", data.get("edges", [])):
                self.G.add_edge(edge["source"], edge["target"], **edge)
        try:
            from graphify.cluster import cluster
            self.communities = cluster(self.G)
        except ImportError:
            self.communities = {0: list(self.G.nodes())} if self.G else {}
        self.embeddings = self._compute_community_embeddings()
        return self._to_topology_dict()

    async def build_from_db(self, session) -> dict:
        """Load the latest topology snapshot from Postgres and build the graph.

        Returns the topology dict.  Falls back to filesystem ``graph.json``
        if no snapshots exist in the DB.

        Phase 2.4 — this becomes the canonical topology loading path.
        """
        from sqlalchemy import desc, select

        from app.models.topology_models import TopologySnapshot

        result = await session.execute(
            select(TopologySnapshot)
            .order_by(desc(TopologySnapshot.version))
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()

        if snapshot is None:
            logger.info("No topology snapshots in DB — falling back to filesystem")
            return await self.build()

        data = snapshot.snapshot_data
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Topology snapshot %s has unparseable data", snapshot.id)
                return await self.build()

        logger.info(
            "Loaded topology from DB snapshot v%d (%d nodes, %d edges)",
            snapshot.version,
            snapshot.node_count,
            snapshot.edge_count,
        )
        return await self.build(data=data)

    async def save_snapshot(self, session, description: str = "") -> str:
        """Persist the current in-memory topology as a new DB snapshot.

        Returns the new snapshot ID.
        """
        from datetime import datetime
        from uuid import uuid4

        from sqlalchemy import func, select

        from app.models.topology_models import TopologySnapshot

        topology = self._to_topology_dict()
        nodes = topology.get("nodes", [])
        edges = topology.get("edges", [])

        # Get next version number
        result = await session.execute(
            select(func.coalesce(func.max(TopologySnapshot.version), 0))
        )
        max_version = result.scalar() or 0

        snapshot_id = str(uuid4())
        now = datetime.now(UTC)

        snapshot = TopologySnapshot(
            id=snapshot_id,
            version=max_version + 1,
            description=description or "Auto-saved topology snapshot",
            node_count=len(nodes),
            edge_count=len(edges),
            community_count=topology.get("communities", 0),
            source="computed",
            snapshot_data=topology,
        )
        session.add(snapshot)
        await session.flush()

        logger.info(
            "Saved topology snapshot v%d: %d nodes, %d edges (id=%s)",
            max_version + 1, len(nodes), len(edges), snapshot_id,
        )
        return snapshot_id

    def _compute_community_embeddings(self) -> dict[int, dict]:
        embeddings = {}
        if not self.communities or not self.G:
            return embeddings
        for cid, node_ids in self.communities.items():
            degs = [self.G.degree(n) for n in node_ids if self.G.has_node(n)]
            avg_deg = sum(degs)/len(degs) if degs else 0.0
            embeddings[cid] = {
                "avg_degree": round(avg_deg, 2),
                "node_count": len(node_ids),
                "edge_count": sum(1 for n in node_ids for _ in self.G.neighbors(n)) if hasattr(self.G, "neighbors") else 0
            }
        return embeddings

    def _to_topology_dict(self) -> dict:
        nodes, edges = [], []
        if not self.G:
            return {"nodes": nodes, "edges": edges, "communities": 0}
        for nid, ndata in self.G.nodes(data=True):
            cid = ndata.get("community")
            nodes.append({
                "id": nid,
                "label": ndata.get("label", nid),
                "stack": ndata.get("stack", "unknown"),
                "community": cid,
                "embedding": self.embeddings.get(cid, {}) if cid is not None else {}
            })
        for src, tgt, edata in self.G.edges(data=True):
            edges.append({
                "source": src,
                "target": tgt,
                "relation": edata.get("relation", "calls"),
                "confidence": edata.get("confidence", "INFERRED")
            })
        return {
            "nodes": nodes,
            "edges": edges,
            "communities": len(self.communities) if self.communities else 0,
            "graphify_path": str(self.graph_path)
        }

    def get_dynamic_topology(self, intent: str = None) -> dict:
        return self._to_topology_dict()


_topology_manager: TopologyManager | None = None


def get_topology_manager() -> TopologyManager:
    global _topology_manager
    if _topology_manager is None:
        _topology_manager = TopologyManager()
    return _topology_manager
