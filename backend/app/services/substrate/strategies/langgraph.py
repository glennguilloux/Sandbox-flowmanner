"""LangGraphStrategy — native LangGraph integration (H5.1).

Replaces: langgraph/agent.py orchestration (~250 lines → ~100 lines of strategy code).

Preserves: langgraph/ tool handlers, approval workflow, persistence, etc.

The substrate event log is the source of truth for workflow-level state.
LangGraph's checkpointer manages intra-node state only (StateGraph's
internal message history and tool execution state).

Boundary:
- Workflow-level: substrate events → ReplayEngine
- Node-level (LangGraph): LangGraph checkpointer → MemorySaver/Redis
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.services.substrate.strategies.base import ExecutionStrategy
from app.services.substrate.workflow_models import (
    StrategyResult,
    Workflow,
    WorkflowType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.substrate.executor import UnifiedExecutor

logger = logging.getLogger(__name__)


class LangGraphStrategy(ExecutionStrategy):
    DEPRECATED = True  # 0% success with 27B model per strategy profiling 2026-07-04
    EXPERIMENTAL = True
    """Native LangGraph integration strategy."""

    def can_handle(self, workflow_type: WorkflowType) -> bool:
        return workflow_type == WorkflowType.LANGGRAPH

    async def validate(self, workflow: Workflow) -> list[str]:
        errors: list[str] = []

        if not workflow.nodes:
            errors.append("LangGraph workflow must have at least 1 node")

        for node in workflow.nodes:
            graph_name = node.config.get("graph_name")
            if not graph_name:
                errors.append(f"LangGraph node '{node.id}' missing 'graph_name' in config")

        return errors

    async def execute(  # type: ignore[override]
        self,
        workflow: Workflow,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
        run_id: str,
    ) -> StrategyResult:
        completed = []
        failed = []
        total_tokens = 0
        total_cost = 0.0

        for node in workflow.nodes:
            if executor.is_aborted(run_id):
                return StrategyResult(success=False, status="aborted", error="Aborted")

            # Try native LangGraph execution first
            result = await self._execute_langgraph_node(node, context, executor, db, run_id, workflow)

            if result.get("success"):
                completed.append(node.id)
                total_tokens += result.get("tokens", 0)
                total_cost += result.get("cost", 0.0)
            else:
                # Fallback: execute through the shared node executor
                fallback_result = await executor.execute_node(
                    db=db,
                    node=node,
                    context=context,
                    budget=workflow.budget,
                    run_id=run_id,
                    workflow=workflow,
                )
                if fallback_result.get("success"):
                    completed.append(node.id)
                    total_tokens += fallback_result.get("tokens", 0)
                    total_cost += fallback_result.get("cost", 0.0)
                else:
                    failed.append(node.id)

        return StrategyResult(
            success=len(failed) == 0,
            status="completed" if not failed else "failed",
            completed_nodes=completed,
            failed_nodes=failed,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
            error=f"{len(failed)} nodes failed" if failed else None,
        )

    # ── Graph registry (lazy-loaded) ─────────────────────────────────────────
    _GRAPH_REGISTRY: dict[str, Any] = {}

    async def _get_graph(self, graph_name: str) -> Any | None:
        """Resolve a graph by name from the registry.

        Supports:
        - ``governance`` — the ControlFlow governance agent graph
        - ``llm:*`` — any graph registered in llm_langgraph agent registry
        - Direct graph names — looked up in the llm_langgraph agent registry

        Returns the compiled LangGraph graph, or ``None`` if not found.
        """
        if graph_name in self._GRAPH_REGISTRY:
            return self._GRAPH_REGISTRY[graph_name]

        graph = None
        try:
            if graph_name == "governance":
                from app.governance.controlflow.agent import get_agent

                agent = get_agent()
                graph = agent.graph  # type: ignore[assignment]
            else:
                from app.services.llm_langgraph.agent import get_agent as get_llm_agent

                agent = get_llm_agent()  # type: ignore[assignment]
                if hasattr(agent, "get_graph"):
                    graph = agent.get_graph(graph_name)
                elif hasattr(agent, "graph"):
                    graph = agent.graph
        except Exception as e:
            logger.debug("Failed to resolve graph '%s': %s", graph_name, e)
            return None

        if graph is not None:
            self._GRAPH_REGISTRY[graph_name] = graph
        return graph

    async def _execute_langgraph_node(
        self,
        node: Any,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
        run_id: str,
        workflow: Workflow,
    ) -> dict[str, Any]:
        """Execute a LangGraph node natively via the graph registry.

        Looks up the graph by ``node.config['graph_name']`` and invokes
        it with ``ainvoke()``.  Returns an error dict if the graph is
        not found or invocation fails — the caller (``execute``) falls
        back to the shared node executor in that case.
        """
        try:
            graph_name = node.config.get("graph_name", "unknown")
            graph = await self._get_graph(graph_name)
            if graph is None:
                return {
                    "success": False,
                    "error": f"Graph '{graph_name}' not found — using shared executor",
                }

            # Invoke the graph natively
            result = await graph.ainvoke(
                {"messages": [{"role": "user", "content": node.input or ""}]},
                config={"configurable": {"thread_id": f"substrate_{run_id}_{node.id}"}},
            )

            return {
                "success": True,
                "result": result,
                "tokens": 0,
                "cost": 0.0,
            }
        except Exception as e:
            logger.warning("LangGraph native execution failed for node %s: %s", node.id, e)
            return {"success": False, "error": str(e)}
