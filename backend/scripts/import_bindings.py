"""Populate agent_tool_bindings and agent_capability_bindings from agent_templates.

Reads each agent_template's ``definition`` JSONB column, extracts tool IDs
and capability strings, resolves them against ``tools_catalog`` and
``capabilities_catalog`` by slug, and inserts rows into the normalized
binding tables.

Usage (inside container):
    python /app/scripts/import_bindings.py

Idempotent: safe to re-run — uses ON CONFLICT DO NOTHING.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime, timezone
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run():
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    now = datetime.now(UTC)

    # ── 1. Load slug→id maps from catalog tables ────────────────────
    async with engine.begin() as conn:
        # tools_catalog slug → id
        tool_rows = await conn.execute(
            sa_text("SELECT id, slug FROM tools_catalog WHERE enabled = true")
        )
        tool_map = {row.slug: row.id for row in tool_rows.fetchall()}
        logger.info("tools_catalog: %d enabled tools", len(tool_map))

        # capabilities_catalog slug → id
        cap_rows = await conn.execute(
            sa_text("SELECT id, slug FROM capabilities_catalog WHERE enabled = true")
        )
        cap_map = {row.slug: row.id for row in cap_rows.fetchall()}
        logger.info("capabilities_catalog: %d enabled capabilities", len(cap_map))

        # agent_templates
        agent_rows = await conn.execute(
            sa_text(
                "SELECT template_id, slug, name, definition FROM agent_templates WHERE is_active = true"
            )
        )
        agents = agent_rows.fetchall()
        logger.info("agent_templates: %d active templates", len(agents))

        # ── 2. Process each agent template ──────────────────────────
        tool_bindings_inserted = 0
        tool_bindings_skipped = 0
        cap_bindings_inserted = 0
        cap_bindings_skipped = 0

        for agent in agents:
            template_id = agent.template_id
            agent_slug = agent.slug
            agent_name = agent.name

            # Parse definition JSONB
            definition = agent.definition
            if isinstance(definition, str):
                try:
                    definition = json.loads(definition)
                except (json.JSONDecodeError, TypeError):
                    definition = {}

            if not definition or not isinstance(definition, dict):
                logger.debug("Agent %s has no parseable definition", agent_slug)
                continue

            # ── 2a. Extract tool_ids from definition->tools ─────────
            tool_configs = definition.get("tools", [])
            if isinstance(tool_configs, list):
                for tc in tool_configs:
                    if isinstance(tc, dict):
                        tool_id_slug = tc.get("tool_id", "")
                    elif isinstance(tc, str):
                        tool_id_slug = tc
                    else:
                        continue

                    if not tool_id_slug:
                        continue

                    catalog_id = tool_map.get(tool_id_slug)
                    if catalog_id is None:
                        tool_bindings_skipped += 1
                        logger.debug(
                            "Agent %s references tool '%s' not found in tools_catalog",
                            agent_slug,
                            tool_id_slug,
                        )
                        continue

                    # Upsert with ON CONFLICT DO NOTHING
                    try:
                        result = await conn.execute(
                            sa_text(
                                """
                                INSERT INTO agent_tool_bindings
                                    (id, agent_id, tool_id, enabled, priority, created_at, updated_at)
                                VALUES (:id, :agent_id, :tool_id, true, 0, :now, :now)
                                ON CONFLICT (agent_id, tool_id) DO NOTHING
                            """
                            ),
                            {
                                "id": str(uuid4()),
                                "agent_id": template_id,
                                "tool_id": catalog_id,
                                "now": now,
                            },
                        )
                        if result.rowcount > 0:
                            tool_bindings_inserted += 1
                        else:
                            tool_bindings_skipped += 1
                    except Exception as exc:
                        tool_bindings_skipped += 1
                        logger.warning(
                            "Failed to insert tool binding %s→%s: %s",
                            agent_slug,
                            tool_id_slug,
                            exc,
                        )

            # ── 2b. Extract capabilities from definition ────────────
            # Python templates store capabilities as a list of strings
            # like ["chat", "analysis", "code"]
            caps = definition.get("capabilities", [])
            if isinstance(caps, list):
                for cap_slug in caps:
                    if not isinstance(cap_slug, str) or not cap_slug:
                        continue

                    catalog_id = cap_map.get(cap_slug)
                    if catalog_id is None:
                        cap_bindings_skipped += 1
                        logger.debug(
                            "Agent %s references capability '%s' not found in capabilities_catalog",
                            agent_slug,
                            cap_slug,
                        )
                        continue

                    try:
                        result = await conn.execute(
                            sa_text(
                                """
                                INSERT INTO agent_capability_bindings
                                    (id, agent_id, capability_id, enabled, priority, created_at, updated_at)
                                VALUES (:id, :agent_id, :capability_id, true, 0, :now, :now)
                                ON CONFLICT (agent_id, capability_id) DO NOTHING
                            """
                            ),
                            {
                                "id": str(uuid4()),
                                "agent_id": template_id,
                                "capability_id": catalog_id,
                                "now": now,
                            },
                        )
                        if result.rowcount > 0:
                            cap_bindings_inserted += 1
                        else:
                            cap_bindings_skipped += 1
                    except Exception as exc:
                        cap_bindings_skipped += 1
                        logger.warning(
                            "Failed to insert capability binding %s→%s: %s",
                            agent_slug,
                            cap_slug,
                            exc,
                        )

    await engine.dispose()
    logger.info(
        "Binding import complete: tool_bindings=%d inserted / %d skipped, capability_bindings=%d inserted / %d skipped",
        tool_bindings_inserted,
        tool_bindings_skipped,
        cap_bindings_inserted,
        cap_bindings_skipped,
    )


if __name__ == "__main__":
    asyncio.run(run())
