"""Unit tests for NodeExecutor (app/services/substrate/node_executor.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.capability_models import BudgetExhausted
from app.services.substrate.workflow_models import WorkflowNode, WorkflowType


def _make_node(
    node_type: str = "llm_call",
    title: str = "Test Node",
    config: dict | None = None,
    max_retries: int = 3,
) -> WorkflowNode:
    return WorkflowNode(
        id=str(uuid4()),
        type=node_type,
        title=title,
        config=config or {},
        max_retries=max_retries,
    )


def _make_mock_node_executor():
    from app.services.substrate.node_executor import NodeExecutor

    mock_executor = MagicMock()
    mock_executor.is_aborted = MagicMock(return_value=False)
    mock_executor.is_running = MagicMock(return_value=True)
    mock_executor.event_log = MagicMock()
    mock_executor.event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
    mock_executor.call_llm = AsyncMock(
        return_value={
            "success": True,
            "response": "Response text",
            "budget": {"prompt_tokens": 10, "completion_tokens": 20, "cost_usd": 0.01},
        }
    )

    node_executor = NodeExecutor(mock_executor)
    return node_executor, mock_executor


def _make_budget(exhausted: bool = False):
    budget = MagicMock()
    budget.is_exhausted = MagicMock(return_value=(exhausted, ""))
    return budget


class TestNodeExecutorInit:
    def test_init_stores_executor_reference(self):
        from app.services.substrate.node_executor import NodeExecutor

        mock_executor = MagicMock()
        ne = NodeExecutor(mock_executor)
        assert ne.executor is mock_executor


class TestDispatchRouting:
    def test_dispatch_has_handler_for_llm_call(self):
        ne, _ = _make_mock_node_executor()
        assert hasattr(ne, "_handle_llm")

    def test_dispatch_has_handler_for_tool(self):
        ne, _ = _make_mock_node_executor()
        assert hasattr(ne, "_handle_tool")

    def test_dispatch_has_handler_for_code(self):
        ne, _ = _make_mock_node_executor()
        assert hasattr(ne, "_handle_code")

    def test_dispatch_has_handler_for_rag(self):
        ne, _ = _make_mock_node_executor()
        assert hasattr(ne, "_handle_rag")

    def test_dispatch_has_handler_for_sub_workflow(self):
        ne, _ = _make_mock_node_executor()
        assert hasattr(ne, "_handle_sub_workflow")

    def test_dispatch_has_handler_for_hitl(self):
        ne, _ = _make_mock_node_executor()
        assert hasattr(ne, "_handle_hitl_interrupt")


class TestExecuteMainLoop:
    @pytest.mark.asyncio
    async def test_execute_success_on_first_try(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node()
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        context = {"mission_id": "m1"}

        mock_result = {"success": True, "output": "ok", "tokens": 10, "cost": 0.01}

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_executor.event_log,
            ),
            patch.object(
                ne, "_dispatch", new_callable=AsyncMock, return_value=mock_result
            ),
        ):
            result = await ne.execute(db, node, context, budget, run_id)

        assert result["success"] is True
        assert node.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_retries_on_failure(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(max_retries=2)
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        context = {"mission_id": "m1"}

        call_count = 0

        async def mock_dispatch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient error")
            return {"success": True, "output": "ok", "tokens": 10, "cost": 0.01}

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_executor.event_log,
            ),
            patch.object(ne, "_dispatch", side_effect=mock_dispatch),
        ):
            result = await ne.execute(db, node, context, budget, run_id)

        assert result["success"] is True
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_fails_after_max_retries(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(max_retries=1)
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        context = {"mission_id": "m1"}

        async def mock_dispatch(*args, **kwargs):
            raise RuntimeError("persistent error")

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_executor.event_log,
            ),
            patch.object(ne, "_dispatch", side_effect=mock_dispatch),
        ):
            result = await ne.execute(db, node, context, budget, run_id)

        assert node.status == "failed"

    @pytest.mark.asyncio
    async def test_execute_aborted_before_dispatch(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node()
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        context = {"mission_id": "m1"}
        mock_executor.is_aborted = MagicMock(return_value=True)

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_executor.event_log,
            ),
            patch.object(ne, "_dispatch", new_callable=AsyncMock) as mock_dispatch,
        ):
            result = await ne.execute(db, node, context, budget, run_id)

        assert result.get("success") is False
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_budget_exhausted_raises(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node()
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget(exhausted=True)
        context = {"mission_id": "m1"}

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_executor.event_log,
            ),
            patch.object(ne, "_dispatch", new_callable=AsyncMock) as mock_dispatch,
            pytest.raises(BudgetExhausted),
        ):
            await ne.execute(db, node, context, budget, run_id)

        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_logs_events(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node()
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        context = {"mission_id": "m1"}

        mock_result = {"success": True, "output": "ok", "tokens": 50, "cost": 0.02}

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_executor.event_log,
            ),
            patch.object(
                ne, "_dispatch", new_callable=AsyncMock, return_value=mock_result
            ),
        ):
            await ne.execute(db, node, context, budget, run_id)

        assert mock_executor.event_log.append.call_count >= 2
        all_events = []
        for call in mock_executor.event_log.append.call_args_list:
            all_events.extend(call[0][2])
        event_types = [e.get("type") for e in all_events]
        assert "task.started" in event_types
        assert "task.completed" in event_types

    @pytest.mark.asyncio
    async def test_execute_logs_failure_event(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(max_retries=0)
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        context = {"mission_id": "m1"}

        async def mock_dispatch(*args, **kwargs):
            raise RuntimeError("boom")

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_executor.event_log,
            ),
            patch.object(ne, "_dispatch", side_effect=mock_dispatch),
        ):
            await ne.execute(db, node, context, budget, run_id)

        all_events = []
        for call in mock_executor.event_log.append.call_args_list:
            all_events.extend(call[0][2])
        event_types = [e.get("type") for e in all_events]
        assert "task.failed" in event_types

    @pytest.mark.asyncio
    async def test_execute_aborted_between_retries(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(max_retries=3)
        db = AsyncMock()
        run_id = str(uuid4())
        budget = _make_budget()
        context = {"mission_id": "m1"}

        call_count = 0

        async def mock_dispatch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("error")
            return {"success": True, "output": "ok"}

        def abort_on_second_check(rid):
            return call_count >= 1

        mock_executor.is_aborted = MagicMock(side_effect=abort_on_second_check)

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_executor.event_log,
            ),
            patch.object(ne, "_dispatch", side_effect=mock_dispatch),
        ):
            result = await ne.execute(db, node, context, budget, run_id)

        assert result.get("success") is False
        assert call_count == 1


class TestHandleCode:
    @pytest.mark.asyncio
    async def test_handle_code_executes_successfully(self):
        ne, _ = _make_mock_node_executor()
        node = _make_node(node_type="code_execution", config={"code": "print(42)"})
        context = {"mission_id": "m1"}

        with patch.object(
            ne,
            "_execute_code_sandboxed",
            new_callable=AsyncMock,
            return_value={
                "success": True,
                "output": {"stdout": "42\n", "return_code": 0},
            },
        ) as mock_exec:
            result = await ne._handle_code(node, context)

        assert result["success"] is True
        mock_exec.assert_awaited_once_with("print(42)")

    @pytest.mark.asyncio
    async def test_handle_code_falls_back_to_context(self):
        ne, _ = _make_mock_node_executor()
        node = _make_node(node_type="code_execution", config={})
        context = {"code": "x = 1"}

        with patch.object(
            ne,
            "_execute_code_sandboxed",
            new_callable=AsyncMock,
            return_value={"success": True, "output": {}},
        ) as mock_exec:
            await ne._handle_code(node, context)

        mock_exec.assert_awaited_once_with("x = 1")

    @pytest.mark.asyncio
    async def test_handle_code_no_code_returns_error(self):
        ne, _ = _make_mock_node_executor()
        node = _make_node(node_type="code_execution", config={})
        context = {}

        result = await ne._handle_code(node, context)
        assert result["success"] is False
        assert "No code" in result["error"]


class TestHandleRAG:
    @pytest.mark.asyncio
    async def test_handle_rag_success(self):
        ne, _ = _make_mock_node_executor()
        node = _make_node(
            node_type="rag_query", config={"query": "test query", "collection": "docs"}
        )
        context = {}

        mock_rag = MagicMock()
        mock_rag.query_documents.return_value = [{"text": "result", "score": 0.9}]

        with patch("app.services.rag_service.RAGService", return_value=mock_rag):
            result = await ne._handle_rag(node, context)

        assert result["success"] is True
        assert result["output"]["query"] == "test query"
        assert result["output"]["collection"] == "docs"
        assert result["output"]["context"] == [{"text": "result", "score": 0.9}]
        mock_rag.query_documents.assert_called_once_with("test query", n_results=5)

    @pytest.mark.asyncio
    async def test_handle_rag_falls_back_to_title(self):
        ne, _ = _make_mock_node_executor()
        node = _make_node(node_type="rag_query", config={})
        context = {}
        node.description = None

        mock_rag = MagicMock()
        mock_rag.query_documents.return_value = []

        with patch("app.services.rag_service.RAGService", return_value=mock_rag):
            result = await ne._handle_rag(node, context)

        # Falls back to node.title as the query
        assert result["success"] is True
        assert result["output"]["query"] == "Test Node"
        assert result["output"]["context"] == []
        mock_rag.query_documents.assert_called_once_with("Test Node", n_results=5)


class TestHandleWebSearch:
    @pytest.mark.asyncio
    async def test_handle_web_search_no_query_returns_error(self):
        ne, _ = _make_mock_node_executor()
        node = _make_node(node_type="web_search", config={})
        node.description = None
        context = {}

        result = await ne._handle_web_search(node, context)
        assert result["success"] is False
        assert "No query" in result["error"]


class TestHandleTool:
    @pytest.mark.asyncio
    async def test_handle_tool_no_tool_name_falls_back_to_llm(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(node_type="tool_call", config={})
        db = AsyncMock()
        run_id = str(uuid4())
        budget = MagicMock()
        context = {"mission_id": "m1"}
        from app.services.substrate.workflow_models import Workflow

        workflow = Workflow(
            id="wf-1",
            type=WorkflowType.SOLO,
            title="Test",
            nodes=[node],
            user_id="1",
        )

        with patch.object(
            ne, "_handle_llm", new_callable=AsyncMock, return_value={"success": True}
        ) as mock_llm:
            mock_executor.check_circuit_breaker = AsyncMock(return_value=(True, ""))
            result = await ne._handle_tool(db, node, context, budget, run_id, workflow)

        assert result["success"] is True
        mock_llm.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_tool_circuit_breaker_blocks(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(node_type="tool_call", config={"tool_name": "web_search"})
        db = AsyncMock()
        run_id = str(uuid4())
        budget = MagicMock()
        context = {"mission_id": "m1"}
        from app.services.substrate.workflow_models import Workflow

        workflow = Workflow(
            id="wf-1",
            type=WorkflowType.SOLO,
            title="Test",
            nodes=[node],
            user_id="1",
        )

        mock_executor.check_circuit_breaker = AsyncMock(
            return_value=(False, "too many calls")
        )

        result = await ne._handle_tool(db, node, context, budget, run_id, workflow)
        assert result["success"] is False
        assert "Circuit breaker" in result["error"]


class TestHandleHITL:
    @pytest.mark.asyncio
    async def test_handle_hitl_creates_interrupt(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(
            node_type="approval", config={"approval_prompt": "Approve this?"}
        )
        db = AsyncMock()
        run_id = str(uuid4())
        context = {"mission_id": "m1"}

        mock_inbox_item = MagicMock()
        mock_inbox_item.id = "inbox-123"
        mock_hitl = MagicMock()
        mock_hitl.create_interrupt = AsyncMock(return_value=mock_inbox_item)
        mock_event_log = MagicMock()
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        from app.services.substrate.workflow_models import Workflow

        workflow = Workflow(
            id="wf-1",
            type=WorkflowType.SOLO,
            title="Test",
            nodes=[node],
            user_id="1",
        )

        # HITLService and get_event_log are imported locally in _handle_hitl_interrupt
        with (
            patch("app.services.hitl_service.HITLService", return_value=mock_hitl),
            patch(
                "app.services.substrate.event_log.get_event_log",
                return_value=mock_event_log,
            ),
        ):
            result = await ne._handle_hitl_interrupt(
                db, node, context, run_id, workflow, interrupt_type="approval"
            )

        assert result["success"] is False
        assert result["requires_human_input"] is True
        assert result["requires_approval"] is True
        assert result["inbox_item_id"] == "inbox-123"

    @pytest.mark.asyncio
    async def test_handle_hitl_clarification_type(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(node_type="human_review", config={})
        db = AsyncMock()
        run_id = str(uuid4())
        context = {}

        mock_inbox_item = MagicMock()
        mock_inbox_item.id = "inbox-456"
        mock_hitl = MagicMock()
        mock_hitl.create_interrupt = AsyncMock(return_value=mock_inbox_item)
        mock_event_log = MagicMock()
        mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])

        # HITLService and get_event_log are imported locally in _handle_hitl_interrupt
        with (
            patch("app.services.hitl_service.HITLService", return_value=mock_hitl),
            patch(
                "app.services.substrate.event_log.get_event_log",
                return_value=mock_event_log,
            ),
        ):
            result = await ne._handle_hitl_interrupt(
                db, node, context, run_id, None, interrupt_type="clarification"
            )

        assert result["requires_clarification"] is True
        assert result["requires_approval"] is False


class TestDispatchRoutingExtended:
    @pytest.mark.asyncio
    async def test_dispatch_unknown_type_returns_error(self):
        ne, mock_executor = _make_mock_node_executor()
        node = MagicMock()
        node.type = "completely_unknown"  # Not in the match cases
        db = AsyncMock()
        budget = MagicMock()
        context = {}
        run_id = str(uuid4())

        result = await ne._dispatch(db, node, context, budget, run_id)
        assert result["success"] is False
        assert "Unknown node type" in result["error"]

    @pytest.mark.asyncio
    async def test_dispatch_phase_gate_passthrough(self):
        ne, _ = _make_mock_node_executor()
        from app.services.substrate.workflow_models import NodeType, WorkflowNode

        node = WorkflowNode(id="pg1", type=NodeType.PHASE_GATE, title="Gate")
        db = AsyncMock()
        budget = MagicMock()
        context = {"data": "test"}
        run_id = str(uuid4())

        result = await ne._dispatch(db, node, context, budget, run_id)
        assert result["success"] is True
        assert result["tokens"] == 0


class TestHandleLLM:
    @pytest.mark.asyncio
    async def test_handle_llm_returns_correct_tokens_and_cost(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(node_type="llm_call", config={"prompt": "Hello"})
        db = AsyncMock()
        run_id = str(uuid4())
        budget = MagicMock()
        context = {"mission_id": "m1"}

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value={
                "success": True,
                "response": "Response",
                "budget": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "spent_usd": 0.01,
                },
            }
        )

        with (
            patch(
                "app.services.budget_enforcer.get_budget_enforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService"
            ) as mock_cb_cls,
        ):
            mock_cb = MagicMock()
            mock_cb.get_breaker = AsyncMock(return_value=None)
            mock_cb_cls.return_value = mock_cb
            result = await ne._handle_llm(db, node, context, budget, run_id)

        # _handle_llm returns the result dict; node.tokens_used is set by execute()
        assert result["success"] is True
        assert result["tokens"] == 30  # 10 prompt + 20 completion
        assert result["cost"] == 0.01  # spent_usd from budget info

    @pytest.mark.asyncio
    async def test_handle_llm_failure_response(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(node_type="llm_call", config={"prompt": "Hello"})
        db = AsyncMock()
        run_id = str(uuid4())
        budget = MagicMock()
        context = {"mission_id": "m1"}

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value={
                "success": False,
                "error": "Rate limited",
            }
        )

        with (
            patch(
                "app.services.budget_enforcer.get_budget_enforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService"
            ) as mock_cb_cls,
        ):
            mock_cb = MagicMock()
            mock_cb.get_breaker = AsyncMock(return_value=None)
            mock_cb_cls.return_value = mock_cb
            result = await ne._handle_llm(db, node, context, budget, run_id)

        assert result["success"] is False
        assert "Rate limited" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_llm_empty_response(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(node_type="llm_call", config={"prompt": "Hello"})
        db = AsyncMock()
        run_id = str(uuid4())
        budget = MagicMock()
        context = {"mission_id": "m1"}

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value={
                "success": True,
                "response": "",
                "budget": {
                    "prompt_tokens": 5,
                    "completion_tokens": 0,
                    "spent_usd": 0.001,
                },
            }
        )

        with (
            patch(
                "app.services.budget_enforcer.get_budget_enforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService"
            ) as mock_cb_cls,
        ):
            mock_cb = MagicMock()
            mock_cb.get_breaker = AsyncMock(return_value=None)
            mock_cb_cls.return_value = mock_cb
            result = await ne._handle_llm(db, node, context, budget, run_id)

        assert result["success"] is False
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_handle_llm_with_system_prompt(self):
        ne, mock_executor = _make_mock_node_executor()
        node = _make_node(
            node_type="llm_call",
            config={
                "prompt": "Hello",
                "system_prompt": "You are helpful",
                "temperature": 0.3,
                "max_tokens": 500,
            },
        )
        db = AsyncMock()
        run_id = str(uuid4())
        budget = MagicMock()
        context = {"mission_id": "m1"}

        mock_enforcer = MagicMock()
        mock_enforcer.call = AsyncMock(
            return_value={
                "success": True,
                "response": "Hi!",
                "budget": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "spent_usd": 0.002,
                },
            }
        )

        with (
            patch(
                "app.services.budget_enforcer.get_budget_enforcer",
                return_value=mock_enforcer,
            ),
            patch(
                "app.services.circuit_breaker_service.CircuitBreakerService"
            ) as mock_cb_cls,
        ):
            mock_cb = MagicMock()
            mock_cb.get_breaker = AsyncMock(return_value=None)
            mock_cb_cls.return_value = mock_cb
            result = await ne._handle_llm(db, node, context, budget, run_id)

        assert result["success"] is True
        # Verify the messages included the system prompt
        call_args = mock_enforcer.call.call_args
        messages = call_args[1]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful"
        assert messages[1]["role"] == "user"
