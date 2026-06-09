"""Seed topology_snapshots from the filesystem graph.json.

Loads the graph.json file (if it exists) and inserts it as the first
topology snapshot.  Idempotent — skips if a snapshot already exists.

Also builds a synthetic topology from agent_templates + tools_catalog
+ capabilities_catalog as a fallback when no graph.json is present.

Usage (inside container):
    python /app/scripts/seed_topology.py
"""

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GRAPH_JSON_PATH = Path("/mnt/workflows/workflows/graphify-out/graph.json")


async def run():
    from sqlalchemy import func, select
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    now = datetime.now(UTC)

    async with engine.begin() as conn:
        # Check if snapshot already exists
        r = await conn.execute(sa_text("SELECT count(*) FROM topology_snapshots"))
        existing = r.scalar()
        if existing > 0:
            logger.info("topology_snapshots already has %d rows — skipping", existing)
            await engine.dispose()
            return

        # Try loading graph.json from filesystem
        data = None
        source = "synthetic"

        if GRAPH_JSON_PATH.exists():
            try:
                data = json.loads(GRAPH_JSON_PATH.read_text())
                source = "imported"
                logger.info(
                    "Loaded graph.json: %d nodes, %d links",
                    len(data.get("nodes", [])),
                    len(data.get("links", data.get("edges", []))),
                )
            except Exception as exc:
                logger.warning("Failed to read graph.json: %s", exc)
                data = None

        # If no graph.json, build synthetic topology from DB tables
        if data is None:
            data = await _build_synthetic_topology(conn)
            source = "computed"
            logger.info(
                "Built synthetic topology: %d nodes, %d edges",
                len(data.get("nodes", [])),
                len(data.get("edges", [])),
            )

        # Insert snapshot
        snapshot_id = str(uuid4())
        nodes = data.get("nodes", [])
        edges = data.get("links", data.get("edges", []))

        # Normalize: ensure "edges" key exists
        if "edges" not in data and "links" in data:
            data["edges"] = data.pop("links")

        await conn.execute(
            sa_text(
                """
                INSERT INTO topology_snapshots
                    (id, version, description, node_count, edge_count,
                     community_count, source, snapshot_data, created_at, updated_at)
                VALUES
                    (:id, 1, :description, :node_count, :edge_count,
                     0, :source, CAST(:snapshot_data AS jsonb), :now, :now)
            """
            ),
            {
                "id": snapshot_id,
                "description": f"Initial topology snapshot from {source}",
                "node_count": len(nodes),
                "edge_count": len(edges),
                "source": source,
                "snapshot_data": json.dumps(data, default=str),
                "now": now,
            },
        )

    await engine.dispose()
    logger.info(
        "Topology snapshot seeded: id=%s, source=%s, %d nodes, %d edges",
        snapshot_id,
        source,
        len(nodes),
        len(edges),
    )


async def _build_synthetic_topology(conn) -> dict:
    """Build a topology graph from agent_templates, tools_catalog, capabilities_catalog.

    Creates nodes for each agent template and edges from agents to their
    bound tools/capabilities.
    """
    from sqlalchemy import text as sa_text

    nodes = []
    edges = []

    # Agent template nodes
    r = await conn.execute(
        sa_text(
            "SELECT template_id, slug, name, agent_type FROM agent_templates WHERE is_active = true"
        )
    )
    agents = r.fetchall()
    for agent in agents:
        nodes.append(
            {
                "id": agent.slug,
                "label": agent.name,
                "stack": agent.agent_type or "agent",
                "type": "agent",
            }
        )

    # Tool nodes (from bindings)
    r = await conn.execute(
        sa_text(
            """
        SELECT DISTINCT tc.slug, tc.name, tc.category
        FROM agent_tool_bindings atb
        JOIN tools_catalog tc ON atb.tool_id = tc.id
    """
        )
    )
    tools = r.fetchall()
    for tool in tools:
        nodes.append(
            {
                "id": tool.slug,
                "label": tool.name,
                "stack": tool.category or "tool",
                "type": "tool",
            }
        )

    # Edges: agent → tool (from bindings)
    r = await conn.execute(
        sa_text(
            """
        SELECT at.slug as agent_slug, tc.slug as tool_slug
        FROM agent_tool_bindings atb
        JOIN agent_templates at ON atb.agent_id = at.template_id
        JOIN tools_catalog tc ON atb.tool_id = tc.id
    """
        )
    )
    bindings = r.fetchall()
    for b in bindings:
        edges.append(
            {
                "source": b.agent_slug,
                "target": b.tool_slug,
                "relation": "uses",
                "confidence": "DECLARED",
            }
        )

    # Capability nodes (from catalog, top-level only)
    r = await conn.execute(
        sa_text(
            "SELECT slug, name, category FROM capabilities_catalog WHERE enabled = true LIMIT 50"
        )
    )
    caps = r.fetchall()
    for cap in caps:
        nodes.append(
            {
                "id": cap.slug,
                "label": cap.name,
                "stack": cap.category or "capability",
                "type": "capability",
            }
        )

    return {"nodes": nodes, "edges": edges}


if __name__ == "__main__":
    asyncio.run(run())
