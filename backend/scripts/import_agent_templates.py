"""Import all agent templates into Postgres with slug, version, and source.

Usage:
    cd /opt/flowmanner/backend
    python -m scripts.import_agent_templates

This script:
1. Loads agent definitions from markdown files (agent_definitions/*.md)
2. Loads Python-defined templates from app/services/nexus/agent_templates.py
3. Upserts each into the agent_templates table with slug, version, source columns
4. Creates version snapshots in agent_template_versions
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run():
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.config import settings
    from app.services.agent_parser import load_all_agents
    from app.services.nexus.agent_templates import AGENT_TEMPLATES

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    now = datetime.now(timezone.utc)

    new_count = 0
    updated_count = 0

    async with engine.begin() as conn:
        # Verify required columns exist (migration must have run first)
        has_slug = await conn.execute(sa_text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'agent_templates' AND column_name = 'slug'"
        ))
        if not has_slug.fetchone():
            logger.error("agent_templates.slug column does not exist. Run Alembic migration first: alembic upgrade head")
            await engine.dispose()
            return

        # ── 1. Import markdown-defined agent templates ───────────────
        logger.info("Loading markdown agent definitions...")
        agents = load_all_agents()
        logger.info("Found %d markdown agent definitions", len(agents))

        for agent_data in agents:
            slug = agent_data["slug"]
            definition = json.dumps(agent_data, default=str)

            result = await conn.execute(
                sa_text("SELECT template_id, version FROM agent_templates WHERE slug = :slug"),
                {"slug": slug},
            )
            existing = result.fetchone()

            config = {
                "emoji": agent_data["emoji"],
                "color": agent_data["color"],
                "vibe": agent_data["vibe"],
                "slug": slug,
                "division": agent_data["division"],
            }

            if existing:
                template_id = existing[0]
                version = existing[1] or 1
                await conn.execute(
                    sa_text("""
                        UPDATE agent_templates SET
                            name = :name, description = :description,
                            system_prompt = :system_prompt, agent_type = :agent_type,
                            model_config = CAST(:model_config AS jsonb), source = 'file_imported',
                            definition = CAST(:definition AS jsonb),
                            version = version + 1, updated_at = :updated_at
                        WHERE slug = :slug
                    """),
                    {
                        "name": agent_data["name"],
                        "description": agent_data["description"],
                        "system_prompt": agent_data["system_prompt"],
                        "agent_type": agent_data["division"],
                        "model_config": json.dumps(config),
                        "definition": definition,
                        "slug": slug,
                        "updated_at": now,
                    },
                )
                await conn.execute(
                    sa_text("""
                        INSERT INTO agent_template_versions (id, template_id, version, snapshot, created_at, updated_at)
                        VALUES (:id, :template_id, :version, CAST(:snapshot AS jsonb), :now, :now)
                    """),
                    {
                        "id": str(uuid4()),
                        "template_id": template_id,
                        "version": version + 1,
                        "snapshot": definition,
                        "now": now,
                    },
                )
                updated_count += 1
            else:
                template_id = str(uuid4())
                await conn.execute(
                    sa_text("""
                        INSERT INTO agent_templates (
                            template_id, name, description, agent_type, system_prompt,
                            model_config, is_active, state, slug, version, source, definition,
                            created_at, updated_at
                        ) VALUES (
                            :template_id, :name, :description, :agent_type, :system_prompt,
                            CAST(:model_config AS jsonb), true, 'defined', :slug, 1, 'file_imported',
                            CAST(:definition AS jsonb), :updated_at, :updated_at
                        )
                    """),
                    {
                        "template_id": template_id,
                        "name": agent_data["name"],
                        "description": agent_data["description"],
                        "agent_type": agent_data["division"],
                        "system_prompt": agent_data["system_prompt"],
                        "model_config": json.dumps(config),
                        "slug": slug,
                        "definition": definition,
                        "updated_at": now,
                    },
                )
                await conn.execute(
                    sa_text("""
                        INSERT INTO agent_template_versions (id, template_id, version, snapshot, created_at, updated_at)
                        VALUES (:id, :template_id, 1, CAST(:snapshot AS jsonb), :now, :now)
                    """),
                    {
                        "id": str(uuid4()),
                        "template_id": template_id,
                        "snapshot": definition,
                        "now": now,
                    },
                )
                new_count += 1

        # ── 2. Import Python-defined agent templates ─────────────────
        logger.info("Importing %d Python agent templates...", len(AGENT_TEMPLATES))

        for tpl in AGENT_TEMPLATES:
            slug = tpl.id
            definition = json.dumps({
                "id": tpl.id,
                "name": tpl.name,
                "description": tpl.description,
                "category": tpl.category.value,
                "icon": tpl.icon,
                "tags": tpl.tags,
                "system_prompt": tpl.model_config.system_prompt,
                "provider": tpl.model_config.provider,
                "model_name": tpl.model_config.model_name,
                "temperature": tpl.model_config.temperature,
                "max_tokens": tpl.model_config.max_tokens,
                "tools": [{"tool_id": t.tool_id, "enabled": t.enabled} for t in tpl.tools],
            }, default=str)

            config = {
                "slug": slug,
                "emoji": tpl.icon,
                "division": tpl.category.value,
            }

            result = await conn.execute(
                sa_text("SELECT template_id, version FROM agent_templates WHERE slug = :slug"),
                {"slug": slug},
            )
            existing = result.fetchone()

            if existing:
                template_id = existing[0]
                version = existing[1] or 1
                await conn.execute(
                    sa_text("""
                        UPDATE agent_templates SET
                            name = :name, description = :description,
                            system_prompt = :system_prompt, agent_type = :agent_type,
                            model_config = CAST(:model_config AS jsonb), source = 'python_imported',
                            definition = CAST(:definition AS jsonb),
                            version = version + 1, updated_at = :updated_at
                        WHERE slug = :slug
                    """),
                    {
                        "name": tpl.name,
                        "description": tpl.description,
                        "system_prompt": tpl.model_config.system_prompt,
                        "agent_type": tpl.category.value,
                        "model_config": json.dumps(config),
                        "definition": definition,
                        "slug": slug,
                        "updated_at": now,
                    },
                )
                await conn.execute(
                    sa_text("""
                        INSERT INTO agent_template_versions (id, template_id, version, snapshot, created_at, updated_at)
                        VALUES (:id, :template_id, :version, :snapshot::jsonb, :now, :now)
                    """),
                    {
                        "id": str(uuid4()),
                        "template_id": template_id,
                        "version": version + 1,
                        "snapshot": definition,
                        "now": now,
                    },
                )
                updated_count += 1
            else:
                template_id = str(uuid4())
                await conn.execute(
                    sa_text("""
                        INSERT INTO agent_templates (
                            template_id, name, description, agent_type, system_prompt,
                            model_config, is_active, state, slug, version, source, definition,
                            created_at, updated_at
                        ) VALUES (
                            :template_id, :name, :description, :agent_type, :system_prompt,
                            CAST(:model_config AS jsonb), true, 'defined', :slug, 1, 'python_imported',
                            CAST(:definition AS jsonb), :updated_at, :updated_at
                        )
                    """),
                    {
                        "template_id": template_id,
                        "name": tpl.name,
                        "description": tpl.description,
                        "agent_type": tpl.category.value,
                        "system_prompt": tpl.model_config.system_prompt,
                        "model_config": json.dumps(config),
                        "slug": slug,
                        "definition": definition,
                        "updated_at": now,
                    },
                )
                await conn.execute(
                    sa_text("""
                        INSERT INTO agent_template_versions (id, template_id, version, snapshot, created_at, updated_at)
                        VALUES (:id, :template_id, 1, CAST(:snapshot AS jsonb), :now, :now)
                    """),
                    {
                        "id": str(uuid4()),
                        "template_id": template_id,
                        "snapshot": definition,
                        "now": now,
                    },
                )
                new_count += 1

    await engine.dispose()
    logger.info(
        "Import complete: %d new, %d updated, %d total",
        new_count, updated_count, new_count + updated_count,
    )


if __name__ == "__main__":
    asyncio.run(run())
