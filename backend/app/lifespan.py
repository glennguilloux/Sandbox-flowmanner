"""
Application Lifespan Manager

Handles startup and shutdown events for the FastAPI application.
Initializes and tears down services that need lifecycle management.
"""

# FAILURE ISOLATION: Langfuse errors must never break application startup.
# _init_langfuse() and _init_litellm_callbacks() must never raise on failure.
# If Langfuse is unavailable at startup, the application still serves requests
# without observability. The circuit breaker in LangfuseService will handle
# reconnection attempts during the recovery window.

import logging
from contextlib import asynccontextmanager

from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    settings.assert_production_ready()
    # === STARTUP ===
    logger.info("Application starting up...")

    _validate_production_secrets()

    # Comment 5: fail fast when an enabled model cannot be served (missing
    # pricing/provider/env key). In production this raises; in dev it warns.
    try:
        from app.services.model_catalog import validate_model_catalog_at_startup

        validate_model_catalog_at_startup()
    except Exception as cat_err:  # pragma: no cover - defensive
        logger.warning("Model catalog startup validation skipped: %s", cat_err)

    # Initialize Langfuse observability
    _init_langfuse()

    # Initialize Sentry error tracking
    _init_sentry()

    # Initialize LiteLLM callbacks (if Langfuse is enabled)
    _init_litellm_callbacks()

    # Seed agent templates from disk (idempotent — ensures DB is populated)
    await _seed_agent_templates()

    # Start trigger scheduler (H2.4: TriggerBridge with 2s polling)
    await _start_trigger_scheduler()

    # Start playground cleanup background task (Phase 4)
    _start_playground_cleanup()

    # ── Hydration Phase: Postgres-native with Python fallback ────────
    # Try to hydrate the in-memory ToolRegistry from the tools_catalog
    # table.  If the table is empty (import scripts haven't been run yet),
    # fall back to the legacy Python-based registration.
    tools_from_db = await _hydrate_tools_from_db()
    if not tools_from_db:
        logger.info("Tool hydration fallback: registering from Python builtins")
        _register_core_tools()

    # Same pattern for capabilities — hydrate from capabilities_catalog,
    # fall back to the legacy agent-capability registration.
    caps_from_db = await _hydrate_capabilities_from_db()
    if not caps_from_db:
        logger.info("Capability hydration fallback: registering from Python builtins")
        await _register_agent_capabilities()

    # Seed marketplace sample listings (idempotent)
    await _seed_marketplace()

    # Load installed plugins from DB (Phase 9.1)
    await _load_plugins()

    # Build topology from DB snapshot (Phase 2.4)
    # Tries topology_snapshots table first, falls back to filesystem graph.json
    await _hydrate_topology_from_db()

    # Initialize semantic tool discovery (indexes tools into Qdrant)
    # Must run AFTER all tool registration (hydration or fallback)
    _init_tool_discovery()

    # Register differentiator stubs in unified_tools registry
    _register_differentiator_stubs_to_unified()

    # Re-register integration capabilities for all active connections
    await _register_integration_capabilities()

    logger.info("Application startup complete")

    yield

    # === SHUTDOWN ===
    logger.info("Application shutting down...")

    # Task 3.3: drain BackgroundTaskManager (ref-held ephemeral tasks)
    try:
        from app.services.background_task_manager import background_task_manager

        await background_task_manager.drain(timeout=5.0)
    except Exception as e:
        logger.debug("BackgroundTaskManager drain error (non-fatal): %s", e)

    # Stop playground cleanup task (Phase 4)
    _stop_playground_cleanup()

    # Stop trigger scheduler (FLO-118)
    await _stop_trigger_scheduler()

    _shutdown_langfuse()

    # Flush Sentry before shutdown
    _shutdown_sentry()

    logger.info("Application shutdown complete")


# ── Postgres-native hydration helpers (Phase 1.4) ──────────────────


def _resolve_handler_ref(handler_ref: str):
    """Resolve a dotted Python path — delegates to :func:`app.tools.base.resolve_handler_ref`.

    Kept for backwards-compatibility with existing tests.
    """
    from app.tools.base import resolve_handler_ref

    return resolve_handler_ref(handler_ref)


async def _hydrate_tools_from_db() -> bool:
    """Load all enabled tools from ``tools_catalog`` into the in-memory ToolRegistry.

    Returns ``True`` if the DB had tools (hydration succeeded), ``False``
    if the table was empty / missing so the caller should fall back to
    the legacy Python-based registration.

    Delegates to ``ToolRegistry.hydrate_from_db(session)`` (Phase 2.1).
    """
    try:
        from app.database import AsyncSessionLocal
        from app.tools.base import get_tool_registry

        async with AsyncSessionLocal() as session:
            registry = get_tool_registry()
            count = await registry.hydrate_from_db(session)

        if count == 0:
            logger.info("tools_catalog is empty — will use Python fallback")
            return False

        return True

    except Exception as e:
        logger.warning("DB tool hydration failed (will use fallback): %s", e)
        return False


async def _hydrate_capabilities_from_db() -> bool:
    """Load all enabled capabilities from ``capabilities_catalog`` into the in-memory CapabilityRegistry.

    Returns ``True`` if the DB had capabilities, ``False`` if the caller
    should fall back to the legacy Python-based registration.

    Delegates to ``CapabilityRegistry.hydrate_from_db(session)`` (Phase 2.2).
    """
    try:
        from app.database import AsyncSessionLocal
        from app.services.nexus.capability_registry import (
            get_capability_registry,
        )

        async with AsyncSessionLocal() as session:
            registry = get_capability_registry()
            count = await registry.hydrate_from_db(session)

        if count == 0:
            logger.info("capabilities_catalog is empty — will use Python fallback")
            return False

        return True

    except Exception as e:
        logger.warning("DB capability hydration failed (will use fallback): %s", e)
        return False


async def _register_agent_capabilities():
    """Register all agent templates as discoverable capabilities.

    Reads templates from both the database (seeded from YAML definitions)
    and the Python agent_templates.py file, then registers each as a
    Capability in the CapabilityRegistry so the orchestrator can find them.

    Also registers agents in the TopologyManager for semantic matching.
    """
    try:
        from sqlalchemy import select

        from app.database import AsyncSessionLocal
        from app.models.agent import AgentTemplate
        from app.services.nexus.agent_templates import AGENT_TEMPLATES
        from app.services.nexus.capability_registry import (
            Capability,
            get_capability_registry,
        )

        registry = get_capability_registry()
        registered = 0

        # ── 1. Register agent templates from the database ──────────
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(AgentTemplate).where(AgentTemplate.is_active.is_(True)))
            db_templates = result.scalars().all()

            for tpl in db_templates:
                try:
                    slug = (tpl.model_config.get("slug") if tpl.model_config else None) or tpl.name.lower().replace(
                        " ", "-"
                    )
                    cap_id = f"agent:{slug}"

                    async def make_handler(template=tpl):
                        async def handler(params: dict):
                            return {
                                "agent": {
                                    "id": template.template_id,
                                    "name": template.name,
                                    "description": template.description,
                                    "agent_type": template.agent_type,
                                    "system_prompt": template.system_prompt,
                                    "model_config": template.model_config,
                                }
                            }

                        return handler

                    capability = Capability(
                        id=cap_id,
                        name=tpl.name,
                        description=tpl.description or f"{tpl.agent_type} agent template",
                        category="agent",
                        handler=await make_handler(),
                        input_schema={
                            "type": "object",
                            "properties": {
                                "task": {"type": "string"},
                            },
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
                    registered += 1
                except Exception as e:
                    logger.warning(
                        "Failed to register DB agent template %s: %s",
                        getattr(tpl, "name", "unknown"),
                        e,
                    )

        # ── 2. Register agent templates from Python definitions ─────
        for tpl in AGENT_TEMPLATES:
            try:
                cap_id = f"agent:{tpl.id}"

                async def make_handler(template=tpl):
                    async def handler(params: dict):
                        return {
                            "agent": {
                                "id": template.id,
                                "name": template.name,
                                "description": template.description,
                                "category": template.category.value,
                                "icon": template.icon,
                                "tags": template.tags,
                                "system_prompt": template.model_config.system_prompt,
                                "model_config": {
                                    "provider": template.model_config.provider,
                                    "model_name": template.model_config.model_name,
                                    "temperature": template.model_config.temperature,
                                    "max_tokens": template.model_config.max_tokens,
                                },
                                "tools": [t.tool_id for t in template.tools],
                            }
                        }

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
                        "properties": {
                            "task": {"type": "string"},
                        },
                    },
                    requires_auth=True,
                    metadata={
                        "template_id": tpl.id,
                        "agent_type": tpl.category.value,
                        "source": "python",
                        "tools": tool_ids,
                        "icon": tpl.icon,
                        "tags": tpl.tags,
                    },
                )
                registry.register(capability)
                registered += 1
            except Exception as e:
                logger.warning(
                    "Failed to register Python agent template %s: %s",
                    getattr(tpl, "name", "unknown"),
                    e,
                )

        # ── 3. Register agents in TopologyManager for semantic matching
        try:
            from app.services.semantic.topology_manager import get_topology_manager

            topo = get_topology_manager()
            all_caps = registry.list_all(category="agent")
            for cap in all_caps:
                try:
                    await topo.register_agent(
                        agent_id=cap.id,
                        description=cap.description,
                        capabilities=[cap.id],
                        category=cap.metadata.get("agent_type", "general"),
                    )
                except Exception:
                    logger.debug(
                        "TopologyManager: skipped agent %s (non-fatal)",
                        cap.id,
                    )
            logger.info(
                "Registered %d agents in topology manager",
                len(all_caps),
            )
        except Exception as e:
            logger.warning("TopologyManager registration skipped (non-fatal): %s", e)

        logger.info(
            "Agent capability registration complete: %d agents registered",
            registered,
        )

    except Exception as e:
        logger.warning("Failed to register agent capabilities (non-fatal): %s", e)


async def _hydrate_topology_from_db():
    """Build the in-memory topology from the latest DB snapshot.

    Tries ``topology_snapshots`` table first.  If empty, falls back to
    filesystem ``graph.json`` via ``TopologyManager.build()``.

    Phase 2.4 — topology becomes Postgres-native.
    """
    try:
        from app.database import AsyncSessionLocal
        from app.services.semantic.topology_manager import get_topology_manager

        topo = get_topology_manager()
        async with AsyncSessionLocal() as session:
            topology = await topo.build_from_db(session)

        node_count = len(topology.get("nodes", []))
        edge_count = len(topology.get("edges", []))
        logger.info("Topology hydrated: %d nodes, %d edges", node_count, edge_count)
    except Exception as e:
        logger.warning("Topology hydration from DB skipped (non-fatal): %s", e)


def _init_tool_discovery():
    """Initialize semantic tool discovery — indexes all registered tools into Qdrant."""
    try:
        from app.services.tool_discovery_service import get_discovery_service

        service = get_discovery_service()
        count = service.initialize()
        if count > 0:
            logger.info("Tool discovery initialized: %d tools indexed in Qdrant", count)
        else:
            logger.info("Tool discovery initialized (no tools in registry or Qdrant unavailable)")
    except Exception as e:
        logger.warning("Failed to initialize tool discovery (non-fatal): %s", e)


def _validate_production_secrets():
    warnings = settings.validate_secrets()
    for w in warnings:
        logger.error("SECURITY: %s", w)
    if warnings:
        raise RuntimeError(f"Refusing to start with placeholder secrets: {'; '.join(warnings)}")


def _init_langfuse():
    """Initialize the Langfuse service singleton."""
    try:
        from app.services.langfuse_service import get_langfuse_service

        service = get_langfuse_service()
        service.initialize(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            enabled=settings.LANGFUSE_ENABLED,
            sampling_rate=settings.LANGFUSE_SAMPLING_RATE,
            flush_interval=settings.LANGFUSE_FLUSH_INTERVAL,
        )

        if service.enabled:
            logger.info("Langfuse observability enabled (host=%s)", settings.LANGFUSE_HOST)
        else:
            logger.info("Langfuse observability disabled")
    except Exception as e:
        logger.warning("Failed to initialize Langfuse (non-fatal): %s", e)


def _init_litellm_callbacks():
    """Configure LiteLLM to use Langfuse callbacks when enabled."""
    try:
        from app.services.langfuse_service import get_langfuse_service

        service = get_langfuse_service()
        if not service.enabled:
            return

        import os

        # Set Langfuse env vars for LiteLLM native callback support
        # LiteLLM reads these env vars directly for its langfuse callback
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
        os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
        os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST

        import litellm

        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
        logger.info("LiteLLM Langfuse callbacks configured via env vars")
    except ImportError:
        logger.debug("LiteLLM not available for callback configuration")
    except Exception as e:
        logger.warning("Failed to configure LiteLLM callbacks (non-fatal): %s", e)


def _shutdown_langfuse():
    """Graceful Langfuse shutdown."""
    try:
        from app.services.langfuse_service import get_langfuse_service

        service = get_langfuse_service()
        service.shutdown()
    except Exception as e:
        logger.debug("Langfuse shutdown error: %s", e)


async def _seed_agent_templates():
    try:
        from app.database import AsyncSessionLocal
        from app.services.agent_service import seed_agent_templates

        async with AsyncSessionLocal() as session:
            result = await seed_agent_templates(session)
            await session.commit()
            logger.info(
                "Agent templates seeded: %d total (%d new, %d updated)",
                result["total"],
                result["new"],
                result["updated"],
            )
    except Exception as e:
        logger.warning("Failed to seed agent templates (non-fatal): %s", e)


def _register_core_tools():
    """Register core tools at startup (fatal on failure).

    Core tools (browser, topology, terminal, integration, llm, data,
    utility, external, differentiators) must load successfully — failure
    is fatal. All other tools are auto-discovered by the scanner.
    """
    try:
        from app.tools.base import get_tool_registry
        from app.tools.browser_click import BrowserClickTool
        from app.tools.browser_close import BrowserCloseTool
        from app.tools.browser_navigate import BrowserNavigateTool
        from app.tools.browser_ping import BrowserPingTool
        from app.tools.browser_screenshot import BrowserScreenshotTool
        from app.tools.browser_scroll import BrowserScrollTool
        from app.tools.browser_snapshot import BrowserSnapshotTool
        from app.tools.browser_type import BrowserTypeTool
        from app.tools.data import CsvParseTool, JsonTransformTool, RegexExtractTool
        from app.tools.differentiators import (
            BrandVoiceEnforcerTool,
            CollaborativeTeamSpaceTool,
            KnowledgeBaseConnectorTool,
            PersistentAgentMemoryTool,
            PIIRedactorTool,
            RAGContextBuilderTool,
            SemanticChunkingTool,
            SemanticMemoryIndexTool,
            SubAgentRouterTool,
            TaskPlannerTool,
        )
        from app.tools.external import CurrencyConvertTool, WeatherCurrentTool
        from app.tools.integration import ExecuteIntegrationTool, ListIntegrationsTool
        from app.tools.llm import LLMClassifyTool, LLMSummarizeTool, LLMTranslateTool
        from app.tools.terminal import TerminalTool
        from app.tools.topology import TopologyTool
        from app.tools.utility import TimestampConverterTool, UUIDGeneratorTool

        tools_to_register = [
            BrowserPingTool(),
            BrowserNavigateTool(),
            BrowserScreenshotTool(),
            BrowserCloseTool(),
            BrowserSnapshotTool(),
            BrowserClickTool(),
            BrowserTypeTool(),
            BrowserScrollTool(),
            TopologyTool(),
            TerminalTool(),
            ListIntegrationsTool(),
            ExecuteIntegrationTool(),
            LLMSummarizeTool(),
            LLMTranslateTool(),
            LLMClassifyTool(),
            JsonTransformTool(),
            CsvParseTool(),
            RegexExtractTool(),
            UUIDGeneratorTool(),
            TimestampConverterTool(),
            WeatherCurrentTool(),
            CurrencyConvertTool(),
            PersistentAgentMemoryTool(),
            SemanticMemoryIndexTool(),
            KnowledgeBaseConnectorTool(),
            BrandVoiceEnforcerTool(),
            CollaborativeTeamSpaceTool(),
            PIIRedactorTool(),
            SemanticChunkingTool(),
            SubAgentRouterTool(),
            TaskPlannerTool(),
            RAGContextBuilderTool(),
        ]

        registry = get_tool_registry()
        for tool in tools_to_register:
            registry.register(tool)
            logger.info("%s tool registered", tool.name)

        for name in [
            "browser_ping",
            "browser_navigate",
            "browser_screenshot",
            "browser_close",
            "browser_snapshot",
            "browser_click",
            "browser_type",
            "browser_scroll",
        ]:
            if registry.get(name) is None:
                raise RuntimeError(f"Browser tool not registered: {name}")
    except Exception as e:
        raise RuntimeError(f"Core tool registration failed: {e}")

    # ── Auto-discover and register ALL remaining tools ────────
    _discover_and_register_all_tools()


def _discover_and_register_all_tools() -> None:
    """Dynamically discover and import all tool modules in app/tools/.

    Scans the tools directory for .py files, excluding infrastructure
    modules (base.py, _file_utils.py, _rlimits.py, redis_cache.py).
    Each module is imported in its own try/except — module-level
    register_tool() calls handle the actual registration.

    Already-imported modules (core tools from _register_core_tools) are
    no-ops since Python caches imports.
    """
    import importlib
    from pathlib import Path

    _EXCLUDE = {
        "base.py",  # Registry infrastructure, not a tool
        "_file_utils.py",  # Utility module
        "_rlimits.py",  # Resource limit utility
        "redis_cache.py",  # Redis cache helper, not a tool
    }

    tools_dir = Path(__file__).parent / "tools"
    if not tools_dir.is_dir():
        logger.warning("Tools directory not found: %s", tools_dir)
        return

    discovered = 0
    failed = 0

    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name in _EXCLUDE:
            continue
        if py_file.name.startswith("__"):
            continue

        module_name = py_file.stem
        module_path = f"app.tools.{module_name}"

        try:
            importlib.import_module(module_path)
            discovered += 1
        except Exception as e:
            failed += 1
            logger.warning(
                "Failed to import tool module %s (non-fatal): %s",
                module_path,
                e,
            )

    logger.info(
        "Tool discovery complete: %d modules imported, %d failed",
        discovered,
        failed,
    )


async def _start_trigger_scheduler():
    """Start the trigger dispatcher.

    Always uses TriggerBridge (2s polling, H2.4).  The legacy 30s
    TriggerScheduler has been removed.  A TriggerBridge failure logs
    an error but does NOT crash application startup — cron trigger
    dispatch is non-critical.
    """
    try:
        from app.services.substrate.trigger_bridge import start_trigger_bridge

        await start_trigger_bridge()
        logger.info("TriggerBridge started (2s polling)")
    except Exception as e:
        logger.error("Failed to start TriggerBridge (trigger dispatch disabled): %s", e)


async def _stop_trigger_scheduler():
    """Stop the trigger dispatcher."""
    try:
        from app.services.substrate.trigger_bridge import stop_trigger_bridge

        await stop_trigger_bridge()
    except Exception as e:
        logger.debug("TriggerBridge stop error (non-fatal): %s", e)


def _start_playground_cleanup():
    """Start the playground sandbox cleanup background task (Phase 4)."""
    try:
        from app.tasks.playground_cleanup import start_playground_cleanup

        start_playground_cleanup()
    except Exception as e:
        logger.warning("Failed to start playground cleanup (non-fatal): %s", e)


def _stop_playground_cleanup():
    """Stop the playground sandbox cleanup background task."""
    try:
        from app.tasks.playground_cleanup import stop_playground_cleanup

        stop_playground_cleanup()
    except Exception as e:
        logger.debug("Playground cleanup stop error (non-fatal): %s", e)


async def _load_plugins():
    """Load all enabled plugins from the database on startup (Phase 9.1)."""
    try:
        from app.database import AsyncSessionLocal
        from app.services.plugin_runtime import get_plugin_runtime

        runtime = get_plugin_runtime()
        async with AsyncSessionLocal() as session:
            count = await runtime.load_installed(session)
        if count > 0:
            logger.info("Plugin runtime: %d plugin(s) loaded", count)
    except Exception as e:
        logger.warning("Failed to load plugins (non-fatal): %s", e)


async def _seed_marketplace():
    try:
        from app.database import AsyncSessionLocal
        from app.services.marketplace_service import seed_marketplace_listings

        async with AsyncSessionLocal() as session:
            result = await seed_marketplace_listings(session)
            await session.commit()
            if result.get("new"):
                logger.info("Marketplace seeded: %d listings", result["new"])
    except Exception as e:
        logger.warning("Failed to seed marketplace (non-fatal): %s", e)


def _init_sentry():
    """Initialize Sentry SDK for error tracking."""
    try:
        from app.services.sentry import init_sentry as do_init_sentry

        if not settings.SENTRY_DSN:
            logger.info("Sentry DSN not configured — error tracking disabled")
            return

        success = do_init_sentry()
        if success:
            logger.info("Sentry error tracking enabled (env=%s)", settings.SENTRY_ENVIRONMENT)
        else:
            logger.warning("Sentry initialization failed — continuing without error tracking")
    except Exception as e:
        logger.warning("Failed to initialize Sentry (non-fatal): %s", e)


def _shutdown_sentry():
    """Flush pending Sentry events before shutdown."""
    try:
        from app.services.sentry import get_sentry_integration

        integration = get_sentry_integration()
        if integration.is_initialized():
            integration.flush(timeout=5.0)
            logger.info("Sentry events flushed")
    except Exception as e:
        logger.debug("Sentry shutdown error (non-fatal): %s", e)


def _register_differentiator_stubs_to_unified():
    """Register P0 differentiator stubs in the unified_tools ToolRegistry.

    This ensures the unified_tools layer discovers these stubs so agents
    can find them via tool search/discovery APIs.
    """
    try:
        from app.services.unified_tools.tool_registry import Tool, get_tool_registry

        registry = get_tool_registry()

        stubs = [
            Tool(
                tool_id="persistent_agent_memory",
                name="Persistent Agent Memory",
                description="Save and recall context across independent agent sessions.",
                category="memory",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=10,
                tags=["memory", "agent", "persistence", "differentiator"],
            ),
            Tool(
                tool_id="semantic_memory_index",
                name="Semantic Memory Index",
                description="Auto-index unstructured conversations into retrievable knowledge graphs.",
                category="memory",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=15,
                tags=["memory", "index", "knowledge-graph", "differentiator"],
            ),
            Tool(
                tool_id="knowledge_base_connector",
                name="Knowledge Base Connector",
                description="Seamlessly connect and sync with existing FlowManner knowledge pages.",
                category="knowledge",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=10,
                tags=["knowledge", "sync", "differentiator"],
            ),
            Tool(
                tool_id="brand_voice_enforcer",
                name="Brand Voice Enforcer",
                description="Evaluate and edit text to match a custom, predefined brand style guide.",
                category="content",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=20,
                tags=["content", "brand", "style-guide", "differentiator"],
            ),
            Tool(
                tool_id="collaborative_team_space",
                name="Collaborative Team Space",
                description="A shared whiteboard memory space for multiple agents to co-edit.",
                category="agent",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=10,
                tags=["agent", "collaboration", "whiteboard", "differentiator"],
            ),
            Tool(
                tool_id="pii_redactor",
                name="PII Redactor",
                description="Automatically mask names, emails, and SSNs before sending to LLMs.",
                category="security",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=10,
                tags=["security", "privacy", "pii", "differentiator"],
            ),
            Tool(
                tool_id="semantic_chunking",
                name="Semantic Chunking",
                description="Intelligently split documents based on paragraph semantics, not character limits.",
                category="vector",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=15,
                tags=["vector", "chunking", "embeddings", "differentiator"],
            ),
            Tool(
                tool_id="sub_agent_router",
                name="Sub-Agent Router",
                description="Dynamically route tasks to specialized agent personas based on intent.",
                category="agent",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=10,
                tags=["agent", "routing", "orchestration", "differentiator"],
            ),
            Tool(
                tool_id="task_planner",
                name="Task Planner",
                description="Decompose complex user requests into a DAG of agent tasks.",
                category="agent",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=20,
                tags=["agent", "planning", "dag", "differentiator"],
            ),
            Tool(
                tool_id="rag_context_builder",
                name="RAG Context Builder",
                description="Assemble retrieved vector chunks into an optimized LLM prompt window.",
                category="knowledge",
                source_service="differentiators",
                requires_auth=True,
                timeout_seconds=10,
                tags=["rag", "context", "prompt-engineering", "differentiator"],
            ),
        ]

        for tool in stubs:
            registry.register(tool)

        logger.info(
            "Registered %d differentiator stubs in unified_tools registry",
            len(stubs),
        )

    except Exception as e:
        logger.warning(
            "Failed to register differentiator stubs in unified_tools (non-fatal): %s",
            e,
        )


async def _register_integration_capabilities():
    """Re-register all active integration connections as Nexus capabilities.

    Survives restarts: after a rebuild, all active connections are
    re-registered so agents can use them immediately.
    """
    try:
        from app.services.integration_bridge import get_integration_bridge

        bridge = get_integration_bridge()
        total = await bridge.register_all_active_connections()
        if total > 0:
            logger.info(
                "Integration bridge: re-registered %d capabilities from active connections",
                total,
            )
    except Exception as e:
        logger.warning("Failed to register integration capabilities (non-fatal): %s", e)
