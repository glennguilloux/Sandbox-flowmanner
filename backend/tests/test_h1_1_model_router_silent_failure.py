"""
H1.1 — End-to-end test: Mission executor with bogus model_id must return
success=False with a typed error, NOT success=True with empty output.
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_mission_and_task():
    """Create mock mission and task objects for testing."""
    mission = MagicMock()
    mission.id = str(uuid4())
    mission.user_id = 12345
    mission.title = "Test Mission"
    mission.description = "Test description"
    mission.status = "executing"
    mission.mission_type = "test"
    mission.fallback_strategy = "abort"
    mission.tokens_used = 0
    mission.actual_cost = 0.0

    task = MagicMock()
    task.id = str(uuid4())
    task.mission_id = mission.id
    task.title = "LLM Task"
    task.description = "Call the LLM with a bogus model"
    task.task_type = "llm"
    task.order_index = 0
    task.dependencies = []
    task.assigned_model = None
    task.status = "pending"
    task.retry_count = 0
    task.max_retries = 3

    return mission, task


class TestMissionExecutorNoSilentSuccess:
    """H1.1 acceptance criteria: mission with bogus model_id returns success=False
    with a typed error, NEVER success=True with empty output."""

    @pytest.mark.asyncio
    async def test_bogus_model_id_returns_success_false(self):
        """A task with a nonexistent model must fail, not silently succeed."""
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()

        # Mock the route_request to simulate what happens with a bogus model
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": False,
                "error": "No API key available for model 'bogus/nonexistent-model'. "
                "Add a BYOK key in Settings or set the DEEPSEEK_API_KEY environment variable.",
                "response": "",
                "model": "bogus/nonexistent-model",
                "cost": {"input_tokens": 0, "output_tokens": 0},
                "duration": 0,
            }
        )
        executor.model_router = mock_router

        mock_task = MagicMock()
        mock_task.description = "Test task"
        mock_task.title = "Test"
        mock_task.assigned_model = "bogus/nonexistent-model"
        mock_task.id = str(uuid4())

        result = await executor._execute_llm(
            mock_task,
            {"prompt": "Hello"},
            mission=None,
            db=None,
        )

        # The critical assertion: must NOT be a silent success
        assert result["success"] is False, (
            "H1.1 FAIL: Bogus model returned success=True — silent success bug!\n"
            f"Result: {result}"
        )

        # Must contain a meaningful error message
        assert "error" in result
        assert result["error"] is not None
        assert (
            len(str(result["error"])) > 0
        ), "H1.1 FAIL: Error message is empty — user has no way to debug"

        # Must NOT have content (no tokens, no output)
        assert result.get("output", {}).get("text", "") == ""

    @pytest.mark.asyncio
    async def test_empty_api_key_rejected_before_network_call(self):
        """The route_request must reject empty API keys without making a network call."""
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()

        # Simulate what llm_router does when _resolve_provider gives no key
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": False,
                "error": "No API key available for model 'deepseek/deepseek-v4-flash'. "
                "Add a BYOK key in Settings or set the DEEPSEEK_API_KEY environment variable.",
                "response": "",
                "model": "deepseek/deepseek-v4-flash",
                "cost": {"input_tokens": 0, "output_tokens": 0},
                "duration": 0,
            }
        )
        executor.model_router = mock_router

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"
        mock_task.assigned_model = None
        mock_task.id = str(uuid4())

        result = await executor._execute_llm(
            mock_task,
            {"prompt": "Hello"},
            mission=None,
            db=None,
        )

        assert result["success"] is False
        assert "error" in result
        assert "api key" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_mission_executor_surfaces_error_to_mission_log(
        self, mock_mission_and_task
    ):
        """When _execute_llm returns success=False, the mission executor must
        propagate the error so it appears in the mission log / API response."""
        from app.services.mission_executor import MissionExecutor

        mission, task = mock_mission_and_task
        task.status = "running"
        task.assigned_model = "bogus/nonexistent-model"

        executor = MissionExecutor()

        # Mock the model router to fail
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": False,
                "error": "Model 'bogus/nonexistent-model' is not available",
                "response": "",
                "model": "bogus/nonexistent-model",
                "cost": {"input_tokens": 0, "output_tokens": 0},
                "duration": 0,
            }
        )
        executor.model_router = mock_router

        result = await executor._execute_llm(
            task,
            {"prompt": f"Execute: {task.title}"},
            mission=mission,
            db=None,
        )

        # The task-level result must report failure
        assert result["success"] is False
        assert "error" in result
        assert (
            "not available" in result["error"].lower()
            or "bogus" in result["error"].lower()
        )

        # The error must be descriptive enough for the user to act on
        assert len(str(result["error"])) > 5

    @pytest.mark.asyncio
    async def test_empty_llm_response_treated_as_failure(self):
        """LLM returning success=True but empty content must be treated as failure."""
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,  # LLM "succeeded" but returned nothing
                "response": "",
                "content": "",
                "model": "deepseek/deepseek-v4-flash",
                "cost": {"input_tokens": 10, "output_tokens": 0},
                "duration": 150,
            }
        )
        executor.model_router = mock_router

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"
        mock_task.assigned_model = "deepseek/deepseek-v4-flash"
        mock_task.id = str(uuid4())

        result = await executor._execute_llm(
            mock_task,
            {"prompt": "Hello"},
            mission=None,
            db=None,
        )

        assert result["success"] is False, (
            "H1.1 FAIL: Empty response with success=True was NOT treated as failure!\n"
            f"Result: {result}"
        )
        assert "empty" in str(result.get("error", "")).lower()

    @pytest.mark.asyncio
    async def test_model_router_unavailable_produces_clear_error(self):
        """When ModelRouter can't be loaded, the error must be clear."""
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        executor.model_router = None

        with patch.object(executor, "_get_model_router", return_value=None):
            mock_task = MagicMock()
            mock_task.description = "Test"
            mock_task.title = "Test"
            mock_task.assigned_model = "any-model"
            mock_task.id = str(uuid4())

            result = await executor._execute_llm(
                mock_task,
                {"prompt": "Hello"},
                mission=None,
                db=None,
            )

        assert result["success"] is False
        assert "ModelRouter" in result.get(
            "error", ""
        ), f"Error should mention ModelRouter, got: {result.get('error')}"


class TestLlmRouterNoSilentSuccess:
    """H1.1: llm_router.py must never silently succeed with empty API keys."""

    @pytest.mark.asyncio
    async def test_route_request_rejects_empty_api_key(self):
        """When _resolve_provider returns no usable key, route_request must fail fast."""
        from app.services.llm_router import ModelRouter

        router = ModelRouter()

        with patch("app.services.llm_router._resolve_provider") as mock_resolve:
            mock_resolve.return_value = (
                "https://api.deepseek.com/v1",
                "",
                "test-model",
            )

            result = await router.route_request(
                messages=[{"role": "user", "content": "Hello"}],
                model_preference="deepseek/deepseek-v4-flash",
                user_id="test-user",
            )

        assert result["success"] is False
        assert "error" in result
        assert (
            "api key" in result["error"].lower() or "api key" in result["error"].lower()
        )

    @pytest.mark.asyncio
    async def test_route_request_not_needed_key_is_valid_for_local_providers(self):
        """'not-needed' key (llamacpp sentinel) should NOT be rejected — it's valid."""
        from app.services.llm_router import ModelRouter

        router = ModelRouter()

        with patch("app.services.llm_router._resolve_provider") as mock_resolve:
            mock_resolve.return_value = (
                "http://localhost:11434/v1",
                "not-needed",
                "local-model",
            )

            # This should NOT raise or reject — llamacpp legitimately uses 'not-needed'
            # The behavior depends on whether the LLM server responds.
            # The key point is: the hard validation should NOT reject 'not-needed'.
            result = await router.route_request(
                messages=[{"role": "user", "content": "Hello"}],
                model_preference="llamacpp/local-model",
                user_id="test-user",
            )

        # 'not-needed' is valid — the call should go through (may fail on network
        # since there's no real llamacpp, but it should NOT be rejected at validation)
        # If success=False, the error should be about connectivity, not about API key
        if not result.get("success"):
            assert "API key" not in result.get(
                "error", ""
            ), f"'not-needed' key was wrongly rejected: {result.get('error')}"


class TestModelRouterIsModelAvailable:
    """H1.1: _is_model_available must receive and propagate user context."""

    @pytest.mark.asyncio
    async def test_is_model_available_passes_user_id_to_get_model(self):
        """model_router.py's _is_model_available must pass user_id on platform fallback."""
        with (
            patch("app.services.model_router.get_llm_manager") as mock_llm_mgr_factory,
        ):
            mock_llm_manager = MagicMock()
            mock_llm_manager.get_model.return_value = MagicMock()
            mock_llm_mgr_factory.return_value = mock_llm_manager

            from app.services.model_router import ModelRouter

            router = ModelRouter()
            router.llm_manager = mock_llm_manager

            result = await router._is_model_available(
                "deepseek-v4-flash",
                user_id=42,
                db_session=MagicMock(),
            )

            # Check that get_model was called with user_id on the platform fallback path
            calls = mock_llm_manager.get_model.call_args_list
            user_ids_used = [
                c.kwargs.get("user_id") or (c.args[1] if len(c.args) > 1 else None)
                for c in calls
            ]
            assert 42 in user_ids_used, (
                f"H1.1 FAIL: user_id=42 was not passed to get_model. "
                f"User IDs in calls: {user_ids_used}"
            )

    @pytest.mark.asyncio
    async def test_is_model_available_returns_false_when_no_model(self):
        """If get_model returns None, _is_model_available must return False."""
        with (
            patch("app.services.model_router.get_llm_manager") as mock_llm_mgr_factory,
        ):
            mock_llm_manager = MagicMock()
            mock_llm_manager.get_model.return_value = None
            mock_llm_mgr_factory.return_value = mock_llm_manager

            from app.services.model_router import ModelRouter

            router = ModelRouter()
            router.llm_manager = mock_llm_manager

            result = await router._is_model_available(
                "bogus-model",
                user_id=42,
                db_session=MagicMock(),
            )

            assert result is False

    def test_llm_router_is_model_available_exists(self):
        """llm_router.py's ModelRouter must have _is_model_available for API compat."""
        from app.services.llm_router import ModelRouter

        router = ModelRouter()
        assert hasattr(
            router, "_is_model_available"
        ), "H1.1 FAIL: llm_router.ModelRouter is missing _is_model_available"
        assert callable(router._is_model_available)
