"""Tests for the `variable_set` Data Control node.

The node writes a named value into the run-scoped ``context["inputs"]`` dict
that ``interpolate_inputs`` already reads, so a downstream
``{{ inputs.<varName> }}`` token resolves. Covers:

  * literal value write + interpolation read-back
  * optional `prefix` isolation of scopes
  * optional `varExpr` safe-expression evaluation (wins over literal value)
  * missing `varName` → failure (no silent no-op)
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


async def _run_variable_set(node, context):
    """Drive _handle_variable_set with a mocked event log (no DB writes)."""
    executor, Budget, _NodeType, _WF = _make_executor()
    mock_event_log = AsyncMock()
    mock_event_log.append = AsyncMock(return_value=[MagicMock(sequence=1)])
    with patch(
        "app.services.substrate.node_executor.get_event_log",
        return_value=mock_event_log,
    ):
        return await executor._handle_variable_set(
            db=AsyncMock(),
            node=node,
            context=context,
            run_id="run-1",
            workflow=MagicMock(id="m1", user_id="u1"),
        )


class TestVariableSetNode:
    """variable_set writes into context["inputs"]; downstream interp reads it."""

    @pytest.mark.asyncio
    async def test_literal_value_resolves_downstream_inputs_token(self):
        from app.services.substrate.interpolate import interpolate_inputs

        executor, Budget, NodeType, WorkflowNode = _make_executor()
        context = {"inputs": {}}

        node = WorkflowNode(
            id="v1",
            type=NodeType.VARIABLE_SET,
            title="Set X",
            config={"varName": "x", "varValue": "hello"},
        )
        result = await _run_variable_set(node, context)
        assert result["success"] is True
        assert result["output"]["key"] == "x"
        assert result["output"]["value"] == "hello"

        # The write must be visible to interpolate_inputs on the same context.
        rendered = interpolate_inputs("value={{ inputs.x }}", context["inputs"])
        assert rendered == "value=hello"

    @pytest.mark.asyncio
    async def test_var_expr_overrides_literal_value(self):
        executor, Budget, NodeType, WorkflowNode = _make_executor()
        # The expression namespace is the flat context dict; previously-set
        # variables live under the "inputs" key, referenced via subscript.
        context = {"inputs": {"count": 4}}

        node = WorkflowNode(
            id="v1",
            type=NodeType.VARIABLE_SET,
            title="Inc",
            config={"varName": "next", "varValue": "ignored", "varExpr": "inputs['count'] + 1"},
        )
        result = await _run_variable_set(node, context)
        assert result["success"] is True
        assert result["output"]["value"] == 5
        assert context["inputs"]["next"] == 5

    @pytest.mark.asyncio
    async def test_prefix_isolates_scope(self):
        executor, Budget, NodeType, WorkflowNode = _make_executor()
        context = {"inputs": {}}

        node = WorkflowNode(
            id="v1",
            type=NodeType.VARIABLE_SET,
            title="Scoped",
            config={"varName": "x", "varValue": "scoped", "prefix": "step1."},
        )
        result = await _run_variable_set(node, context)
        assert result["success"] is True
        assert result["output"]["key"] == "step1.x"
        # Prefixed key present, unprefixed absent → scopes don't collide.
        assert context["inputs"]["step1.x"] == "scoped"
        assert "x" not in context["inputs"]

    @pytest.mark.asyncio
    async def test_missing_var_name_fails(self):
        executor, Budget, NodeType, WorkflowNode = _make_executor()
        context = {"inputs": {}}

        node = WorkflowNode(
            id="v1",
            type=NodeType.VARIABLE_SET,
            title="Bad",
            config={"varValue": "x"},
        )
        result = await _run_variable_set(node, context)
        assert result["success"] is False
        assert "varName" in result["error"]

    @pytest.mark.asyncio
    async def test_creates_inputs_dict_when_absent(self):
        from app.services.substrate.interpolate import interpolate_inputs

        executor, Budget, NodeType, WorkflowNode = _make_executor()
        context: dict = {}  # no "inputs" key at all

        node = WorkflowNode(
            id="v1",
            type=NodeType.VARIABLE_SET,
            title="Seed",
            config={"varName": "seed", "varValue": "42"},
        )
        result = await _run_variable_set(node, context)
        assert result["success"] is True
        assert "inputs" in context
        assert interpolate_inputs("{{ inputs.seed }}", context["inputs"]) == "42"

    @pytest.mark.asyncio
    async def test_invalid_expr_fails_cleanly(self):
        executor, Budget, NodeType, WorkflowNode = _make_executor()
        context = {"inputs": {}}

        node = WorkflowNode(
            id="v1",
            type=NodeType.VARIABLE_SET,
            title="BadExpr",
            config={"varName": "x", "varExpr": "import os; os.system('echo pwn')"},
        )
        result = await _run_variable_set(node, context)
        assert result["success"] is False
        assert "expr" in result["error"]
