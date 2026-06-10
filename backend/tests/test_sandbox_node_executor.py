"""Tests for Sandbox Node Executor — Phase 3 workflow integration."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
pytestmark = pytest.mark.integration


class TestSandboxNodeType:
    """Verify SANDBOX enum value exists and is valid."""

    def test_sandbox_node_type_exists_in_enum(self):
        from app.services.substrate.workflow_models import NodeType

        assert NodeType.SANDBOX == "sandbox"
        assert NodeType("sandbox") == NodeType.SANDBOX

    def test_sandbox_node_type_included_in_enum_members(self):
        from app.services.substrate.workflow_models import NodeType

        assert "SANDBOX" in [m.name for m in NodeType]


class TestSandboxEventTypes:
    """Verify sandbox event type constants exist."""

    def test_all_sandbox_event_types_defined(self):
        from app.models.substrate_models import SubstrateEventType

        assert SubstrateEventType.SANDBOX_CREATED == "sandbox.created"
        assert SubstrateEventType.SANDBOX_FILES_WRITTEN == "sandbox.files_written"
        assert SubstrateEventType.SANDBOX_TASK_SUBMITTED == "sandbox.task_submitted"
        assert SubstrateEventType.SANDBOX_TASK_PROGRESS == "sandbox.task_progress"
        assert SubstrateEventType.SANDBOX_TASK_COMPLETED == "sandbox.task_completed"
        assert SubstrateEventType.SANDBOX_TASK_FAILED == "sandbox.task_failed"
        assert SubstrateEventType.SANDBOX_SNAPSHOT_CREATED == "sandbox.snapshot_created"


class TestSandboxRunStateProjection:
    """Verify sandbox events don't break RunState.apply()."""

    def test_sandbox_events_are_noop_in_run_state(self):
        from app.models.substrate_models import SubstrateEventType, SubstrateRunState

        state = SubstrateRunState(run_id="test-run")
        state.status = "executing"

        # Create a mock event with a sandbox event type
        event = MagicMock()
        event.type = SubstrateEventType.SANDBOX_CREATED
        event.sequence = 1
        event.timestamp = None
        event.payload = {"sandbox_id": "sb-1", "node_id": "n1"}

        # Should not raise
        state.apply(event)
        # Status should remain unchanged (sandbox events are informational)
        assert state.status == "executing"

    def test_sandbox_task_progress_is_noop(self):
        from app.models.substrate_models import SubstrateEventType, SubstrateRunState

        state = SubstrateRunState(run_id="test-run")

        event = MagicMock()
        event.type = SubstrateEventType.SANDBOX_TASK_PROGRESS
        event.sequence = 2
        event.timestamp = None
        event.payload = {"task_id": "task-1", "message": "Installing", "percent": 50}

        state.apply(event)
        # No state change
        assert state.status == "pending"


class TestSandboxNodeDispatch:
    """Verify SANDBOX node type routes correctly in NodeExecutor._dispatch."""

    @pytest.mark.asyncio
    async def test_dispatch_routes_sandbox_to_handler(self):
        """_dispatch should route SANDBOX to _handle_sandbox_node."""
        from app.models.capability_models import Budget
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        executor = NodeExecutor(MagicMock())
        node = WorkflowNode(
            id="n1",
            type=NodeType.SANDBOX,
            title="Test",
            config={"task_prompt": "build"},
        )

        # Inject mocked sandbox client and service
        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        mock_client.submit_task.return_value = {"id": "task-1"}
        mock_client.write_file = AsyncMock(return_value={"written": True})

        async def mock_events(*args, **kwargs):
            yield {
                "id": "1",
                "type": "complete",
                "data": '{"stdout":"done","exit_code":0}',
            }

        mock_client.task_events = mock_events

        mock_svc.get_sandbox_for_mission = AsyncMock(return_value=None)
        mock_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-1")

        mock_event_log = AsyncMock()
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await executor._dispatch(
                db=AsyncMock(),
                node=node,
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is True
        assert result["output"]["sandbox_id"] == "sb-1"


class TestSandboxNodeEvents:
    """Verify correct substrate events are emitted during sandbox execution."""

    @pytest.mark.asyncio
    async def test_emits_create_submit_complete_events(self):
        from app.models.capability_models import Budget
        from app.models.substrate_models import SubstrateEventType
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        mock_event_log = AsyncMock()
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            executor = NodeExecutor(MagicMock())

            mock_client = AsyncMock()
            mock_svc = MagicMock()
            executor._sbx_client = mock_client
            executor._sbx_svc = mock_svc

            mock_svc.get_sandbox_for_mission = AsyncMock(return_value=None)
            mock_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-1")
            mock_client.submit_task.return_value = {"id": "task-1"}
            mock_client.write_file = AsyncMock()

            async def mock_events(*args, **kwargs):
                yield {
                    "id": "1",
                    "type": "progress",
                    "data": '{"message":"Installing","percent":50}',
                }
                yield {
                    "id": "2",
                    "type": "complete",
                    "data": '{"stdout":"ok","exit_code":0}',
                }

            mock_client.task_events = mock_events

            node = WorkflowNode(
                id="n1",
                type=NodeType.SANDBOX,
                title="Test",
                config={"task_prompt": "build app"},
            )

            result = await executor._handle_sandbox_node(
                db=AsyncMock(),
                node=node,
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

            assert result["success"] is True

            # Verify events were emitted
            event_types = [
                c.args[2][0]["type"] for c in mock_event_log.append.call_args_list
            ]
            assert SubstrateEventType.SANDBOX_CREATED in event_types
            assert SubstrateEventType.SANDBOX_TASK_SUBMITTED in event_types
            assert SubstrateEventType.SANDBOX_TASK_PROGRESS in event_types
            assert SubstrateEventType.SANDBOX_TASK_COMPLETED in event_types


class TestSandboxNodeErrorHandling:
    """Verify error handling for sandbox node failures."""

    @pytest.mark.asyncio
    async def test_missing_task_prompt_returns_error(self):
        from app.models.capability_models import Budget
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        executor = NodeExecutor(MagicMock())
        node = WorkflowNode(
            id="n1",
            type=NodeType.SANDBOX,
            title="Test",
            config={},  # No task_prompt
        )

        result = await executor._handle_sandbox_node(
            db=AsyncMock(),
            node=node,
            context={},
            budget=Budget(),
            run_id="run-1",
            workflow=MagicMock(id="m1", user_id="u1"),
        )

        assert result["success"] is False
        assert "No task_prompt" in result["error"]

    @pytest.mark.asyncio
    async def test_task_submit_failure_returns_error(self):
        from app.models.capability_models import Budget
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        executor = NodeExecutor(MagicMock())
        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        mock_svc.get_sandbox_for_mission = AsyncMock(return_value=None)
        mock_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-1")
        mock_client.submit_task.side_effect = Exception("sandboxd unreachable")

        node = WorkflowNode(
            id="n1",
            type=NodeType.SANDBOX,
            title="Test",
            config={"task_prompt": "build app"},
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
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is False
        assert "sandboxd unreachable" in result["error"]

    @pytest.mark.asyncio
    async def test_sse_stream_error_returns_failure(self):
        from app.models.capability_models import Budget
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        executor = NodeExecutor(MagicMock())
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
                "type": "error",
                "data": '{"error":"Container OOM"}',
            }

        mock_client.task_events = mock_events

        node = WorkflowNode(
            id="n1",
            type=NodeType.SANDBOX,
            title="Test",
            config={"task_prompt": "build app"},
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
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is False
        assert "Container OOM" in result["error"]

    @pytest.mark.asyncio
    async def test_sse_stream_ended_without_event_returns_failure(self):
        from app.models.capability_models import Budget
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        executor = NodeExecutor(MagicMock())
        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        mock_svc.get_sandbox_for_mission = AsyncMock(return_value=None)
        mock_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-1")
        mock_client.submit_task.return_value = {"id": "task-1"}

        # Empty stream — no events yielded
        async def mock_events(*args, **kwargs):
            return
            yield  # make it an async generator

        mock_client.task_events = mock_events

        node = WorkflowNode(
            id="n1",
            type=NodeType.SANDBOX,
            title="Test",
            config={"task_prompt": "build app"},
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
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is False
        assert "unexpected" in result["error"].lower()


class TestSandboxNodeConfig:
    """Verify config options are respected."""

    @pytest.mark.asyncio
    async def test_shared_workspace_reuses_sandbox(self):
        from app.models.capability_models import Budget
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        executor = NodeExecutor(MagicMock())
        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        # Existing sandbox found
        mock_svc.get_sandbox_for_mission = AsyncMock(return_value="existing-sb")

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
            config={"task_prompt": "build", "shared_workspace": True},
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
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is True
        assert result["output"]["sandbox_id"] == "existing-sb"
        # Should NOT have called ensure_sandbox_for_mission
        mock_svc.ensure_sandbox_for_mission.assert_not_called()

    @pytest.mark.asyncio
    async def test_input_files_are_written(self):
        from app.models.capability_models import Budget
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        executor = NodeExecutor(MagicMock())
        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        mock_svc.get_sandbox_for_mission = AsyncMock(return_value=None)
        mock_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-1")
        mock_client.submit_task.return_value = {"id": "task-1"}
        mock_client.write_file = AsyncMock()

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
            config={
                "task_prompt": "build",
                "input_files": {
                    "src/index.tsx": "console.log('hello')",
                    "package.json": '{"name":"test"}',
                },
            },
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
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is True
        # Verify write_file was called for each input file
        assert mock_client.write_file.call_count == 2

    @pytest.mark.asyncio
    async def test_snapshot_before_creates_snapshot(self):
        from app.models.capability_models import Budget
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        executor = NodeExecutor(MagicMock())
        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        mock_svc.get_sandbox_for_mission = AsyncMock(return_value=None)
        mock_svc.ensure_sandbox_for_mission = AsyncMock(return_value="sb-1")
        mock_client.create_snapshot = AsyncMock(
            return_value={"id": "snap-1", "name": "pre_n1"}
        )
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
            config={"task_prompt": "build", "snapshot_before": True},
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
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=MagicMock(id="m1", user_id="u1"),
            )

        assert result["success"] is True
        mock_client.create_snapshot.assert_awaited_once_with("sb-1", "pre_n1")


class TestSandboxNodeLazyProperties:
    """Verify lazy initialization of sandbox client and service."""

    def test_sandbox_client_lazy_init(self):
        from app.services.substrate.node_executor import NodeExecutor

        executor = NodeExecutor(MagicMock())
        assert executor._sbx_client is None

        with patch(
            "app.services.substrate.node_executor.get_sandboxd_client",
            return_value=MagicMock(),
        ) as mock_get:
            client = executor._sandbox_client
            mock_get.assert_called_once()
            assert client is not None

    def test_sandbox_service_lazy_init(self):
        from app.services.substrate.node_executor import NodeExecutor

        executor = NodeExecutor(MagicMock())
        assert executor._sbx_svc is None

        mock_client = MagicMock()
        executor._sbx_client = mock_client

        with patch(
            "app.services.substrate.node_executor.SandboxService",
            return_value=MagicMock(),
        ) as mock_svc_cls:
            svc = executor._sandbox_service
            mock_svc_cls.assert_called_once_with(mock_client)
            assert svc is not None

    @pytest.mark.asyncio
    async def test_ephemeral_sandbox_without_mission(self):
        """When no workflow/mission, creates an ephemeral sandbox."""
        from app.models.capability_models import Budget
        from app.services.substrate.node_executor import NodeExecutor
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        executor = NodeExecutor(MagicMock())
        mock_client = AsyncMock()
        mock_svc = MagicMock()
        executor._sbx_client = mock_client
        executor._sbx_svc = mock_svc

        mock_client.create = AsyncMock(
            return_value={"id": "ephemeral-sb", "status": "running"}
        )
        mock_client.submit_task = AsyncMock(return_value={"id": "task-1"})

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
            config={"task_prompt": "build"},
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
                context={},
                budget=Budget(),
                run_id="run-1",
                workflow=None,  # No workflow = no mission
            )

        assert result["success"] is True
        assert result["output"]["sandbox_id"] == "ephemeral-sb"
        mock_client.create.assert_awaited_once()
