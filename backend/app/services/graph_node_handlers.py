"""Node handler registry and base class for graph execution.

Each node type (task, webhook, condition, etc.) has a handler that
implements BaseNodeHandler.execute() and validate().
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Any

import httpx

if TYPE_CHECKING:
    from app.services.graph_executor import GraphInterpreter

logger = logging.getLogger(__name__)


class BaseNodeHandler(ABC):
    """Abstract base for all node type handlers."""

    @abstractmethod
    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        """Execute this node and return {"success": True, "output": {...}}."""

    async def validate(self, node: dict) -> list[str]:
        """Pre-execution validation. Return list of error strings."""
        return []


class NodeHandlerRegistry:
    """Maps node type strings to handler instances."""

    def __init__(self) -> None:
        self._handlers: dict[str, BaseNodeHandler] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("task", TaskNodeHandler())
        self.register("start", StartNodeHandler())
        self.register("end", EndNodeHandler())
        self.register("webhook", WebhookNodeHandler())
        self.register("condition", ConditionNodeHandler())
        self.register("parallel", ParallelNodeHandler())
        self.register("loop", LoopNodeHandler())
        self.register("approval", ApprovalNodeHandler())
        self.register("delay", DelayNodeHandler())
        self.register("transform", TransformNodeHandler())
        self.register("log", LogNodeHandler())
        self.register("subflow", SubFlowNodeHandler())

    def register(self, node_type: str, handler: BaseNodeHandler) -> None:
        self._handlers[node_type] = handler

    def register_plugin(self, node_type: str, handler: BaseNodeHandler) -> None:
        """Register a plugin-provided handler.  Overwrites built-in if collision."""
        if node_type in self._handlers:
            logger.warning(
                "Plugin handler '%s' overwriting existing handler",
                node_type,
            )
        self._handlers[node_type] = handler
        logger.info("Plugin handler registered: %s", node_type)

    def unregister(self, node_type: str) -> None:
        self._handlers.pop(node_type, None)

    def get(self, node_type: str) -> BaseNodeHandler | None:
        return self._handlers.get(node_type)

    def registered_types(self) -> list[str]:
        return list(self._handlers.keys())

    def plugin_types(self) -> list[str]:
        """Return node types registered by plugins (not built-in)."""
        built_in = {
            "task",
            "start",
            "end",
            "webhook",
            "condition",
            "parallel",
            "loop",
            "approval",
            "delay",
            "transform",
            "log",
            "subflow",
        }
        return [t for t in self._handlers if t not in built_in]


# ─── Concrete Handlers ───


class StartNodeHandler(BaseNodeHandler):
    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        return {"success": True, "output": {"started": True}}


class EndNodeHandler(BaseNodeHandler):
    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        return {"success": True, "output": {"completed": True}}


class TaskNodeHandler(BaseNodeHandler):
    """Executes a task node via ModelRouter (LLM call)."""

    async def validate(self, node: dict) -> list[str]:
        errors = []
        data = node.get("data", {})
        if not data.get("label"):
            errors.append("Task node requires a label")
        return errors

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        data = node.get("data", {})
        description = context.resolve_interpolation(
            data.get("description", data.get("label", ""))
        )
        model_pref = data.get("modelPreference")
        timeout = data.get("timeout", 60)

        try:
            from app.services.llm_router import ModelRouter

            router = ModelRouter()
            result = await asyncio.wait_for(
                router.route_request(
                    prompt=description,
                    model_preference=model_pref,
                ),
                timeout=timeout,
            )
            if result.get("success"):
                return {
                    "success": True,
                    "output": {
                        "text": result.get("response", ""),
                        "tokens": result.get("cost", {}),
                    },
                }
            return {"success": False, "error": result.get("error", "LLM call failed")}
        except TimeoutError:
            return {"success": False, "error": f"Task timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class WebhookNodeHandler(BaseNodeHandler):
    """Makes an HTTP request with the node's configured URL/method/headers/body."""

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        data = node.get("data", {})
        url = context.resolve_interpolation(data.get("url", ""))
        method = (data.get("method") or "GET").upper()
        headers = data.get("headers") or {}
        body = context.resolve_interpolation(data.get("body"))
        auth_type = data.get("authType", "none")

        if not url:
            return {"success": False, "error": "No URL configured"}

        request_headers = dict(headers)
        if auth_type == "bearer" and data.get("authToken"):
            request_headers["Authorization"] = f"Bearer {data['authToken']}"
        elif auth_type == "api_key" and data.get("apiKey"):
            request_headers["X-API-Key"] = data["apiKey"]

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    headers=request_headers,
                    content=(
                        body if body and method in ("POST", "PUT", "PATCH") else None
                    ),
                )
                try:
                    resp_body = resp.json()
                except Exception:
                    resp_body = resp.text

                return {
                    "success": True,
                    "output": {
                        "status_code": resp.status_code,
                        "headers": dict(resp.headers),
                        "body": resp_body,
                    },
                }
        except Exception as e:
            return {"success": False, "error": str(e)}


class ConditionNodeHandler(BaseNodeHandler):
    """Evaluates a Python expression against the execution context."""

    BLOCKED = {"import", "exec", "eval", "open", "__", "os.", "sys.", "subprocess"}

    async def validate(self, node: dict) -> list[str]:
        expr = node.get("data", {}).get("expression", "")
        if not expr:
            return ["Condition node requires an expression"]
        return []

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        expr = context.resolve_interpolation(node.get("data", {}).get("expression", ""))
        expr_str = str(expr)

        for blocked in self.BLOCKED:
            if blocked in expr_str:
                return {
                    "success": False,
                    "error": f"Blocked expression containing '{blocked}'",
                }

        try:
            safe_globals: dict[str, dict[str, Any]] = {"__builtins__": {}}
            safe_locals = {"ctx": context, "True": True, "False": False, "None": None}
            result = eval(expr_str, safe_globals, safe_locals)
            return {
                "success": True,
                "output": {"result": bool(result), "expression": expr_str},
            }
        except Exception as e:
            return {"success": False, "error": f"Expression error: {e}"}


class ParallelNodeHandler(BaseNodeHandler):
    """Executes downstream branches concurrently."""

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        data = node.get("data", {})
        join_mode = data.get("joinMode", "all")

        if interpreter is None:
            return {"success": False, "error": "Parallel node requires interpreter"}

        # Find downstream nodes (direct children of this parallel node)
        node_id = node.get("id", "")
        downstream_ids = [
            e.get("target") for e in interpreter.edges if e.get("source") == node_id
        ]

        if not downstream_ids:
            return {
                "success": True,
                "output": {
                    "join_mode": join_mode,
                    "branches": {},
                    "note": "No downstream branches",
                },
            }

        # Execute all branches concurrently
        branch_coros = [interpreter._execute_node(did, {}) for did in downstream_ids]

        if join_mode == "any":
            # Return first completed branch
            done, _ = await asyncio.wait(
                [asyncio.create_task(c) for c in branch_coros],
                return_when=asyncio.FIRST_COMPLETED,
            )
            branch_outputs = {}
            for task in done:
                result = task.result()
                # Use the first result
                branch_outputs[downstream_ids[0]] = result
                break
        else:
            # Wait for all branches
            results = await asyncio.gather(*branch_coros, return_exceptions=True)
            branch_outputs = {}
            for did, result in zip(downstream_ids, results, strict=False):
                if isinstance(result, Exception):
                    branch_outputs[did] = {"success": False, "error": str(result)}
                else:
                    branch_outputs[did] = result

        return {
            "success": True,
            "output": {
                "join_mode": join_mode,
                "branches": branch_outputs,
            },
        }


class LoopNodeHandler(BaseNodeHandler):
    """Executes downstream nodes per iteration."""

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        data = node.get("data", {})
        loop_mode = data.get("loopMode", "count")
        max_iterations = min(data.get("maxIterations", 100), 1000)

        # Determine iteration items
        iterations: list[dict] = []
        if loop_mode == "count":
            count = min(data.get("loopCount", 1), max_iterations)
            iterations = [{"index": i} for i in range(count)]
        elif loop_mode == "foreach":
            raw_expr = data.get("loopExpression", "[]")
            items = context.resolve_interpolation(raw_expr)
            if isinstance(items, str):
                items = context.get(raw_expr, items)
            if isinstance(items, str):
                try:
                    items = json.loads(items)
                except Exception:
                    items = []
            iterations = [
                {"index": i, "item": item}
                for i, item in enumerate(items[:max_iterations])
            ]
        elif loop_mode == "while":
            for i in range(max_iterations):
                context.set_iteration_var("loop_index", i)
                expr = context.resolve_interpolation(
                    data.get("loopExpression", "False")
                )
                try:
                    if not eval(str(expr), {"__builtins__": {}}, {"ctx": context}):
                        break
                except Exception:
                    break
                iterations.append({"index": i})

        # If no interpreter, just return iteration metadata
        if interpreter is None:
            return {
                "success": True,
                "output": {
                    "loop_mode": loop_mode,
                    "iterations": len(iterations),
                    "items": iterations,
                },
            }

        # Find downstream nodes to execute per iteration
        node_id = node.get("id", "")
        downstream_ids = [
            e.get("target") for e in interpreter.edges if e.get("source") == node_id
        ]

        iteration_outputs: list[dict] = []
        for iteration in iterations:
            # Set iteration context
            for k, v in iteration.items():
                context.set_iteration_var(k, v)

            # Execute downstream nodes for this iteration
            iter_result = {}
            for did in downstream_ids:
                result = await interpreter._execute_node(did, {})
                iter_result[did] = result
                if result.get("success"):
                    context.set_node_output(f"{did}_iter{iteration['index']}", result)

            iteration_outputs.append({"iteration": iteration, "outputs": iter_result})

        return {
            "success": True,
            "output": {
                "loop_mode": loop_mode,
                "iterations": len(iterations),
                "iteration_outputs": iteration_outputs,
            },
        }


class ApprovalNodeHandler(BaseNodeHandler):
    """Pauses execution and returns approval request metadata."""

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        data = node.get("data", {})

        # If interpreter available, signal pause
        if interpreter is not None:
            from app.services.graph_service import pause_execution

            await pause_execution(interpreter.db, interpreter.execution.id)

        return {
            "success": True,
            "output": {
                "status": "paused",
                "approver_role": data.get("approverRole", "any"),
                "timeout_hours": data.get("approvalTimeout", 24),
                "escalation_policy": data.get("escalationPolicy", "reject"),
            },
            "pause": True,
        }


class DelayNodeHandler(BaseNodeHandler):
    """Sleeps for the configured duration."""

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        data = node.get("data", {})
        delay_type = data.get("delayType", "fixed")
        delay_ms = data.get("delayMs", 1000)
        max_delay_ms = data.get("maxDelayMs", 30000)

        actual_delay = (
            min(delay_ms * 2, max_delay_ms) if delay_type == "exponential" else delay_ms
        )

        actual_delay = min(actual_delay, 60000)
        await asyncio.sleep(actual_delay / 1000)

        return {
            "success": True,
            "output": {"delayed_ms": actual_delay, "delay_type": delay_type},
        }


class TransformNodeHandler(BaseNodeHandler):
    """Applies a data transformation (jq-like, template, or script)."""

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        data = node.get("data", {})
        transform_type = data.get("transformType", "template")
        expression = context.resolve_interpolation(data.get("transformExpression", ""))

        try:
            if transform_type == "template":
                result = self._apply_template(str(expression), context)
            elif transform_type == "jq":
                result = self._apply_jq(str(expression), context)
            else:
                result = {"transformed": expression}
            return {
                "success": True,
                "output": {"transform_type": transform_type, "result": result},
            }
        except Exception as e:
            return {"success": False, "error": f"Transform error: {e}"}

    def _apply_template(self, template: str, context: Any) -> str:
        import re

        def replacer(m):
            ref = m.group(1).strip()
            val = context._resolve_ref(ref)
            return str(val) if val is not None else ""

        return re.sub(r"\{\{([^}]+)\}\}", replacer, template)

    def _apply_jq(self, expression: str, context: Any) -> Any:
        parts = expression.strip().lstrip(".").split(".")
        obj = context._data
        for p in parts:
            if p and isinstance(obj, dict):
                obj = obj.get(p)
            elif p and isinstance(obj, list):
                try:
                    obj = obj[int(p)]
                except (ValueError, IndexError):
                    return None
        return obj


class LogNodeHandler(BaseNodeHandler):
    """Logs a message with the configured level."""

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        data = node.get("data", {})
        level = data.get("level", "info")
        message = context.resolve_interpolation(data.get("message", ""))

        log_func = getattr(logger, level, logger.info)
        log_func("LogNode: %s", message)

        return {
            "success": True,
            "output": {"logged": True, "level": level, "message": str(message)},
        }


class SubFlowNodeHandler(BaseNodeHandler):
    """Executes a nested workflow by missionId."""

    MAX_DEPTH = 5

    async def execute(
        self, node: dict, context: Any, interpreter: GraphInterpreter | None = None
    ) -> dict:
        data = node.get("data", {})
        mission_id = data.get("missionId")
        if not mission_id:
            return {"success": False, "error": "No missionId configured"}

        depth = context.get("_subflow_depth", 0)
        if depth >= self.MAX_DEPTH:
            return {
                "success": False,
                "error": f"Subflow depth limit ({self.MAX_DEPTH}) exceeded",
            }

        if interpreter is None:
            return {"success": False, "error": "Subflow node requires interpreter"}

        # Load subflow workflow from DB
        from app.services.graph_service import get_graph_workflow

        sub_workflow = await get_graph_workflow(interpreter.db, mission_id)
        if sub_workflow is None:
            return {
                "success": False,
                "error": f"Subflow workflow '{mission_id}' not found",
            }

        # Create nested interpreter
        from app.services.graph_executor import GraphInterpreter

        sub_interpreter = GraphInterpreter(
            interpreter.db, sub_workflow, interpreter.execution
        )
        sub_interpreter.context._data["_subflow_depth"] = depth + 1
        sub_interpreter.context._data.update(context._data)

        # Execute subflow
        try:
            result = await sub_interpreter.execute()
            return {
                "success": True,
                "output": {
                    "subflow_id": mission_id,
                    "subflow_name": data.get("missionName", ""),
                    "status": "completed",
                    "subflow_outputs": result.get("outputs", {}),
                },
            }
        except Exception as e:
            return {"success": False, "error": f"Subflow execution failed: {e}"}
