import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestMissionExecutorInterface:
    def test_mission_executor_has_execute_mission(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        assert callable(getattr(executor, "execute_mission", None))

    def test_mission_executor_wires_submodules(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        assert executor.cost_tracker is not None
        assert executor.llm_exec is not None
        assert executor.planner is not None
        assert executor.task_exec is not None
        assert callable(getattr(executor.task_exec, "execute_task", None))


# ── LlmExecutor tests (moved from MissionExecutor._execute_llm) ───────────────


class TestExecuteLlmErrorPropagation:
    """LlmExecutor.execute_llm must NOT swallow success=False from ModelRouter."""

    @pytest.mark.asyncio
    async def test_execute_llm_propagates_model_router_failure(self):
        from app.services.llm_executor import LlmExecutor

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": False,
                "error": "No models available",
            }
        )
        executor = LlmExecutor(get_model_router=lambda: mock_router)

        mock_task = MagicMock()
        mock_task.description = "Test task"
        mock_task.title = "Test"

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_llm_returns_success_true_on_valid_response(self):
        from app.services.llm_executor import LlmExecutor

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "This is the LLM response",
                "cost": {"input_tokens": 10, "output_tokens": 20},
            }
        )
        executor = LlmExecutor(get_model_router=lambda: mock_router)

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is True
        assert result["output"]["text"] == "This is the LLM response"

    @pytest.mark.asyncio
    async def test_execute_llm_treats_empty_response_as_failure(self):
        from app.services.llm_executor import LlmExecutor

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "",
                "cost": {"input_tokens": 5, "output_tokens": 0},
            }
        )
        executor = LlmExecutor(get_model_router=lambda: mock_router)

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_llm_returns_failure_when_model_router_unavailable(self):
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor(get_model_router=lambda: None)

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is False
        assert "ModelRouter" in result.get("error", "")


# ── MissionExecutor._classify_error (still on executor) ───────────────────────


class TestClassifyError:
    """_classify_error: retryable vs permanent classification."""

    def test_timeout_is_retryable(self):
        import httpx

        from app.services.mission_errors import RetryableMissionError
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        exc = httpx.TimeoutException("timed out")
        result = executor._classify_error(exc)
        assert isinstance(result, RetryableMissionError)

    def test_429_is_retryable(self):
        import httpx

        from app.services.mission_errors import RetryableMissionError
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        mock_response = MagicMock()
        mock_response.status_code = 429
        exc = httpx.HTTPStatusError(
            "rate limited", request=MagicMock(), response=mock_response
        )
        result = executor._classify_error(exc)
        assert isinstance(result, RetryableMissionError)

    def test_401_is_permanent(self):
        import httpx

        from app.services.mission_errors import PermanentMissionError
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        mock_response = MagicMock()
        mock_response.status_code = 401
        exc = httpx.HTTPStatusError(
            "unauthorized", request=MagicMock(), response=mock_response
        )
        result = executor._classify_error(exc)
        assert isinstance(result, PermanentMissionError)

    def test_mission_error_passthrough(self):
        from app.services.mission_errors import PermanentMissionError
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        exc = PermanentMissionError("test")
        result = executor._classify_error(exc)
        assert result is exc

    def test_unknown_is_retryable(self):
        from app.services.mission_errors import RetryableMissionError
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        exc = ValueError("something weird")
        result = executor._classify_error(exc)
        assert isinstance(result, RetryableMissionError)


# ── MissionExecutor._transition_status (still on executor) ────────────────────


class TestTransitionStatus:
    """_transition_status: both valid and invalid transitions."""

    @pytest.mark.asyncio
    async def test_transitions_and_logs(self):
        from app.models.mission_models import MissionStatus
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_mission = MagicMock()
        mock_mission.id = uuid4()
        mock_mission.title = "Test"
        mock_mission.status = "pending"
        mock_mission.error_message = None
        mock_mission.completed_at = None

        mock_log_fn = AsyncMock()
        with patch.object(executor, "_log", mock_log_fn):
            await executor._transition_status(
                mock_db, mock_mission, MissionStatus.RUNNING, cause="test"
            )

        assert mock_mission.status == MissionStatus.RUNNING
        mock_db.commit.assert_called()
        mock_log_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_sets_completed_at_on_terminal(self):
        from app.models.mission_models import MissionStatus
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_mission = MagicMock()
        mock_mission.id = uuid4()
        mock_mission.title = "Test"
        mock_mission.status = "running"
        mock_mission.error_message = None
        mock_mission.completed_at = None

        with patch.object(executor, "_log", AsyncMock()):
            await executor._transition_status(
                mock_db, mock_mission, MissionStatus.COMPLETED, cause="done"
            )

        assert mock_mission.completed_at is not None


# ── MissionPlanner tests (moved from MissionExecutor._build_plan_prompt) ──────


class TestBuildPlanPrompt:
    """_build_plan_prompt: verify prompt structure (now on MissionPlanner)."""

    def test_includes_mission_fields(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner()
        mock_mission = MagicMock()
        mock_mission.title = "Build a website"
        mock_mission.description = "Create a landing page"
        mock_mission.mission_type = "development"
        mock_mission.constraints = {}

        prompt = planner._build_plan_prompt(mock_mission)
        assert "Build a website" in prompt
        assert "Create a landing page" in prompt
        assert "development" in prompt
        assert "JSON array" in prompt


# ── TaskExecutor._aggregate_results tests ─────────────────────────────────────


class TestAggregateResults:
    """_aggregate_results: edge cases (now on TaskExecutor)."""

    def test_empty_tasks(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()
        result = executor._aggregate_results([])
        assert result["summary"]["total_tasks"] == 0
        assert result["summary"]["completed"] == 0

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

        result = executor._aggregate_results([completed, failed])
        assert result["summary"]["total_tasks"] == 2
        assert result["summary"]["completed"] == 1
        assert result["summary"]["failed"] == 1
        assert len(result["tasks"]) == 1  # only completed


# ── CostTracker.estimate_cost tests ───────────────────────────────────────────


class TestEstimateCost:
    """CostTracker.estimate_cost: correct arithmetic."""

    def test_deepseek_cost(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("deepseek-chat", 1_000_000)
        assert abs(cost - 0.14) < 0.01

    def test_default_cost(self):
        from app.services.cost_tracker import CostTracker

        tracker = CostTracker()
        cost = tracker.estimate_cost("unknown-model", 1_000_000)
        assert abs(cost - 0.5) < 0.01


# ── Concurrency safety ────────────────────────────────────────────────────────


class TestConcurrencySafety:
    """execute_mission must use with_for_update() and validate state after lock."""

    @pytest.mark.asyncio
    async def test_execute_mission_validates_runnable_state(self):
        """Mission not in QUEUED or PLANNED should be rejected after lock."""
        from app.models.mission_models import MissionStatus
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_mission = MagicMock()
        mock_mission.id = uuid4()
        mock_mission.title = "Test"
        mock_mission.status = MissionStatus.COMPLETED  # not runnable
        mock_mission.user_id = 1

        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_mission
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.mission_executor.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_session.return_value.__aexit__.return_value = None
            with patch("app.services.mission_executor.tracer"):
                result = await executor.execute_mission(uuid4())

        assert result["success"] is False
        assert "Cannot execute" in result.get("error", "")
