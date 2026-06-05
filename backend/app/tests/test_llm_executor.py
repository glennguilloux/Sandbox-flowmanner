"""Unit tests for app/services/llm_executor.py — LlmExecutor."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


# ── execute_llm ────────────────────────────────────────────────────────────────


class TestExecuteLlm:
    """LlmExecutor.execute_llm: LLM task execution."""

    @pytest.mark.asyncio
    async def test_propagates_model_router_failure(self):
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
        mock_task.description = "Test"
        mock_task.title = "Test"
        mock_task.assigned_model = None

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is False
        assert result["error"] == "No models available"

    @pytest.mark.asyncio
    async def test_returns_success_on_valid_response(self):
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
        mock_task.assigned_model = None

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is True
        assert result["output"]["text"] == "This is the LLM response"
        assert result["tokens"] == 30

    @pytest.mark.asyncio
    async def test_treats_empty_response_as_failure(self):
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
        mock_task.assigned_model = None

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is False
        assert "empty" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_treats_whitespace_only_as_empty(self):
        from app.services.llm_executor import LlmExecutor

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "   \n  ",
                "cost": {"input_tokens": 3, "output_tokens": 1},
            }
        )
        executor = LlmExecutor(get_model_router=lambda: mock_router)

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_returns_failure_when_model_router_unavailable(self):
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor(get_model_router=lambda: None)
        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is False
        assert "ModelRouter" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_uses_task_description_as_fallback_prompt(self):
        """When no prompt in input_data, uses task.description or title."""
        from app.services.llm_executor import LlmExecutor

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "OK",
                "cost": {"input_tokens": 1, "output_tokens": 1},
            }
        )
        executor = LlmExecutor(get_model_router=lambda: mock_router)

        mock_task = MagicMock()
        mock_task.description = "Fallback description"
        mock_task.title = "Test Title"
        mock_task.assigned_model = None

        await executor.execute_llm(mock_task, {})
        # Verify the prompt passed to the router was the description
        call_args = mock_router.route_request.call_args
        messages = call_args[1]["messages"]
        assert messages[-1]["content"] == "Fallback description"

    @pytest.mark.asyncio
    async def test_records_cost_on_success(self):
        from app.services.llm_executor import LlmExecutor

        mock_cost_tracker = MagicMock()
        mock_cost_tracker.record_llm_call = AsyncMock()
        mock_cost_tracker.estimate_cost = MagicMock(return_value=0.0042)

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "Response text",
                "model": "deepseek-chat",
                "provider": "deepseek",
                "cost": {"input_tokens": 10, "output_tokens": 20},
            }
        )

        executor = LlmExecutor(
            cost_tracker=mock_cost_tracker,
            get_model_router=lambda: mock_router,
        )

        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.description = "Test"
        mock_task.title = "Test"
        mock_task.assigned_model = None

        mock_mission = MagicMock()
        mock_mission.id = "mission-1"
        mock_mission.user_id = 1

        await executor.execute_llm(mock_task, {"prompt": "Hello"}, mission=mock_mission)
        mock_cost_tracker.record_llm_call.assert_called_once()
        call_kwargs = mock_cost_tracker.record_llm_call.call_args[1]
        assert call_kwargs["success"] is True
        assert call_kwargs["mission_id"] == "mission-1"
        assert call_kwargs["task_id"] == "task-1"

    @pytest.mark.asyncio
    async def test_records_cost_on_exception(self):
        from app.services.llm_executor import LlmExecutor

        mock_cost_tracker = MagicMock()
        mock_cost_tracker.record_llm_call = AsyncMock()

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(side_effect=ValueError("boom"))

        executor = LlmExecutor(
            cost_tracker=mock_cost_tracker,
            get_model_router=lambda: mock_router,
        )

        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.description = "Test"
        mock_task.title = "Test"
        mock_task.assigned_model = "some-model"

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is False

        # Should record the failed call
        failure_calls = [
            c
            for c in mock_cost_tracker.record_llm_call.call_args_list
            if c[1]["success"] is False
        ]
        assert len(failure_calls) == 1
        assert failure_calls[0][1]["error_message"] == "boom"

    @pytest.mark.asyncio
    async def test_handles_missing_cost_info_gracefully(self):
        from app.services.llm_executor import LlmExecutor

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "response": "OK",
            }
        )
        executor = LlmExecutor(get_model_router=lambda: mock_router)

        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"
        mock_task.assigned_model = None

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_reraises_retryable_error(self):
        from app.services.llm_executor import LlmExecutor
        from app.services.mission_errors import RetryableMissionError

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            side_effect=RetryableMissionError("overloaded")
        )

        executor = LlmExecutor(get_model_router=lambda: mock_router)
        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"

        with pytest.raises(RetryableMissionError):
            await executor.execute_llm(mock_task, {"prompt": "Hello"})

    @pytest.mark.asyncio
    async def test_catches_permanent_error(self):
        from app.services.llm_executor import LlmExecutor
        from app.services.mission_errors import PermanentMissionError

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            side_effect=PermanentMissionError("forbidden")
        )

        executor = LlmExecutor(get_model_router=lambda: mock_router)
        mock_task = MagicMock()
        mock_task.description = "Test"
        mock_task.title = "Test"

        result = await executor.execute_llm(mock_task, {"prompt": "Hello"})
        assert result["success"] is False
        assert result.get("permanent") is True


# ── _build_llm_messages ───────────────────────────────────────────────────────


class TestBuildLlmMessages:
    """LlmExecutor._build_llm_messages: message array construction."""

    @pytest.mark.asyncio
    async def test_starts_with_system_when_agent_assigned(self):
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor()

        mock_task = MagicMock()
        mock_task.assigned_agent_id = "agent-1"
        mock_task.id = "task-1"

        with patch.object(
            executor,
            "_resolve_agent_system_prompt",
            return_value="You are a helpful assistant",
        ):
            messages = await executor._build_llm_messages(mock_task, "Do something")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are a helpful assistant"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Do something"

    @pytest.mark.asyncio
    async def test_no_system_message_without_agent(self):
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor()

        mock_task = MagicMock()
        mock_task.assigned_agent_id = None
        mock_task.id = "task-1"

        messages = await executor._build_llm_messages(mock_task, "Do something")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_no_system_when_prompt_is_none(self):
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor()

        mock_task = MagicMock()
        mock_task.assigned_agent_id = "agent-1"
        mock_task.id = "task-2"

        with patch.object(executor, "_resolve_agent_system_prompt", return_value=None):
            messages = await executor._build_llm_messages(mock_task, "Test prompt")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"


# ── _resolve_agent_system_prompt ──────────────────────────────────────────────


class TestResolveAgentSystemPrompt:
    """LlmExecutor._resolve_agent_system_prompt: agent template resolution."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_agent_assigned(self):
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor()
        mock_task = MagicMock()
        mock_task.assigned_agent_id = None

        result = await executor._resolve_agent_system_prompt(mock_task)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_prompt_from_matching_template(self):
        from app.models.agent import AgentTemplate
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor()

        mock_template = MagicMock(spec=AgentTemplate)
        mock_template.system_prompt = "Act as a code reviewer"

        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_template

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_task = MagicMock()
        mock_task.assigned_agent_id = "tmpl-123"

        with patch("app.services.llm_executor.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            result = await executor._resolve_agent_system_prompt(mock_task)

        assert result == "Act as a code reviewer"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_template_matches(self):
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor()

        mock_result = MagicMock()
        mock_result.scalars().first.return_value = None

        mock_db = AsyncMock()
        # Both queries return None
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_task = MagicMock()
        mock_task.assigned_agent_id = "tmpl-nonexistent"

        with patch("app.services.llm_executor.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            result = await executor._resolve_agent_system_prompt(mock_task)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_template_has_no_system_prompt(self):
        from app.models.agent import AgentTemplate
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor()

        mock_template = MagicMock(spec=AgentTemplate)
        mock_template.system_prompt = None

        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_template

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_task = MagicMock()
        mock_task.assigned_agent_id = "tmpl-no-prompt"

        with patch("app.services.llm_executor.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            result = await executor._resolve_agent_system_prompt(mock_task)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_db_error(self):
        from app.services.llm_executor import LlmExecutor

        executor = LlmExecutor()

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB connection lost"))

        mock_task = MagicMock()
        mock_task.assigned_agent_id = "tmpl-error"

        with patch("app.services.llm_executor.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            result = await executor._resolve_agent_system_prompt(mock_task)

        assert result is None
