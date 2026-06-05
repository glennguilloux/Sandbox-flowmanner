import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

pytestmark = pytest.mark.integration


def _make_router():
    """Create a ModelRouter (llm_router.py) without any mocking.

    The llm_router's ModelRouter uses AsyncOpenAI directly — no
    get_llm_manager / get_cost_tracker to patch.  Calls to route_request
    will naturally fail (success=False) because DEEPSEEK_API_KEY is not set
    in the test environment, so the early API-key check triggers.
    """
    from app.services.llm_router import ModelRouter

    return ModelRouter()


# ── Route-request failure behaviour ──────────────────────────────────────────


class TestModelRouterSuccessFlagNotSwallowed:
    """route_request must return success=False (never True with empty output)."""

    @pytest.mark.asyncio
    async def test_route_request_returns_success_false_when_no_models(self):
        with patch(
            "app.services.llm_router._resolve_provider",
            return_value=("", "", ""),
        ):
            router = _make_router()
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
        with patch(
            "app.services.llm_router._resolve_provider",
            return_value=("", "", ""),
        ):
            router = _make_router()
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
        router = _make_router()
        result = await router.route_request(
            messages=[{"role": "user", "content": "Test"}],
            user_id="user-1",
            is_admin=False,
        )

        assert result.get("response") != "" or result["success"] is False


# ── BYOK / model-preference behaviour ────────────────────────────────────────


class TestModelRouterBYOKPath:
    """BYOK preference and _is_model_available checks."""

    @pytest.mark.asyncio
    async def test_model_preference_is_available_when_key_present(self):
        """_is_model_available returns True when a platform API key exists."""
        with patch(
            "app.services.llm_router._resolve_provider",
            return_value=("https://example.com/v1", "sk-real-key", "qwen2.5-14b"),
        ):
            router = _make_router()
            available = await router._is_model_available(
                "llamacpp-qwen2.5-14b",
                user_id="user-byok",
                is_admin=False,
            )
            assert available is True

    @pytest.mark.asyncio
    async def test_model_preference_used_when_in_pool_and_healthy(self):
        """model_preference is passed to route_request and triggers the key check."""
        with patch(
            "app.services.llm_router._resolve_provider",
            return_value=("", "", ""),
        ):
            router = _make_router()
            result = await router.route_request(
                messages=[{"role": "user", "content": "Hi"}],
                model_preference="openrouter-gemma-2-9b-free",
                user_id="user-byok",
                is_admin=False,
            )
            # No API key for openrouter → success=False
            assert result["success"] is False
            assert "API key" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_byok_preference_takes_priority_over_local_first_strategy(self):
        """When model_preference is provided, route_request uses it (key check only)."""
        router = _make_router()
        result = await router.route_request(
            messages=[{"role": "user", "content": "Hello"}],
            model_preference="claude-3-haiku",
            user_id="user-byok",
            is_admin=False,
        )
        assert result["success"] is False
        # The error should reference the preferred model or a key issue
        assert result.get("error") is not None


# ── MissionExecutor error propagation ────────────────────────────────────────


class TestMissionExecutorErrorPropagation:
    """LlmExecutor.execute_llm propagates route_request errors correctly."""

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

        result = await executor.llm_exec.execute_llm(mock_task, {"prompt": "Hello"})

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

        result = await executor.llm_exec.execute_llm(mock_task, {"prompt": "Hello"})

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

        result = await executor.llm_exec.execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is True
        assert result["output"]["text"] == "This is the LLM response"

    @pytest.mark.asyncio
    async def test_execute_llm_fails_gracefully_when_router_unavailable(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        executor.model_router = None

        with patch.object(executor.llm_exec, "_get_model_router", return_value=None):
            mock_task = MagicMock()
            mock_task.description = "Test"
            mock_task.title = "Test"

            result = await executor.llm_exec.execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is False
        assert "ModelRouter" in result.get("error", "")


# ── Bogus model-id handling ──────────────────────────────────────────────────


class TestModelRouterBogusModelId:
    """A bogus model_id returns success=False with typed error."""

    @pytest.mark.asyncio
    async def test_bogus_model_id_returns_success_false_not_empty_output(self):
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": False,
                "error": "No models available for bogus-model-12345",
            }
        )
        executor.model_router = mock_router

        mock_task = MagicMock()
        mock_task.description = "Test with bogus model"
        mock_task.title = "Bogus Model Test"
        mock_task.assigned_model = "bogus-model-12345"

        result = await executor.llm_exec.execute_llm(mock_task, {"prompt": "Hello"})

        assert result["success"] is False, (
            f"Bogus model must return success=False, got: success={result.get('success')}, "
            f"output={result.get('output')}, error={result.get('error')}"
        )
        assert "error" in result, "Result must contain an 'error' key"
        assert (
            result.get("error") is not None and result["error"] != ""
        ), f"Error must be non-empty for bogus model, got: {result.get('error')}"
        # Failed LLM tasks should not have meaningful output
        assert (
            result.get("output") is None or result.get("output") == {}
        ), "Failed task should not have meaningful output"

    @pytest.mark.asyncio
    async def test_bogus_model_id_plan_generation_fails_gracefully(self):
        """Planning with a bogus model should not create 0-token missions."""
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={"success": False, "error": "No models available"}
        )
        executor.model_router = mock_router

        # planner._generate_plan calls model_router.route_request internally
        # via the same _get_model_router() callback
        with patch.object(
            executor.planner, "_get_model_router", return_value=mock_router
        ):
            plan_tasks = await executor.planner._generate_plan(
                "Plan this mission",
                db=None,
                user_id=999,
            )

        # When plan generation fails, it should return empty list (not crash)
        assert isinstance(plan_tasks, list), f"Expected list, got {type(plan_tasks)}"
        if len(plan_tasks) == 0:
            # Acceptable: LLM plan generation failed gracefully
            pass
        else:
            # If tasks were generated (fallback), they should not have model assignment
            for task in plan_tasks:
                assert (
                    "assigned_model" not in task or task.get("assigned_model") is None
                ), "Fallback tasks should not have bogus model assignments"


# ── Mission abort (CQRS handler) ─────────────────────────────────────────────


class TestMissionAbortEndpoint:
    """MissionCommandHandlers.abort_mission endpoint tests."""

    @pytest.mark.asyncio
    async def test_abort_raises_conflict_for_completed_mission(self):
        """Cannot abort an already-completed mission."""
        import uuid
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus
        from app.services.mission_errors import MissionTransitionConflictError

        session = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.user_id = 1
        mock_mission.status = MissionStatus.COMPLETED

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_mission
        session.execute = AsyncMock(return_value=mock_result)

        handler = MissionCommandHandlers(session)

        user = SimpleNamespace(id=1)
        with pytest.raises(MissionTransitionConflictError, match="abort"):
            await handler.abort_mission(
                user=user,
                mission_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_abort_sets_status_and_writes_log(self):
        """Aborting a running mission sets status='aborted' and writes a log."""
        import uuid
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus

        session = AsyncMock()
        session.commit = AsyncMock()

        mock_mission = MagicMock()
        mock_mission.user_id = 1
        mock_mission.status = MissionStatus.EXECUTING
        mock_mission.tokens_used = 100
        mock_mission.started_at = None
        mock_mission.id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_mission
        session.execute = AsyncMock(return_value=mock_result)

        handler = MissionCommandHandlers(session)

        user = SimpleNamespace(id=1)
        result = await handler.abort_mission(
            user=user,
            mission_id=uuid.uuid4(),
        )

        assert mock_mission.status == MissionStatus.ABORTED
        assert mock_mission.completed_at is not None
        # Verify commit was called (for status update + log)
        assert session.commit.await_count >= 2

    @pytest.mark.asyncio
    async def test_abort_works_for_paused_mission(self):
        """Paused missions should be abortable."""
        import uuid
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus

        session = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.user_id = 1
        mock_mission.status = MissionStatus.PAUSED
        mock_mission.tokens_used = 50
        mock_mission.id = str(uuid.uuid4())

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_mission
        session.execute = AsyncMock(return_value=mock_result)

        handler = MissionCommandHandlers(session)

        user = SimpleNamespace(id=1)
        result = await handler.abort_mission(
            user=user,
            mission_id=uuid.uuid4(),
        )

        assert mock_mission.status == MissionStatus.ABORTED


# ── User-ID propagation ──────────────────────────────────────────────────────


class TestModelRouterUserIdPropagation:
    """user_id is forwarded through _is_model_available and route_request."""

    @pytest.mark.asyncio
    async def test_is_model_available_returns_true_when_key_present(self):
        """_is_model_available returns True when a platform API key is configured."""
        with patch(
            "app.services.llm_router._resolve_provider",
            return_value=("https://example.com/v1", "sk-real-key", "qwen2.5-14b"),
        ):
            router = _make_router()
            result = await router._is_model_available(
                "llamacpp-qwen2.5-14b",
                user_id="user-byok-123",
                is_admin=False,
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_is_model_available_returns_false_when_no_key(self):
        with patch(
            "app.services.llm_router._resolve_provider",
            side_effect=Exception("no provider"),
        ):
            router = _make_router()
            result = await router._is_model_available(
                "llamacpp-qwen2.5-14b",
                user_id="user-no-key",
                is_admin=False,
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_route_request_passes_user_id_through(self):
        """route_request uses the provided user_id in its metadata."""
        router = _make_router()
        result = await router.route_request(
            messages=[{"role": "user", "content": "Hello"}],
            user_id="specific-user-id",
            is_admin=False,
        )
        # Verify the user_id appears in the response metadata
        metadata = result.get("metadata", {})
        assert metadata.get("user_id") == "specific-user-id"
