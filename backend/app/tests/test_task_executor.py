"""Unit tests for app/services/task_executor.py — TaskExecutor."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


# ── execute_task dispatch ─────────────────────────────────────────────────────


class TestExecuteTaskDispatch:
    """TaskExecutor.execute_task: routes to correct sub-handler by task_type."""

    @pytest.mark.asyncio
    async def test_routes_llm_task(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(return_value={"success": True, "output": {"text": "ok"}})

        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = "mission-1"
        mock_task = MagicMock()
        mock_task.task_type = "llm"
        mock_task.title = "LLM Task"
        mock_task.input_data = {}
        mock_task.dependencies = []

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert result["success"] is True
        mock_llm.execute_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_llm_call_variant(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(return_value={"success": True, "output": {"text": "ok"}})

        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = "mission-1"
        mock_task = MagicMock()
        mock_task.task_type = "llm_call"
        mock_task.title = "LLM Call"
        mock_task.input_data = {}
        mock_task.dependencies = []

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert result["success"] is True
        mock_llm.execute_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_routes_tool_task(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = "m1"
        mock_task = MagicMock()
        mock_task.task_type = "tool"
        mock_task.title = "Tool Task"
        mock_task.input_data = {"tool_id": "web_search", "params": {"query": "test"}}
        mock_task.dependencies = []

        with patch.object(executor, "_execute_tool", AsyncMock(return_value={"success": True})):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_tool_execution_variant(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "tool_execution"
        mock_task.title = "Tool Exec"
        mock_task.input_data = {"tool_id": "code_executor", "params": {}}
        mock_task.dependencies = []

        with patch.object(executor, "_execute_tool", AsyncMock(return_value={"success": True})):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_rag_task(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "rag"
        mock_task.title = "RAG Query"
        mock_task.input_data = {"query": "test", "collection": "docs"}
        mock_task.dependencies = []

        with patch.object(executor, "_execute_rag", AsyncMock(return_value={"success": True})):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_rag_query_variant(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "rag_query"
        mock_task.title = "RAG"
        mock_task.input_data = {"query": "test"}
        mock_task.dependencies = []

        with patch.object(executor, "_execute_rag", AsyncMock(return_value={"success": True})):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_web_search_task(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "web_search"
        mock_task.title = "Web Search"
        mock_task.input_data = {"query": "test"}
        mock_task.dependencies = []

        with patch.object(executor, "_execute_web_search", AsyncMock(return_value={"success": True})):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_code_task(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "code"
        mock_task.title = "Code Exec"
        mock_task.input_data = {"code": "print(1)"}
        mock_task.dependencies = []

        with patch.object(executor, "_execute_code", AsyncMock(return_value={"success": True})):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_code_execution_variant(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "code_execution"
        mock_task.title = "Code Exec"
        mock_task.input_data = {"code": "print(1)"}
        mock_task.dependencies = []

        with patch.object(executor, "_execute_code", AsyncMock(return_value={"success": True})):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_file_operation_task(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "file_operation"
        mock_task.title = "File Op"
        mock_task.input_data = {"operation": "read", "path": "test.txt"}
        mock_task.dependencies = []

        with patch.object(executor, "_execute_file", AsyncMock(return_value={"success": True})):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_review_task(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "review"
        mock_task.title = "Human Review"
        mock_task.input_data = {}
        mock_task.dependencies = []

        with patch.object(
            executor,
            "_request_human_input",
            AsyncMock(return_value={"success": False, "requires_input": True}),
        ):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["requires_input"] is True

    @pytest.mark.asyncio
    async def test_routes_human_review_variant(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "human_review"
        mock_task.title = "Human Review"
        mock_task.input_data = {}
        mock_task.dependencies = []

        with patch.object(
            executor,
            "_request_human_input",
            AsyncMock(return_value={"success": False, "requires_input": True}),
        ):
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
            assert result["requires_input"] is True

    @pytest.mark.asyncio
    async def test_routes_browser_task(self):
        from app.services.task_executor import TaskExecutor

        mock_browser = MagicMock()
        mock_browser.execute_browser_tool = AsyncMock(return_value={"success": True, "output": {}})

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, browser_runner=mock_browser, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "browser_navigate"
        mock_task.title = "Navigate"
        mock_task.input_data = {"url": "https://x"}
        mock_task.dependencies = []

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert result["success"] is True
        mock_browser.execute_browser_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_task_type(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "nonexistent_type"
        mock_task.title = "Unknown"
        mock_task.input_data = {}
        mock_task.dependencies = []

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert result["success"] is False
        assert "Unknown task type" in result["error"]

    @pytest.mark.asyncio
    async def test_sets_task_status_to_running_on_start(self):
        from app.models.mission_models import MissionTaskStatus
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(return_value={"success": True, "output": {"text": "ok"}})

        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = "m1"
        mock_task = MagicMock()
        mock_task.task_type = "llm"
        mock_task.title = "Test"
        mock_task.input_data = {}
        mock_task.dependencies = []

        await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert mock_task.status == MissionTaskStatus.RUNNING
        assert mock_task.started_at is not None

    @pytest.mark.asyncio
    async def test_reraises_retryable_error(self):
        from app.services.mission_errors import RetryableMissionError
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(side_effect=RetryableMissionError("overloaded"))

        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "llm"
        mock_task.title = "Test"
        mock_task.input_data = {}
        mock_task.dependencies = []

        with pytest.raises(RetryableMissionError):
            await executor.execute_task(mock_db, mock_mission, mock_task, {})

    @pytest.mark.asyncio
    async def test_catches_permanent_error(self):
        from app.services.mission_errors import PermanentMissionError
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(side_effect=PermanentMissionError("forbidden"))

        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "llm"
        mock_task.title = "Test"
        mock_task.input_data = {}
        mock_task.dependencies = []

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert result["success"] is False
        assert result.get("permanent") is True

    @pytest.mark.asyncio
    async def test_catches_general_exception(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(side_effect=RuntimeError("something broke"))

        executor = TaskExecutor(llm_executor=mock_llm, log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_task = MagicMock()
        mock_task.task_type = "llm"
        mock_task.title = "Test"
        mock_task.input_data = {}
        mock_task.dependencies = []

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert result["success"] is False


# ── _execute_tool ─────────────────────────────────────────────────────────────


class TestExecuteTool:
    """TaskExecutor._execute_tool: tool handler routing."""

    @pytest.mark.asyncio
    async def test_falls_back_to_llm_when_no_tool_id(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(return_value={"success": True, "output": {"text": "fallback"}})

        executor = TaskExecutor(llm_executor=mock_llm)
        mock_task = MagicMock()
        mock_task.title = "Test"
        mock_mission = MagicMock()

        result = await executor._execute_tool(mock_task, {"params": {}}, mock_mission)
        assert result["success"] is True
        mock_llm.execute_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()
        mock_task.title = "Test"

        result = await executor._execute_tool(mock_task, {"tool_id": "nonexistent", "params": {}})
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_routes_to_web_search_handler(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()
        mock_task.title = "Test"

        with patch(
            "app.services.mission_tools.tool_web_search",
            AsyncMock(return_value={"success": True}),
        ):
            result = await executor._execute_tool(mock_task, {"tool_id": "web_search", "params": {"query": "test"}})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_to_code_executor_handler(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        with patch(
            "app.services.mission_tools.tool_code_executor",
            AsyncMock(return_value={"success": True}),
        ):
            result = await executor._execute_tool(mock_task, {"tool_id": "code_executor", "params": {"code": "1+1"}})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_to_file_reader_handler(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        with patch(
            "app.services.mission_tools.tool_file_reader",
            AsyncMock(return_value={"success": True}),
        ):
            result = await executor._execute_tool(mock_task, {"tool_id": "file_reader", "params": {"path": "x"}})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_to_rag_search_handler(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        with patch.object(executor, "_execute_rag_query", AsyncMock(return_value={"success": True})):
            result = await executor._execute_tool(mock_task, {"tool_id": "rag_search", "params": {"query": "test"}})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_rag_requires_query(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        result = await executor._execute_tool(mock_task, {"tool_id": "rag_search", "params": {}})
        assert result["success"] is False
        assert "No query" in result["error"]

    @pytest.mark.asyncio
    async def test_rag_uses_input_data_query_fallback(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        with patch.object(executor, "_execute_rag_query", AsyncMock(return_value={"success": True})) as mock_rag:
            result = await executor._execute_tool(
                mock_task,
                {"tool_id": "rag_search", "params": {}, "query": "fallback query"},
            )
        assert result["success"] is True
        mock_rag.assert_called_once_with("fallback query", "default")

    @pytest.mark.asyncio
    async def test_routes_to_api_caller_handler(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        with patch(
            "app.services.mission_tools.tool_api_caller",
            AsyncMock(return_value={"success": True}),
        ):
            result = await executor._execute_tool(mock_task, {"tool_id": "api_caller", "params": {"url": "x"}})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_routes_to_data_analyzer_handler(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        with patch(
            "app.services.mission_tools.tool_data_analyzer",
            AsyncMock(return_value={"success": True}),
        ):
            result = await executor._execute_tool(mock_task, {"tool_id": "data_analyzer", "params": {"data": []}})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_report_generator_returns_error_without_model_router(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        result = await executor._execute_tool(mock_task, {"tool_id": "report_generator", "params": {"data": {}}})
        assert result["success"] is False
        assert "ModelRouter" in result["error"]

    @pytest.mark.asyncio
    async def test_report_generator_generates_report(self):
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "# Report\n\nContent here",
                "cost": {"input_tokens": 5, "output_tokens": 20},
            }
        )
        mock_llm._get_model_router = lambda: mock_router

        executor = TaskExecutor(llm_executor=mock_llm)
        mock_task = MagicMock()
        mock_mission = MagicMock()
        mock_mission.user_id = 1

        result = await executor._execute_tool(
            mock_task,
            {
                "tool_id": "report_generator",
                "params": {"data": {"key": "val"}, "format": "markdown"},
            },
            mission=mock_mission,
        )
        assert result["success"] is True
        assert result["output"]["format"] == "markdown"

    @pytest.mark.asyncio
    async def test_tool_catches_retryable_error(self):
        from app.services.mission_errors import RetryableMissionError
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        with (
            patch(
                "app.services.mission_tools.tool_web_search",
                AsyncMock(side_effect=RetryableMissionError("overloaded")),
            ),
            pytest.raises(RetryableMissionError),
        ):
            await executor._execute_tool(mock_task, {"tool_id": "web_search", "params": {"query": "test"}})

    @pytest.mark.asyncio
    async def test_tool_catches_permanent_error(self):
        from app.services.mission_errors import PermanentMissionError
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        with patch(
            "app.services.mission_tools.tool_web_search",
            AsyncMock(side_effect=PermanentMissionError("forbidden")),
        ):
            result = await executor._execute_tool(mock_task, {"tool_id": "web_search", "params": {"query": "test"}})
        assert result["success"] is False
        assert result.get("permanent") is True

    @pytest.mark.asyncio
    async def test_tool_catches_general_exception(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()

        with patch(
            "app.services.mission_tools.tool_web_search",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            result = await executor._execute_tool(mock_task, {"tool_id": "web_search", "params": {"query": "test"}})
        assert result["success"] is False
        assert "Tool execution failed" in result["error"]


# ── _resolve_input ────────────────────────────────────────────────────────────


class TestResolveInput:
    """TaskExecutor._resolve_input: dependency output merging."""

    def test_returns_input_as_is_without_dependencies(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()
        mock_task.input_data = {"key": "value"}
        mock_task.dependencies = None

        result = executor._resolve_input(mock_task, {})
        assert result == {"key": "value"}

    def test_resolves_empty_input_data(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()
        mock_task.input_data = None
        mock_task.dependencies = None

        result = executor._resolve_input(mock_task, {})
        assert result == {}

    def test_merges_dependency_outputs(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()
        mock_task.input_data = {"prompt": "Hello"}
        mock_task.dependencies = [0, 1]

        dep_0 = MagicMock()
        dep_0.order_index = 0
        dep_0.output_data = {"text": "From dep 0"}

        dep_1 = MagicMock()
        dep_1.order_index = 1
        dep_1.output_data = {"text": "From dep 1"}

        task_map = {0: dep_0, 1: dep_1}

        result = executor._resolve_input(mock_task, task_map)
        assert result["prompt"] == "Hello"
        assert result["dep_0"] == {"text": "From dep 0"}
        assert result["dep_1"] == {"text": "From dep 1"}

    def test_skips_missing_dependencies(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()
        mock_task.input_data = {"prompt": "Hello"}
        mock_task.dependencies = [0, 5]  # index 5 doesn't exist

        dep_0 = MagicMock()
        dep_0.order_index = 0
        dep_0.output_data = {"text": "ok"}

        task_map = {0: dep_0}

        result = executor._resolve_input(mock_task, task_map)
        assert "dep_0" in result
        assert "dep_5" not in result

    def test_skips_dependency_without_output(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        mock_task = MagicMock()
        mock_task.input_data = {}
        mock_task.dependencies = [0]

        dep_0 = MagicMock()
        dep_0.order_index = 0
        dep_0.output_data = None

        task_map = {0: dep_0}

        result = executor._resolve_input(mock_task, task_map)
        assert "dep_0" not in result


# ── _aggregate_results ────────────────────────────────────────────────────────


class TestAggregateResults:
    """TaskExecutor._aggregate_results: result aggregation."""

    def test_empty_tasks(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        result = executor._aggregate_results([])
        assert result["summary"]["total_tasks"] == 0
        assert result["summary"]["completed"] == 0
        assert result["summary"]["failed"] == 0

    def test_mixed_results(self):
        from app.models.mission_models import MissionTaskStatus
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        completed = MagicMock()
        completed.status = MissionTaskStatus.COMPLETED
        completed.title = "Done"
        completed.task_type = "llm"
        completed.output_data = {"text": "ok"}
        completed.tokens_used = 100
        completed.cost = 0.01

        failed = MagicMock()
        failed.status = MissionTaskStatus.FAILED
        failed.title = "Fail"
        failed.task_type = "tool"

        pending = MagicMock()
        pending.status = MissionTaskStatus.PENDING
        pending.title = "Pending"
        pending.task_type = "code"

        result = executor._aggregate_results([completed, failed, pending])
        assert result["summary"]["total_tasks"] == 3
        assert result["summary"]["completed"] == 1
        assert result["summary"]["failed"] == 1
        assert len(result["tasks"]) == 1  # only completed

    def test_all_completed(self):
        from app.models.mission_models import MissionTaskStatus
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        tasks = []
        for i in range(3):
            t = MagicMock()
            t.status = MissionTaskStatus.COMPLETED
            t.title = f"Task {i}"
            t.task_type = "llm"
            t.output_data = {}
            t.tokens_used = 0
            t.cost = 0.0
            tasks.append(t)

        result = executor._aggregate_results(tasks)
        assert result["summary"]["completed"] == 3
        assert len(result["tasks"]) == 3

    def test_includes_generated_at(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        result = executor._aggregate_results([])
        assert "generated_at" in result


# ── _apply_fallback ───────────────────────────────────────────────────────────


class TestApplyFallback:
    """TaskExecutor._apply_fallback: failure recovery strategies."""

    @pytest.mark.asyncio
    async def test_human_escalate_pauses_mission(self):
        from app.models.mission_models import MissionStatus
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor(log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.fallback_strategy = "human_escalate"
        mock_mission.status = "running"
        mock_task = MagicMock()
        mock_task.title = "Failing Task"

        await executor._apply_fallback(mock_db, mock_mission, mock_task, "something went wrong")
        assert mock_mission.status == MissionStatus.PAUSED
        assert "Failing Task" in mock_mission.error_message

    @pytest.mark.asyncio
    async def test_abort_fails_mission(self):
        from app.models.mission_models import MissionStatus
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor(log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.fallback_strategy = "abort"
        mock_task = MagicMock()
        mock_task.title = "Broken Task"

        await executor._apply_fallback(mock_db, mock_mission, mock_task, "unrecoverable")
        assert mock_mission.status == MissionStatus.FAILED

    @pytest.mark.asyncio
    async def test_skip_does_nothing(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor(log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.fallback_strategy = "skip"
        mock_mission.status = "running"
        mock_mission.error_message = None
        mock_task = MagicMock()
        mock_task.title = "Skippable"

        await executor._apply_fallback(mock_db, mock_mission, mock_task, "non-critical")
        assert mock_mission.status == "running"  # unchanged

    @pytest.mark.asyncio
    async def test_retry_does_nothing(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor(log_callback=AsyncMock())
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.fallback_strategy = "retry"
        mock_mission.status = "running"
        mock_task = MagicMock()
        mock_task.title = "Retryable"

        await executor._apply_fallback(mock_db, mock_mission, mock_task, "transient error")
        assert mock_mission.status == "running"  # unchanged

    @pytest.mark.asyncio
    async def test_logs_fallback_application(self):
        from app.services.task_executor import TaskExecutor

        mock_log = AsyncMock()
        executor = TaskExecutor(log_callback=mock_log)
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = "m1"
        mock_mission.fallback_strategy = "skip"
        mock_task = MagicMock()
        mock_task.id = "t1"
        mock_task.title = "Test"

        await executor._apply_fallback(mock_db, mock_mission, mock_task, "error")
        mock_log.assert_called_once()
        call_args = mock_log.call_args[0]
        assert call_args[1] == "m1"  # mission_id
        assert call_args[2] == "t1"  # task_id
