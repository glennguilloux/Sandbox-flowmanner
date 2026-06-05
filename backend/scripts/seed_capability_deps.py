"""Seed capability_dependencies from agent template tool overlap and semantic clustering.

Inference strategies:
1. **Tool overlap** — Two agents sharing ≥2 tools get a "preferred" bidirectional
   dependency (they can substitute or complement each other).
2. **Semantic clustering** — Agents sharing a name-prefix domain (e.g.
   "academic-*", "customer-support-*") get "optional" dependencies within
   their cluster.

Usage (inside container):
    python /app/scripts/seed_capability_deps.py

Idempotent: ON CONFLICT (capability_id, depends_on_id) DO NOTHING.
"""

import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Semantic domain clusters ────────────────────────────────────────
# Agents whose slug contains any of these prefixes share a domain.
DOMAIN_PREFIXES = [
    "academic-",
    "account-",
    "customer-support",
    "data-",
    "devops-",
    "financial-",
    "hr-",
    "it-",
    "legal-",
    "marketing-",
    "medical-",
    "sales-",
    "supply-chain-",
    "technical-",
]

# Minimum shared tools to create a "preferred" dependency
MIN_SHARED_TOOLS = 2

# Maximum dependencies per agent (cap the graph density)
MAX_DEPS_PER_AGENT = 10


async def run():
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    now = datetime.now(timezone.utc)

    async with engine.begin() as conn:
        # ── 1. Load capability slug → id map ────────────────────────
        r = await conn.execute(sa_text(
            "SELECT id, slug FROM capabilities_catalog WHERE enabled = true"
        ))
        cap_map = {row.slug: row.id for row in r.fetchall()}
        logger.info("Loaded %d capabilities from catalog", len(cap_map))

        # ── 2. Load agent → tools mapping from bindings ─────────────
        r = await conn.execute(sa_text("""
            SELECT at.slug as agent_slug, tc.slug as tool_slug
            FROM agent_tool_bindings atb
            JOIN agent_templates at ON atb.agent_id = at.template_id
            JOIN tools_catalog tc ON atb.tool_id = tc.id
        """))
        agent_tools = defaultdict(set)
        for row in r.fetchall():
            agent_tools[row.agent_slug].add(row.tool_slug)
        logger.info("Loaded tool bindings for %d agents", len(agent_tools))

        # ── 3. Build capability slug → agent slug mapping ───────────
        # Agent templates have slugs like "general-assistant-v1"
        # Capabilities have slugs like "agent__general-assistant-v1"
        agent_slugs = set()
        cap_to_agent = {}
        for cap_slug in cap_map:
            if cap_slug.startswith("agent__"):
                agent_slug = cap_slug[len("agent__"):]
                cap_to_agent[cap_slug] = agent_slug
                agent_slugs.add(agent_slug)

        logger.info("Mapped %d capability slugs to agent slugs", len(cap_to_agent))

        # ── 4. Infer dependencies ───────────────────────────────────
        deps = []  # (cap_slug_a, cap_slug_b, dependency_type)

        # Strategy 1: Tool overlap — normalize to capability slugs
        agent_list = list(agent_tools.keys())
        existing = set()
        for i in range(len(agent_list)):
            for j in range(i + 1, len(agent_list)):
                a = agent_list[i]
                b = agent_list[j]
                shared = agent_tools[a] & agent_tools[b]
                if len(shared) >= MIN_SHARED_TOOLS:
                    cap_a = f"agent__{a}"
                    cap_b = f"agent__{b}"
                    if cap_a in cap_map and cap_b in cap_map:
                        deps.append((cap_a, cap_b, "preferred"))
                        deps.append((cap_b, cap_a, "preferred"))
                        existing.add((cap_a, cap_b))
                        existing.add((cap_b, cap_a))

        logger.info("Tool overlap: %d dependency pairs", len(deps) // 2)

        # Strategy 2: Semantic domain clustering
        domain_members = defaultdict(list)
        for agent_slug in agent_slugs:
            for prefix in DOMAIN_PREFIXES:
                if agent_slug.startswith(prefix):
                    domain_members[prefix].append(agent_slug)
                    break

        sem_deps = 0
        for prefix, members in domain_members.items():
            if len(members) < 2:
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    cap_a = f"agent__{members[i]}"
                    cap_b = f"agent__{members[j]}"
                    if cap_a in cap_map and cap_b in cap_map:
                        if (cap_a, cap_b) not in existing:
                            deps.append((cap_a, cap_b, "optional"))
                            deps.append((cap_b, cap_a, "optional"))
                            existing.add((cap_a, cap_b))
                            existing.add((cap_b, cap_a))
                            sem_deps += 1

        logger.info("Semantic clustering: %d additional dependency pairs", sem_deps)

        # ── 5. Cap per-agent dependency count ───────────────────────
        dep_count = defaultdict(int)
        capped = []
        for cap_a, cap_b, dep_type in deps:
            if dep_count[cap_a] < MAX_DEPS_PER_AGENT:
                capped.append((cap_a, cap_b, dep_type))
                dep_count[cap_a] += 1
            # else: skip this dep but keep processing others

        logger.info("After capping at %d deps/agent: %d total", MAX_DEPS_PER_AGENT, len(capped))

        # ── 6. Insert into capability_dependencies ──────────────────
        inserted = 0
        skipped = 0
        for cap_a, cap_b, dep_type in capped:
            cap_id_a = cap_map[cap_a]
            cap_id_b = cap_map[cap_b]
            try:
                result = await conn.execute(
                    sa_text("""
                        INSERT INTO capability_dependencies
                            (id, capability_id, depends_on_id, dependency_type, created_at, updated_at)
                        VALUES (:id, :cap_id, :dep_id, :dep_type, :now, :now)
                        ON CONFLICT (capability_id, depends_on_id) DO NOTHING
                    """),
                    {
                        "id": str(uuid4()),
                        "cap_id": cap_id_a,
                        "dep_id": cap_id_b,
                        "dep_type": dep_type,
                        "now": now,
                    },
                )
                if result.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as exc:
                skipped += 1
                logger.debug("Skipped dep %s→%s: %s", cap_a, cap_b, exc)

    await engine.dispose()
    logger.info(
        "Capability dependencies seed: %d inserted, %d skipped", inserted, skipped,
    )


if __name__ == "__main__":
    asyncio.run(run())
