"""Unit tests for Wave 1: ModelRouter user_id propagation + error chain verification."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


# ═══════════════════════════════════════════════════════════════════════════════
# Task 1 — ModelRouter user_id propagation
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelRouterIsModelAvailable:
    """_is_model_available must use user_id and db params for BYOK key checks."""

    @pytest.mark.asyncio
    async def test_is_model_available_accepts_user_id_and_db_params(self):
        """Method signature includes user_id and db keyword arguments."""
        import inspect

        from app.services.llm_router import ModelRouter

        router = ModelRouter()
        sig = inspect.signature(router._is_model_available)
        assert "user_id" in sig.parameters
        assert "db" in sig.parameters
        assert "model_id" in sig.parameters

    @pytest.mark.asyncio
    async def test_is_model_available_returns_false_with_no_key(self):
        """When no platform key and no BYOK key, returns False gracefully."""
        from unittest.mock import MagicMock

        from app.services.llm_router import ModelRouter

        router = ModelRouter(user_id="user-no-key")
        # No platform key, no BYOK key in DB
        with patch("app.services.llm_router._resolve_provider") as mock_resolve:
            mock_resolve.return_value = (  # returns empty API key
                "https://api.example.com",
                "",  # no platform key
                "some-model",
            )
            mock_db = MagicMock()
            # Simulate empty BYOK lookup
            with patch.object(router, "_get_byok_key", AsyncMock(return_value=(None, None))):
                result = await router._is_model_available(
                    "some-provider/some-model",
                    user_id="user-no-key",
                    db=mock_db,
                )
        assert result is False

    @pytest.mark.asyncio
    async def test_is_model_available_returns_true_with_platform_key(self):
        """When platform API key exists, returns True without needing BYOK."""
        from app.services.llm_router import ModelRouter

        router = ModelRouter()
        with patch("app.services.llm_router._resolve_provider") as mock_resolve:
            mock_resolve.return_value = (
                "https://api.example.com",
                "sk-valid-platform-key",
                "some-model",
            )
            result = await router._is_model_available(
                "some-provider/some-model",
                user_id="user-1",
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_is_model_available_uses_self_user_id_as_fallback(self):
        """When user_id not passed, falls back to self.user_id from constructor."""
        from app.services.llm_router import ModelRouter

        mock_db = MagicMock()
        router = ModelRouter(user_id="user-from-constructor", db_session=mock_db)
        # _resolve_provider returns empty key, so we check BYOK
        with patch("app.services.llm_router._resolve_provider") as mock_resolve:
            mock_resolve.return_value = ("https://api.example.com", "", "some-model")
            with patch.object(router, "_get_byok_key", AsyncMock(return_value=("sk-byok", None))):
                result = await router._is_model_available(
                    "some-provider/some-model",
                    # user_id NOT passed explicitly — uses self.user_id
                )
        assert result is True


# ═══════════════════════════════════════════════════════════════════════════════
# Task 2 — Error chain propagation
# ═══════════════════════════════════════════════════════════════════════════════


class TestLlmExecutorErrorPropagation:
    """LlmExecutor must NOT swallow success=False from ModelRouter.route_request()."""

    @pytest.mark.asyncio
    async def test_propagates_route_request_failure_with_error_message(self):
        """When route_request returns success=False, execute_llm returns the error."""
        from app.services.llm_executor import LlmExecutor

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": False,
                "error": "No models available for user",
                "cost": {"input_tokens": 0, "output_tokens": 0},
            }
        )
        executor = LlmExecutor(get_model_router=lambda: mock_router)

        mock_task = MagicMock()
        mock_task.description = "Test task"
        mock_task.title = "Test"
        mock_task.assigned_model = None

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is False
        assert result["error"] == "No models available for user"
        assert result["tokens"] == 0

    @pytest.mark.asyncio
    async def test_returns_error_on_missing_user_id(self):
        """If route_request fails because user_id not propagated, error surfaces."""
        from app.services.llm_executor import LlmExecutor

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": False,
                "error": "No API key available for model 'deepseek/model'. Add a BYOK key.",
                "cost": {},
            }
        )
        executor = LlmExecutor(get_model_router=lambda: mock_router)

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"
        mock_task.assigned_model = "deepseek/model"

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is False
        assert "BYOK" in result["error"]


class TestTaskExecutorErrorPropagation:
    """TaskExecutor must pass LlmExecutor errors through to the caller."""

    @pytest.mark.asyncio
    async def test_execute_task_llm_case_propagates_error(self):
        """llm/llm_call task type returns LlmExecutor's error dict unchanged."""
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(
            return_value={
                "success": False,
                "error": "LLM call failed: timeout",
                "tokens": 0,
            }
        )

        executor = TaskExecutor(llm_executor=mock_llm)

        mock_task = MagicMock()
        mock_task.task_type = "llm"
        mock_task.title = "Test LLM task"
        mock_task.id = "task-1"
        mock_task.status = MagicMock()
        mock_task.started_at = None
        mock_task.input_data = {"prompt": "Hello"}
        mock_task.dependencies = None

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = uuid4()

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert result["success"] is False
        assert "timeout" in result["error"]


class TestMissionExecutorErrorPropagation:
    """MissionExecutor must check result.get('success') and mark tasks FAILED."""

    @pytest.mark.asyncio
    async def test_execute_task_failure_propagates_through_chain(self):
        """When TaskExecutor returns success=False, error is accessible via result dict."""
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(
            return_value={
                "success": False,
                "error": "Simulated task failure",
            }
        )

        executor = TaskExecutor(llm_executor=mock_llm)

        mock_task = MagicMock()
        mock_task.task_type = "llm"
        mock_task.title = "Failing Task"
        mock_task.id = uuid4()
        mock_task.status = MagicMock()
        mock_task.started_at = None
        mock_task.input_data = {"prompt": "Test"}
        mock_task.dependencies = None

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = uuid4()

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert result["success"] is False
        assert result["error"] == "Simulated task failure"

    @pytest.mark.asyncio
    async def test_task_success_path_still_works(self):
        """Success tasks return success=True with output — regression guard."""
        from app.services.task_executor import TaskExecutor

        mock_llm = MagicMock()
        mock_llm.execute_llm = AsyncMock(
            return_value={
                "success": True,
                "output": {"text": "Task completed successfully"},
                "tokens": 1000,
            }
        )

        executor = TaskExecutor(llm_executor=mock_llm)

        mock_task = MagicMock()
        mock_task.task_type = "llm"
        mock_task.title = "Success Task"
        mock_task.id = uuid4()
        mock_task.status = MagicMock()
        mock_task.started_at = None
        mock_task.input_data = {"prompt": "Test"}
        mock_task.dependencies = None

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = uuid4()

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})
        assert result["success"] is True
        assert result["output"]["text"] == "Task completed successfully"


class TestErrorChainNoSilentFallback:
    """Verify no silent fallback to empty output anywhere in the chain."""

    @pytest.mark.asyncio
    async def test_llm_executor_never_returns_success_with_empty_text(self):
        """Empty/whitespace LLM response must fail, not succeed silently."""
        from app.services.llm_executor import LlmExecutor

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "   \n  ",
                "cost": {"input_tokens": 5, "output_tokens": 1},
            }
        )
        executor = LlmExecutor(get_model_router=lambda: mock_router)

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"
        mock_task.assigned_model = None

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is False
        assert "empty" in str(result.get("error", "")).lower()

    @pytest.mark.asyncio
    async def test_route_request_failure_is_never_treated_as_success(self):
        """success=False from route_request must NEVER be treated as success."""
        from app.services.llm_router import ModelRouter

        router = ModelRouter()
        result = router._maybe_dict_result(
            result=MagicMock(success=False, content="", error="Boom", usage={}),
            duration=0,
            user_id="user-1",
            is_admin=False,
        )
        # When self.db is None (executor path), returns dict
        assert isinstance(result, dict)
        assert result["success"] is False
        assert result["error"] == "Boom"
        assert result["response"] == ""
        # Content should NOT be propagated as success output
        assert not result.get("response")  # empty on failure
