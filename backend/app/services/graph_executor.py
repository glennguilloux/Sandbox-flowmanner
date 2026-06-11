"""Graph Execution Engine — interprets saved flows and executes nodes.

Uses topological sort from dag_executor.py for execution order.
Routes each node type to the appropriate handler via NodeHandlerRegistry.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.models.graph import GraphExecution, GraphState, GraphWorkflow
from app.services.graph_node_handlers import NodeHandlerRegistry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ExecutionContext:
    """Shared state that flows between nodes during graph execution."""

    def __init__(self, input_data: dict | None = None) -> None:
        self._data: dict[str, Any] = dict(input_data or {})
        self._node_outputs: dict[str, dict] = {}
        self._iteration_vars: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get_node_output(self, node_id: str) -> dict | None:
        return self._node_outputs.get(node_id)

    def set_node_output(self, node_id: str, output: dict) -> None:
        self._node_outputs[node_id] = output

    def get_iteration_var(self, key: str, default: Any = None) -> Any:
        return self._iteration_vars.get(key, default)

    def set_iteration_var(self, key: str, value: Any) -> None:
        self._iteration_vars[key] = value

    def resolve_interpolation(self, template: str) -> Any:
        """Resolve {{node_id.output.field}} or {{variable}} references."""
        if not isinstance(template, str) or "{{" not in template:
            return template

        pattern = r"\{\{([^}]+)\}\}"
        matches = list(re.finditer(pattern, template))

        if len(matches) == 1 and matches[0].group(0) == template.strip():
            return self._resolve_ref(matches[0].group(1).strip())

        result = template
        for m in matches:
            ref = m.group(1).strip()
            val = self._resolve_ref(ref)
            result = result.replace(m.group(0), str(val) if val is not None else "")
        return result

    def _resolve_ref(self, ref: str) -> Any:
        parts = ref.split(".")
        if parts[0] in self._node_outputs:
            obj = self._node_outputs[parts[0]]
            for p in parts[1:]:
                if isinstance(obj, dict):
                    obj = obj.get(p)
                else:
                    return None
            return obj
        if parts[0] in self._iteration_vars:
            return self._iteration_vars[parts[0]]
        return self._data.get(parts[0])

    def interpolate_dict(self, data: dict) -> dict:
        """Resolve all interpolation references in a dict."""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = self.resolve_interpolation(v)
            elif isinstance(v, dict):
                result[k] = self.interpolate_dict(v)
            elif isinstance(v, list):
                result[k] = [self.resolve_interpolation(i) if isinstance(i, str) else i for i in v]
            else:
                result[k] = v
        return result

    def to_dict(self) -> dict:
        return {
            "data": self._data,
            "node_outputs": self._node_outputs,
            "iteration_vars": self._iteration_vars,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExecutionContext:
        ctx = cls(data.get("data", {}))
        ctx._node_outputs = data.get("node_outputs", {})
        ctx._iteration_vars = data.get("iteration_vars", {})
        return ctx


class GraphInterpreter:
    """Traverses a graph definition and dispatches nodes to handlers."""

    def __init__(
        self,
        db: AsyncSession,
        workflow: GraphWorkflow,
        execution: GraphExecution,
    ) -> None:
        self.db = db
        self.workflow = workflow
        self.execution = execution
        self.graph_def: dict = workflow.graph_definition or {}
        self.nodes: list[dict] = self.graph_def.get("nodes", [])
        self.edges: list[dict] = self.graph_def.get("edges", [])
        self.registry = NodeHandlerRegistry()
        self.context = ExecutionContext(execution.input_data)

    def _get_subgraph_nodes(self, start_node_id: str) -> set[str]:
        """BFS from start node to find all downstream nodes."""
        result: set[str] = set()
        queue = [start_node_id]
        while queue:
            current = queue.pop(0)
            if current in result:
                continue
            result.add(current)
            for edge in self.edges:
                if edge.get("source") == current:
                    target = edge.get("target")
                    if target and target not in result:
                        queue.append(target)
        return result

    async def execute(self, start_node_id: str | None = None) -> dict:
        """Main entry: topological sort → dispatch → collect results.

        If start_node_id is set, filters the graph to only that node
        and its downstream subgraph, using cached upstream results.
        """
        if not self.nodes:
            return {"status": "completed", "outputs": {}}

        # Filter to subgraph if start_node_id specified
        active_node_ids = self._get_subgraph_nodes(start_node_id) if start_node_id else {n["id"] for n in self.nodes}

        # Filter edges to only those within active nodes
        active_edges = [
            e for e in self.edges if e.get("source") in active_node_ids and e.get("target") in active_node_ids
        ]

        # Kahn's on reduced graph
        layers = self._topological_sort(active_node_ids, active_edges)
        if layers is None:
            raise ValueError("Graph contains a cycle")

        all_outputs: dict[str, dict] = {}

        for layer in layers:
            tasks = [self._execute_node(node_id, all_outputs) for node_id in layer]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for node_id, result in zip(layer, results, strict=False):
                if isinstance(result, Exception):
                    logger.error("Node %s failed: %s", node_id, result)
                    all_outputs[node_id] = {
                        "success": False,
                        "error": str(result),
                    }
                    await self._record_state(node_id, all_outputs[node_id])
                    raise result
                else:
                    all_outputs[node_id] = result
                    self.context.set_node_output(node_id, result)  # type: ignore[arg-type]
                    await self._record_state(node_id, result)  # type: ignore[arg-type]

                    # Check for pause signal (approval node)
                    if isinstance(result, dict) and result.get("pause"):
                        logger.info("Execution paused at node %s", node_id)
                        return {
                            "status": "paused",
                            "outputs": all_outputs,
                            "paused_at": node_id,
                        }

        return {"status": "completed", "outputs": all_outputs}

    def _topological_sort(
        self,
        node_ids: set[str] | None = None,
        edge_list: list[dict] | None = None,
    ) -> list[list[str]] | None:
        """Kahn's algorithm on graph edges. Returns layers or None on cycle.

        Args:
            node_ids: Optional set of node IDs to sort (defaults to all nodes).
            edge_list: Optional list of edges to use (defaults to self.edges).
        """
        if node_ids is None:
            node_ids = {n["id"] for n in self.nodes}
        if edge_list is None:
            edge_list = self.edges

        in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)
        dependents: dict[str, list[str]] = {nid: [] for nid in node_ids}

        for edge in edge_list:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if src in node_ids and tgt in node_ids:
                in_degree[tgt] += 1
                dependents[src].append(tgt)

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        layers: list[list[str]] = []
        visited = 0

        while queue:
            layers.append(list(queue))
            visited += len(queue)
            next_queue = []
            for nid in queue:
                for dep in dependents[nid]:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        next_queue.append(dep)
            queue = next_queue

        if visited != len(node_ids):
            return None
        return layers

    async def _execute_node(self, node_id: str, all_outputs: dict[str, dict]) -> dict:
        node = next((n for n in self.nodes if n["id"] == node_id), None)
        if node is None:
            return {"success": False, "error": f"Node {node_id} not found"}

        node_type = node.get("data", {}).get("nodeType", "task")
        handler = self.registry.get(node_type)

        # Phase 9.1: Fall back to plugin runtime for unregistered node types
        if handler is None:
            try:
                from app.services.plugin_runtime import get_plugin_runtime

                plugin_handler = get_plugin_runtime().get_handler(node_type)
                if plugin_handler is not None:
                    handler = plugin_handler
            except Exception as _e:
                logger.debug("PluginRuntime lookup failed for '%s': %s", node_type, _e)

        if handler is None:
            return {
                "success": False,
                "error": f"No handler for node type '{node_type}'",
            }

        errors = await handler.validate(node)
        if errors:
            return {"success": False, "error": f"Validation failed: {errors}"}

        return await handler.execute(node, self.context, self)

    async def _record_state(self, node_id: str, output: dict) -> None:
        state = GraphState(
            id=str(uuid4()),
            execution_id=self.execution.id,
            workflow_id=self.workflow.id,
            state_data={"node_id": node_id, "output": output},
        )
        self.db.add(state)
        await self.db.flush()

        # Broadcast node state update via WebSocket
        try:
            import asyncio

            from app.websocket.mission_ws import sio as _sio

            try:
                loop = asyncio.get_running_loop()
                asyncio.create_task(
                    _sio.emit(
                        "graph:node_state",
                        {
                            "execution_id": self.execution.id,
                            "node_id": node_id,
                            "status": (
                                "failed"
                                if isinstance(output, dict) and not output.get("success", True)
                                else "completed"
                            ),
                            "output": output,
                        },
                        room=f"graph_exec_{self.execution.id}",
                    )
                )
            except RuntimeError as e:
                logger.debug("graph_ws_emit_no_loop execution_id=%s error=%s", self.execution.id, str(e))
        except Exception as e:
            logger.debug("graph_ws_emit_failed execution_id=%s error=%s", self.execution.id, str(e))
