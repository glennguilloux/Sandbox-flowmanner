import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


class TestMissionExecutorInterface:
    def test_mission_executor_has_execute_mission(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        assert callable(getattr(executor, "execute_mission", None))

    def test_mission_executor_has_execute_task(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        assert callable(getattr(executor, "execute_task", None))


class TestExecuteLlmErrorPropagation:
    """_execute_llm must NOT swallow success=False from ModelRouter."""

    @pytest.mark.asyncio
    async def test_execute_llm_propagates_model_router_failure(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": False,
                "error": "No models available",
            }
        )
        executor.model_router = mock_router

        mock_task = MagicMock()
        mock_task.description = "Test task"
        mock_task.title = "Test"

        result = await executor._execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_llm_returns_success_true_on_valid_response(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "This is the LLM response",
                "cost": {"input_tokens": 10, "output_tokens": 20},
            }
        )
        executor.model_router = mock_router

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"

        result = await executor._execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is True
        assert result["output"]["text"] == "This is the LLM response"

    @pytest.mark.asyncio
    async def test_execute_llm_treats_empty_response_as_failure(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "",
                "cost": {"input_tokens": 5, "output_tokens": 0},
            }
        )
        executor.model_router = mock_router

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"

        result = await executor._execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_execute_llm_returns_failure_when_model_router_unavailable(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        executor.model_router = None

        with patch.object(executor, "_get_model_router", return_value=None):
            mock_task = MagicMock()
            mock_task.description = "Test"
            mock_task.title = "Test"

            result = await executor._execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is False
        assert "ModelRouter" in result.get("error", "")
