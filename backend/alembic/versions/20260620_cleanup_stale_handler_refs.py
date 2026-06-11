"""NULL out stale handler_refs that produce startup warnings.

These handler_ref values point to modules/classes that don't exist in the
codebase.  Setting them to NULL lets hydrate_from_db skip them silently
instead of logging a warning on every startup.

Stale tools_catalog entries (8):
- document_analyzer → app.tools.pdf_parser.PDFParserTool
- database_query → app.tools.postgresql_client.PostgreSQLClientTool
- knowledge_base → app.tools.knowledge_base_connector.KnowledgeBaseConnectorTool
- web_search → app.tools.google_search_api.GoogleSearchAPITool
- blog_post_expander → app.tools.blog_post_expander.BlogPostExpanderTool
- google_search_api → app.tools.google_search_api.GoogleSearchApiTool
- pdf_parser → app.tools.pdf_parser.PdfParserTool
- postgresql_client → app.tools.postgresql_client.PostgresqlClientTool

Stale capabilities_catalog entries (10):
- agent__customer-support-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
- agent__general-assistant-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
- agent__code-assistant-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
- agent__research-analyst-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
- agent__content-writer-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
- agent__data-scientist-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
- agent__automation-specialist-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
- agent__financial-analyst-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
- agent__legal-assistant-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
- agent__creative-writer-v1 → app.services.nexus.agent_templates:get_template_by_id(...)
"""

from sqlalchemy import text

from alembic import op

# revision identifiers
revision = "cleanup_stale_handler_refs_001"
down_revision = "fk_remaining_constraints_001"
branch_labels = None
depends_on = None

_STALE_TOOL_SLUGS = (
    "document_analyzer",
    "database_query",
    "knowledge_base",
    "web_search",
    "blog_post_expander",
    "google_search_api",
    "pdf_parser",
    "postgresql_client",
)

_STALE_CAP_SLUGS = (
    "agent__customer-support-v1",
    "agent__general-assistant-v1",
    "agent__code-assistant-v1",
    "agent__research-analyst-v1",
    "agent__content-writer-v1",
    "agent__data-scientist-v1",
    "agent__automation-specialist-v1",
    "agent__financial-analyst-v1",
    "agent__legal-assistant-v1",
    "agent__creative-writer-v1",
)


def upgrade() -> None:
    conn = op.get_bind()

    # NULL out stale handler_refs in tools_catalog
    result = conn.execute(
        text("UPDATE tools_catalog SET handler_ref = NULL WHERE slug = ANY(:slugs) AND handler_ref IS NOT NULL"),
        {"slugs": list(_STALE_TOOL_SLUGS)},
    )
    print(f"  tools_catalog: cleared {result.rowcount} stale handler_refs")

    # NULL out stale handler_refs in capabilities_catalog
    result = conn.execute(
        text("UPDATE capabilities_catalog SET handler_ref = NULL WHERE slug = ANY(:slugs) AND handler_ref IS NOT NULL"),
        {"slugs": list(_STALE_CAP_SLUGS)},
    )
    print(f"  capabilities_catalog: cleared {result.rowcount} stale handler_refs")


def downgrade() -> None:
    """Restore handler_refs from the original seed scripts.

    NOTE: This downgrade re-runs the seed scripts which will restore the
    stale handler_refs.  In practice, these should remain NULL'd.
    """
    # We don't restore the stale handler_refs — they pointed to non-existent
    # modules.  If the modules are added later, re-run add_stub_tools.py or
    # import_builtin_capabilities.py.
    pass
