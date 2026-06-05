"""Tests for graph execution engine: interpreter, context, and handlers."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.graph_executor import ExecutionContext, GraphInterpreter
from app.services.graph_node_handlers import (
    BaseNodeHandler,
    ConditionNodeHandler,
    DelayNodeHandler,
    EndNodeHandler,
    LogNodeHandler,
    LoopNodeHandler,
    NodeHandlerRegistry,
    ParallelNodeHandler,
    StartNodeHandler,
    SubFlowNodeHandler,
    TaskNodeHandler,
    TransformNodeHandler,
    WebhookNodeHandler,
    ApprovalNodeHandler,
)


# ── ExecutionContext Tests ──


class TestExecutionContext:
    def test_init_with_input(self):
        ctx = ExecutionContext({"key": "value"})
        assert ctx.get("key") == "value"

    def test_set_get(self):
        ctx = ExecutionContext()
        ctx.set("foo", "bar")
        assert ctx.get("foo") == "bar"

    def test_node_output_roundtrip(self):
        ctx = ExecutionContext()
        ctx.set_node_output("n1", {"result": 42})
        assert ctx.get_node_output("n1") == {"result": 42}

    def test_resolve_direct_variable(self):
        ctx = ExecutionContext({"name": "Alice"})
        assert ctx.resolve_interpolation("{{name}}") == "Alice"

    def test_resolve_node_output(self):
        ctx = ExecutionContext()
        ctx.set_node_output("n1", {"output": {"text": "hello"}})
        assert ctx.resolve_interpolation("{{n1.output.text}}") == "hello"

    def test_resolve_missing_returns_none(self):
        ctx = ExecutionContext()
        assert ctx.resolve_interpolation("{{missing.key}}") is None

    def test_resolve_no_interpolation(self):
        ctx = ExecutionContext()
        assert ctx.resolve_interpolation("plain text") == "plain text"

    def test_to_dict_from_dict_roundtrip(self):
        ctx = ExecutionContext({"a": 1})
        ctx.set_node_output("n1", {"b": 2})
        data = ctx.to_dict()
        restored = ExecutionContext.from_dict(data)
        assert restored.get("a") == 1
        assert restored.get_node_output("n1") == {"b": 2}

    def test_interpolate_dict(self):
        ctx = ExecutionContext({"x": 10})
        result = ctx.interpolate_dict({"val": "{{x}}", "static": "hi"})
        assert result["val"] == 10
        assert result["static"] == "hi"

    def test_iteration_vars(self):
        ctx = ExecutionContext()
        ctx.set_iteration_var("i", 5)
        assert ctx.get_iteration_var("i") == 5


# ── Registry Tests ──


class TestNodeHandlerRegistry:
    def test_default_handlers_registered(self):
        reg = NodeHandlerRegistry()
        assert reg.get("task") is not None
        assert reg.get("webhook") is not None
        assert reg.get("condition") is not None
        assert reg.get("parallel") is not None
        assert reg.get("loop") is not None
        assert reg.get("approval") is not None
        assert reg.get("delay") is not None
        assert reg.get("transform") is not None
        assert reg.get("log") is not None
        assert reg.get("subflow") is not None
        assert reg.get("start") is not None
        assert reg.get("end") is not None

    def test_unknown_type_returns_none(self):
        reg = NodeHandlerRegistry()
        assert reg.get("nonexistent") is None

    def test_custom_registration(self):
        reg = NodeHandlerRegistry()
        custom = StartNodeHandler()
        reg.register("custom", custom)
        assert reg.get("custom") is custom

    def test_registered_types_count(self):
        reg = NodeHandlerRegistry()
        assert len(reg.registered_types()) == 12


# ── Handler Tests ──


class TestStartNodeHandler:
    @pytest.mark.asyncio
    async def test_execute(self):
        handler = StartNodeHandler()
        result = await handler.execute({"data": {"nodeType": "start"}}, ExecutionContext())
        assert result["success"] is True
        assert result["output"]["started"] is True


class TestEndNodeHandler:
    @pytest.mark.asyncio
    async def test_execute(self):
        handler = EndNodeHandler()
        result = await handler.execute({"data": {"nodeType": "end"}}, ExecutionContext())
        assert result["success"] is True
        assert result["output"]["completed"] is True


class TestTaskNodeHandler:
    @pytest.mark.asyncio
    async def test_validate_no_label(self):
        handler = TaskNodeHandler()
        errors = await handler.validate({"data": {"nodeType": "task"}})
        assert len(errors) == 1
        assert "label" in errors[0]

    @pytest.mark.asyncio
    async def test_validate_with_label(self):
        handler = TaskNodeHandler()
        errors = await handler.validate({"data": {"nodeType": "task", "label": "My Task"}})
        assert errors == []

    @pytest.mark.asyncio
    async def test_execute_no_model_router(self):
        handler = TaskNodeHandler()
        result = await handler.execute(
            {"data": {"nodeType": "task", "label": "Test", "description": "Do something"}},
            ExecutionContext(),
        )
        assert result["success"] is False


class TestWebhookNodeHandler:
    @pytest.mark.asyncio
    async def test_execute_no_url(self):
        handler = WebhookNodeHandler()
        result = await handler.execute(
            {"data": {"nodeType": "webhook", "method": "GET"}},
            ExecutionContext(),
        )
        assert result["success"] is False
        assert "url" in result["error"].lower() or "No URL" in result["error"]


class TestConditionNodeHandler:
    @pytest.mark.asyncio
    async def test_validate_no_expression(self):
        handler = ConditionNodeHandler()
        errors = await handler.validate({"data": {"nodeType": "condition"}})
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_execute_true(self):
        handler = ConditionNodeHandler()
        ctx = ExecutionContext({"count": 5})
        result = await handler.execute(
            {"data": {"nodeType": "condition", "expression": "ctx.get('count') > 3"}},
            ctx,
        )
        assert result["success"] is True
        assert result["output"]["result"] is True

    @pytest.mark.asyncio
    async def test_execute_false(self):
        handler = ConditionNodeHandler()
        ctx = ExecutionContext({"count": 1})
        result = await handler.execute(
            {"data": {"nodeType": "condition", "expression": "ctx.get('count') > 3"}},
            ctx,
        )
        assert result["success"] is True
        assert result["output"]["result"] is False

    @pytest.mark.asyncio
    async def test_blocks_dangerous_expression(self):
        handler = ConditionNodeHandler()
        result = await handler.execute(
            {"data": {"nodeType": "condition", "expression": "__import__('os').system('ls')"}},
            ExecutionContext(),
        )
        assert result["success"] is False
        assert "Blocked" in result["error"]


class TestLoopNodeHandler:
    @pytest.mark.asyncio
    async def test_count_mode(self):
        handler = LoopNodeHandler()
        result = await handler.execute(
            {"id": "loop1", "data": {"nodeType": "loop", "loopMode": "count", "loopCount": 3, "maxIterations": 100}},
            ExecutionContext(),
        )
        assert result["success"] is True
        assert result["output"]["iterations"] == 3

    @pytest.mark.asyncio
    async def test_max_iterations_enforced(self):
        handler = LoopNodeHandler()
        result = await handler.execute(
            {"id": "loop1", "data": {"nodeType": "loop", "loopMode": "count", "loopCount": 999, "maxIterations": 100}},
            ExecutionContext(),
        )
        assert result["success"] is True
        assert result["output"]["iterations"] == 100

    @pytest.mark.asyncio
    async def test_foreach_mode(self):
        handler = LoopNodeHandler()
        ctx = ExecutionContext({"items": [1, 2, 3]})
        result = await handler.execute(
            {"id": "loop1", "data": {"nodeType": "loop", "loopMode": "foreach", "loopExpression": "items", "maxIterations": 100}},
            ctx,
        )
        assert result["success"] is True
        assert result["output"]["iterations"] == 3

    @pytest.mark.asyncio
    async def test_with_interpreter_executes_downstream(self):
        handler = LoopNodeHandler()
        mock_interp = MagicMock()
        mock_interp.edges = [{"source": "loop1", "target": "task1"}]
        mock_interp._execute_node = AsyncMock(return_value={"success": True, "output": {"done": True}})

        result = await handler.execute(
            {"id": "loop1", "data": {"nodeType": "loop", "loopMode": "count", "loopCount": 2, "maxIterations": 100}},
            ExecutionContext(),
            interpreter=mock_interp,
        )
        assert result["success"] is True
        assert result["output"]["iterations"] == 2
        assert len(result["output"]["iteration_outputs"]) == 2
        assert mock_interp._execute_node.call_count == 2


class TestDelayNodeHandler:
    @pytest.mark.asyncio
    async def test_fixed_delay(self):
        handler = DelayNodeHandler()
        result = await handler.execute(
            {"data": {"nodeType": "delay", "delayMs": 10, "delayType": "fixed"}},
            ExecutionContext(),
        )
        assert result["success"] is True
        assert result["output"]["delayed_ms"] == 10

    @pytest.mark.asyncio
    async def test_exponential_delay(self):
        handler = DelayNodeHandler()
        result = await handler.execute(
            {"data": {"nodeType": "delay", "delayMs": 100, "delayType": "exponential", "maxDelayMs": 5000}},
            ExecutionContext(),
        )
        assert result["success"] is True
        assert result["output"]["delayed_ms"] == 200


class TestTransformNodeHandler:
    @pytest.mark.asyncio
    async def test_template_transform(self):
        handler = TransformNodeHandler()
        ctx = ExecutionContext({"name": "Alice"})
        result = await handler.execute(
            {"data": {"nodeType": "transform", "transformType": "template", "transformExpression": "Hello {{name}}"}},
            ctx,
        )
        assert result["success"] is True
        assert result["output"]["result"] == "Hello Alice"

    @pytest.mark.asyncio
    async def test_jq_transform(self):
        handler = TransformNodeHandler()
        ctx = ExecutionContext({"user": {"name": "Bob"}})
        result = await handler.execute(
            {"data": {"nodeType": "transform", "transformType": "jq", "transformExpression": ".user.name"}},
            ctx,
        )
        assert result["success"] is True
        assert result["output"]["result"] == "Bob"


class TestLogNodeHandler:
    @pytest.mark.asyncio
    async def test_log_message(self):
        handler = LogNodeHandler()
        ctx = ExecutionContext({"step": "done"})
        result = await handler.execute(
            {"data": {"nodeType": "log", "level": "info", "message": "Step {{step}}"}},
            ctx,
        )
        assert result["success"] is True
        assert result["output"]["logged"] is True
        assert "Step done" in result["output"]["message"]


class TestParallelNodeHandler:
    @pytest.mark.asyncio
    async def test_no_interpreter_fails(self):
        handler = ParallelNodeHandler()
        result = await handler.execute(
            {"id": "p1", "data": {"nodeType": "parallel", "joinMode": "all"}},
            ExecutionContext(),
        )
        assert result["success"] is False
        assert "interpreter" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_no_downstream_branches(self):
        handler = ParallelNodeHandler()
        mock_interp = MagicMock()
        mock_interp.edges = []
        result = await handler.execute(
            {"id": "p1", "data": {"nodeType": "parallel", "joinMode": "all"}},
            ExecutionContext(),
            interpreter=mock_interp,
        )
        assert result["success"] is True
        assert result["output"]["branches"] == {}

    @pytest.mark.asyncio
    async def test_executes_branches_concurrently(self):
        handler = ParallelNodeHandler()
        mock_interp = MagicMock()
        mock_interp.edges = [
            {"source": "p1", "target": "t1"},
            {"source": "p1", "target": "t2"},
        ]
        mock_interp._execute_node = AsyncMock(return_value={"success": True, "output": {"done": True}})

        result = await handler.execute(
            {"id": "p1", "data": {"nodeType": "parallel", "joinMode": "all"}},
            ExecutionContext(),
            interpreter=mock_interp,
        )
        assert result["success"] is True
        assert len(result["output"]["branches"]) == 2
        assert mock_interp._execute_node.call_count == 2


class TestApprovalNodeHandler:
    @pytest.mark.asyncio
    async def test_returns_pause_signal(self):
        handler = ApprovalNodeHandler()
        result = await handler.execute(
            {"data": {"nodeType": "approval", "approverRole": "manager"}},
            ExecutionContext(),
        )
        assert result["success"] is True
        assert result["pause"] is True
        assert result["output"]["status"] == "paused"

    @pytest.mark.asyncio
    async def test_with_interpreter_pauses_execution(self):
        handler = ApprovalNodeHandler()
        mock_interp = MagicMock()
        mock_interp.db = AsyncMock()
        mock_interp.execution = MagicMock()
        mock_interp.execution.id = "exec-1"

        with patch("app.services.graph_service.pause_execution", new_callable=AsyncMock) as mock_pause:
            result = await handler.execute(
                {"data": {"nodeType": "approval", "approverRole": "admin"}},
                ExecutionContext(),
                interpreter=mock_interp,
            )
            mock_pause.assert_called_once_with(mock_interp.db, "exec-1")
            assert result["pause"] is True


class TestSubFlowNodeHandler:
    @pytest.mark.asyncio
    async def test_no_mission_id_fails(self):
        handler = SubFlowNodeHandler()
        result = await handler.execute(
            {"data": {"nodeType": "subflow"}},
            ExecutionContext(),
        )
        assert result["success"] is False
        assert "missionId" in result["error"]

    @pytest.mark.asyncio
    async def test_no_interpreter_fails(self):
        handler = SubFlowNodeHandler()
        result = await handler.execute(
            {"data": {"nodeType": "subflow", "missionId": "sub-1"}},
            ExecutionContext(),
        )
        assert result["success"] is False
        assert "interpreter" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_depth_limit(self):
        handler = SubFlowNodeHandler()
        ctx = ExecutionContext({"_subflow_depth": 5})
        result = await handler.execute(
            {"data": {"nodeType": "subflow", "missionId": "sub-1"}},
            ctx,
        )
        assert result["success"] is False
        assert "depth limit" in result["error"].lower()


# ── GraphInterpreter Tests ──


class TestGraphInterpreter:
    def _make_interpreter(self, nodes, edges, input_data=None):
        workflow = MagicMock()
        workflow.id = "wf-1"
        workflow.graph_definition = {"nodes": nodes, "edges": edges}
        execution = MagicMock()
        execution.id = "exec-1"
        execution.input_data = input_data or {}
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        return GraphInterpreter(db, workflow, execution)

    def test_topological_sort_linear(self):
        nodes = [
            {"id": "a", "data": {"nodeType": "start"}},
            {"id": "b", "data": {"nodeType": "task", "label": "T"}},
            {"id": "c", "data": {"nodeType": "end"}},
        ]
        edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]
        interp = self._make_interpreter(nodes, edges)
        layers = interp._topological_sort()
        assert layers is not None
        assert layers[0] == ["a"]
        assert layers[1] == ["b"]
        assert layers[2] == ["c"]

    def test_topological_sort_cycle(self):
        nodes = [
            {"id": "a", "data": {"nodeType": "task", "label": "A"}},
            {"id": "b", "data": {"nodeType": "task", "label": "B"}},
        ]
        edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]
        interp = self._make_interpreter(nodes, edges)
        assert interp._topological_sort() is None

    def test_topological_sort_empty(self):
        interp = self._make_interpreter([], [])
        assert interp._topological_sort() is None or interp._topological_sort() == []

    @pytest.mark.asyncio
    async def test_execute_empty_graph(self):
        interp = self._make_interpreter([], [])
        result = await interp.execute()
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_execute_simple_graph(self):
        nodes = [
            {"id": "s", "data": {"nodeType": "start"}},
            {"id": "e", "data": {"nodeType": "end"}},
        ]
        edges = [{"source": "s", "target": "e"}]
        interp = self._make_interpreter(nodes, edges)
        result = await interp.execute()
        assert result["status"] == "completed"
        assert "s" in result["outputs"]
        assert "e" in result["outputs"]

    @pytest.mark.asyncio
    async def test_approval_pauses_execution(self):
        nodes = [
            {"id": "s", "data": {"nodeType": "start"}},
            {"id": "a", "data": {"nodeType": "approval", "approverRole": "admin"}},
            {"id": "e", "data": {"nodeType": "end"}},
        ]
        edges = [{"source": "s", "target": "a"}, {"source": "a", "target": "e"}]
        interp = self._make_interpreter(nodes, edges)

        with patch("app.services.graph_service.pause_execution", new_callable=AsyncMock):
            result = await interp.execute()
            assert result["status"] == "paused"
            assert result["paused_at"] == "a"
            assert "e" not in result["outputs"]
