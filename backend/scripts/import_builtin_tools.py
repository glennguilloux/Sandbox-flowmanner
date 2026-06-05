"""Import all builtin tools from the in-memory ToolRegistry into Postgres.

Usage:
    cd /opt/flowmanner/backend
    python -m scripts.import_builtin_tools

This script:
1. Bootstraps the in-memory ToolRegistry (same as lifespan.py startup)
2. Reads every registered tool
3. Upserts each into the tools_catalog table (by slug)
4. Creates a version snapshot in tool_versions
"""

import asyncio
import importlib
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


def _tool_type_from_module(module_name: str) -> str:
    """Infer tool_type from module name."""
    integration_slugs = {
        "slack_communicator", "gmail_sender", "notion_sync", "telegram_bot",
        "twilio_sms_sender", "stripe_operations", "salesforce_lead_creator",
        "sendgrid_campaign", "shopify_inventory_sync", "google_workspace_hub",
        "google_search_api", "google_analytics_reporter", "aws_s3_uploader",
        "github_manager", "github_actions_trigger", "linkedin_publisher",
        "instagram_media_publisher", "x_twitter_scheduler", "hubspot_crm_link",
        "linear_tasks", "vercel_deployer", "pinecone_manager",
    }
    if module_name in integration_slugs:
        return "integration"
    return "builtin"


def _handler_ref(tool) -> str:
    """Build handler_ref from the tool instance's class."""
    return f"{type(tool).__module__}.{type(tool).__name__}"


async def run():
    from sqlalchemy import select, text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.config import settings

    # ── 1. Bootstrap the in-memory ToolRegistry ──────────────────────
    from app.tools.base import get_tool_registry, register_tool

    # Import and register all core tools (same as lifespan._register_core_tools)
    from app.tools.browser_ping import BrowserPingTool
    from app.tools.browser_navigate import BrowserNavigateTool
    from app.tools.browser_screenshot import BrowserScreenshotTool
    from app.tools.browser_close import BrowserCloseTool
    from app.tools.browser_snapshot import BrowserSnapshotTool
    from app.tools.browser_click import BrowserClickTool
    from app.tools.browser_type import BrowserTypeTool
    from app.tools.browser_scroll import BrowserScrollTool
    from app.tools.topology import TopologyTool
    from app.tools.terminal import TerminalTool
    from app.tools.integration import ListIntegrationsTool, ExecuteIntegrationTool
    from app.tools.llm import LLMSummarizeTool, LLMTranslateTool, LLMClassifyTool
    from app.tools.data import JsonTransformTool, CsvParseTool, RegexExtractTool
    from app.tools.utility import UUIDGeneratorTool, TimestampConverterTool
    from app.tools.external import WeatherCurrentTool, CurrencyConvertTool
    from app.tools.differentiators import (
        PersistentAgentMemoryTool, SemanticMemoryIndexTool,
        KnowledgeBaseConnectorTool, BrandVoiceEnforcerTool,
        CollaborativeTeamSpaceTool, PIIRedactorTool,
        SemanticChunkingTool, SubAgentRouterTool,
        TaskPlannerTool, RAGContextBuilderTool,
    )

    core_tools = [
        BrowserPingTool(), BrowserNavigateTool(), BrowserScreenshotTool(),
        BrowserCloseTool(), BrowserSnapshotTool(), BrowserClickTool(),
        BrowserTypeTool(), BrowserScrollTool(), TopologyTool(), TerminalTool(),
        ListIntegrationsTool(), ExecuteIntegrationTool(),
        LLMSummarizeTool(), LLMTranslateTool(), LLMClassifyTool(),
        JsonTransformTool(), CsvParseTool(), RegexExtractTool(),
        UUIDGeneratorTool(), TimestampConverterTool(),
        WeatherCurrentTool(), CurrencyConvertTool(),
        PersistentAgentMemoryTool(), SemanticMemoryIndexTool(),
        KnowledgeBaseConnectorTool(), BrandVoiceEnforcerTool(),
        CollaborativeTeamSpaceTool(), PIIRedactorTool(),
        SemanticChunkingTool(), SubAgentRouterTool(),
        TaskPlannerTool(), RAGContextBuilderTool(),
    ]

    registry = get_tool_registry()
    for tool in core_tools:
        registry.register(tool)

    # Auto-discover remaining tools
    _EXCLUDE = {"base.py", "_file_utils.py", "_rlimits.py", "redis_cache.py"}
    tools_dir = Path(__file__).resolve().parent.parent / "app" / "tools"
    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name in _EXCLUDE or py_file.name.startswith("__"):
            continue
        try:
            importlib.import_module(f"app.tools.{py_file.stem}")
        except Exception as e:
            logger.warning("Failed to import %s: %s", py_file.stem, e)

    all_tools = registry.list_all()
    logger.info("In-memory registry: %d tools loaded", len(all_tools))

    # ── 2. Upsert into Postgres ──────────────────────────────────────
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    now = datetime.now(timezone.utc)

    new_count = 0
    updated_count = 0
    skipped_count = 0

    async with engine.begin() as conn:
        # Ensure table exists
        exists = await conn.execute(
            sa_text("SELECT 1 FROM information_schema.tables WHERE table_name = 'tools_catalog'")
        )
        if not exists.fetchone():
            logger.error("tools_catalog table does not exist. Run Alembic migration first.")
            await engine.dispose()
            return

        for tool in all_tools:
            slug = tool.tool_id
            tool_class = type(tool).__name__
            module_name = type(tool).__module__.split(".")[-1]
            handler = _handler_ref(tool)

            input_schema = None
            output_schema = None
            if hasattr(tool, "metadata") and tool.metadata:
                input_schema = tool.metadata.input_schema or None
                output_schema = tool.metadata.output_schema or None

            # Pre-serialize JSON fields to strings (::jsonb cast is not safe in text() queries)
            row_data = {
                "slug": slug,
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "tool_type": _tool_type_from_module(module_name),
                "handler_ref": handler,
                "input_schema": json.dumps(input_schema) if input_schema else None,
                "output_schema": json.dumps(output_schema) if output_schema else None,
                "tags": json.dumps(getattr(tool, "tags", []) or []),
                "tier": getattr(tool, "tier", 1),
                "timeout_seconds": getattr(tool.metadata, "timeout_seconds", 30) if hasattr(tool, "metadata") and tool.metadata else 30,
                "requires_auth": getattr(tool.metadata, "requires_auth", True) if hasattr(tool, "metadata") and tool.metadata else True,
                "source": "builtin_imported",
                "updated_at": now,
            }

            # Check if exists
            result = await conn.execute(
                sa_text("SELECT id, version FROM tools_catalog WHERE slug = :slug"),
                {"slug": slug},
            )
            existing = result.fetchone()

            if existing:
                tool_id = existing[0]
                version = existing[1]
                # Update
                await conn.execute(
                    sa_text("""
                        UPDATE tools_catalog SET
                            name = :name, description = :description, category = :category,
                            tool_type = :tool_type, handler_ref = :handler_ref,
                            input_schema = CAST(:input_schema AS jsonb), output_schema = CAST(:output_schema AS jsonb),
                            tags = CAST(:tags AS jsonb), tier = :tier, timeout_seconds = :timeout_seconds,
                            requires_auth = :requires_auth, source = :source,
                            version = version + 1, updated_at = :updated_at
                        WHERE slug = :slug
                    """),
                    row_data,
                )
                # Create version snapshot
                await conn.execute(
                    sa_text("""
                        INSERT INTO tool_versions (id, tool_id, version, snapshot, created_at, updated_at)
                        VALUES (:id, :tool_id, :version, CAST(:snapshot AS jsonb), :now, :now)
                    """),
                    {
                        "id": str(uuid4()),
                        "tool_id": tool_id,
                        "version": version + 1,
                        "snapshot": json.dumps(row_data, default=str),
                        "now": now,
                    },
                )
                updated_count += 1
            else:
                tool_id = str(uuid4())
                await conn.execute(
                    sa_text("""
                        INSERT INTO tools_catalog (
                            id, slug, name, description, category, tool_type,
                            handler_ref, input_schema, output_schema, tags, tier,
                            timeout_seconds, requires_auth, source, version,
                            created_at, updated_at
                        ) VALUES (
                            :id, :slug, :name, :description, :category, :tool_type,
                            :handler_ref, CAST(:input_schema AS jsonb), CAST(:output_schema AS jsonb), CAST(:tags AS jsonb), :tier,
                            :timeout_seconds, :requires_auth, :source, 1,
                            :updated_at, :updated_at
                        )
                    """),
                    {**row_data, "id": tool_id},
                )
                # Create version snapshot
                await conn.execute(
                    sa_text("""
                        INSERT INTO tool_versions (id, tool_id, version, snapshot, created_at, updated_at)
                        VALUES (:id, :tool_id, 1, CAST(:snapshot AS jsonb), :now, :now)
                    """),
                    {
                        "id": str(uuid4()),
                        "tool_id": tool_id,
                        "snapshot": json.dumps(row_data, default=str),
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
