# Graph Report - flowmanner-backend  (2026-04-08)

## Corpus Check
- 144 files · ~63,433 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2059 nodes · 4152 edges · 75 communities detected
- Extraction: 52% EXTRACTED · 48% INFERRED · 0% AMBIGUOUS · INFERRED: 1978 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `BaseTool` - 209 edges
2. `ToolResult` - 206 edges
3. `ToolInput` - 205 edges
4. `Capability` - 125 edges
5. `LearningPattern` - 66 edges
6. `CapabilityRegistry` - 41 edges
7. `MarketplaceListingModel` - 41 edges
8. `MarketplaceCategoryModel` - 41 edges
9. `MarketplaceReviewModel` - 41 edges
10. `UserInstallationModel` - 41 edges
11. `AIAgent` - 40 edges
12. `ToolDiscoveryService` - 39 edges
13. `FailureAnalyzer` - 38 edges
14. `DistributedExecutor` - 37 edges
15. `ComposedCapabilityModel` - 37 edges
16. `MarketplaceService` - 33 edges
17. `NexusOrchestrator` - 32 edges
18. `CapabilityComposer` - 28 edges
19. `AgentRegistration` - 28 edges
20. `LearningService` - 25 edges

## Surprising Connections (you probably didn't know these)
- `Main service combining embedding and planning capabilities.     Integrates with` --uses--> `LearningPattern`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/services/tool_discovery_service.py → /mnt/workflows/workflows/apps/backend/app/models/feedback_models.py
- `Generate tool execution plan` --uses--> `LearningPattern`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/services/tool_discovery_service.py → /mnt/workflows/workflows/apps/backend/app/models/feedback_models.py
- `Alias for plan() - used by MetaLoopAgent.         Includes query preprocessing (` --uses--> `LearningPattern`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/services/tool_discovery_service.py → /mnt/workflows/workflows/apps/backend/app/models/feedback_models.py
- `Get performance metrics for a specific tool.          Args:             tool_id:` --uses--> `LearningPattern`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/services/tool_discovery_service.py → /mnt/workflows/workflows/apps/backend/app/models/feedback_models.py
- `Apply learned patterns from LearningPattern DB to tool rankings.         Queries` --uses--> `LearningPattern`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/services/tool_discovery_service.py → /mnt/workflows/workflows/apps/backend/app/models/feedback_models.py
- `Pydantic schemas for API request/response validation.` --uses--> `Capability`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/schemas/__init__.py → /mnt/workflows/workflows/apps/backend/app/services/nexus/capability_registry.py
- `Pydantic schemas for API request/response validation.` --uses--> `CapabilityRegistry`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/schemas/__init__.py → /mnt/workflows/workflows/apps/backend/app/services/nexus/capability_registry.py
- `Pydantic schemas for API request/response validation.` --uses--> `NexusOrchestrator`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/schemas/__init__.py → /mnt/workflows/workflows/apps/backend/app/services/nexus/orchestrator.py
- `HealthCheckTool` --uses--> `BaseTool`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/tools/health_check.py → /mnt/workflows/workflows/apps/backend/app/tools/base.py
- `HealthCheckTool` --uses--> `ToolInput`  [INFERRED]
  /mnt/workflows/workflows/apps/backend/app/tools/health_check.py → /mnt/workflows/workflows/apps/backend/app/tools/base.py

## Communities

### Community 0 - "BaseTool"
Cohesion: 0.02
Nodes (212): AgentHandoffInput, AgentHandoffTool, Agent Handoff Tool (Tier 3)  Orchestration on data models: - Transfers context b, Get agent from registry, Input schema for agent_handoff tool, Get conversation history from agent, Get memories from agent, Get working context from agent (+204 more)

### Community 1 - "BaseModel"
Cohesion: 0.02
Nodes (193): AgentCreate, AgentResponse, AgentTemplateCreate, AgentTemplateResponse, AgentTemplateUpdate, AgentUpdate, Config, delete_item() (+185 more)

### Community 2 - "Capability"
Cohesion: 0.04
Nodes (113): AgentCategory, AgentMemoryConfig, AgentModelConfig, AgentTemplate, AgentToolConfig, get_featured_templates(), get_template_by_id(), get_templates_by_category() (+105 more)

### Community 3 - "ToolDiscoveryService"
Cohesion: 0.03
Nodes (102): DistributedExecutor, DistributedTask, ExecutionDAG, get_distributed_executor(), initialize_worker_capabilities(), NexusCeleryTasks, Distributed Executor - Celery-based Distributed Task Execution  Enables distribu, Directed Acyclic Graph for execution planning (+94 more)

### Community 4 - "Base"
Cohesion: 0.01
Nodes (29): ABC, Agent, AgentTemplate, Base, error(), execute(), get(), get_openai_schemas() (+21 more)

### Community 5 - "LearningPattern"
Cohesion: 0.03
Nodes (66): LearningPattern, MissionAnalytics, Feedback and learning pattern models., get_learning_service(), get_pattern_embedding_service(), LearningService, PatternEmbeddingService, Service for extracting and applying learning patterns with semantic search. (+58 more)

### Community 6 - "Span"
Cohesion: 0.03
Nodes (61): ErrorRecord, get_observability_service(), Metric, ObservabilityService, PerformanceStats, Observability & Tracing - Distributed tracing and performance monitoring  Provid, Convert span to dictionary, Complete trace with all spans (+53 more)

### Community 7 - "CapabilityRegistry"
Cohesion: 0.04
Nodes (44): AgentCapability, AgentCapabilityRegistrar, AgentRegistration, Agent Capability Registrar - Self-Registering Agents System  UPGRADE 6: Self-Reg, Lazy-load capability registry, Lazy-load tool discovery service, Register an agent with auto-discovered tools and capabilities.          Args:, Discover relevant tools for an agent based on type and filters.          Uses To (+36 more)

### Community 8 - "ToolVersioningService"
Cohesion: 0.04
Nodes (36): DeprecationNotice, get_versioning_service(), Migration, parse(), Tool Versioning System - Semantic versioning and lifecycle management for tools, Bump major version (breaking changes), Bump minor version (new features), Bump patch version (bug fixes) (+28 more)

### Community 9 - "CostOptimizer"
Cohesion: 0.04
Nodes (34): Budget, CostEstimate, CostOptimizer, get_cost_optimizer(), ModelPricing, OptimizationRecommendation, PricingModel, Cost Optimization Engine - Token tracking and budget management  Provides compre (+26 more)

### Community 10 - "flow.py"
Cohesion: 0.05
Nodes (45): DeclarativeBase, Config, create_run(), create_step(), delete_item(), FlowRunCreate, FlowRunResponse, FlowStepCreate (+37 more)

### Community 11 - "SecurityService"
Cohesion: 0.06
Nodes (22): AuditEvent, AuditEventType, get_security_service(), Permission, PermissionSet, RateLimitRule, RateLimitState, Security Hardening - Input validation, rate limiting, and audit logging  Provide (+14 more)

### Community 12 - "ChainExecutionEngine"
Cohesion: 0.08
Nodes (30): ChainExecutionEngine, _filter_gather_results(), Agent Chain Service - Chain Execution Engine  Executes multi-step agent chains w, Execute a single chain step., Execute sub-steps in parallel with resilient error handling., Execute a single step sequentially., Execute a single atomic step (tool call, agent spawn, etc.)., Executes predefined agent chains with resilient parallel execution.      Prevent (+22 more)

### Community 13 - "ExecutionDAG"
Cohesion: 0.07
Nodes (29): DAGStep, ExecutionDAG, Execution DAG Engine - DAG execution with per-step timeout enforcement.  Prevent, Return the status dict for a given step., A single step in the execution DAG., DAG execution engine with per-step timeout enforcement.      Each step is wrappe, Add a step to the DAG., Return step IDs in topological order using Kahn's algorithm (BFS with in-degree (+21 more)

### Community 14 - "TopologyManager"
Cohesion: 0.11
Nodes (19): AIExecutionPlanner, ExecutionPlan, ExecutionStep, get_ai_execution_planner(), AI-Powered Execution Planner - Semantic matching for intelligent agent selection, Setup default planning rules as fallback, Register an agent for semantic matching, Create an execution plan using semantic matching.          Args:             goa (+11 more)

### Community 15 - "auth_service.py"
Cohesion: 0.1
Nodes (16): create_user(), hash_password(), Authentication service - JWT tokens, password hashing, user management., RefreshToken, store_refresh_token(), list_models(), list_providers(), ModelInfo (+8 more)

### Community 16 - "ContextBuilder"
Cohesion: 0.09
Nodes (14): ContextBuilder, ContextSource, Context Builder - Assembles context from multiple sources  Pulls relevant contex, Fetch context from a single source, Assemble context string from all source data, Score how relevant the context is to the query, Enable a context source, Disable a context source (+6 more)

### Community 17 - "ExecutionPlanner"
Cohesion: 0.1
Nodes (14): ExecutionPlan, ExecutionPlanner, ExecutionStep, Execution Planner - Plans multi-step operations across systems  Given a goal, de, Add a custom planning rule, Create an execution plan for a goal.          Args:             goal: Natural la, A single step in an execution plan, Add dependencies between steps based on capability types (+6 more)

### Community 18 - "OrchestratePipelineTool"
Cohesion: 0.2
Nodes (1): OrchestratePipelineTool

### Community 19 - "MemoryService"
Cohesion: 0.16
Nodes (9): get_memory_integration(), MemoryIntegration, Extract key information from a conversation.          Uses heuristics to identif, Integrates long-term memory into chat sessions.      Features:     - Injects rel, Get or create memory integration instance, Get or create memory service instance, Inject relevant memories into the conversation context.          Item 7: Memory, Extract important information from conversation and store as memories. (+1 more)

### Community 20 - "HealthCheckTool"
Cohesion: 0.19
Nodes (2): HealthCheckTool, Health Check Tool (Tier 4)

### Community 21 - "orchestration.py"
Cohesion: 0.15
Nodes (0): 

### Community 22 - "mission_service.py"
Cohesion: 0.17
Nodes (0): 

### Community 23 - "chat_service.py"
Cohesion: 0.17
Nodes (0): 

### Community 24 - "swarm_service.py"
Cohesion: 0.17
Nodes (0): 

### Community 25 - "graph_service.py"
Cohesion: 0.18
Nodes (0): 

### Community 26 - "agent_service.py"
Cohesion: 0.2
Nodes (0): 

### Community 27 - "flow_service.py"
Cohesion: 0.2
Nodes (0): 

### Community 28 - "workflow_service.py"
Cohesion: 0.2
Nodes (0): 

### Community 29 - "webhooks.py"
Cohesion: 0.2
Nodes (0): 

### Community 30 - "llm_advanced.py"
Cohesion: 0.2
Nodes (0): 

### Community 31 - "agent_memory_service.py"
Cohesion: 0.22
Nodes (0): 

### Community 32 - "EchoTool"
Cohesion: 0.29
Nodes (2): EchoTool, test_create_tool_handler_uses_tool_input_schema_and_returns_dict()

### Community 33 - "ApiCompatibilityMiddleware"
Cohesion: 0.29
Nodes (3): BaseHTTPMiddleware, ApiCompatibilityMiddleware, MetricsMiddleware

### Community 34 - "analytics.py"
Cohesion: 0.29
Nodes (0): 

### Community 35 - "community.py"
Cohesion: 0.29
Nodes (0): 

### Community 36 - "memory.py"
Cohesion: 0.29
Nodes (0): 

### Community 37 - "agent_tool_service.py"
Cohesion: 0.33
Nodes (0): 

### Community 38 - "file_service.py"
Cohesion: 0.33
Nodes (0): 

### Community 39 - "main_fastapi.py"
Cohesion: 0.4
Nodes (0): 

### Community 40 - "mission_analytics.py"
Cohesion: 0.4
Nodes (0): 

### Community 41 - "api_keys.py"
Cohesion: 0.4
Nodes (0): 

### Community 42 - "config.py"
Cohesion: 0.5
Nodes (2): BaseSettings, Settings

### Community 43 - "agent_execution_service.py"
Cohesion: 0.5
Nodes (0): 

### Community 44 - "SelfImprovementEngine"
Cohesion: 0.5
Nodes (1): SelfImprovementEngine

### Community 45 - "domain_agents.py"
Cohesion: 0.5
Nodes (0): 

### Community 46 - "get_db()"
Cohesion: 0.67
Nodes (2): get_db(), FastAPI dependency that yields an async database session.

### Community 47 - "websocket_manager.py"
Cohesion: 0.67
Nodes (0): 

### Community 48 - "MissionExecutor"
Cohesion: 0.67
Nodes (1): MissionExecutor

### Community 49 - "AppError"
Cohesion: 0.67
Nodes (2): Exception, AppError

### Community 50 - "rag_compat.py"
Cohesion: 0.67
Nodes (0): 

### Community 51 - "lifespan.py"
Cohesion: 1.0
Nodes (0): 

### Community 52 - "deps.py"
Cohesion: 1.0
Nodes (0): 

### Community 53 - "flow_compat.py"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Lazy load the search service"
Cohesion: 1.0
Nodes (1): Lazy load the search service

### Community 55 - "Unique tool identifier"
Cohesion: 1.0
Nodes (1): Unique tool identifier

### Community 56 - "Human-readable tool description"
Cohesion: 1.0
Nodes (1): Human-readable tool description

### Community 57 - "Pydantic model for input validation"
Cohesion: 1.0
Nodes (1): Pydantic model for input validation

### Community 58 - "Optional JSON schema for output validation"
Cohesion: 1.0
Nodes (1): Optional JSON schema for output validation

### Community 59 - "Whether tool requires authentication"
Cohesion: 1.0
Nodes (1): Whether tool requires authentication

### Community 60 - "Default timeout for tool execution"
Cohesion: 1.0
Nodes (1): Default timeout for tool execution

### Community 61 - "Tags for tool categorization"
Cohesion: 1.0
Nodes (1): Tags for tool categorization

### Community 62 - "Execute the tool with validated input.          Args:             input_data: Va"
Cohesion: 1.0
Nodes (1): Execute the tool with validated input.          Args:             input_data: Va

### Community 63 - "Register a tool instance"
Cohesion: 1.0
Nodes (1): Register a tool instance

### Community 64 - "List all registered tool names, optionally filtered by tags"
Cohesion: 1.0
Nodes (1): List all registered tool names, optionally filtered by tags

### Community 65 - "Get full tool metadata as dict"
Cohesion: 1.0
Nodes (1): Get full tool metadata as dict

### Community 66 - "List all registered tools with full metadata (legacy behavior)"
Cohesion: 1.0
Nodes (1): List all registered tools with full metadata (legacy behavior)

### Community 67 - "Get OpenAI function schemas for all tools"
Cohesion: 1.0
Nodes (1): Get OpenAI function schemas for all tools

### Community 68 - "Execute a tool by name"
Cohesion: 1.0
Nodes (1): Execute a tool by name

### Community 69 - "rag_service.py"
Cohesion: 1.0
Nodes (0): 

### Community 70 - "Context manager for tracing an operation.          Usage:             async with"
Cohesion: 1.0
Nodes (1): Context manager for tracing an operation.          Usage:             async with

### Community 71 - "Register all Nexus tasks with Celery"
Cohesion: 1.0
Nodes (1): Register all Nexus tasks with Celery

### Community 72 - "Parse version string like '1.2.3' or '1.2.3-beta+build"
Cohesion: 1.0
Nodes (1): Parse version string like '1.2.3' or '1.2.3-beta+build

### Community 73 - "celery_app.py"
Cohesion: 1.0
Nodes (0): 

### Community 74 - "mission_ws.py"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **259 isolated node(s):** `FastAPI dependency that yields an async database session.`, `Health Check Tool (Tier 4)`, `Get Config Tool (Tier 4)`, `Monitor Performance Tool (Tier 4)`, `Web Search Tool for AI Agents Provides autonomous web search capability with int` (+254 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `lifespan.py`** (2 nodes): `lifespan.py`, `lifespan()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `deps.py`** (2 nodes): `deps.py`, `get_current_user()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `flow_compat.py`** (2 nodes): `flow_compat.py`, `get_flow_runs()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Lazy load the search service`** (1 nodes): `Lazy load the search service`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Unique tool identifier`** (1 nodes): `Unique tool identifier`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Human-readable tool description`** (1 nodes): `Human-readable tool description`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Pydantic model for input validation`** (1 nodes): `Pydantic model for input validation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Optional JSON schema for output validation`** (1 nodes): `Optional JSON schema for output validation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Whether tool requires authentication`** (1 nodes): `Whether tool requires authentication`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Default timeout for tool execution`** (1 nodes): `Default timeout for tool execution`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Tags for tool categorization`** (1 nodes): `Tags for tool categorization`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Execute the tool with validated input.          Args:             input_data: Va`** (1 nodes): `Execute the tool with validated input.          Args:             input_data: Va`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Register a tool instance`** (1 nodes): `Register a tool instance`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `List all registered tool names, optionally filtered by tags`** (1 nodes): `List all registered tool names, optionally filtered by tags`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Get full tool metadata as dict`** (1 nodes): `Get full tool metadata as dict`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `List all registered tools with full metadata (legacy behavior)`** (1 nodes): `List all registered tools with full metadata (legacy behavior)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Get OpenAI function schemas for all tools`** (1 nodes): `Get OpenAI function schemas for all tools`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Execute a tool by name`** (1 nodes): `Execute a tool by name`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `rag_service.py`** (1 nodes): `rag_service.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Context manager for tracing an operation.          Usage:             async with`** (1 nodes): `Context manager for tracing an operation.          Usage:             async with`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Register all Nexus tasks with Celery`** (1 nodes): `Register all Nexus tasks with Celery`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Parse version string like '1.2.3' or '1.2.3-beta+build`** (1 nodes): `Parse version string like '1.2.3' or '1.2.3-beta+build`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `celery_app.py`** (1 nodes): `celery_app.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `mission_ws.py`** (1 nodes): `mission_ws.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.