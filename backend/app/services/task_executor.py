"""Task execution dispatch — extracted from MissionExecutor.

Handles the execution of individual tasks within a mission, delegating to
specialized sub-modules for LLM, browser, RAG, code, and tool operations.

Usage::

    executor = TaskExecutor(
        llm_executor=LlmExecutor(...),
        browser_runner=BrowserTaskRunner(),
        cost_tracker=CostTracker(),
        get_rag_service=lambda: rag_svc,
        workspace="/tmp/missions",
        log_callback=log_fn,
    )
    result = await executor.execute_task(db, mission, task, task_map)
"""

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.services.mission_errors import PermanentMissionError, RetryableMissionError

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Dispatches and executes individual mission tasks.

    Routes tasks by ``task_type`` to the appropriate backend (LLM, tool,
    browser, RAG, web_search, code, file_operation, review) and applies
    fallback strategies on failure.

    Args:
        llm_executor: :class:`LlmExecutor` for LLM-based tasks.
        browser_runner: :class:`BrowserTaskRunner` for browser-based tasks.
        cost_tracker: :class:`CostTracker` for recording LLM activity.
        get_rag_service: Callable returning a ``RAGService`` instance (or
            ``None``).  Called lazily for late binding.
        workspace: Path to the mission workspace directory for file
            operations.
        resource_limits: Dict of sandbox resource limits (e.g.
            ``{"max_memory_mb": 256, "timeout_seconds": 30}``).
        log_callback: Async callable with signature
            ``(db, mission_id, task_id, level, message, extra_data)``.

    Example:
        >>> executor = TaskExecutor(
        ...     llm_executor=llm_exec,
        ...     browser_runner=browser_runner,
        ...     workspace="/data/missions/workspace",
        ... )
        >>> result = await executor.execute_task(db, mission, task, task_map)
    """

    def __init__(
        self,
        llm_executor=None,
        browser_runner=None,
        cost_tracker=None,
        get_rag_service=None,
        workspace: str = "",
        resource_limits: dict[str, Any] | None = None,
        log_callback=None,
    ):
        self.llm_executor = llm_executor
        self.browser_runner = browser_runner
        self.cost_tracker = cost_tracker
        self._get_rag_service = get_rag_service or (lambda: None)
        self.workspace = workspace
        self.resource_limits = resource_limits or {}
        self._log = log_callback or _nop_log

    # ── Main dispatch ──────────────────────────────────────────────────────

    async def execute_task(self, db, mission, task, task_map: dict[str, Any]) -> dict[str, Any]:
        """Execute a single task, routing to the appropriate handler.

        Sets ``task.status`` to ``RUNNING``, resolves dependency outputs,
        dispatches to the backend matching ``task.task_type``, and
        classifies any errors.

        Args:
            db: SQLAlchemy async session.
            mission: Mission model instance.
            task: Task model instance with ``.task_type``,
                ``.input_data``, and ``.dependencies``.
            task_map: Dict of ``{order_index: task}`` for dependency
                resolution.

        Returns:
            Dict:
                - ``success`` (bool)
                - ``output`` (Any) — backend-specific result
                - ``error`` (str) — on failure
                - ``permanent`` (bool, optional) — ``True`` for
                  non-retryable errors
                - ``requires_input`` (bool, optional) — ``True`` for
                  review tasks awaiting human input

        Raises:
            RetryableMissionError: Transient failure the caller should retry.
        """
        from app.models.mission_models import MissionTaskStatus

        task.status = MissionTaskStatus.RUNNING
        task.started_at = datetime.now(UTC)
        await db.commit()

        await self._log(db, mission.id, task.id, "info", f"Executing: {task.title}")

        input_data = self._resolve_input(task, task_map)

        result: dict[str, Any] = {"success": False, "error": "Unknown task type"}

        try:
            from app.services.browser_task_runner import BROWSER_TASK_TYPES

            match task.task_type:
                case "llm" | "llm_call":
                    result = await self.llm_executor.execute_llm(task, input_data, mission, db)
                case "tool" | "tool_execution":
                    result = await self._execute_tool(task, input_data, mission, db)
                case "rag" | "rag_query":
                    result = await self._execute_rag(task, input_data)
                case "web_search":
                    result = await self._execute_web_search(task, input_data, mission, db)
                case "code" | "code_execution":
                    result = await self._execute_code(task, input_data, mission, db)
                case "file_operation":
                    result = await self._execute_file(task, input_data, mission, db)
                case "review" | "human_review":
                    result = await self._request_human_input(db, mission, task)
                case "http_integration" | "http_request":
                    result = await self._execute_http_integration(task, input_data, mission, db)
                case "integration_action":
                    result = await self._execute_integration_action(task, input_data, mission, db)
                case _ if task.task_type in BROWSER_TASK_TYPES:
                    result = await self.browser_runner.execute_browser_tool(task, input_data, mission)
                case _:
                    result = {
                        "success": False,
                        "error": f"Unknown task type: {task.task_type}",
                    }
        except RetryableMissionError as e:
            logger.warning("Retryable error in task %s: %s", task.id, e)
            raise
        except PermanentMissionError as e:
            logger.error("Permanent error in task %s: %s", task.id, e)
            result = {"success": False, "error": str(e), "permanent": True}
        except Exception as e:
            logger.exception("Error in task %s", task.id)
            result = {"success": False, "error": str(e)}

        return result

    # ── Tool execution ─────────────────────────────────────────────────────

    async def _execute_tool(self, task, input_data: dict[str, Any], mission=None, db=None) -> dict[str, Any]:
        """Route to a named tool handler or fall back to LLM.

        Args:
            task: Task model instance.
            input_data: Dict with ``tool_id`` and ``params`` keys.
            mission: Optional mission for attribution.
            db: Optional SQLAlchemy session.

        Returns:
            Tool execution result dict.

        Raises:
            RetryableMissionError: Re-raised from tool handlers.
        """
        tool_id = input_data.get("tool_id")
        params = input_data.get("params", {})

        if not tool_id:
            logger.info("No tool_id for task %s, using LLM fallback", task.title)
            return await self.llm_executor.execute_llm(task, input_data, mission, db)

        tool_handlers = {
            "web_search": self._tool_web_search,
            "code_executor": self._tool_code_executor,
            "file_reader": self._tool_file_reader,
            "rag_search": self._tool_rag_search,
            "api_caller": self._tool_api_caller,
            "data_analyzer": self._tool_data_analyzer,
            "report_generator": self._tool_report_generator,
        }

        handler = tool_handlers.get(tool_id)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_id}"}

        try:
            if tool_id == "report_generator":
                return await handler(params, input_data, mission, db=db)
            return await handler(params, input_data)
        except RetryableMissionError as e:
            logger.warning("Retryable tool error in task %s: %s", task.id, e)
            raise
        except PermanentMissionError as e:
            logger.error("Permanent tool error in task %s: %s", task.id, e)
            return {"success": False, "error": str(e), "permanent": True}
        except Exception as e:
            return {"success": False, "error": f"Tool execution failed: {e!s}"}

    # ── Individual tool handlers ───────────────────────────────────────────

    async def _tool_web_search(self, params: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
        """Run a web search via mission_tools."""
        from app.services.mission_tools import tool_web_search

        return await tool_web_search(params, input_data)

    async def _tool_code_executor(self, params: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute code via mission_tools."""
        from app.services.mission_tools import tool_code_executor

        return await tool_code_executor(params, input_data)

    async def _tool_file_reader(self, params: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
        """Read files via mission_tools."""
        from app.services.mission_tools import tool_file_reader

        return await tool_file_reader(params, input_data)

    async def _tool_rag_search(self, params: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
        """Run a RAG query with query validation.

        Args:
            params: Dict with ``query`` and optionally ``collection``.
            input_data: Fallback for ``query`` if not in params.

        Returns:
            RAG search result dict.
        """
        query = params.get("query", input_data.get("query"))
        if not query:
            return {"success": False, "error": "No query provided"}

        return await self._execute_rag_query(query, params.get("collection", "default"))

    async def _tool_api_caller(self, params: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
        """Call an external API via mission_tools."""
        from app.services.mission_tools import tool_api_caller

        return await tool_api_caller(params, input_data)

    async def _tool_data_analyzer(self, params: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
        """Analyze data via mission_tools."""
        from app.services.mission_tools import tool_data_analyzer

        return await tool_data_analyzer(params, input_data)

    async def _tool_report_generator(
        self,
        params: dict[str, Any],
        input_data: dict[str, Any],
        mission=None,
        db=None,
    ) -> dict[str, Any]:
        """Generate a report via LLM.

        Args:
            params: Dict with ``data`` and ``format`` (e.g. ``"markdown"``).
            input_data: Fallback data source.
            mission: Optional mission for user attribution.
            db: Optional SQLAlchemy session for cost recording.

        Returns:
            Report generation result dict with ``output.report`` and
            ``output.format`` keys.
        """
        data = params.get("data", input_data)
        format_type = params.get("format", "markdown")

        model_router = self.llm_executor._get_model_router() if self.llm_executor else None
        if not model_router:
            return {"success": False, "error": "ModelRouter not available"}

        prompt = (
            f"Generate a {format_type} report based on the following data:\n\n"
            f"{json.dumps(data, indent=2, default=str)[: settings.MISSION_REPORT_JSON_SLICE_LIMIT]}\n\n"
            "Create a well-structured report with:\n"
            "1. Executive Summary\n"
            "2. Key Findings\n"
            "3. Detailed Analysis\n"
            "4. Recommendations\n"
        )

        start_time = time.monotonic()
        model_id = "deepseek-v4-flash"
        provider = "deepseek"
        success = False
        error_msg = None
        prompt_tokens = 0
        completion_tokens = 0

        try:
            user_id = str(mission.user_id) if mission and mission.user_id else "system"
            response = await model_router.route_request(
                model_preference="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                user_id=user_id,
                db_session=db,
                is_admin=False,
            )

            if not response.get("success"):
                error_msg = response.get("error", "LLM call failed")
                return {"success": False, "error": error_msg, "tokens": 0}

            report_content = response.get("response", "")
            cost_info = response.get("cost", {})
            prompt_tokens = cost_info.get("input_tokens", 0)
            completion_tokens = cost_info.get("output_tokens", 0)
            tokens = prompt_tokens + completion_tokens
            success = True

            return {
                "success": True,
                "output": {"report": report_content, "format": format_type},
                "tokens": tokens,
            }
        except Exception as e:
            error_msg = str(e)
            return {"success": False, "error": str(e)}
        finally:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            if self.cost_tracker:
                await self.cost_tracker.record_llm_call(
                    db=db,
                    mission_id=str(mission.id) if mission else None,
                    task_id=None,
                    model_id=model_id,
                    provider=provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=self.cost_tracker.estimate_cost(model_id, prompt_tokens + completion_tokens),
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error_msg,
                )

    # ── RAG execution ──────────────────────────────────────────────────────

    async def _execute_rag(self, task, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute a RAG (retrieval-augmented generation) task.

        Args:
            task: Task model with ``.description`` and ``.title`` as
                fallback query source.
            input_data: Dict with ``query`` and ``collection`` keys.

        Returns:
            RAG query result dict.
        """
        query = input_data.get("query", task.description or task.title)
        collection = input_data.get("collection", "default")

        return await self._execute_rag_query(query, collection)

    async def _execute_rag_query(self, query: str, collection: str = "default") -> dict[str, Any]:
        """Query the RAG service for relevant documents.

        Args:
            query: Search query string.
            collection: Qdrant collection name.

        Returns:
            Dict with ``success``, ``output.query``, ``output.context``,
            and ``output.collection`` keys.
        """
        rag_service = self._get_rag_service()

        if not rag_service:
            return {"success": False, "error": "RAGService not available"}

        try:
            context = rag_service.query_documents(query, n_results=5)

            return {
                "success": True,
                "output": {
                    "query": query,
                    "context": context,
                    "collection": collection,
                },
            }
        except Exception as e:
            return {"success": False, "error": f"RAG query failed: {e!s}"}

    # ── Web execution ──────────────────────────────────────────────────────

    async def _execute_web_search(self, task, input_data: dict[str, Any], mission=None, db=None) -> dict[str, Any]:
        """Execute a web search or scrape task.

        If ``input_data`` contains a ``url`` key, performs a web scrape.
        Otherwise falls back to LLM (semantic search).

        Args:
            task: Task model instance.
            input_data: Dict with optional ``url`` and ``query`` keys.
            mission: Optional mission for LLM fallback.
            db: Optional SQLAlchemy session for LLM fallback.

        Returns:
            Web search result dict.
        """
        url = input_data.get("url")
        query = input_data.get("query", task.description)

        if url:
            return await self._execute_web_scrape(url)
        else:
            logger.info("Task %s: No url/search API, falling back to LLM", task.id)
            return await self.llm_executor.execute_llm(task, input_data, mission, db)

    async def _execute_web_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, Any] | None = None,
        body: Any = None,
    ) -> dict[str, Any]:
        """Make a generic HTTP request via mission_tools."""
        from app.services.mission_tools import execute_web_request

        return await execute_web_request(url, method, headers, body)

    async def _execute_web_scrape(self, url: str) -> dict[str, Any]:
        """Scrape and extract content from a URL."""
        from app.services.mission_tools import execute_web_scrape

        return await execute_web_scrape(url)

    # ── Code execution ─────────────────────────────────────────────────────

    async def _execute_code(self, task, input_data: dict[str, Any], mission=None, db=None) -> dict[str, Any]:
        """Execute Python code in a sandbox.

        Falls back to LLM if no code is provided in ``input_data``.

        Args:
            task: Task model instance.
            input_data: Dict with ``code`` key containing Python source.
            mission: Optional mission for LLM fallback.
            db: Optional SQLAlchemy session for LLM fallback.

        Returns:
            Code execution result dict.
        """
        code = input_data.get("code")

        if not code:
            logger.info("Task %s: No code in input_data, falling back to LLM", task.id)
            return await self.llm_executor.execute_llm(task, input_data, mission, db)

        return await self._execute_code_from_string(code)

    async def _execute_code_from_string(self, code: str) -> dict[str, Any]:
        """Execute a Python code string in a sandbox.

        Args:
            code: Python source code as a string.

        Returns:
            Sandbox execution result dict.
        """
        from app.services.mission_code_sandbox import execute_python_in_sandbox

        return execute_python_in_sandbox(code, self.workspace, self.resource_limits)

    # ── File execution ─────────────────────────────────────────────────────

    async def _execute_file(self, task, input_data: dict[str, Any], mission=None, db=None) -> dict[str, Any]:
        """Execute a file operation (read, write, list) in the workspace.

        Falls back to LLM if no ``path`` is provided in ``input_data``.

        Args:
            task: Task model instance.
            input_data: Dict with ``operation`` (``"read"``, ``"write"``,
                ``"list"``) and ``path`` keys.  ``content`` is required
                for ``"write"``.
            mission: Optional mission for LLM fallback.
            db: Optional SQLAlchemy session for LLM fallback.

        Returns:
            File operation result dict.
        """
        operation = input_data.get("operation", "read")
        path = input_data.get("path")

        if not path:
            logger.info("Task %s: No path in input_data, falling back to LLM", task.id)
            return await self.llm_executor.execute_llm(task, input_data, mission, db)

        full_path = os.path.join(self.workspace, path)

        try:
            if operation == "read":
                with open(full_path, "r") as f:
                    return {"success": True, "output": {"content": f.read()}}
            elif operation == "write":
                content = input_data.get("content", "")
                with open(full_path, "w") as f:
                    f.write(content)
                return {"success": True, "output": {"path": full_path}}
            elif operation == "list":
                return {
                    "success": True,
                    "output": {"files": os.listdir(full_path)},
                }
            else:
                return {
                    "success": False,
                    "error": f"Unknown operation: {operation}",
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Integration action execution ───────────────────────────────────────

    async def _execute_integration_action(
        self, task, input_data: dict[str, Any], mission=None, db=None
    ) -> dict[str, Any]:
        """Execute a pre-built integration action via the action registry.

        Expects ``input_data`` to contain ``connection_id``,
        ``action_name``, and ``params``.

        Args:
            task: Task model instance.
            input_data: Dict with connection_id, action_name, params.
            mission: Mission for user context.
            db: SQLAlchemy async session.

        Returns:
            Action execution result dict.
        """
        connection_id = input_data.get("connection_id")
        action_name = input_data.get("action_name")
        params = input_data.get("params", {})

        if not connection_id:
            return {"success": False, "error": "Missing connection_id"}
        if not action_name:
            return {"success": False, "error": "Missing action_name"}

        if not mission or not mission.user_id:
            return {"success": False, "error": "Mission has no user_id"}

        try:
            from app.services.action_registry import execute_action

            return await execute_action(
                user_id=str(mission.user_id),
                connection_id=connection_id,
                action_name=action_name,
                params=params,
                db=db,
            )
        except Exception as exc:
            logger.exception("Integration action failed for task %s", task.id)
            return {"success": False, "error": str(exc)}

    # ── HTTP integration execution ─────────────────────────────────────────

    async def _execute_http_integration(
        self, task, input_data: dict[str, Any], mission=None, db=None
    ) -> dict[str, Any]:
        """Execute an HTTP outbound integration task.

        Args:
            task: Task model with integration_config_id in input_data.
            input_data: Dict with integration_config_id, method, path, headers, body, query_params.
            mission: Mission for attribution.
            db: SQLAlchemy async session.

        Returns:
            HTTP execution result dict.
        """
        integration_config_id = input_data.get("integration_config_id")
        if not integration_config_id:
            return {"success": False, "error": "No integration_config_id provided"}

        try:
            from sqlalchemy import select

            from app.models.integration_models import HttpIntegrationConfig
            from app.services.http_integration_executor import (
                get_http_integration_executor,
            )

            result = await db.execute(
                select(HttpIntegrationConfig).where(
                    HttpIntegrationConfig.id == str(integration_config_id),
                    HttpIntegrationConfig.is_active == True,
                )
            )
            config = result.scalars().first()
            if not config:
                return {
                    "success": False,
                    "error": "Integration config not found or inactive",
                }

            executor = get_http_integration_executor()
            return await executor.execute(
                db=db,
                config=config,
                method=input_data.get("method", "GET"),
                path=input_data.get("path", ""),
                headers=input_data.get("headers"),
                body=input_data.get("body"),
                query_params=input_data.get("query_params"),
                mission_id=str(mission.id) if mission else None,
                task_id=str(task.id) if task and hasattr(task, "id") else None,
            )
        except Exception as e:
            logger.exception("HTTP integration execution failed for task %s: %s", task.id, e)
            return {"success": False, "error": f"HTTP integration error: {e!s}"}

    # ── Human input / fallback ─────────────────────────────────────────────

    async def _request_human_input(self, db, mission, task) -> dict[str, Any]:
        """Pause execution and request human review input.

        Sets ``task.status`` to ``"waiting_input"`` and commits.

        Args:
            db: SQLAlchemy async session.
            mission: Mission model instance.
            task: Task model instance.

        Returns:
            Dict with ``requires_input: True``.
        """
        task.status = "waiting_input"
        await db.commit()

        await self._log(db, mission.id, task.id, "info", "Waiting for human input")

        return {
            "success": False,
            "error": "Waiting for human input",
            "requires_input": True,
        }

    async def _apply_fallback(self, db, mission, task, error: str) -> None:
        """Apply the mission's fallback strategy after a task failure.

        Supports four strategies defined on ``mission.fallback_strategy``:
        ``"human_escalate"`` (pauses mission), ``"abort"`` (fails mission),
        ``"skip"``, and ``"retry"`` (both no-ops at this level — the
        orchestrator handles re-execution).

        Args:
            db: SQLAlchemy async session.
            mission: Mission model instance.
            task: Task model instance.
            error: Error message describing the failure.
        """
        from app.models.mission_models import MissionStatus

        strategy = mission.fallback_strategy or "human_escalate"

        await self._log(
            db,
            mission.id,
            task.id,
            "warning",
            f"Applying fallback strategy: {strategy}",
        )

        match strategy:
            case "human_escalate":
                mission.status = MissionStatus.PAUSED
                mission.error_message = f"Task '{task.title}' requires human attention: {error}"
            case "abort":
                mission.status = MissionStatus.FAILED
                mission.error_message = f"Task '{task.title}' failed: {error}"
            case "skip":
                pass
            case "retry":
                pass

        await db.commit()

    # ── Input resolution / aggregation ─────────────────────────────────────

    def _resolve_input(self, task, task_map: dict[str, Any]) -> dict[str, Any]:
        """Merge a task's input_data with resolved dependency outputs.

        For each index in ``task.dependencies``, looks up the corresponding
        task in ``task_map`` and injects its ``output_data`` as
        ``dep_{index}``.

        Args:
            task: Task with ``.input_data`` (dict or None) and
                ``.dependencies`` (list of ints or None).
            task_map: Dict of ``{order_index: task}``.

        Returns:
            Merged input dict with ``dep_*`` keys for resolved dependencies.
        """
        input_data = task.input_data or {}

        for dep_idx in task.dependencies or []:
            dep_task = next((t for t in task_map.values() if t.order_index == dep_idx), None)
            if dep_task and dep_task.output_data:
                input_data[f"dep_{dep_idx}"] = dep_task.output_data

        return input_data

    def _aggregate_results(self, tasks: list) -> dict[str, Any]:
        """Aggregate results across all tasks into a summary.

        Args:
            tasks: List of task model instances.

        Returns:
            Dict with ``summary`` (total/completed/failed counts),
            ``tasks`` (completed task details), and ``generated_at``
            timestamp.
        """
        from app.models.mission_models import MissionTaskStatus

        completed_tasks = [t for t in tasks if t.status == MissionTaskStatus.COMPLETED]

        return {
            "summary": {
                "total_tasks": len(tasks),
                "completed": len(completed_tasks),
                "failed": len([t for t in tasks if t.status == MissionTaskStatus.FAILED]),
            },
            "tasks": [
                {
                    "title": t.title,
                    "task_type": t.task_type,
                    "output": t.output_data,
                    "tokens_used": t.tokens_used,
                    "cost": t.cost,
                }
                for t in completed_tasks
            ],
            "generated_at": datetime.now(UTC).isoformat(),
        }


async def _nop_log(db, mission_id, task_id, level, message, extra_data=None):
    """No-op log callback used when none is provided to TaskExecutor."""
    pass
