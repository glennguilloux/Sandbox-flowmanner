"""
Nexus Orchestrator - Central coordination service

Enables any subsystem to request capabilities from any other.
Provides unified interface for cross-system operations.
"""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.core.llm_result import normalize_llm_result
from app.services.learning_service import get_learning_service

# Lazy import to avoid circular dependency
from ..tool_discovery_service import ToolDiscoveryService, get_discovery_service
from .capability_registry import Capability, get_capability_registry
from .distributed_executor import DistributedExecutor, get_distributed_executor

if TYPE_CHECKING:
    import asyncio

logger = logging.getLogger(__name__)


@dataclass
class OperationResult:
    """Result of a Nexus operation"""

    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: float = 0
    capabilities_used: list[str] = field(default_factory=list)
    trace_id: str | None = None


@dataclass
class ExecutionContext:
    """Context for operation execution"""

    user_id: str | None = None
    session_id: str | None = None
    conversation_id: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class NexusOrchestrator:
    """
    Central orchestrator that coordinates all subsystem operations.

    Key capabilities:
    - Capability Discovery: Every service registers what it can do
    - Cross-System Requests: Chain operations across services
    - Context Assembly: Pulls relevant context before operations
    - Execution Planning: Determines which services to invoke
    """

    def __init__(
        self,
        discovery_service: ToolDiscoveryService = None,
        distributed_mode: bool = False,
    ):
        self.registry = get_capability_registry()
        self.discovery_service = discovery_service or get_discovery_service()
        self.learning_service = get_learning_service()
        self._context_builders: dict[str, Callable] = {}
        self._execution_hooks: dict[str, list[Callable]] = {}
        self._active_operations: dict[str, asyncio.Task] = {}
        # Bug #9 fix: Add distributed execution support
        self.distributed_mode = distributed_mode
        self._distributed_executor: DistributedExecutor | None = None

    @property
    def distributed_executor(self) -> DistributedExecutor:
        """Lazily initialize distributed executor on first access."""
        if self._distributed_executor is None:
            self._distributed_executor = get_distributed_executor()
        return self._distributed_executor

    async def initialize(self):
        """Initialize the orchestrator and register default capabilities"""
        logger.info("Initializing Nexus Orchestrator...")
        await self._register_builtin_capabilities()
        logger.info(
            "Nexus Orchestrator initialized with %s capabilities",
            len(self.registry._capabilities),
        )

    async def _register_builtin_capabilities(self):
        """Register built-in system capabilities from the tools ecosystem"""
        from app.tools import get_registry

        from .capability_registry import Capability

        tool_registry = get_registry()
        registered_count = 0

        # Register all tools from the unified tool ecosystem
        for tool_name in tool_registry.list_tools():
            try:
                tool = tool_registry.get(tool_name)
                if tool:
                    # Create capability from tool
                    capability = Capability(
                        id=f"tool:{tool_name}",
                        name=tool.name if hasattr(tool, "name") else tool_name,
                        description=(tool.description if hasattr(tool, "description") else f"Execute {tool_name} tool"),
                        category="tools",
                        handler=self._create_tool_handler(tool),
                        input_schema=getattr(tool, "input_schema", {}),
                        output_schema=getattr(tool, "output_schema", {}),
                        requires_auth=False,
                        metadata={"tool_name": tool_name, "source": "builtin"},
                    )
                    self.registry.register(capability)
                    registered_count += 1
            except Exception as e:
                logger.warning("Failed to register tool %s: %s", tool_name, e)

        logger.info("Registered %s built-in tool capabilities", registered_count)

    def _create_tool_handler(self, tool):
        """Create an async handler for a tool"""

        async def tool_handler(params: dict):
            try:
                result = await tool.execute(tool.input_schema(**params), context=None)
                # Convert ToolResult to dict for compatibility
                if hasattr(result, "to_dict"):
                    return result.to_dict()
                return result
            except Exception as e:
                logger.error("Tool execution failed: %s", e)
                return {"error": str(e), "success": False}

        return tool_handler

    def register_capability(self, capability: Capability):
        """Register a new capability with the orchestrator"""
        self.registry.register(capability)
        logger.info("Registered capability: %s", capability.id)

    def register_context_builder(self, source: str, builder: Callable[[ExecutionContext], Awaitable[dict]]):
        """Register a context builder for a specific source"""
        self._context_builders[source] = builder
        logger.info("Registered context builder for: %s", source)

    async def build_context(self, ctx: ExecutionContext) -> dict[str, Any]:
        """Assemble context from all registered sources"""
        context: dict[str, Any] = {
            "user_id": ctx.user_id,
            "session_id": ctx.session_id,
            "conversation_id": ctx.conversation_id,
            "agent_id": ctx.agent_id,
            "sources": {},
            "timestamp": datetime.now(UTC).isoformat(),
        }

        for source, builder in self._context_builders.items():
            try:
                source_context = await builder(ctx)
                context["sources"][source] = source_context
            except Exception as e:
                logger.warning("Context builder %s failed: %s", source, e)
                context["sources"][source] = {"error": str(e)}

        return context

    async def execute(
        self,
        capability_id: str,
        params: dict[str, Any],
        ctx: ExecutionContext | None = None,
    ) -> OperationResult:
        """Execute a single capability.

        Bug #9 fix: Uses DistributedExecutor when distributed_mode is enabled.
        """
        start_time = datetime.now(UTC)

        try:
            capability = self.registry.get(capability_id)
            if not capability:
                return OperationResult(success=False, error=f"Capability not found: {capability_id}")

            if ctx:
                params["_context"] = await self.build_context(ctx)

            # Bug #9 fix: Use DistributedExecutor when distributed_mode is enabled
            if self.distributed_mode and self.distributed_executor.is_available():
                logger.info("Executing capability %s in distributed mode", capability_id)
                task_id = await self.distributed_executor.submit_task(
                    coro=capability.execute(params),  # type: ignore[arg-type]
                    task_name=f"capability:{capability_id}",
                    metadata={"capability_id": capability_id, "params": params},
                )
                # Wait for task completion — bounded (trust-boundary skill:
                # an autonomous loop MUST have a hard wall-clock bound; an
                # unbounded `while True:` hangs forever if the distributed
                # task is lost / never flips status).
                import asyncio

                poll_deadline_s = float(getattr(self.distributed_executor, "poll_timeout_seconds", 300) or 300)
                poll_start = datetime.now(UTC).timestamp()
                while True:
                    if datetime.now(UTC).timestamp() - poll_start > poll_deadline_s:
                        return OperationResult(
                            success=False,
                            error=f"Distributed task {task_id} poll timed out after {poll_deadline_s}s",
                        )
                    task = self.distributed_executor.get_task_status(task_id)
                    if task and task.status.value in ("success", "failure"):
                        break
                    await asyncio.sleep(0.1)

                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

                if task.status.value == "success":
                    return OperationResult(
                        success=True,
                        data=task.result,
                        execution_time_ms=execution_time,
                        capabilities_used=[capability_id],
                    )
                else:
                    return OperationResult(
                        success=False,
                        error=task.error or "Distributed execution failed",
                        execution_time_ms=execution_time,
                        capabilities_used=[capability_id],
                    )
            else:
                # Local execution (default)
                result = await capability.execute(params)

                execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

                return OperationResult(
                    success=True,
                    data=result,
                    execution_time_ms=execution_time,
                    capabilities_used=[capability_id],
                )

        except Exception as e:
            logger.error("Error executing %s: %s", capability_id, e)
            return OperationResult(success=False, error=str(e))

    async def execute_chain(
        self, operations: list[dict[str, Any]], ctx: ExecutionContext | None = None
    ) -> OperationResult:
        """Execute a chain of operations."""
        start_time = datetime.now(UTC)
        accumulated_data: dict[str, Any] = {}
        capabilities_used: list[str] = []

        for op in operations:
            capability_id = op["capability"]
            params = {**op.get("params", {}), **accumulated_data}

            result = await self.execute(capability_id, params, ctx)

            if not result.success:
                return OperationResult(
                    success=False,
                    error=f"Chain failed at {capability_id}: {result.error}",
                    capabilities_used=capabilities_used,
                )

            accumulated_data.update(result.data or {})
            capabilities_used.append(capability_id)

        execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return OperationResult(
            success=True,
            data=accumulated_data,
            execution_time_ms=execution_time,
            capabilities_used=capabilities_used,
        )

    async def plan_and_execute(self, goal: str, ctx: ExecutionContext | None = None) -> OperationResult:
        """Given a goal, determine which capabilities to invoke and execute."""
        plan = await self._create_plan_ai(goal) or await self._create_plan(goal)

        if not plan:
            return OperationResult(success=False, error=f"Could not create plan for goal: {goal}")

        return await self.execute_chain(plan, ctx)

    async def _create_plan_ai(self, goal: str) -> list[dict[str, Any]] | None:
        """Use AI-powered planning with semantic tool discovery."""
        try:
            # Inject historical learning context (Upgrade 7: Memory-Driven Planning)
            learning_context = None
            if self.learning_service:
                try:
                    learning_context = await self.learning_service.inject_into_planner_context(
                        task_description=goal, mission_type=None
                    )
                    if learning_context and learning_context.get("has_historical_data"):
                        logger.info(
                            "Injected learning context: %s",
                            learning_context.get("context_summary", "")[:100],
                        )
                except Exception as e:
                    logger.warning("Failed to inject learning context: %s", e)

            # Use ToolDiscoveryService for semantic tool selection
            if self.discovery_service:
                tool_plan = self.discovery_service.plan_for_task(goal, max_tools=10)

                if tool_plan and tool_plan.recommended_tools:
                    plan = []
                    for tool_result in tool_plan.recommended_tools:
                        tool_id = tool_result.tool.tool_id  # type: ignore[attr-defined]
                        # Map tool_id to capability format
                        capability_id = f"tool:{tool_id}"
                        plan.append(
                            {
                                "capability": capability_id,
                                "params": {"task": goal},
                                "reasoning": tool_result.match_reasons,
                                "score": tool_result.score,
                            }
                        )

                    logger.info(
                        "Semantic discovery created plan with %s tools (confidence: %.2f)",
                        len(plan),
                        tool_plan.confidence,
                    )
                    return plan

            # Fallback to LLM-based planning with ALL capabilities (no 20-tool cap)
            from ..model_router import get_model_router

            model_router = get_model_router()

            capabilities = self.registry.list_all()
            cap_descriptions = [
                f"- {cap.id}: {cap.description}"
                for cap in capabilities  # All capabilities, no cap
            ]

            system_prompt = "You are an execution planner. Given a goal and available capabilities, create a JSON execution plan. Return ONLY a JSON array of objects with capability and params keys."

            user_message = f"Goal: {goal}\n\nAvailable capabilities:\n{chr(10).join(cap_descriptions)}\n\nCreate an execution plan (JSON array only):"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            response = await model_router.route_request(
                messages=messages,
                user_id="system",
                is_admin=True,
                max_tokens=500,
                temperature=0.3,
            )

            # Normalize across router return shapes (dict vs object) and treat a
            # success=False as a failure (the previously checked "content" key
            # never appears on the model_router result, so successful calls
            # were wrongly discarded). normalize_llm_result raises on failure;
            # the outer except degrades to None per the function contract.
            content = normalize_llm_result(response, context="_create_plan_ai").strip()
            if "```" in content:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
                if match:
                    content = match.group(1).strip()

            plan = json.loads(content)
            if isinstance(plan, list):
                logger.info("AI planning created plan with %s steps", len(plan))
                return plan

            return None

        except Exception as e:
            logger.warning("AI planning failed: %s", e)
            return None

    async def _create_plan(self, goal: str) -> list[dict[str, Any]]:
        """Create an execution plan using semantic tool discovery."""
        plan = []

        # Use semantic search if discovery service available
        if self.discovery_service:
            try:
                results = self.discovery_service.search(goal, top_k=5)

                for result in results:
                    tool_id = result.tool.tool_id  # type: ignore[attr-defined]
                    capability_id = f"tool:{tool_id}"
                    plan.append(
                        {
                            "capability": capability_id,
                            "params": {"query": goal},
                            "score": result.score,
                            "reasons": result.match_reasons,
                        }
                    )

                if plan:
                    logger.info("Semantic search found %s relevant capabilities", len(plan))
                    return plan
            except Exception as e:
                logger.warning("Semantic search failed: %s", e)

        # Fallback to keyword matching
        goal_lower = goal.lower()

        if ("search" in goal_lower or "find" in goal_lower) and ("knowledge" in goal_lower or "document" in goal_lower):
            plan.append({"capability": "tool:search_knowledge", "params": {"query": goal}})

        if "agent" in goal_lower or "execute" in goal_lower:
            plan.append({"capability": "tool:spawn_agent", "params": {"task": goal}})

        if "web" in goal_lower or "browse" in goal_lower:
            plan.append({"capability": "tool:research", "params": {"query": goal}})

        return plan

    async def semantic_capability_search(
        self,
        query: str,
        top_k: int = 5,
        tier_filter: list[int] | None = None,
        category_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search over capabilities using ToolDiscoveryService.

        Args:
            query: Natural language query
            top_k: Maximum results
            tier_filter: Optional tier filter (1-4)
            category_filter: Optional category filter

        Returns:
            List of capability matches with scores
        """
        if not self.discovery_service:
            return []

        results = self.discovery_service.search(
            query, top_k=top_k, tier_filter=tier_filter, category_filter=category_filter
        )

        return [
            {
                "capability_id": f"tool:{r.tool.tool_id}",  # type: ignore[attr-defined]
                "name": r.tool.name,  # type: ignore[attr-defined]
                "description": r.tool.description,  # type: ignore[attr-defined]
                "tier": r.tool.tier,  # type: ignore[attr-defined]
                "category": r.tool.category,  # type: ignore[attr-defined]
                "score": r.score,
                "match_reasons": r.match_reasons,
            }
            for r in results
        ]

    def list_capabilities(self, category: str | None = None) -> list[Capability]:
        """List all registered capabilities, optionally filtered by category"""
        return self.registry.list_all(category)

    def get_capability_info(self, capability_id: str) -> dict[str, Any] | None:
        """Get detailed information about a capability"""
        cap = self.registry.get(capability_id)
        if cap:
            return {
                "id": cap.id,
                "name": cap.name,
                "description": cap.description,
                "category": cap.category,
                "input_schema": cap.input_schema,
                "output_schema": cap.output_schema,
                "requires_auth": cap.requires_auth,
                "cost_estimate": cap.cost_estimate,
            }
        return None


# ── Global orchestrator singleton ──────────────────────────────────

_nexus_orchestrator: NexusOrchestrator | None = None


def get_nexus_orchestrator(distributed_mode: bool = False) -> NexusOrchestrator:
    """Get or create the global Nexus orchestrator instance.

    Args:
        distributed_mode: If True, use DistributedExecutor for capability execution.
    """
    global _nexus_orchestrator
    if _nexus_orchestrator is None:
        _nexus_orchestrator = NexusOrchestrator(distributed_mode=distributed_mode)
    return _nexus_orchestrator
