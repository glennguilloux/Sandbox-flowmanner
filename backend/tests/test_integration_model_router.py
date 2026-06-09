import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


def _make_router(get_model_return=None, cost_ok=True):
    with (
        patch("app.services.llm_router.get_llm_manager") as mock_llm_mgr_factory,
        patch("app.services.llm_router.get_cost_tracker") as mock_cost_factory,
    ):
        mock_llm_manager = MagicMock()
        mock_llm_manager.get_model.return_value = get_model_return
        mock_llm_mgr_factory.return_value = mock_llm_manager

        mock_cost_tracker = MagicMock()
        mock_cost_tracker.check_permission.return_value = cost_ok
        mock_cost_tracker.check_cost_limits.return_value = cost_ok
        mock_cost_factory.return_value = mock_cost_tracker

        from app.services.llm_router import ModelRouter

        router = ModelRouter()
        router._test_llm_manager = mock_llm_manager
        return router


class TestModelRouterSuccessFlagNotSwallowed:
    @pytest.mark.asyncio
    async def test_route_request_returns_success_false_when_no_models(self):
        router = _make_router(get_model_return=None)
        result = await router.route_request(
            messages=[{"role": "user", "content": "Hello"}],
            user_id="user-1",
            is_admin=False,
        )

        assert isinstance(result, dict)
        assert "success" in result
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_route_request_success_false_contains_error_message(self):
        router = _make_router(get_model_return=None)
        result = await router.route_request(
            messages=[{"role": "user", "content": "Hello"}],
            user_id="user-abc",
            is_admin=False,
        )

        assert result["success"] is False
        assert isinstance(result.get("error"), str)
        assert len(result["error"]) > 0

    @pytest.mark.asyncio
    async def test_route_request_never_returns_empty_response_on_failure(self):
        router = _make_router(get_model_return=None)
        result = await router.route_request(
            messages=[{"role": "user", "content": "Test"}],
            user_id="user-1",
            is_admin=False,
        )

        assert result.get("response") != "" or result["success"] is False


class TestModelRouterBYOKPath:
    @pytest.mark.asyncio
    async def test_model_preference_is_selected_when_available(self):
        mock_llm = MagicMock()
        router = _make_router(get_model_return=mock_llm)
        router.routing_strategy = "local-first"

        selected = await router._select_model(
            user_id="user-byok",
            is_admin=False,
            model_preference="ollama-qwen2.5-14b",
        )

        assert selected == "ollama-qwen2.5-14b"

    @pytest.mark.asyncio
    async def test_model_preference_used_when_in_pool_and_healthy(self):
        mock_llm = MagicMock()
        router = _make_router(get_model_return=mock_llm)

        result = await router._select_model(
            user_id="user-byok",
            is_admin=False,
            model_preference="openrouter-gemma-2-9b-free",
        )

        assert result == "openrouter-gemma-2-9b-free"

    @pytest.mark.asyncio
    async def test_byok_preference_takes_priority_over_local_first_strategy(self):
        mock_llm = MagicMock()

        with (
            patch("app.services.llm_router.get_llm_manager") as mock_llm_mgr_factory,
            patch("app.services.llm_router.get_cost_tracker") as mock_cost_factory,
        ):
            mock_llm_manager = MagicMock()
            mock_llm_manager.get_model.return_value = mock_llm
            mock_llm_mgr_factory.return_value = mock_llm_manager

            mock_cost_tracker = MagicMock()
            mock_cost_tracker.check_permission.return_value = True
            mock_cost_tracker.check_cost_limits.return_value = True
            mock_cost_factory.return_value = mock_cost_tracker

            from app.services.llm_router import ModelRouter

            router = ModelRouter()

        selected = await router._select_model(
            user_id="user-byok",
            is_admin=False,
            model_preference="claude-3-haiku",
        )

        assert selected == "claude-3-haiku"


class TestMissionExecutorErrorPropagation:
    @pytest.mark.asyncio
    async def test_execute_llm_propagates_success_false(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={"success": False, "error": "No models available"}
        )
        executor.model_router = mock_router

        mock_task = MagicMock()
        mock_task.description = "Test task"
        mock_task.title = "Test"

        result = await executor._execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is False
        assert "error" in result
        assert result["error"] != ""

    @pytest.mark.asyncio
    async def test_execute_llm_does_not_return_success_true_with_empty_output(self):
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
    async def test_execute_llm_returns_success_true_with_content(self):
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
    async def test_execute_llm_fails_gracefully_when_router_unavailable(self):
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


class TestModelRouterUserIdPropagation:
    def test_is_model_available_passes_user_id_to_get_model(self):
        mock_llm = MagicMock()
        router = _make_router(get_model_return=mock_llm)

        result = router._is_model_available(
            "ollama-qwen2.5-14b", user_id="user-byok-123", is_admin=False
        )

        router._test_llm_manager.get_model.assert_called_once_with(
            "ollama-qwen2.5-14b", user_id="user-byok-123"
        )
        assert result is True

    def test_is_model_available_returns_false_when_get_model_returns_none(self):
        router = _make_router(get_model_return=None)

        result = router._is_model_available(
            "ollama-qwen2.5-14b", user_id="user-no-key", is_admin=False
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_route_request_passes_user_id_through_to_model_lookup(self):
        mock_llm = MagicMock()

        with (
            patch("app.services.llm_router.get_llm_manager") as mock_llm_mgr_factory,
            patch("app.services.llm_router.get_cost_tracker") as mock_cost_factory,
        ):
            mock_llm_manager = MagicMock()
            mock_llm_manager.get_model.return_value = mock_llm
            mock_llm_mgr_factory.return_value = mock_llm_manager

            mock_cost_tracker = MagicMock()
            mock_cost_tracker.check_permission.return_value = True
            mock_cost_tracker.check_cost_limits.return_value = True
            mock_cost_factory.return_value = mock_cost_tracker

            from app.services.llm_router import ModelRouter

            router = ModelRouter()
            router._test_llm_manager = mock_llm_manager

        mock_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content="Hello", usage_metadata={})
        )

        await router._select_model(user_id="specific-user-id", is_admin=False)

        calls = mock_llm_manager.get_model.call_args_list
        user_ids_used = [
            c.kwargs.get("user_id") or (c.args[1] if len(c.args) > 1 else None)
            for c in calls
        ]
        assert any(uid == "specific-user-id" for uid in user_ids_used)
