"""DAGStrategy — dependency-ordered parallel execution (H5.1).

Replaces: dag_executor.py (179 lines → ~80 lines of strategy code).

Uses Kahn's algorithm for topological sort, executing nodes in
parallel within each layer.  Layer 0 runs first, layer N only after
all nodes in layers 0..N-1 complete.

Scope B additions (Finding 3 / Feature variant):
- CONDITION nodes evaluate their boolean expression via the shared
  ``_safe_eval`` helper (node_executor) and the strategy gates the
  branch: a downstream edge originating at a CONDITION node is taken
  only when its ``edge.condition`` ("true"/"false") matches the
  evaluated boolean. validate() stays satisfied because every branch
  edge references a real node id.
- LOOP nodes drive bounded iteration at the strategy level: the configured
  loop body (node.config["body"]) is re-executed up to
  max_iterations times, checking node.config["stop_condition"] each pass.
  A hard cap guards against runaway loops and a per-iteration substrate
  event is emitted (the event log is the source of truth).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.services.substrate.node_executor import _safe_eval
from app.services.substrate.strategies.base import (
    ExecutionStrategy,
    _validate_edge_endpoints,
)
from app.services.substrate.workflow_models import (
    StrategyResult,
    Workflow,
    WorkflowType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.substrate.executor import UnifiedExecutor

logger = logging.getLogger(__name__)

# Edge.condition values that gate a branch off a CONDITION node.
_BRANCH_TRUE = "true"
_BRANCH_FALSE = "false"


class DAGStrategy(ExecutionStrategy):
    """DAG workflow strategy — topological sort + layer-parallel execution."""

    def can_handle(self, workflow_type: WorkflowType) -> bool:
        return workflow_type == WorkflowType.DAG

    async def validate(self, workflow: Workflow) -> list[str]:
        errors: list[str] = []

        if not workflow.nodes:
            errors.append("DAG workflow must have at least 1 node")

        errors.extend(_validate_edge_endpoints(workflow))

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
        # Nodes already executed (incl. loop-body nodes driven by a LOOP node)
        # are skipped during normal layering to avoid double execution.
        executed: set[str] = set()

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

            # Determine which nodes in this layer are executable given
            # CONDITION branch gating on their incoming edges.
            executable = [
                nid
                for nid in layer
                if nid not in executed and self._incoming_branch_passed(workflow, nid, node_outputs)
            ]

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

            results: Any = await asyncio.gather(*tasks, return_exceptions=True)

            from app.services.substrate.hitl_pause import HITLPaused

            for nid, result in zip(executable, results, strict=False):
                if isinstance(result, Exception):
                    # Q1-B chunk 1: Propagate HITLPaused — don't treat as failure
                    if isinstance(result, HITLPaused):
                        raise result
                    failed_nodes.append(nid)
                    node_outputs[nid] = {"error": str(result)}
                elif result.get("success"):
                    completed_nodes.append(nid)
                    executed.add(nid)
                    total_tokens += result.get("tokens", 0)
                    total_cost += result.get("cost", 0.0)
                    node_outputs[nid] = result.get("output", {})

                    # Scope B: a LOOP marker node drives bounded iteration
                    # of its configured body at the strategy level.
                    if workflow.node_map[nid].type.value == "loop":
                        await self._run_loop_body(
                            workflow,
                            nid,
                            context,
                            executor,
                            db,
                            run_id,
                            node_outputs,
                            executed,
                            completed_nodes,
                            failed_nodes,
                        )

                    # Scope B (T1-D2): a SPLIT node fans its collection out
                    # into one branch per item at runtime. The handler already
                    # resolved the collection into ``output["items"]``; here we
                    # expand the split's single outgoing edge(s) into N parallel
                    # executions of the immediate downstream target(s), one per
                    # item. Targets are marked executed so the normal layering
                    # (later layer) skips them - they only run via the fan-out.
                    if workflow.node_map[nid].type.value == "split" and not node_outputs[nid].get("empty", False):
                        await self._run_split_branches(
                            workflow,
                            nid,
                            node_outputs[nid],
                            context,
                            executor,
                            db,
                            run_id,
                            node_outputs,
                            executed,
                            completed_nodes,
                            failed_nodes,
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

    # ── CONDITION branch gating ──────────────────────────────────────

    def _incoming_branch_passed(self, workflow: Workflow, nid: str, node_outputs: dict[str, Any]) -> bool:
        """True if all incoming edges from CONDITION nodes permit execution.

        An edge from a CONDITION node carries edge.condition == "true" or
        "false". The edge is taken only when the condition's evaluated
        boolean matches. Edges without a condition (or not from a condition
        node) don't gate.
        """
        # Build incoming edges for this node (validate() guarantees the
        # edge endpoints reference real node ids).
        incoming = [e for e in workflow.edges if e.target == nid]
        for edge in incoming:
            src = workflow.node_map.get(edge.source)
            if src is None:
                continue
            # A fan-out edge from an EMPTY split node produces no branches, so
            # the downstream target must be skipped (the run continues past the
            # split). Mirrors CONDITION branch gating but is keyed on the split
            # node's resolved ``empty`` flag rather than an edge condition.
            if src.type.value == "split":
                if not edge.condition:
                    src_out = node_outputs.get(edge.source, {})
                    if isinstance(src_out, dict) and src_out.get("empty"):
                        return False
                continue
            if src.type.value != "condition":
                continue
            if not edge.condition:
                continue
            cond_out = node_outputs.get(edge.source, {})
            cond_value = bool(cond_out.get("value")) if isinstance(cond_out, dict) else bool(cond_out)
            branch = edge.condition.strip().lower()
            if branch == _BRANCH_TRUE and not cond_value:
                return False
            if branch == _BRANCH_FALSE and cond_value:
                return False
        return True

    # ── LOOP bounded iteration ───────────────────────────────────────

    async def _run_loop_body(
        self,
        workflow: Workflow,
        loop_node_id: str,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
        run_id: str,
        node_outputs: dict[str, Any],
        executed: set[str],
        completed_nodes: list[str],
        failed_nodes: list[str],
    ) -> None:
        """Drive bounded iteration of a LOOP node's body.

        Config (node.config):
            body: list[str] of node ids forming the loop body, in
                   execution order (the caller is responsible for it being
                   a valid topo order within the body).
            max_iterations: hard cap (default 10, clamped to 1000).
            stop_condition: optional boolean expression evaluated (via the
                   shared safe evaluator) against node_outputs each pass;
                   the loop breaks when it evaluates truthy.

        Each iteration re-executes the body nodes; a per-iteration substrate
        event is emitted so the event log captures the loop history. A hard
        cap prevents infinite loops even if stop_condition never holds.
        """
        loop_node = workflow.node_map[loop_node_id]
        body = loop_node.config.get("body") or []
        if not isinstance(body, list) or not body:
            return

        max_iterations = int(loop_node.config.get("max_iterations", 10))
        max_iterations = max(1, min(max_iterations, 1000))
        stop_condition = loop_node.config.get("stop_condition")

        for iteration in range(max_iterations):
            # Hard-cap guard: emit an event and bail if we exceed the cap.
            if iteration >= max_iterations:
                break

            # Re-run each body node in order. Body nodes are skipped during
            # normal layering (they're already in ``executed``), so this is
            # the single place they run.
            body_failed = False
            for body_nid in body:
                body_node = workflow.node_map.get(body_nid)
                if body_node is None:
                    continue
                result = await executor.execute_node(
                    db=db,
                    node=body_node,
                    context={**context, "previous_outputs": node_outputs},
                    budget=workflow.budget,
                    run_id=run_id,
                    workflow=workflow,
                )
                if result.get("success"):
                    executed.add(body_nid)
                    if body_nid not in completed_nodes:
                        completed_nodes.append(body_nid)
                    node_outputs[body_nid] = result.get("output", {})
                else:
                    body_failed = True
                    if body_nid not in failed_nodes:
                        failed_nodes.append(body_nid)
                    node_outputs[body_nid] = {"error": result.get("error")}

            # Emit a per-iteration event (event log is source of truth).
            try:
                from app.services.substrate.event_log import get_event_log

                event_log = get_event_log()
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": "node.loop.iteration",
                            "payload": {
                                "node_id": loop_node_id,
                                "iteration": iteration + 1,
                                "max_iterations": max_iterations,
                                "body_failed": body_failed,
                            },
                            "actor": "dag_strategy",
                            "task_id": loop_node_id,
                        }
                    ],
                )
            except Exception as e:
                logger.debug("Loop iteration event skipped: %s", e)

            if body_failed:
                break

            # Evaluate stop_condition against the latest outputs.
            if stop_condition:
                try:
                    if _safe_eval(stop_condition, node_outputs):
                        break
                except Exception as e:
                    logger.debug("Loop stop_condition eval failed: %s", e)
                    break

    # ── Split (runtime fan-out) ──────────────────────────────────

    async def _run_split_branches(
        self,
        workflow: Workflow,
        split_node_id: str,
        split_output: dict[str, Any],
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
        run_id: str,
        node_outputs: dict[str, Any],
        executed: set[str],
        completed_nodes: list[str],
        failed_nodes: list[str],
    ) -> None:
        """Fan a split node's collection out into one branch per item.

        For each item in ``split_output["items"]``, the split node's immediate
        downstream target(s) (the nodes reached via its outgoing edges) are
        executed once, in parallel, with that item injected as the node's
        ``input``. This is the data-driven analogue of RouterNode's per-route
        branches: one dynamic edge per item at runtime.

        Items run in parallel (one asyncio task per (item, target) pair). Each
        target is marked ``executed`` so the normal layered traversal skips it
        - it only runs through this fan-out. The split node itself is already
        in ``executed``.

        An empty collection (``split_output["empty"] is True``) produces no
        branches; the caller is responsible for not invoking this helper in
        that case, so the run simply continues past the split node.
        """
        items = split_output.get("items") or []
        if not items:
            return

        # Immediate downstream targets reached via the split's outgoing edges.
        targets: list[str] = []
        for edge in workflow.dependency_map.get(split_node_id, []):
            if edge.target not in targets:
                targets.append(edge.target)

        if not targets:
            return

        async def _run_one(item_idx: int, item: Any, target_nid: str) -> None:
            target_node = workflow.node_map.get(target_nid)
            if target_node is None:
                return
            # Inject the item as the node's input so the per-item payload flows
            # downstream. ``previous_outputs`` keeps the rest of the context.
            branch_context = {
                **context,
                "input": item,
                "previous_outputs": node_outputs,
                "split_item_index": item_idx,
            }
            result = await executor.execute_node(
                db=db,
                node=target_node,
                context=branch_context,
                budget=workflow.budget,
                run_id=run_id,
                workflow=workflow,
            )
            if result.get("success"):
                executed.add(target_nid)
                if target_nid not in completed_nodes:
                    completed_nodes.append(target_nid)
                node_outputs[target_nid] = result.get("output", {})
            else:
                if target_nid not in failed_nodes:
                    failed_nodes.append(target_nid)
                node_outputs[target_nid] = {"error": result.get("error")}

        # Parallel across items x targets.
        fan_tasks = [_run_one(idx, item, target_nid) for idx, item in enumerate(items) for target_nid in targets]
        await asyncio.gather(*fan_tasks, return_exceptions=True)

    # ── Topological sort (Kahn) ───────────────────────────────────

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
