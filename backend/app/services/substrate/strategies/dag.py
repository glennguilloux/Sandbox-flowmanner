"""DAGStrategy — dependency-ordered parallel execution (H5.1).

Replaces: dag_executor.py (179 lines → ~80 lines of strategy code).

Uses Kahn's algorithm for topological sort, executing nodes in
parallel within each layer.  Layer 0 runs first, layer N only after
all nodes in layers 0..N-1 complete.
"""

from __future__ import annotations

import asyncio
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


class DAGStrategy(ExecutionStrategy):
    """DAG workflow strategy — topological sort + layer-parallel execution."""

    def can_handle(self, workflow_type: WorkflowType) -> bool:
        return workflow_type == WorkflowType.DAG

    async def validate(self, workflow: Workflow) -> list[str]:
        errors: list[str] = []
        node_ids = {n.id for n in workflow.nodes}

        if not workflow.nodes:
            errors.append("DAG workflow must have at least 1 node")

        for edge in workflow.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge source '{edge.source}' not found in nodes")
            if edge.target not in node_ids:
                errors.append(f"Edge target '{edge.target}' not found in nodes")

        if self._has_cycle(workflow):
            errors.append("DAG contains a cycle")

        return errors

    async def execute(
        self,
        workflow: Workflow,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
        run_id: str,
    ) -> StrategyResult:
        layers = self._topological_sort(workflow)

        completed_nodes: list[str] = []
        failed_nodes: list[str] = []
        total_tokens = 0
        total_cost = 0.0
        node_outputs: dict[str, Any] = {}

        for layer in layers:
            # Check abort signal between layers
            if executor.is_aborted(run_id):
                return StrategyResult(
                    success=False,
                    status="aborted",
                    error="Aborted",
                    completed_nodes=completed_nodes,
                    failed_nodes=failed_nodes,
                    total_tokens=total_tokens,
                    total_cost_usd=total_cost,
                )

            tasks = [
                executor.execute_node(
                    db=db,
                    node=workflow.node_map[nid],
                    context={**context, "previous_outputs": node_outputs},
                    budget=workflow.budget,
                    run_id=run_id,
                    workflow=workflow,
                )
                for nid in layer
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            from app.services.substrate.hitl_pause import HITLPaused

            for nid, result in zip(layer, results, strict=False):
                if isinstance(result, Exception):
                    # Q1-B chunk 1: Propagate HITLPaused — don't treat as failure
                    if isinstance(result, HITLPaused):
                        raise result
                    failed_nodes.append(nid)
                    node_outputs[nid] = {"error": str(result)}
                elif result.get("success"):
                    completed_nodes.append(nid)
                    total_tokens += result.get("tokens", 0)
                    total_cost += result.get("cost", 0.0)
                    node_outputs[nid] = result.get("output", {})
                else:
                    failed_nodes.append(nid)
                    node_outputs[nid] = {"error": result.get("error")}

        return StrategyResult(
            success=len(failed_nodes) == 0,
            status="completed" if not failed_nodes else "failed",
            data=node_outputs,
            error=f"{len(failed_nodes)} nodes failed" if failed_nodes else None,
            completed_nodes=completed_nodes,
            failed_nodes=failed_nodes,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
        )

    def _topological_sort(self, workflow: Workflow) -> list[list[str]]:
        """Kahn's algorithm: return execution layers."""
        in_deg = workflow.get_in_degree()

        queue = [nid for nid, deg in in_deg.items() if deg == 0]
        layers: list[list[str]] = []
        visited = 0

        while queue:
            layers.append(list(queue))
            visited += len(queue)
            next_queue = []
            for nid in queue:
                for edge in workflow.dependency_map.get(nid, []):
                    in_deg[edge.target] -= 1
                    if in_deg[edge.target] == 0:
                        next_queue.append(edge.target)
            queue = next_queue

        if visited != len(workflow.nodes):
            raise ValueError("DAG contains a cycle")

        return layers

    def _has_cycle(self, workflow: Workflow) -> bool:
        """Check for cycles using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        node_ids = {n.id for n in workflow.nodes}
        color: dict[str, int] = {n.id: WHITE for n in workflow.nodes}
        adj: dict[str, list[str]] = {n.id: [] for n in workflow.nodes}
        for e in workflow.edges:
            # Skip edges that reference non-existent nodes (caught by validate)
            if e.source in node_ids and e.target in node_ids:
                adj[e.source].append(e.target)

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for neighbor in adj[node]:
                if color[neighbor] == GRAY:
                    return True
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        return any(color[nid] == WHITE and dfs(nid) for nid in color)
