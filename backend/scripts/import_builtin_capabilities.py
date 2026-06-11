"""Import all builtin capabilities from the in-memory CapabilityRegistry into Postgres.

Usage:
    cd /opt/flowmanner/backend
    python -m scripts.import_builtin_capabilities

This script:
1. Bootstraps the CapabilityRegistry (same as lifespan.py startup)
2. Reads every registered capability
3. Upserts each into the capabilities_catalog table (by slug)
4. Creates a version snapshot in capability_versions
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

    # ── 1. Bootstrap CapabilityRegistry ──────────────────────────────
    from app.services.nexus.capability_registry import (
        Capability,
        get_capability_registry,
    )

    registry = get_capability_registry()

    # Register agent templates as capabilities (same as lifespan._register_agent_capabilities)
    try:
        from sqlalchemy import select

        from app.database import AsyncSessionLocal
        from app.models.agent import AgentTemplate
        from app.services.nexus.agent_templates import AGENT_TEMPLATES

        # DB templates
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(AgentTemplate).where(AgentTemplate.is_active.is_(True)))
            db_templates = result.scalars().all()

            for tpl in db_templates:
                slug = (tpl.model_config.get("slug") if tpl.model_config else None) or tpl.name.lower().replace(
                    " ", "-"
                )
                cap_id = f"agent:{slug}"

                async def make_handler(template=tpl):
                    async def handler(params: dict):
                        return {"agent": {"id": template.template_id, "name": template.name}}

                    return handler

                capability = Capability(
                    id=cap_id,
                    name=tpl.name,
                    description=tpl.description or f"{tpl.agent_type} agent template",
                    category="agent",
                    handler=await make_handler(),
                    input_schema={
                        "type": "object",
                        "properties": {"task": {"type": "string"}},
                    },
                    requires_auth=True,
                    metadata={
                        "template_id": tpl.template_id,
                        "agent_type": tpl.agent_type,
                        "source": "database",
                        "slug": slug,
                    },
                )
                registry.register(capability)

        # Python templates
        for tpl in AGENT_TEMPLATES:
            cap_id = f"agent:{tpl.id}"

            async def make_handler(template=tpl):
                async def handler(params: dict):
                    return {"agent": {"id": template.id, "name": template.name}}

                return handler

            tool_ids = [t.tool_id for t in tpl.tools]
            capability = Capability(
                id=cap_id,
                name=tpl.name,
                description=tpl.description,
                category="agent",
                handler=await make_handler(),
                input_schema={
                    "type": "object",
                    "properties": {"task": {"type": "string"}},
                },
                requires_auth=True,
                metadata={
                    "template_id": tpl.id,
                    "agent_type": tpl.category.value,
                    "source": "python",
                    "tools": tool_ids,
                },
            )
            registry.register(capability)

    except Exception as e:
        logger.warning("Failed to load agent templates as capabilities: %s", e)

    all_caps = registry.list_all()
    logger.info("In-memory registry: %d capabilities loaded", len(all_caps))

    # ── 2. Upsert into Postgres ──────────────────────────────────────
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    now = datetime.now(UTC)

    new_count = 0
    updated_count = 0

    async with engine.begin() as conn:
        exists = await conn.execute(
            sa_text("SELECT 1 FROM information_schema.tables WHERE table_name = 'capabilities_catalog'")
        )
        if not exists.fetchone():
            logger.error("capabilities_catalog table does not exist. Run Alembic migration first.")
            await engine.dispose()
            return

        for cap in all_caps:
            slug = cap.id.replace(":", "__").replace("/", "__")
            handler_ref = None
            if cap.metadata.get("source") == "python":
                handler_ref = (
                    f"app.services.nexus.agent_templates:get_template_by_id('{cap.metadata.get('template_id', '')}')"
                )

            row_data = {
                "slug": slug,
                "name": cap.name,
                "description": cap.description,
                "category": cap.category,
                "handler_ref": handler_ref,
                "input_schema": (json.dumps(cap.input_schema) if cap.input_schema else None),
                "output_schema": (json.dumps(cap.output_schema) if cap.output_schema else None),
                "timeout_seconds": cap.timeout_seconds,
                "rate_limit": cap.rate_limit,
                "source": cap.metadata.get("source", "builtin_imported"),
                "metadata": json.dumps(cap.metadata, default=str),
                "updated_at": now,
            }

            result = await conn.execute(
                sa_text("SELECT id, version FROM capabilities_catalog WHERE slug = :slug"),
                {"slug": slug},
            )
            existing = result.fetchone()

            if existing:
                cap_id = existing[0]
                version = existing[1]
                await conn.execute(
                    sa_text(
                        """
                        UPDATE capabilities_catalog SET
                            name = :name, description = :description, category = :category,
                            handler_ref = :handler_ref,
                            input_schema = CAST(:input_schema AS jsonb), output_schema = CAST(:output_schema AS jsonb),
                            timeout_seconds = :timeout_seconds, rate_limit = :rate_limit,
                            source = :source, metadata = CAST(:metadata AS jsonb),
                            version = version + 1, updated_at = :updated_at
                        WHERE slug = :slug
                    """
                    ),
                    row_data,
                )
                await conn.execute(
                    sa_text(
                        """
                        INSERT INTO capability_versions (id, capability_id, version, snapshot, created_at, updated_at)
                        VALUES (:id, :capability_id, :version, CAST(:snapshot AS jsonb), :now, :now)
                    """
                    ),
                    {
                        "id": str(uuid4()),
                        "capability_id": cap_id,
                        "version": version + 1,
                        "snapshot": json.dumps(row_data, default=str),
                        "now": now,
                    },
                )
                updated_count += 1
            else:
                cap_id = str(uuid4())
                await conn.execute(
                    sa_text(
                        """
                        INSERT INTO capabilities_catalog (
                            id, slug, name, description, category, handler_ref,
                            input_schema, output_schema, timeout_seconds, rate_limit,
                            source, metadata, version, created_at, updated_at
                        ) VALUES (
                            :id, :slug, :name, :description, :category, :handler_ref,
                            CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb), :timeout_seconds, :rate_limit,
                            :source, CAST(:metadata AS jsonb), 1, :updated_at, :updated_at
                        )
                    """
                    ),
                    {**row_data, "id": cap_id},
                )
                await conn.execute(
                    sa_text(
                        """
                        INSERT INTO capability_versions (id, capability_id, version, snapshot, created_at, updated_at)
                        VALUES (:id, :capability_id, 1, CAST(:snapshot AS jsonb), :now, :now)
                    """
                    ),
                    {
                        "id": str(uuid4()),
                        "capability_id": cap_id,
                        "snapshot": json.dumps(row_data, default=str),
                        "now": now,
                    },
                )
                new_count += 1

    await engine.dispose()
    logger.info(
        "Import complete: %d new, %d updated, %d total",
        new_count,
        updated_count,
        new_count + updated_count,
    )


if __name__ == "__main__":
    asyncio.run(run())
