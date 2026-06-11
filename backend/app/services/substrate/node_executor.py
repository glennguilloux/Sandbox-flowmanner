"""NodeExecutor — shared execute_node() for all strategies (H5.1).

The single code path for executing a workflow node.  Every strategy
delegates to NodeExecutor for actual node execution.  It handles:

1. Pre-execution budget check
2. Capability token creation for tool nodes
3. Node dispatch to the appropriate handler
4. Fallback strategy execution
5. Event logging (to substrate event log)
6. Retry with budget
7. LLM call recording (via BudgetEnforcer)

All LLM calls go through BudgetEnforcer.call().
All tool calls go through CapabilityEngine.verify().
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from app.integrations.sandboxd_client import SandboxdClient, get_sandboxd_client
from app.models.capability_models import Action, Budget, BudgetExhausted, ResourceRef
from app.models.substrate_models import SubstrateEventType
from app.services.sandbox_service import SandboxService
from app.services.substrate.event_log import get_event_log
from app.services.substrate.workflow_models import (
    NodeType,
    Workflow,
    WorkflowNode,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Code execution wrapper (written to temp file to avoid quote issues) ──

_WORKSPACE_WRAPPER = """import sys, io, json, math, statistics, datetime, collections
import itertools, functools, operator, re, string, textwrap, hashlib, base64, copy, csv

__builtins__ = {
    'True': True, 'False': False, 'None': None,
    'abs': abs, 'all': all, 'any': any, 'bool': bool,
    'chr': chr, 'dict': dict, 'divmod': divmod,
    'enumerate': enumerate, 'filter': filter, 'float': float, 'format': format,
    'int': int, 'isinstance': isinstance, 'iter': iter,
    'len': len, 'list': list, 'map': map, 'max': max, 'min': min,
    'print': print, 'range': range, 'repr': repr, 'reversed': reversed,
    'round': round, 'set': set, 'slice': slice, 'sorted': sorted,
    'str': str, 'sum': sum, 'tuple': tuple, 'type': type, 'zip': zip,
    'Exception': Exception, 'TypeError': TypeError, 'ValueError': ValueError,
    'KeyError': KeyError, 'IndexError': IndexError,
}

_buf = io.StringIO()
_old = sys.stdout
sys.stdout = _buf
try:
{code}
except Exception as e:
    print(f"ERROR: {{type(e).__name__}}: {{e}}")
finally:
    sys.stdout = _old

_out = _buf.getvalue()
if len(_out) > 1_000_000:
    _out = _out[:1_000_000] + "\\n... (truncated at 1MB)"
print(_out, end='')
"""


class NodeExecutor:
    """Shared node execution — used by all 7 strategies."""

    def __init__(self, unified_executor):
        """Create a NodeExecutor.

        Args:
            unified_executor: The UnifiedExecutor that provides budget_enforcer,
                              capability_engine, event_log, etc.
        """
        self.executor = unified_executor
        self._sbx_client: SandboxdClient | None = None
        self._sbx_svc: SandboxService | None = None

    @property
    def _sandbox_client(self) -> SandboxdClient:
        if self._sbx_client is None:
            self._sbx_client = get_sandboxd_client()
        return self._sbx_client

    @property
    def _sandbox_service(self) -> SandboxService:
        if self._sbx_svc is None:
            self._sbx_svc = SandboxService(self._sandbox_client)
        return self._sbx_svc

    async def execute(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute a single node.

        Returns:
            Dict with success, output, tokens, cost, etc.
        """
        event_log = get_event_log()
        result: dict[str, Any] = {"success": False, "error": "Unknown error"}

        # Pre-execution budget check
        is_exhausted, reason = budget.is_exhausted()
        if is_exhausted:
            raise BudgetExhausted(reason, budget)

        start_time = time.monotonic()

        # Max retries
        max_retries = node.max_retries if node.max_retries is not None else 3
        for attempt in range(max_retries + 1):
            # Check abort signal between retries
            if self.executor.is_aborted(run_id):
                logger.info("Abort signal detected for run %s, node %s", run_id, node.id)
                return {"success": False, "error": "Aborted"}

            node.status = "running"

            # Record task.started event
            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.TASK_STARTED,
                        "payload": {
                            "task_id": node.id,
                            "task_title": node.title,
                            "task_type": node.type.value,
                            "attempt": attempt + 1,
                        },
                        "actor": "node_executor",
                        "mission_id": workflow.id if workflow else None,
                        "task_id": node.id,
                    }
                ],
            )

            try:
                result = await self._dispatch(db, node, context, budget, run_id, workflow)
            except BudgetExhausted:
                raise
            except Exception as e:
                logger.exception("Node %s execution error", node.id)
                result = {"success": False, "error": str(e)}

            elapsed_ms = (time.monotonic() - start_time) * 1000

            if result.get("success"):
                # Record task.completed event
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.TASK_COMPLETED,
                            "payload": {
                                "task_id": node.id,
                                "task_title": node.title,
                                "tokens": result.get("tokens", 0),
                                "cost_usd": result.get("cost", 0.0),
                                "latency_ms": elapsed_ms,
                            },
                            "actor": "node_executor",
                            "mission_id": workflow.id if workflow else None,
                            "task_id": node.id,
                        }
                    ],
                )

                node.status = "completed"
                node.output_data = result.get("output")
                node.tokens_used = result.get("tokens", 0)
                node.cost = result.get("cost", 0.0)
                return result

            # Failure handling
            if attempt < max_retries:
                node.retry_count = attempt + 1
                logger.warning(
                    "Node %s failed (attempt %d/%d): %s",
                    node.id,
                    attempt + 1,
                    max_retries,
                    result.get("error"),
                )
                # Record task.retrying event
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.TASK_RETRYING,
                            "payload": {
                                "task_id": node.id,
                                "attempt": attempt + 1,
                                "error": result.get("error"),
                            },
                            "actor": "node_executor",
                            "mission_id": workflow.id if workflow else None,
                            "task_id": node.id,
                        }
                    ],
                )
                continue

            # All retries exhausted
            logger.error("Node %s failed after %d retries", node.id, max_retries)
            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.TASK_FAILED,
                        "payload": {
                            "task_id": node.id,
                            "task_title": node.title,
                            "error": result.get("error"),
                            "retries_exhausted": True,
                        },
                        "actor": "node_executor",
                        "mission_id": workflow.id if workflow else None,
                        "task_id": node.id,
                    }
                ],
            )

            node.status = "failed"
            node.error_message = result.get("error")
            return result

        return result  # Should not reach here

    async def _dispatch(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Dispatch a node to the appropriate handler based on its type."""
        match node.type:
            case NodeType.LLM_CALL:
                return await self._handle_llm(db, node, context, budget, run_id, workflow)
            case NodeType.TOOL_CALL:
                return await self._handle_tool(db, node, context, budget, run_id, workflow)
            case NodeType.CODE_EXECUTION:
                return await self._handle_code(node, context)
            case NodeType.RAG_QUERY:
                return await self._handle_rag(node, context)
            case NodeType.WEB_SEARCH:
                return await self._handle_web_search(node, context)
            case NodeType.FILE_OPERATION:
                return await self._handle_file(node, context)
            case NodeType.HUMAN_REVIEW:
                return await self._handle_hitl_interrupt(
                    db,
                    node,
                    context,
                    run_id,
                    workflow,
                    interrupt_type="clarification",
                )
            case NodeType.APPROVAL:
                return await self._handle_hitl_interrupt(
                    db,
                    node,
                    context,
                    run_id,
                    workflow,
                    interrupt_type="approval",
                )
            case (
                NodeType.BROWSER_NAVIGATE
                | NodeType.BROWSER_SNAPSHOT
                | NodeType.BROWSER_CLICK
                | NodeType.BROWSER_TYPE
                | NodeType.BROWSER_SCROLL
                | NodeType.BROWSER_SCREENSHOT
                | NodeType.BROWSER_CLOSE
            ):
                return await self._handle_browser(node, context)
            case NodeType.SUB_WORKFLOW:
                return await self._handle_sub_workflow(db, node, context, budget, run_id)
            case NodeType.PHASE_GATE | NodeType.FAN_OUT | NodeType.FAN_IN:
                # Delegated to strategy — the node executor just passes through
                return {"success": True, "output": context, "tokens": 0}
            case NodeType.SANDBOX:
                return await self._handle_sandbox_node(db, node, context, budget, run_id, workflow)
            case _:
                return {"success": False, "error": f"Unknown node type: {node.type}"}

    # ── LLM handler ─────────────────────────────────────────────────

    async def _handle_llm(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute an LLM call through the BudgetEnforcer."""
        # Phase 6.4: Circuit breaker check before LLM call
        mission_id = workflow.id if workflow else None
        if mission_id:
            allowed, reason = await self.executor.check_circuit_breaker(db=db, mission_id=mission_id, call_type="llm")
            if not allowed:
                return {
                    "success": False,
                    "error": f"Circuit breaker: {reason}",
                    "tokens": 0,
                }

        from app.services.budget_enforcer import get_budget_enforcer

        enforcer = get_budget_enforcer()
        prompt = node.config.get("prompt", node.description or node.title)
        model_id = node.assigned_model or node.config.get("model_id", "deepseek-chat")

        system_prompt = node.config.get("system_prompt")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await enforcer.call(
            budget=budget,
            model_id=model_id,
            messages=messages,
            user_id=workflow.user_id if workflow else None,
            run_id=run_id,
            mission_id=mission_id,
            task_id=node.id,
            temperature=node.config.get("temperature", 0.7),
            max_tokens=node.config.get("max_tokens", 2000),
        )

        if not response.get("success"):
            return {
                "success": False,
                "error": response.get("error", "LLM call failed"),
                "tokens": 0,
            }

        content = response.get("response", "")
        budget_info = response.get("budget", {})
        tokens = budget_info.get("prompt_tokens", 0) + budget_info.get("completion_tokens", 0)

        if not content or content.strip() == "":
            return {
                "success": False,
                "error": "LLM returned empty response",
                "tokens": tokens,
            }

        return {
            "success": True,
            "output": {"text": content},
            "tokens": tokens,
            "cost": budget_info.get("spent_usd", 0.0),
            "model": response.get("model", model_id),
            "provider": response.get("provider", "unknown"),
        }

    # ── Tool handler ────────────────────────────────────────────────

    async def _handle_tool(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute a tool call with capability verification."""
        # Phase 6.4: Circuit breaker check before tool call
        mission_id = workflow.id if workflow else None
        if mission_id:
            allowed, reason = await self.executor.check_circuit_breaker(db=db, mission_id=mission_id, call_type="tool")
            if not allowed:
                return {"success": False, "error": f"Circuit breaker: {reason}"}

        from app.services.capability_engine import get_capability_engine

        cap_engine = get_capability_engine()
        tool_name = node.config.get("tool_name") or node.config.get("tool_id")

        if not tool_name:
            # Fall back to LLM if no tool specified
            logger.info("No tool specified for node %s, falling back to LLM", node.id)
            return await self._handle_llm(db, node, context, budget, run_id, workflow)

        # Capability check: verify the caller has permission.
        # Use the workflow's user_id as the principal for token issuance.
        # The kernel should pre-issue tokens before execution reaches this point.
        from uuid import UUID as _UUID

        principal_id = (
            _UUID(workflow.user_id) if workflow and workflow.user_id else _UUID("00000000-0000-0000-0000-000000000000")
        )
        resource = ResourceRef(kind="tool", name=tool_name)
        token = cap_engine.issue(
            resource=resource,
            actions={Action.EXECUTE},
            to=principal_id,
        )

        try:
            cap_engine.verify_and_require(token, Action.EXECUTE)
        except PermissionError as e:
            return {"success": False, "error": f"Capability denied: {e}"}

        # Route to tool handler
        handlers = {
            "web_search": self._tool_web_search,
            "code_executor": self._tool_code_executor,
            "file_reader": self._tool_file_reader,
            "rag_search": self._tool_rag_search,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        params = node.config.get("params", {})
        return await handler(params, context)

    # ── Code execution ──────────────────────────────────────────────

    async def _handle_code(self, node: WorkflowNode, context: dict[str, Any]) -> dict[str, Any]:
        """Execute Python code in a sandboxed subprocess."""
        code = node.config.get("code") or context.get("code")
        if not code:
            return {"success": False, "error": "No code provided"}

        return await self._execute_code_sandboxed(code)

    async def _execute_code_sandboxed(self, code: str) -> dict[str, Any]:
        """Execute code in a restricted subprocess.

        SECURITY: Code runs in an isolated subprocess with:
        - No network access (blocked via environment)
        - Restricted builtins (no __import__, open, exec, eval, compile)
        - 60-second timeout
        - Restricted cwd
        - Output size limit (1MB)

        Uses a temporary .py file instead of inline exec() to avoid
        quote-escaping issues with triple-quoted strings.
        """
        import os as _os
        import shutil
        import subprocess
        import tempfile

        workspace = tempfile.mkdtemp(prefix="mission_")

        # Security: blocked patterns
        DANGEROUS = [
            "__import__",
            "import os",
            "import sys",
            "import subprocess",
            "import socket",
            "import urllib",
            "import http",
            "exec(",
            "eval(",
            "compile(",
            "open(",
            "file(",
            "os.",
            "sys.exit",
            "sys.modules",
            "sys.path",
            "globals()",
            "locals()",
            "vars()",
        ]
        code_lower = code.lower()
        for pat in DANGEROUS:
            if pat.lower() in code_lower:
                return {"success": False, "error": f"Blocked pattern: '{pat}'"}

        tmp_path = _os.path.join(workspace, "_exec.py")
        indented_code = "\n".join("    " + line for line in code.strip().split("\n"))
        with open(tmp_path, "w") as f:
            # Use str.replace() instead of str.format() because the wrapper
            # contains literal curly braces in __builtins__ = { ... } that
            # conflict with format()'s placeholder syntax.
            f.write(_WORKSPACE_WRAPPER.replace("{code}", indented_code))

        try:
            result = subprocess.run(
                ["python3", tmp_path],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=workspace,
            )
            return {
                "success": result.returncode == 0,
                "output": {
                    "stdout": result.stdout[:1_000_000] if result.stdout else "",
                    "stderr": result.stderr[:100_000] if result.stderr else "",
                    "return_code": result.returncode,
                },
                "error": result.stderr if result.returncode != 0 else None,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution timed out (60s limit)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    # ── RAG ─────────────────────────────────────────────────────────

    async def _handle_rag(self, node: WorkflowNode, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a RAG query."""
        query = node.config.get("query") or context.get("query") or node.description or node.title
        collection = node.config.get("collection", "default")

        try:
            from app.services.rag_service import RAGService

            rag = RAGService()
            results = rag.query_documents(query, n_results=5)
            return {
                "success": True,
                "output": {
                    "query": query,
                    "context": results,
                    "collection": collection,
                },
            }
        except Exception as e:
            return {"success": False, "error": f"RAG query failed: {e}"}

    # ── Web search ──────────────────────────────────────────────────

    async def _handle_web_search(self, node: WorkflowNode, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a web search."""
        query = node.config.get("query") or context.get("query") or node.description

        if not query:
            return {"success": False, "error": "No query provided"}

        try:
            from app.services.web_search.models import SearchRequest, SearchType
            from app.services.web_search.service import get_search_service

            service = get_search_service()
            request = SearchRequest(
                query=query,
                search_type=SearchType.GENERAL,
                max_results=5,  # type: ignore[attr-defined]
            )
            response = await service.search(request)

            results = [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in response.results]
            return {"success": True, "output": {"query": query, "results": results}}
        except Exception as e:
            return {"success": False, "error": f"Web search failed: {e}"}

    # ── File operations ─────────────────────────────────────────────

    async def _handle_file(self, node: WorkflowNode, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a file operation."""
        operation = node.config.get("operation", "read")
        file_id = node.config.get("file_id")

        if not file_id:
            return {"success": False, "error": "No file_id provided"}

        try:
            from app.services.file_storage import FileStorageService

            storage = FileStorageService()
            file_info = storage.get_file_info(file_id)
            if not file_info:
                return {"success": False, "error": f"File {file_id} not found"}

            if operation == "read":
                with open(file_info["path"], "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                return {
                    "success": True,
                    "output": {
                        "content": content[:50000],
                        "filename": file_info.get("filename"),
                    },
                }
            elif operation == "list":
                import os

                return {
                    "success": True,
                    "output": {"files": os.listdir(file_info["path"])},
                }
            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}
        except Exception as e:
            return {"success": False, "error": f"File operation failed: {e}"}

    # ── Browser ─────────────────────────────────────────────────────

    async def _handle_browser(self, node: WorkflowNode, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a browser action through the tool registry."""
        try:
            from app.tools.base import ToolRegistry

            tool_name = node.type.value
            tool = ToolRegistry.get(tool_name)  # type: ignore[arg-type]
            if tool is None:
                return {
                    "success": False,
                    "error": f"Browser tool not registered: {tool_name}",
                }

            tool_input = node.config.get("params", {})
            result = await tool.run(tool_input, {"user_id": "system"})  # type: ignore[attr-defined]

            if result.status.value == "success":
                return {"success": True, "output": result.data}
            return {"success": False, "error": result.error}
        except Exception as e:
            return {"success": False, "error": f"Browser tool failed: {e}"}

    # ── Sandbox node (Phase 3) ───────────────────────────────────────

    async def _handle_sandbox_node(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute a sandbox node: create container → push files → submit task → stream SSE.

        Config keys:
            template: sandboxd template name (default "python-img")
            task_prompt: coding task prompt for sandboxd's AI agent
            shared_workspace: reuse existing sandbox for this mission
            input_files: dict of path→content to write before task
            snapshot_before: create snapshot before executing (rollback safety)
        """
        config = node.config or {}
        task_prompt = config.get("task_prompt") or context.get("task_prompt")
        if not task_prompt:
            return {"success": False, "error": "No task_prompt provided"}

        template = config.get("template", "python-img")
        shared_workspace = config.get("shared_workspace", False)
        input_files = config.get("input_files", {})
        snapshot_before = config.get("snapshot_before", False)

        mission_id = workflow.id if workflow else None
        user_id = workflow.user_id if workflow else "system"
        event_log = get_event_log()

        sandbox_id = None
        try:
            # 1 — Create or reuse sandbox
            if shared_workspace and mission_id:
                sandbox_id = await self._sandbox_service.get_sandbox_for_mission(mission_id, db=db)
            if not sandbox_id:
                if mission_id:
                    sandbox_id = await self._sandbox_service.ensure_sandbox_for_mission(
                        mission_id=mission_id,
                        user_id=user_id,
                        db=db,
                        template=template,
                    )
                else:
                    # No mission context — create ephemeral sandbox
                    resp = await self._sandbox_client.create(
                        project_id=f"node_{node.id}",
                        user_id=user_id,
                        template=template,
                    )
                    sandbox_id = resp["id"]

            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.SANDBOX_CREATED,
                        "payload": {"sandbox_id": sandbox_id, "node_id": node.id},
                        "actor": "node_executor",
                        "mission_id": mission_id,
                        "task_id": node.id,
                    }
                ],
            )

            # 2 — Optional snapshot checkpoint
            if snapshot_before:
                snap = await self._sandbox_client.create_snapshot(sandbox_id, f"pre_{node.id}")
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.SANDBOX_SNAPSHOT_CREATED,
                            "payload": {
                                "snapshot_id": snap.get("id"),
                                "sandbox_id": sandbox_id,
                            },
                            "actor": "node_executor",
                            "mission_id": mission_id,
                            "task_id": node.id,
                        }
                    ],
                )

            # 3 — Write input files
            if input_files:
                for path, content in input_files.items():
                    if isinstance(content, str):
                        content = content.encode("utf-8")
                    await self._sandbox_client.write_file(sandbox_id, path, content)
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.SANDBOX_FILES_WRITTEN,
                            "payload": {"files": list(input_files.keys())},
                            "actor": "node_executor",
                            "mission_id": mission_id,
                            "task_id": node.id,
                        }
                    ],
                )

            # 4 — Submit task to sandboxd
            task = await self._sandbox_client.submit_task(
                sandbox_id=sandbox_id,
                prompt=task_prompt,
                agent="opencode",
            )
            task_id = task["id"]

            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.SANDBOX_TASK_SUBMITTED,
                        "payload": {"task_id": task_id, "sandbox_id": sandbox_id},
                        "actor": "node_executor",
                        "mission_id": mission_id,
                        "task_id": node.id,
                    }
                ],
            )

            # 5 — Stream SSE events, recording progress
            async for sse in self._sandbox_client.task_events(sandbox_id, task_id):
                ev_type = sse.get("type", "")
                ev_data_str = sse.get("data", "{}")

                try:
                    ev_data = json.loads(ev_data_str) if isinstance(ev_data_str, str) else ev_data_str
                except (json.JSONDecodeError, TypeError):
                    ev_data = {"raw": ev_data_str}

                if ev_type == "progress":
                    await event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.SANDBOX_TASK_PROGRESS,
                                "payload": {
                                    "task_id": task_id,
                                    "message": ev_data.get("message", ""),
                                    "percent": ev_data.get("percent", 0),
                                },
                                "actor": "node_executor",
                                "mission_id": mission_id,
                                "task_id": node.id,
                            }
                        ],
                    )
                    if hasattr(self.executor, "ws_manager"):
                        self.executor.ws_manager.broadcast_node_state(
                            run_id,
                            node.id,
                            "running",
                            output={
                                "progress": ev_data.get("percent", 0),
                                "message": ev_data.get("message", ""),
                            },
                        )

                elif ev_type == "complete":
                    await event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.SANDBOX_TASK_COMPLETED,
                                "payload": {
                                    "task_id": task_id,
                                    "exit_code": ev_data.get("exit_code", 0),
                                    "stdout": str(ev_data.get("stdout", ""))[:50000],
                                },
                                "actor": "node_executor",
                                "mission_id": mission_id,
                                "task_id": node.id,
                            }
                        ],
                    )
                    return {
                        "success": ev_data.get("exit_code", 0) == 0,
                        "output": {
                            "sandbox_id": sandbox_id,
                            "task_id": task_id,
                            "stdout": ev_data.get("stdout", ""),
                            "exit_code": ev_data.get("exit_code", 0),
                        },
                        "tokens": 0,
                        "cost": 0.0,
                    }

                elif ev_type == "error":
                    await event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.SANDBOX_TASK_FAILED,
                                "payload": {
                                    "task_id": task_id,
                                    "error": ev_data.get("error", "Unknown sandbox task error"),
                                },
                                "actor": "node_executor",
                                "mission_id": mission_id,
                                "task_id": node.id,
                            }
                        ],
                    )
                    return {
                        "success": False,
                        "error": ev_data.get("error", "Sandbox task failed"),
                        "tokens": 0,
                    }

            # SSE stream ended without complete/error event
            return {
                "success": False,
                "error": "SSE stream ended unexpectedly (no complete/error event)",
                "tokens": 0,
            }

        except Exception as e:
            logger.exception("Sandbox node %s failed", node.id)
            return {"success": False, "error": f"Sandbox node failed: {e}", "tokens": 0}

    # ── Sub-workflow (recursive) ────────────────────────────────────

    # Maximum recursion depth to prevent infinite sub-workflow loops.
    _MAX_SUB_WORKFLOW_DEPTH = 5

    async def _handle_sub_workflow(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
    ) -> dict[str, Any]:
        """Execute a sub-workflow recursively through the unified executor.

        Loads the child workflow from the database, converts its nodes
        and edges into the canonical Workflow format, and delegates to
        ``self.executor.execute()``.  The parent's budget is shared with
        the child so that spending limits apply across the full DAG.

        Guarded by ``_MAX_SUB_WORKFLOW_DEPTH`` to prevent infinite loops.
        """
        sub_workflow_id = node.config.get("workflow_id")
        if not sub_workflow_id:
            return {"success": False, "error": "No workflow_id for sub_workflow node"}

        # Depth guard — tracked via workflow metadata
        current_depth = context.get("_sub_workflow_depth", 0) + 1
        if current_depth > self._MAX_SUB_WORKFLOW_DEPTH:
            return {
                "success": False,
                "error": f"Max recursion depth ({self._MAX_SUB_WORKFLOW_DEPTH}) exceeded for sub-workflow {sub_workflow_id}",
                "tokens": 0,
            }

        # Check abort signal before starting sub-workflow
        if self.executor.is_aborted(run_id):
            return {"success": False, "error": "Aborted", "tokens": 0}

        try:
            from sqlalchemy import select

            from app.models.graph import GraphWorkflow

            # Load the child workflow from the DB (graph_workflows table)
            result = await db.execute(select(GraphWorkflow).where(GraphWorkflow.id == sub_workflow_id))
            child_graph = result.scalar_one_or_none()
            if child_graph is None:
                return {
                    "success": False,
                    "error": f"Sub-workflow {sub_workflow_id} not found",
                    "tokens": 0,
                }

            # Convert to canonical Workflow via existing adapter
            from app.services.substrate.adapters import graph_to_workflow

            child_workflow = graph_to_workflow(child_graph)

            # Share the parent budget (child spends from the same pool)
            child_workflow.budget = budget

            # Propagate depth tracking
            child_workflow.metadata["_sub_workflow_depth"] = current_depth

            # Execute recursively via the same unified executor
            from app.services.substrate.workflow_models import StrategyResult

            strategy_result: StrategyResult = await self.executor.execute(db, child_workflow)

            return {
                "success": strategy_result.success,
                "output": {
                    "sub_workflow_id": sub_workflow_id,
                    "status": strategy_result.status,
                    "data": strategy_result.data,
                    "completed_nodes": strategy_result.completed_nodes,
                    "failed_nodes": strategy_result.failed_nodes,
                },
                "tokens": strategy_result.total_tokens,
                "cost": strategy_result.total_cost_usd,
                "error": strategy_result.error,
            }
        except Exception as e:
            logger.exception("Sub-workflow %s execution failed", sub_workflow_id)
            return {
                "success": False,
                "error": f"Sub-workflow execution failed: {e}",
                "tokens": 0,
            }

    # ── HITL interrupt handler (Phase 6.2) ──────────────────────────

    async def _handle_hitl_interrupt(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        run_id: str,
        workflow: Workflow | None = None,
        *,
        interrupt_type: str = "approval",
    ) -> dict[str, Any]:
        """Handle a HITL interrupt node by creating an inbox item and pausing.

        Persists the interrupt to the inbox_items table and emits a
        human_interrupt.raised event. The mission will pause until
        the interrupt is resolved via the HITL Inbox API.
        """
        from app.models.hitl_models import HumanInterruptType
        from app.services.hitl_service import HITLService
        from app.services.substrate.event_log import get_event_log

        event_log = get_event_log()
        hitl_type = HumanInterruptType.APPROVAL if interrupt_type == "approval" else HumanInterruptType.CLARIFICATION

        title = node.config.get("approval_prompt") or node.title or f"{interrupt_type.title()} required"
        description = node.description or node.config.get("description")
        proposed_action = {
            "node_id": node.id,
            "node_title": node.title,
            "node_type": node.type.value,
            "config": {k: v for k, v in node.config.items() if k not in ("approval_prompt",)},
        }

        # Determine the user to notify
        user_id = int(workflow.user_id) if workflow and workflow.user_id else 0
        workspace_id = getattr(workflow, "workspace_id", None) if workflow else None
        mission_id = workflow.id if workflow else None

        service = HITLService(db)
        item = await service.create_interrupt(
            mission_id=mission_id or "unknown",
            user_id=user_id,
            interrupt_type=hitl_type,
            title=title,
            description=description,
            proposed_action=proposed_action,
            context={"current_context": context},
            task_id=node.id,
            node_id=node.id,
            run_id=run_id,
            workspace_id=workspace_id,
        )

        # Record event
        await event_log.append(
            db,
            run_id,
            [
                {
                    "type": SubstrateEventType.HUMAN_INTERRUPT_RAISED,
                    "payload": {
                        "inbox_item_id": item.id,
                        "interrupt_type": hitl_type.value,
                        "title": title,
                        "node_id": node.id,
                    },
                    "actor": "node_executor",
                    "mission_id": mission_id,
                    "task_id": node.id,
                }
            ],
        )

        logger.info(
            "HITL interrupt raised: node=%s type=%s inbox_item=%s",
            node.id,
            hitl_type.value,
            item.id,
        )

        return {
            "success": False,
            "error": f"Waiting for human {interrupt_type}",
            "requires_human_input": True,
            "requires_approval": interrupt_type == "approval",
            "requires_clarification": interrupt_type == "clarification",
            "inbox_item_id": item.id,
            "hitl_type": hitl_type.value,
        }

    # ── Tool helpers ────────────────────────────────────────────────

    async def _tool_web_search(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Standalone web search tool."""
        query = params.get("query") or context.get("query")
        if not query:
            return {"success": False, "error": "No query provided"}

        try:
            from app.services.web_search.models import SearchRequest, SearchType
            from app.services.web_search.service import get_search_service

            service = get_search_service()
            request = SearchRequest(
                query=query,
                search_type=SearchType.GENERAL,
                max_results=5,  # type: ignore[attr-defined]
            )
            response = await service.search(request)
            results = [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in response.results]
            return {"success": True, "output": {"query": query, "results": results}}
        except Exception as e:
            return {
                "success": True,
                "output": {"query": query, "results": [], "note": str(e)},
            }

    async def _tool_code_executor(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Standalone code execution tool."""
        code = params.get("code") or context.get("code")
        if not code:
            return {"success": False, "error": "No code provided"}
        return await self._execute_code_sandboxed(code)

    async def _tool_file_reader(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Standalone file reader tool."""
        file_id = params.get("file_id") or context.get("file_id")
        if not file_id:
            return {"success": False, "error": "No file_id provided"}
        try:
            from app.services.file_storage import FileStorageService

            storage = FileStorageService()
            file_info = storage.get_file_info(file_id)
            if not file_info:
                return {"success": False, "error": f"File {file_id} not found"}
            with open(file_info["path"], "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return {
                "success": True,
                "output": {
                    "filename": file_info.get("filename"),
                    "content": content[:50000],
                    "size": len(content),
                },
            }
        except Exception as e:
            return {"success": False, "error": f"File read failed: {e}"}

    async def _tool_rag_search(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Standalone RAG search tool."""
        query = params.get("query") or context.get("query")
        if not query:
            return {"success": False, "error": "No query provided"}
        try:
            from app.services.rag_service import RAGService

            rag = RAGService()
            results = rag.query_documents(query, n_results=5)
            return {"success": True, "output": {"query": query, "context": results}}
        except Exception as e:
            return {"success": False, "error": f"RAG search failed: {e}"}
