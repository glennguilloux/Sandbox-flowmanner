"""GraphStrategy — conditional edges + context interpolation (H5.1).

Replaces: graph_executor.py (293 lines → ~120 lines of strategy code).

Supports:
- Conditional edges: edge.condition is evaluated at runtime
- Context interpolation: {{node_id.output.field}} references
- Subgraph execution: start_node_id filters to a subgraph
"""

from __future__ import annotations

import asyncio
import logging
import re
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


class GraphStrategy(ExecutionStrategy):
    """Graph workflow strategy — conditional edges + context interpolation."""

    def can_handle(self, workflow_type: WorkflowType) -> bool:
        return workflow_type == WorkflowType.GRAPH

    async def validate(self, workflow: Workflow) -> list[str]:
        errors: list[str] = []
        node_ids = {n.id for n in workflow.nodes}

        if not workflow.nodes:
            errors.append("Graph workflow must have at least 1 node")

        for edge in workflow.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge source '{edge.source}' not found")  # noqa: PERF401

        return errors

    async def execute(
        self,
        workflow: Workflow,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
        run_id: str,
    ) -> StrategyResult:
        start_node_id = context.get("start_node_id")

        active_ids = (
            self._get_subgraph_ids(workflow, start_node_id) if start_node_id else {n.id for n in workflow.nodes}
        )
        active_edges = [e for e in workflow.edges if e.source in active_ids and e.target in active_ids]
        layers = self._topological_sort_for_ids(workflow, active_ids, active_edges)

        completed_nodes: list[str] = []
        failed_nodes: list[str] = []
        total_tokens = 0
        total_cost = 0.0
        node_outputs: dict[str, Any] = {**context.get("previous_outputs", {})}

        for layer in layers:
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

            executable = []
            for nid in layer:
                incoming = [e for e in active_edges if e.target == nid]
                if all(self._evaluate_condition(e, node_outputs) for e in incoming):
                    executable.append(nid)

            tasks = [
                executor.execute_node(
                    db=db,
                    node=workflow.node_map[nid],
                    context={**context, "previous_outputs": node_outputs},
                    budget=workflow.budget,
                    run_id=run_id,
                    workflow=workflow,
                )
                for nid in executable
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for nid, result in zip(executable, results, strict=False):
                if isinstance(result, Exception):
                    failed_nodes.append(nid)
                    node_outputs[nid] = {"error": str(result)}
                elif result.get("success"):
                    completed_nodes.append(nid)
                    total_tokens += result.get("tokens", 0)
                    total_cost += result.get("cost", 0.0)
                    node_outputs[nid] = result.get("output", {})
                    if isinstance(result.get("output"), dict) and result["output"].get("pause"):
                        return StrategyResult(
                            success=False,
                            status="paused",
                            data=node_outputs,
                            completed_nodes=completed_nodes,
                            failed_nodes=failed_nodes,
                            total_tokens=total_tokens,
                            total_cost_usd=total_cost,
                        )
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

    def _get_subgraph_ids(self, workflow: Workflow, start_id: str) -> set[str]:
        result: set[str] = set()
        if start_id not in workflow.node_map:
            return result
        queue = [start_id]
        while queue:
            current = queue.pop(0)
            if current in result:
                continue
            result.add(current)
            for edge in workflow.dependency_map.get(current, []):
                queue.append(edge.target)
        return result

    def _evaluate_condition(self, edge, node_outputs: dict[str, Any]) -> bool:
        if not edge.condition:
            return True
        try:
            resolved = self._resolve_interpolation(edge.condition, node_outputs)
            if isinstance(resolved, bool):
                return resolved
            if isinstance(resolved, str):
                return resolved.strip().lower() in ("true", "success", "completed")
            return bool(resolved)
        except Exception:
            return True

    def _resolve_interpolation(self, template: str, outputs: dict[str, Any]) -> Any:
        if not isinstance(template, str) or "{{" not in template:
            return template
        pattern = r"\{\{([^}]+)\}\}"
        matches = list(re.finditer(pattern, template))
        if len(matches) == 1 and matches[0].group(0) == template.strip():
            return self._resolve_ref(matches[0].group(1).strip(), outputs)
        result = template
        for m in matches:
            ref = m.group(1).strip()
            val = self._resolve_ref(ref, outputs)
            result = result.replace(m.group(0), str(val) if val is not None else "")
        return result

    def _resolve_ref(self, ref: str, outputs: dict[str, Any]) -> Any:
        parts = ref.split(".")
        node_id = parts[0]
        if node_id in outputs:
            obj = outputs[node_id]
            for part in parts[1:]:
                if isinstance(obj, dict):
                    obj = obj.get(part)
                else:
                    return None
            return obj
        return None

    def _topological_sort_for_ids(self, workflow: Workflow, node_ids: set[str], edges: list) -> list[list[str]]:
        in_deg: dict[str, int] = dict.fromkeys(node_ids, 0)
        deps: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in edges:
            in_deg[edge.target] = in_deg.get(edge.target, 0) + 1
            deps.setdefault(edge.source, []).append(edge.target)

        queue = [nid for nid, deg in in_deg.items() if deg == 0]
        layers: list[list[str]] = []
        visited = 0

        while queue:
            layers.append(list(queue))
            visited += len(queue)
            next_queue = []
            for nid in queue:
                for dep in deps.get(nid, []):
                    in_deg[dep] -= 1
                    if in_deg[dep] == 0:
                        next_queue.append(dep)
            queue = next_queue

        return layers
