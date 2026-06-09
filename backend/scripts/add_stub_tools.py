"""Add missing stub tools to tools_catalog for agent template binding resolution.

15 tool IDs are referenced by agent_templates but don't exist in tools_catalog.
This script adds them as stubs with a passthrough handler_ref so the binding
import can match them by slug.

Some stubs map to existing tools (e.g. web_search → google_search_api handler).
Others get a lightweight stub that returns a "not yet implemented" message.

Usage (inside container):
    python /app/scripts/add_stub_tools.py

Idempotent: safe to re-run (ON CONFLICT DO NOTHING on slug).
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Stub tool definitions ───────────────────────────────────────────
# Each entry: (slug, name, description, category, handler_ref, tags)
# handler_ref=None → will use the generic passthrough stub
STUB_TOOLS = [
    {
        "slug": "web_search",
        "name": "Web Search",
        "description": "Search the web for information using search engines.",
        "category": "research-knowledge-retrieval",
        "handler_ref": "app.tools.google_search_api.GoogleSearchAPITool",
        "tags": ["search", "web", "research"],
    },
    {
        "slug": "calculator",
        "name": "Calculator",
        "description": "Perform mathematical calculations and evaluations.",
        "category": "utility",
        "handler_ref": "app.tools.python_sandbox.PythonSandboxTool",
        "tags": ["math", "calculation", "utility"],
    },
    {
        "slug": "code_executor",
        "name": "Code Executor",
        "description": "Execute code snippets in a sandboxed environment.",
        "category": "code-execution-and-development",
        "handler_ref": "app.tools.python_sandbox.PythonSandboxTool",
        "tags": ["code", "execution", "sandbox"],
    },
    {
        "slug": "file_operations",
        "name": "File Operations",
        "description": "Read, write, and manage files on the filesystem.",
        "category": "file-handling",
        "handler_ref": None,
        "tags": ["files", "filesystem", "io"],
    },
    {
        "slug": "git_operations",
        "name": "Git Operations",
        "description": "Manage git repositories — clone, commit, branch, merge, diff.",
        "category": "developer-tools",
        "handler_ref": "app.tools.git_repo_manager.GitRepoManagerTool",
        "tags": ["git", "vcs", "developer"],
    },
    {
        "slug": "document_analyzer",
        "name": "Document Analyzer",
        "description": "Analyze and extract information from documents (PDF, DOCX, etc.).",
        "category": "file-handling",
        "handler_ref": "app.tools.pdf_parser.PDFParserTool",
        "tags": ["documents", "analysis", "extraction"],
    },
    {
        "slug": "data_visualization",
        "name": "Data Visualization",
        "description": "Create charts, graphs, and visual representations of data.",
        "category": "visual-reasoning-and-image-analysis",
        "handler_ref": None,
        "tags": ["charts", "visualization", "data"],
    },
    {
        "slug": "database_query",
        "name": "Database Query",
        "description": "Execute SQL queries against databases.",
        "category": "database",
        "handler_ref": "app.tools.postgresql_client.PostgreSQLClientTool",
        "tags": ["database", "sql", "query"],
    },
    {
        "slug": "knowledge_base",
        "name": "Knowledge Base",
        "description": "Search and retrieve information from the knowledge base.",
        "category": "knowledge",
        "handler_ref": "app.tools.knowledge_base_connector.KnowledgeBaseConnectorTool",
        "tags": ["knowledge", "search", "retrieval"],
    },
    {
        "slug": "seo_analyzer",
        "name": "SEO Analyzer",
        "description": "Analyze content for SEO optimization — keywords, meta tags, readability.",
        "category": "seo-marketing",
        "handler_ref": "app.tools.keyword_density_analyzer.KeywordDensityAnalyzerTool",
        "tags": ["seo", "marketing", "content"],
    },
    {
        "slug": "ticket_system",
        "name": "Ticket System",
        "description": "Create, update, and manage support tickets.",
        "category": "communication",
        "handler_ref": None,
        "tags": ["tickets", "support", "helpdesk"],
    },
    {
        "slug": "order_lookup",
        "name": "Order Lookup",
        "description": "Look up order details, status, and tracking information.",
        "category": "e-commerce-business",
        "handler_ref": None,
        "tags": ["orders", "ecommerce", "lookup"],
    },
    {
        "slug": "api_connector",
        "name": "API Connector",
        "description": "Connect to external APIs — send requests, handle auth, parse responses.",
        "category": "api-integrations",
        "handler_ref": None,
        "tags": ["api", "http", "integration"],
    },
    {
        "slug": "webhook_manager",
        "name": "Webhook Manager",
        "description": "Register, manage, and trigger webhooks for event-driven workflows.",
        "category": "api-integrations",
        "handler_ref": None,
        "tags": ["webhooks", "events", "automation"],
    },
    {
        "slug": "workflow_builder",
        "name": "Workflow Builder",
        "description": "Design and execute automated workflows with branching logic.",
        "category": "automation",
        "handler_ref": None,
        "tags": ["workflows", "automation", "orchestration"],
    },
]


async def run():
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    now = datetime.now(timezone.utc)

    inserted = 0
    skipped = 0

    async with engine.begin() as conn:
        for tool in STUB_TOOLS:
            try:
                tool_id = str(uuid4())
                result = await conn.execute(
                    sa_text(
                        """
                        INSERT INTO tools_catalog (
                            id, slug, name, description, category, tool_type,
                            handler_ref, tags, source, version,
                            enabled, visibility, requires_auth, timeout_seconds, tier,
                            created_at, updated_at
                        ) VALUES (
                            :id, :slug, :name, :description, :category, 'stub',
                            :handler_ref, CAST(:tags AS jsonb), 'stub_imported', 1,
                            true, 'public', false, 30, 1,
                            :now, :now
                        )
                        ON CONFLICT (slug) DO NOTHING
                    """
                    ),
                    {
                        "id": tool_id,
                        "slug": tool["slug"],
                        "name": tool["name"],
                        "description": tool["description"],
                        "category": tool["category"],
                        "handler_ref": tool["handler_ref"],
                        "tags": json.dumps(tool["tags"]),
                        "now": now,
                    },
                )
                if result.rowcount > 0:
                    # Create version snapshot (matches Phase 1 pattern)
                    snapshot = json.dumps(
                        {
                            "slug": tool["slug"],
                            "name": tool["name"],
                            "description": tool["description"],
                            "category": tool["category"],
                            "tool_type": "stub",
                            "handler_ref": tool["handler_ref"],
                            "tags": tool["tags"],
                            "source": "stub_imported",
                        },
                        default=str,
                    )
                    await conn.execute(
                        sa_text(
                            """
                            INSERT INTO tool_versions (id, tool_id, version, snapshot, created_at, updated_at)
                            VALUES (:id, :tool_id, 1, CAST(:snapshot AS jsonb), :now, :now)
                        """
                        ),
                        {
                            "id": str(uuid4()),
                            "tool_id": tool_id,
                            "snapshot": snapshot,
                            "now": now,
                        },
                    )
                    inserted += 1
                    logger.info("  Inserted: %s", tool["slug"])
                else:
                    skipped += 1
                    logger.debug("  Already exists: %s", tool["slug"])
            except Exception as exc:
                logger.warning("Failed to insert %s: %s", tool["slug"], exc)

    await engine.dispose()
    logger.info(
        "Stub tools import: %d inserted, %d skipped (already existed)",
        inserted,
        skipped,
    )


if __name__ == "__main__":
    asyncio.run(run())
