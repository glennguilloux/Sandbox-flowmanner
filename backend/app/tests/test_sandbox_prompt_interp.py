"""Tests for {{ inputs.* }} interpolation in the sandbox node task prompt.

The sandbox node must substitute ``{{ inputs.<key> }}`` tokens in the
``task_prompt`` with the run's input values (reachable via ``context["inputs"]``)
before submitting the task to sandboxd. Literal braces that are not
``{{ inputs.* }}`` tokens must be left untouched.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
pytestmark = pytest.mark.integration


def _make_executor():
    from app.models.capability_models import Budget
    from app.services.substrate.node_executor import NodeExecutor
    from app.services.substrate.workflow_models import NodeType, WorkflowNode

    return NodeExecutor(MagicMock()), Budget, NodeType, WorkflowNode


class TestSandboxPromptInputsInterp:
    """Verify {{ inputs.* }} tokens are resolved from context["inputs"]."""

    @pytest.mark.asyncio
    async def test_inputs_token_is_replaced_with_value(self):
        executor, Budget, NodeType, WorkflowNode = _make_executor()

        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        mock_svc.get_sandbox_for_mission = AsyncMock(return_value=None)
        mock_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-1")
        mock_client.submit_task.return_value = {"id": "task-1"}

        async def mock_events(*args, **kwargs):
            yield {
                "id": "1",
                "type": "complete",
                "data": '{"stdout":"ok","exit_code":0}',
            }

        mock_client.task_events = mock_events

        node = WorkflowNode(
            id="n1",
            type=NodeType.SANDBOX,
            title="Test",
            config={"task_prompt": "Clone {{ inputs.repo_url }} and build it"},
        )

        mock_event_log = AsyncMock()
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await executor._handle_sandbox_node(
                db=AsyncMock(),
                node=node,
                context={"inputs": {"repo_url": "https://github.com/glennguilloux/Sandbox-flowmanner"}},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is True
        submitted_prompt = mock_client.submit_task.call_args.kwargs["prompt"]
        assert "https://github.com/glennguilloux/Sandbox-flowmanner" in submitted_prompt
        assert "{{ inputs.repo_url }}" not in submitted_prompt

    @pytest.mark.asyncio
    async def test_literal_braces_are_preserved(self):
        executor, Budget, NodeType, WorkflowNode = _make_executor()

        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        mock_svc.get_sandbox_for_mission = AsyncMock(return_value=None)
        mock_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-1")
        mock_client.submit_task.return_value = {"id": "task-1"}

        async def mock_events(*args, **kwargs):
            yield {
                "id": "1",
                "type": "complete",
                "data": '{"stdout":"ok","exit_code":0}',
            }

        mock_client.task_events = mock_events

        node = WorkflowNode(
            id="n1",
            type=NodeType.SANDBOX,
            title="Test",
            config={"task_prompt": "Run the {agent} loop; clone {{ inputs.repo_url }}"},
        )

        mock_event_log = AsyncMock()
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await executor._handle_sandbox_node(
                db=AsyncMock(),
                node=node,
                context={"inputs": {"repo_url": "https://github.com/glennguilloux/Sandbox-flowmanner"}},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is True
        submitted_prompt = mock_client.submit_task.call_args.kwargs["prompt"]
        # The literal single-brace token is preserved.
        assert "{agent}" in submitted_prompt
        # The inputs token is replaced.
        assert "{{ inputs.repo_url }}" not in submitted_prompt
        assert "https://github.com/glennguilloux/Sandbox-flowmanner" in submitted_prompt

    @pytest.mark.asyncio
    async def test_unknown_input_token_is_left_untouched(self):
        executor, Budget, NodeType, WorkflowNode = _make_executor()

        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        mock_svc.get_sandbox_for_mission = AsyncMock(return_value=None)
        mock_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-1")
        mock_client.submit_task.return_value = {"id": "task-1"}

        async def mock_events(*args, **kwargs):
            yield {
                "id": "1",
                "type": "complete",
                "data": '{"stdout":"ok","exit_code":0}',
            }

        mock_client.task_events = mock_events

        node = WorkflowNode(
            id="n1",
            type=NodeType.SANDBOX,
            title="Test",
            config={"task_prompt": "Clone {{ inputs.missing }} now"},
        )

        mock_event_log = AsyncMock()
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await executor._handle_sandbox_node(
                db=AsyncMock(),
                node=node,
                context={"inputs": {"repo_url": "x"}},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is True
        submitted_prompt = mock_client.submit_task.call_args.kwargs["prompt"]
        # Unknown input key → token stays as-is (no crash).
        assert "{{ inputs.missing }}" in submitted_prompt
