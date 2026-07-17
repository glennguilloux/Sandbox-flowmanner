"""
Integration tests for UnifiedExecutor + Strategy execution.

Exercises the full executor pipeline (SoloStrategy, DAGStrategy) with
mocked LLM calls, event log, and database session.  Targets the executor.py
coverage gap — the strategy dispatch, node execution, retry logic,
circuit breaker, budget enforcement, abort signals, and crash recovery.

Usage:
    pytest tests/integration/test_executor_strategies.py -v
"""

from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

from app.models.capability_models import Budget, BudgetExhausted
from app.models.substrate_models import SubstrateEventType
from app.services.substrate.executor import UnifiedExecutor, _find_resume_point
from app.services.substrate.node_executor import NodeExecutor
from app.services.substrate.strategies.dag import DAGStrategy
from app.services.substrate.strategies.graph import GraphStrategy
from app.services.substrate.strategies.langgraph import LangGraphStrategy
from app.services.substrate.strategies.meta import MetaStrategy
from app.services.substrate.strategies.pipeline import PipelineStrategy
from app.services.substrate.strategies.solo import SoloStrategy
from app.services.substrate.strategies.swarm import SwarmStrategy
from app.services.substrate.workflow_models import (
    NodeType,
    StrategyResult,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    WorkflowType,
)

pytestmark = pytest.mark.integration


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures & Helpers
# ═══════════════════════════════════════════════════════════════════════════

# The patch target for get_budget_enforcer — imported locally inside _handle_llm
BUDGET_ENFORCER_PATCH = "app.services.budget_enforcer.get_budget_enforcer"


def _make_llm_node(
    node_id: str = "node-1",
    title: str = "Summarize",
    prompt: str = "Summarize this",
    model: str = "deepseek-chat",
    max_retries: int = 3,
    **extra_config,
) -> WorkflowNode:
    """Create an LLM_CALL node."""
    config = {"prompt": prompt, "model_id": model, **extra_config}
    return WorkflowNode(
        id=node_id,
        type=NodeType.LLM_CALL,
        title=title,
        description=f"LLM task: {title}",
        config=config,
        assigned_model=model,
        max_retries=max_retries,
    )


def _make_code_node(
    node_id: str = "code-1",
    code: str = "print(42)",
    max_retries: int = 1,
) -> WorkflowNode:
    """Create a CODE_EXECUTION node."""
    return WorkflowNode(
        id=node_id,
        type=NodeType.CODE_EXECUTION,
        title="Execute code",
        config={"code": code},
        max_retries=max_retries,
    )


def _make_solo_workflow(
    node: WorkflowNode | None = None,
    *,
    workflow_id: str | None = None,
    user_id: str = "42",
) -> Workflow:
    """Create a solo workflow with one node."""
    node = node or _make_llm_node()
    return Workflow(
        id=workflow_id or str(uuid4()),
        type=WorkflowType.SOLO,
        title="Solo Workflow",
        description="A single-node test workflow",
        nodes=[node],
        edges=[],
        budget=Budget(
            max_cost_usd=Decimal("5.00"),
            max_wall_time_seconds=120,
            max_iterations=50,
            max_depth=5,
        ),
        user_id=user_id,
        metadata={"substrate_run_id": str(uuid4())},
    )


def _make_dag_workflow(
    nodes: list[WorkflowNode] | None = None,
    edges: list[WorkflowEdge] | None = None,
    *,
    workflow_id: str | None = None,
    user_id: str = "42",
) -> Workflow:
    """Create a DAG workflow with two dependent nodes."""
    n1 = _make_llm_node(node_id="fetch", title="Fetch Data", max_retries=2)
    n2 = _make_llm_node(node_id="summarize", title="Summarize", max_retries=2)
    n2.dependencies = ["fetch"]

    nodes = nodes or [n1, n2]
    edges = edges or [WorkflowEdge(source="fetch", target="summarize")]

    return Workflow(
        id=workflow_id or str(uuid4()),
        type=WorkflowType.DAG,
        title="DAG Workflow",
        description="A two-node DAG",
        nodes=nodes,
        edges=edges,
        budget=Budget(
            max_cost_usd=Decimal("10.00"),
            max_wall_time_seconds=300,
            max_iterations=100,
            max_depth=5,
        ),
        user_id=user_id,
        metadata={"substrate_run_id": str(uuid4())},
    )


def _make_dag_three_layer(
    *,
    workflow_id: str | None = None,
    user_id: str = "42",
) -> Workflow:
    """Create a 3-layer DAG: A → {B, C} → D."""
    a = _make_llm_node(node_id="a", title="Node A")
    b = _make_llm_node(node_id="b", title="Node B")
    c = _make_llm_node(node_id="c", title="Node C")
    d = _make_llm_node(node_id="d", title="Node D")
    b.dependencies = ["a"]
    c.dependencies = ["a"]
    d.dependencies = ["b", "c"]

    return Workflow(
        id=workflow_id or str(uuid4()),
        type=WorkflowType.DAG,
        title="3-Layer DAG",
        nodes=[a, b, c, d],
        edges=[
            WorkflowEdge(source="a", target="b"),
            WorkflowEdge(source="a", target="c"),
            WorkflowEdge(source="b", target="d"),
            WorkflowEdge(source="c", target="d"),
        ],
        budget=Budget(
            max_cost_usd=Decimal("20.00"),
            max_wall_time_seconds=600,
            max_iterations=200,
            max_depth=10,
        ),
        user_id=user_id,
        metadata={"substrate_run_id": str(uuid4())},
    )


_PHASES = ["dispatch", "research", "draft", "debate", "consensus", "synthesis", "review"]


def _make_valid_strategy_workflow(wf_type: WorkflowType) -> Workflow:
    """Build a minimal VALID workflow of the given strategy type.

    No dangling edges and no other validation errors, so that appending a
    single dangling edge isolates the edge-endpoint check.  Used by the
    edge-endpoint parity tests (F3 parity: every strategy must reject a
    dangling edge source/target, not only DAG/Graph).
    """
    nodes: list[WorkflowNode] = []
    edges: list[WorkflowEdge] = []

    if wf_type == WorkflowType.DAG:
        a = _make_llm_node(node_id="a")
        b = _make_llm_node(node_id="b")
        b.dependencies = ["a"]
        nodes = [a, b]
        edges = [WorkflowEdge(source="a", target="b")]
    elif wf_type == WorkflowType.GRAPH:
        a = _make_llm_node(node_id="a")
        b = _make_llm_node(node_id="b")
        nodes = [a, b]
        edges = [WorkflowEdge(source="a", target="b")]
    elif wf_type == WorkflowType.SWARM:
        fo = WorkflowNode(id="fo", type=NodeType.FAN_OUT, title="Fan Out")
        fi = WorkflowNode(id="fi", type=NodeType.FAN_IN, title="Fan In")
        nodes = [fo, fi]
        edges = [WorkflowEdge(source="fo", target="fi")]
    elif wf_type == WorkflowType.PIPELINE:
        nodes = [WorkflowNode(id=p, type=NodeType.PHASE_GATE, title=p, config={"phase": p}) for p in _PHASES]
        edges = [WorkflowEdge(source=_PHASES[i], target=_PHASES[i + 1]) for i in range(len(_PHASES) - 1)]
    elif wf_type == WorkflowType.META:
        nodes = [WorkflowNode(id="sub", type=NodeType.SUB_WORKFLOW, title="Sub", config={})]
    elif wf_type == WorkflowType.LANGGRAPH:
        nodes = [
            WorkflowNode(
                id="g",
                type=NodeType.LLM_CALL,
                title="Graph",
                config={"graph_name": "governance"},
            )
        ]
    else:
        raise ValueError(f"unsupported workflow type for helper: {wf_type}")

    return Workflow(
        id=str(uuid4()),
        type=wf_type,
        title=f"{wf_type.value} parity",
        description="edge-endpoint parity workflow",
        nodes=nodes,
        edges=edges,
        budget=Budget(
            max_cost_usd=Decimal("5.00"),
            max_wall_time_seconds=120,
            max_iterations=50,
            max_depth=5,
        ),
        user_id="42",
        metadata={"substrate_run_id": str(uuid4())},
    )


def _mock_llm_response(
    content: str = "LLM response text",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    spent_usd: float = 0.001,
) -> dict:
    """A successful BudgetEnforcer.call() response.

    Must include both ``cost`` (used by run_service) and ``budget``
    (used by node_executor._handle_llm to extract token counts via
    ``budget_info.get('prompt_tokens')`` / ``budget_info.get('completion_tokens')``).
    """
    return {
        "success": True,
        "response": content,
        "model": "deepseek-chat",
        "provider": "deepseek",
        "cost": {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
        },
        "budget": {
            "spent_usd": spent_usd,
            "remaining_usd": 4.999,
            "iterations_used": 1,
            "budget_exhausted": False,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }


def _mock_llm_failure(error: str = "Model unavailable") -> dict:
    """A failed BudgetEnforcer.call() response."""
    return {
        "success": False,
        "error": error,
        "model": "deepseek-chat",
        "provider": "deepseek",
        "cost": {"input_tokens": 0, "output_tokens": 0},
        "budget": {
            "spent_usd": 0.0,
            "remaining_usd": 5.0,
            "iterations_used": 1,
            "budget_exhausted": False,
        },
    }


def _make_mock_event_log():
    """Create a properly configured mock EventLog.

    NodeExecutor calls get_event_log() directly (singleton bypass), so
    this mock needs to be patched into that module-level function.
    The mock's _count_events and get_latest_sequence return plain ints
    (not coroutines) so the real EventLog.append arithmetic works.
    """
    el = MagicMock()
    el.run_exists = AsyncMock(return_value=False)
    el.get_latest_sequence = AsyncMock(return_value=0)
    # _handle_llm awaits find_by_idempotency_key (node_executor.py:508) for the
    # LLM-output replay cache. Returning None = cache miss, so the node proceeds
    # to the (mocked) budget-enforcer LLM call. Omitting this leaves a plain
    # MagicMock, which cannot be awaited -> TypeError for every strategy path.
    el.find_by_idempotency_key = AsyncMock(return_value=None)
    el.MAX_EVENTS_PER_RUN = 100_000

    _events: list = []

    async def _append(db, run_id, events, **kwargs):
        for e in events:
            mock_event = MagicMock()
            mock_event.type = e["type"]
            mock_event.payload = e.get("payload", {})
            mock_event.run_id = run_id
            mock_event.sequence = len(_events) + 1
            mock_event.blueprint_id = kwargs.get("blueprint_id")
            mock_event.mission_id = e.get("mission_id")
            _events.append(mock_event)
        return _events[-len(events) :]

    async def _get_events(db, run_id, event_type=None, **kwargs):
        """Filter stored events by event_type if provided."""
        if event_type is not None:
            return [e for e in _events if e.type == event_type]
        return list(_events)

    el.append = AsyncMock(side_effect=_append)
    el.get_events = AsyncMock(side_effect=_get_events)
    el._events = _events
    return el


@pytest.fixture
def mock_db():
    """Mock async database session."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    # begin_nested for circuit breaker savepoints
    nested_ctx = AsyncMock()
    nested_ctx.__aenter__ = AsyncMock()
    nested_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested_ctx)
    return db


@pytest.fixture
def mock_event_log():
    """Mock EventLog for the executor constructor (used for event recording)."""
    return _make_mock_event_log()


@pytest.fixture
def mock_replay_engine():
    """Mock ReplayEngine."""
    re = AsyncMock()
    re.rebuild_state = AsyncMock()
    return re


def _make_executor(
    event_log=None,
    replay_engine=None,
) -> UnifiedExecutor:
    """Create a UnifiedExecutor with mocked dependencies."""
    executor = UnifiedExecutor(
        event_log=event_log or _make_mock_event_log(),
        replay_engine=replay_engine or AsyncMock(),
    )
    # Disable circuit breaker by default (savepoint errors in mock DB)
    executor._ensure_circuit_breaker = AsyncMock()
    return executor


# ═══════════════════════════════════════════════════════════════════════════
# Context manager for patching BOTH budget enforcer AND event log
# ═══════════════════════════════════════════════════════════════════════════


def _patch_budget_and_event_log(mock_enforcer=None, mock_el=None):
    """Return a context manager that patches both budget enforcer and event log.

    NodeExecutor calls ``get_event_log()`` directly (singleton), bypassing
    the executor's injected event_log.  We must also patch that path.
    """
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        enforcer = mock_enforcer or AsyncMock()
        with (
            patch(BUDGET_ENFORCER_PATCH) as mock_get_enf,
            patch("app.services.substrate.node_executor.get_event_log") as mock_get_el,
        ):
            mock_get_enf.return_value = enforcer
            mock_get_el.return_value = mock_el or _make_mock_event_log()
            yield enforcer

    return _ctx()


# ═══════════════════════════════════════════════════════════════════════════
# SoloStrategy Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSoloStrategy:
    """Test SoloStrategy execution with mocked LLM."""

    @pytest.mark.asyncio
    async def test_solo_success(self, mock_db, mock_event_log):
        """Solo workflow with one LLM node executes successfully."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            strategy = SoloStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert result.status == "completed"
        assert len(result.completed_nodes) == 1
        assert len(result.failed_nodes) == 0
        assert result.total_tokens == 150  # 100 + 50
        assert result.data is not None

    @pytest.mark.asyncio
    async def test_solo_llm_failure(self, mock_db, mock_event_log):
        """Solo workflow fails when LLM returns failure."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_failure("Rate limit"))),
            mock_el=mock_event_log,
        ):
            strategy = SoloStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert result.status == "failed"
        assert len(result.failed_nodes) == 1
        assert "Rate limit" in (result.error or "")

    @pytest.mark.asyncio
    async def test_solo_empty_llm_response_fails(self, mock_db, mock_event_log):
        """Solo workflow fails when LLM returns empty response."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(
                call=AsyncMock(
                    return_value={
                        "success": True,
                        "response": "",
                        "model": "deepseek-chat",
                        "provider": "deepseek",
                        "cost": {"input_tokens": 10, "output_tokens": 0},
                        "budget": {
                            "spent_usd": 0.0,
                            "remaining_usd": 5.0,
                            "iterations_used": 1,
                            "budget_exhausted": False,
                        },
                    }
                )
            ),
            mock_el=mock_event_log,
        ):
            strategy = SoloStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert "empty" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_solo_aborted_before_execution(self, mock_db, mock_event_log):
        """Solo workflow returns aborted when abort signal is set."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        run_id = workflow.metadata["substrate_run_id"]
        executor._abort_signals[run_id] = asyncio.Event()
        executor._abort_signals[run_id].set()

        strategy = SoloStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert result.status == "aborted"

    @pytest.mark.asyncio
    async def test_solo_with_system_prompt(self, mock_db, mock_event_log):
        """Solo LLM node with system_prompt sends two messages."""
        node = _make_llm_node()
        node.config["system_prompt"] = "You are a helpful assistant."
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        mock_enforcer = AsyncMock(call=AsyncMock(return_value=_mock_llm_response()))

        with _patch_budget_and_event_log(
            mock_enforcer=mock_enforcer,
            mock_el=mock_event_log,
        ):
            strategy = SoloStrategy()
            await strategy.execute(workflow, {}, executor, mock_db)

        call_kwargs = mock_enforcer.call.call_args.kwargs
        messages = call_kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


class TestSoloStrategyValidation:
    """Test SoloStrategy.validate()."""

    @pytest.mark.asyncio
    async def test_validate_accepts_single_node_no_edges(self):
        workflow = _make_solo_workflow()
        strategy = SoloStrategy()
        errors = await strategy.validate(workflow)
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_rejects_multiple_nodes(self):
        workflow = _make_solo_workflow()
        workflow.nodes.append(_make_llm_node(node_id="node-2"))
        strategy = SoloStrategy()
        errors = await strategy.validate(workflow)
        assert any("exactly 1 node" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_edges(self):
        workflow = _make_solo_workflow()
        workflow.edges.append(WorkflowEdge(source="node-1", target="node-2"))
        strategy = SoloStrategy()
        errors = await strategy.validate(workflow)
        assert any("no edges" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════════════
# DAGStrategy Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestDAGStrategy:
    """Test DAGStrategy execution with mocked LLM."""

    @pytest.mark.asyncio
    async def test_dag_two_node_success(self, mock_db, mock_event_log):
        """Two-node DAG: fetch → summarize, both succeed."""
        workflow = _make_dag_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            strategy = DAGStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert result.status == "completed"
        assert len(result.completed_nodes) == 2
        assert "fetch" in result.completed_nodes
        assert "summarize" in result.completed_nodes
        assert result.total_tokens == 300
        assert "fetch" in result.data
        assert "summarize" in result.data

    @pytest.mark.asyncio
    async def test_dag_three_layer_parallel(self, mock_db, mock_event_log):
        """Three-layer DAG: A → {B, C} → D. B and C execute in parallel."""
        workflow = _make_dag_three_layer()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            strategy = DAGStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert len(result.completed_nodes) == 4
        assert result.total_tokens == 600

    @pytest.mark.asyncio
    async def test_dag_partial_failure(self, mock_db, mock_event_log):
        """DAG where the first node fails → overall DAG reports failure.

        Uses max_retries=0 on fetch so the first failure isn't retried.
        """
        n1 = _make_llm_node(node_id="fetch", title="Fetch Data", max_retries=0)
        n2 = _make_llm_node(node_id="summarize", title="Summarize", max_retries=0)
        n2.dependencies = ["fetch"]
        workflow = _make_dag_workflow(
            nodes=[n1, n2],
            edges=[WorkflowEdge(source="fetch", target="summarize")],
        )
        executor = _make_executor(event_log=mock_event_log)

        call_count = 0

        async def _alternating(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_llm_failure("API Error")
            return _mock_llm_response()

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(side_effect=_alternating)),
            mock_el=mock_event_log,
        ):
            strategy = DAGStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert "fetch" in result.failed_nodes

    @pytest.mark.asyncio
    async def test_dag_aborted_between_layers(self, mock_db, mock_event_log):
        """DAG aborts mid-execution when abort signal is set between layers."""
        workflow = _make_dag_three_layer()
        executor = _make_executor(event_log=mock_event_log)
        run_id = workflow.metadata["substrate_run_id"]

        call_count = 0

        async def _abort_after_first(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                executor._abort_signals[run_id] = asyncio.Event()
                executor._abort_signals[run_id].set()
            return _mock_llm_response()

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(side_effect=_abort_after_first)),
            mock_el=mock_event_log,
        ):
            strategy = DAGStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert result.status == "aborted"
        assert "a" in result.completed_nodes

    @pytest.mark.asyncio
    async def test_dag_node_output_flows_to_downstream(self, mock_db, mock_event_log):
        """DAG passes previous_outputs context to downstream nodes."""
        workflow = _make_dag_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            strategy = DAGStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert result.data["fetch"] is not None
        assert result.data["summarize"] is not None


class TestDAGStrategyValidation:
    """Test DAGStrategy.validate()."""

    @pytest.mark.asyncio
    async def test_validate_accepts_valid_dag(self):
        workflow = _make_dag_workflow()
        strategy = DAGStrategy()
        errors = await strategy.validate(workflow)
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_dag(self):
        workflow = Workflow(
            id=str(uuid4()),
            type=WorkflowType.DAG,
            title="Empty DAG",
            nodes=[],
            edges=[],
        )
        strategy = DAGStrategy()
        errors = await strategy.validate(workflow)
        assert any("at least 1 node" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_source(self):
        workflow = _make_dag_workflow()
        workflow.edges.append(WorkflowEdge(source="nonexistent", target="summarize"))
        strategy = DAGStrategy()
        errors = await strategy.validate(workflow)
        assert any("Edge source" in e and "nonexistent" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_target(self):
        workflow = _make_dag_workflow()
        workflow.edges.append(WorkflowEdge(source="fetch", target="nonexistent"))
        strategy = DAGStrategy()
        errors = await strategy.validate(workflow)
        assert any("Edge target" in e and "nonexistent" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_cycle(self):
        """A → B → A is a cycle."""
        a = _make_llm_node(node_id="a")
        b = _make_llm_node(node_id="b")
        b.dependencies = ["a"]
        workflow = Workflow(
            id=str(uuid4()),
            type=WorkflowType.DAG,
            title="Cyclic DAG",
            nodes=[a, b],
            edges=[
                WorkflowEdge(source="a", target="b"),
                WorkflowEdge(source="b", target="a"),
            ],
        )
        strategy = DAGStrategy()
        errors = await strategy.validate(workflow)
        assert any("cycle" in e.lower() for e in errors)


# ═══════════════════════════════════════════════════════════════════════════
# Edge-endpoint parity (F3): every strategy must reject dangling edges.
# Previously only DAG/Graph checked this; Swarm/Pipeline/Meta/LangGraph
# silently accepted a dangling edge (source or target names a missing node).
# ═══════════════════════════════════════════════════════════════════════════


class TestSwarmEdgeParity:
    """SwarmStrategy must reject a dangling edge source/target."""

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_source(self):
        wf = _make_valid_strategy_workflow(WorkflowType.SWARM)
        wf.edges.append(WorkflowEdge(source="nonexistent", target="fi"))
        errors = await SwarmStrategy().validate(wf)
        assert any("Edge source" in e and "nonexistent" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_target(self):
        wf = _make_valid_strategy_workflow(WorkflowType.SWARM)
        wf.edges.append(WorkflowEdge(source="fo", target="nonexistent"))
        errors = await SwarmStrategy().validate(wf)
        assert any("Edge target" in e and "nonexistent" in e for e in errors)


class TestPipelineEdgeParity:
    """PipelineStrategy must reject a dangling edge source/target."""

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_source(self):
        wf = _make_valid_strategy_workflow(WorkflowType.PIPELINE)
        wf.edges.append(WorkflowEdge(source="nonexistent", target="research"))
        errors = await PipelineStrategy().validate(wf)
        assert any("Edge source" in e and "nonexistent" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_target(self):
        wf = _make_valid_strategy_workflow(WorkflowType.PIPELINE)
        wf.edges.append(WorkflowEdge(source="dispatch", target="nonexistent"))
        errors = await PipelineStrategy().validate(wf)
        assert any("Edge target" in e and "nonexistent" in e for e in errors)


class TestMetaEdgeParity:
    """MetaStrategy must reject a dangling edge source/target."""

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_source(self):
        wf = _make_valid_strategy_workflow(WorkflowType.META)
        wf.edges.append(WorkflowEdge(source="nonexistent", target="sub"))
        errors = await MetaStrategy().validate(wf)
        assert any("Edge source" in e and "nonexistent" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_target(self):
        wf = _make_valid_strategy_workflow(WorkflowType.META)
        wf.edges.append(WorkflowEdge(source="sub", target="nonexistent"))
        errors = await MetaStrategy().validate(wf)
        assert any("Edge target" in e and "nonexistent" in e for e in errors)


class TestLangGraphEdgeParity:
    """LangGraphStrategy must reject a dangling edge source/target."""

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_source(self):
        wf = _make_valid_strategy_workflow(WorkflowType.LANGGRAPH)
        wf.edges.append(WorkflowEdge(source="nonexistent", target="g"))
        errors = await LangGraphStrategy().validate(wf)
        assert any("Edge source" in e and "nonexistent" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_target(self):
        wf = _make_valid_strategy_workflow(WorkflowType.LANGGRAPH)
        wf.edges.append(WorkflowEdge(source="g", target="nonexistent"))
        errors = await LangGraphStrategy().validate(wf)
        assert any("Edge target" in e and "nonexistent" in e for e in errors)


class TestDAGTopologicalSort:
    """Test DAGStrategy._topological_sort() in isolation."""

    def test_linear_chain(self):
        a = _make_llm_node(node_id="a")
        b = _make_llm_node(node_id="b")
        b.dependencies = ["a"]
        workflow = _make_dag_workflow(nodes=[a, b], edges=[WorkflowEdge(source="a", target="b")])
        strategy = DAGStrategy()
        layers = strategy._topological_sort(workflow)
        assert len(layers) == 2
        assert layers[0] == ["a"]
        assert layers[1] == ["b"]

    def test_diamond_shape(self):
        """A → {B, C} → D"""
        workflow = _make_dag_three_layer()
        strategy = DAGStrategy()
        layers = strategy._topological_sort(workflow)
        assert len(layers) == 3
        assert layers[0] == ["a"]
        assert set(layers[1]) == {"b", "c"}
        assert layers[2] == ["d"]

    def test_independent_nodes(self):
        """All nodes in a single layer."""
        a = _make_llm_node(node_id="a")
        b = _make_llm_node(node_id="b")
        c = _make_llm_node(node_id="c")
        workflow = _make_dag_workflow(nodes=[a, b, c], edges=[])
        strategy = DAGStrategy()
        layers = strategy._topological_sort(workflow)
        assert len(layers) == 1
        assert set(layers[0]) == {"a", "b", "c"}


# ═══════════════════════════════════════════════════════════════════════════
# UnifiedExecutor Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestUnifiedExecutorExecute:
    """Test UnifiedExecutor.execute() — the top-level entry point."""

    @pytest.mark.asyncio
    async def test_execute_solo_workflow(self, mock_db, mock_event_log):
        """UnifiedExecutor.execute() with a solo workflow."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.success is True
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_dag_workflow(self, mock_db, mock_event_log):
        """UnifiedExecutor.execute() with a DAG workflow."""
        workflow = _make_dag_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.success is True
        assert len(result.completed_nodes) == 2

    @pytest.mark.asyncio
    async def test_execute_validates_workflow(self, mock_db, mock_event_log):
        """UnifiedExecutor validates workflow before executing."""
        workflow = _make_solo_workflow()
        workflow.nodes.append(_make_llm_node(node_id="node-2"))
        executor = _make_executor(event_log=mock_event_log)

        result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.success is False
        assert result.status == "failed"
        assert "validation" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_execute_budget_exhausted(self, mock_db, mock_event_log):
        """BudgetExhausted during execution is caught and reported."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(side_effect=BudgetExhausted("Cost exceeded", workflow.budget))),
            mock_el=mock_event_log,
        ):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.success is False
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_execute_unhandled_exception(self, mock_db, mock_event_log):
        """Unhandled exception in strategy is caught and reported."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with patch.object(SoloStrategy, "execute", side_effect=RuntimeError("Crash")):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.success is False
        assert result.status == "failed"
        assert "Crash" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_records_started_and_terminal_events(self, mock_db, mock_event_log):
        """execute() emits MISSION_STARTED and MISSION_COMPLETED events."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert mock_event_log.append.call_count >= 2
        calls = mock_event_log.append.call_args_list
        first_type = calls[0].args[2][0]["type"]
        last_type = calls[-1].args[2][0]["type"]
        assert first_type == SubstrateEventType.MISSION_STARTED
        assert last_type == SubstrateEventType.MISSION_COMPLETED

    @pytest.mark.asyncio
    async def test_execute_records_failed_event_on_failure(self, mock_db, mock_event_log):
        """execute() emits MISSION_FAILED when workflow fails."""
        workflow = _make_solo_workflow()
        workflow.nodes[0].max_retries = 0
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_failure())),
            mock_el=mock_event_log,
        ):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.status == "failed"
        calls = mock_event_log.append.call_args_list
        last_type = calls[-1].args[2][0]["type"]
        assert last_type == SubstrateEventType.MISSION_FAILED

    @pytest.mark.asyncio
    async def test_execute_passes_blueprint_id_to_events(self, mock_db, mock_event_log):
        """execute() passes blueprint_id to EventLog.append()."""
        workflow = _make_solo_workflow()
        bp_id = str(uuid4())
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            await executor.execute(db=mock_db, workflow=workflow, blueprint_id=bp_id)

        first_call_kwargs = mock_event_log.append.call_args_list[0].kwargs
        assert first_call_kwargs.get("blueprint_id") == bp_id

    @pytest.mark.asyncio
    async def test_execute_sets_execution_time_ms(self, mock_db, mock_event_log):
        """execute() populates execution_time_ms on the result."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_execute_with_existing_run_id(self, mock_db, mock_event_log):
        """execute() uses the provided run_id."""
        workflow = _make_solo_workflow()
        custom_run_id = str(uuid4())
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            await executor.execute(db=mock_db, workflow=workflow, run_id=custom_run_id)

        first_call_args = mock_event_log.append.call_args_list[0].args
        assert first_call_args[1] == custom_run_id


class TestUnifiedExecutorCrashRecovery:
    """Test crash recovery via ReplayEngine."""

    @pytest.mark.asyncio
    async def test_resume_completed_run_returns_immediately(self, mock_db, mock_event_log, mock_replay_engine):
        """If a run already completed, executor returns the result immediately."""
        workflow = _make_solo_workflow()
        run_id = str(uuid4())
        mock_event_log.run_exists = AsyncMock(return_value=True)

        completed_state = MagicMock()
        completed_state.status = "completed"
        completed_state.completed_tasks = {"node-1"}
        completed_state.failed_tasks = set()
        completed_state.total_tokens = 100
        completed_state.total_cost_usd = 0.002
        completed_state.error_message = None
        mock_replay_engine.rebuild_state = AsyncMock(return_value=completed_state)

        executor = _make_executor(event_log=mock_event_log, replay_engine=mock_replay_engine)

        result = await executor.execute(db=mock_db, workflow=workflow, run_id=run_id)

        assert result.success is True
        assert result.status == "completed"
        assert result.total_tokens == 100

    @pytest.mark.asyncio
    async def test_resume_failed_run_returns_immediately(self, mock_db, mock_event_log, mock_replay_engine):
        """If a run already failed, executor returns the failed result."""
        workflow = _make_solo_workflow()
        run_id = str(uuid4())
        mock_event_log.run_exists = AsyncMock(return_value=True)

        failed_state = MagicMock()
        failed_state.status = "failed"
        failed_state.completed_tasks = set()
        failed_state.failed_tasks = {"node-1"}
        failed_state.total_tokens = 0
        failed_state.total_cost_usd = 0.0
        failed_state.error_message = "API timeout"
        mock_replay_engine.rebuild_state = AsyncMock(return_value=failed_state)

        executor = _make_executor(event_log=mock_event_log, replay_engine=mock_replay_engine)

        result = await executor.execute(db=mock_db, workflow=workflow, run_id=run_id)

        assert result.success is False
        assert result.status == "failed"
        assert "API timeout" in (result.error or "")


class TestExecutorAbortSignal:
    """Test abort signal management."""

    @pytest.mark.asyncio
    async def test_abort_sets_signal(self):
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        run_id = str(uuid4())

        result = await executor.abort(run_id, "test")
        assert result is True
        assert executor.is_aborted(run_id) is True

    @pytest.mark.asyncio
    async def test_abort_idempotent(self):
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        run_id = str(uuid4())

        await executor.abort(run_id)
        result = await executor.abort(run_id)
        assert result is False

    def test_is_running_returns_false_for_unknown(self):
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        # is_running checks the _abort_signals dict synchronously
        assert executor._abort_signals.get(str(uuid4())) is None

    def test_is_aborted_returns_false_for_unknown(self):
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        assert executor.is_aborted(str(uuid4())) is False

    @pytest.mark.asyncio
    async def test_pause_returns_false(self):
        """Pause is not yet implemented."""
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        result = await executor.pause("run-1")
        assert result is False


# ═══════════════════════════════════════════════════════════════════════════
# NodeExecutor Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestNodeExecutorRetry:
    """Test NodeExecutor retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_succeed(self, mock_db, mock_event_log):
        """NodeExecutor retries a failed node and succeeds on second attempt."""
        node = _make_llm_node(max_retries=3)
        budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50)
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        call_count = 0

        async def _fail_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_llm_failure("Temporary error")
            return _mock_llm_response()

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(side_effect=_fail_then_succeed)),
            mock_el=mock_event_log,
        ):
            result = await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

        assert result["success"] is True
        assert call_count == 2
        assert node.retry_count == 1

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_failure(self, mock_db, mock_event_log):
        """NodeExecutor fails after all retries are exhausted."""
        node = _make_llm_node(max_retries=1)
        budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50)
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_failure("Persistent error"))),
            mock_el=mock_event_log,
        ):
            result = await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

        assert result["success"] is False
        assert "Persistent error" in (result.get("error") or "")
        assert node.status == "failed"

    @pytest.mark.asyncio
    async def test_retry_aborted_mid_retry(self, mock_db, mock_event_log):
        """NodeExecutor stops retrying when abort signal is set."""
        node = _make_llm_node(max_retries=3)
        budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50)
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        call_count = 0

        async def _fail_and_abort(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                executor._abort_signals[run_id] = asyncio.Event()
                executor._abort_signals[run_id].set()
                return _mock_llm_failure("Error")
            return _mock_llm_response()

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(side_effect=_fail_and_abort)),
            mock_el=mock_event_log,
        ):
            result = await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

        assert result["success"] is False
        assert result.get("error") == "Aborted"


class TestNodeExecutorDispatch:
    """Test NodeExecutor._dispatch() for different node types."""

    @pytest.mark.asyncio
    async def test_dispatch_code_execution(self, mock_db, mock_event_log):
        """Code execution node runs successfully."""
        node = _make_code_node(code="print('hello')")
        budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50)
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

        assert result["success"] is True
        assert "hello" in result["output"]["stdout"]

    @pytest.mark.asyncio
    async def test_dispatch_code_execution_failure(self, mock_db, mock_event_log):
        """Code execution with syntax error fails."""
        node = _make_code_node(code="this is not valid python !!!", max_retries=0)
        budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50)
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_dispatch_code_blocked_pattern(self, mock_db, mock_event_log):
        """Code with dangerous patterns is blocked."""
        node = _make_code_node(code="import os; os.system('rm -rf /')", max_retries=0)
        budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50)
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        with patch(
            "app.services.substrate.node_executor.get_event_log",
            return_value=mock_event_log,
        ):
            result = await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

        assert result["success"] is False
        assert "blocked" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_pass_through_node_types(self, mock_db, mock_event_log):
        """PHASE_GATE, FAN_OUT, FAN_IN pass through with success."""
        for node_type in (NodeType.FAN_IN, NodeType.FAN_OUT, NodeType.PHASE_GATE):
            node = WorkflowNode(
                id=f"passthrough-{node_type.value}",
                type=node_type,
                title=f"{node_type.value} node",
            )
            budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50)
            run_id = str(uuid4())
            workflow = _make_solo_workflow(node=node)
            executor = _make_executor(event_log=mock_event_log)

            node_exec = NodeExecutor(executor)
            result = await node_exec._dispatch(mock_db, node, {}, budget, run_id, workflow)
            assert result["success"] is True, f"{node_type.value} should pass through"

    @pytest.mark.asyncio
    async def test_dispatch_exception_wrapped_as_failure(self, mock_db, mock_event_log):
        """Unhandled exception in _dispatch is caught and returned as failure."""
        node = _make_llm_node(max_retries=0)
        budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50)
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        with (
            patch(
                "app.services.substrate.node_executor.get_event_log",
                return_value=mock_event_log,
            ),
            patch.object(NodeExecutor, "_dispatch", side_effect=RuntimeError("Unexpected crash")),
        ):
            result = await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

        assert result["success"] is False
        assert "Unexpected crash" in result["error"]


class TestNodeExecutorBudgetExhaustion:
    """Test budget exhaustion during node execution."""

    @pytest.mark.asyncio
    async def test_budget_exhausted_before_node_execution(self, mock_db, mock_event_log):
        """BudgetExhausted is raised when budget is already exhausted."""
        node = _make_llm_node()
        budget = Budget(max_cost_usd=Decimal("0.00"), max_iterations=0)
        budget.spent_usd = Decimal("1.00")
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        with pytest.raises(BudgetExhausted):
            await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

    @pytest.mark.asyncio
    async def test_budget_exhausted_propagates_from_enforcer(self, mock_db, mock_event_log):
        """BudgetExhausted from BudgetEnforcer.call() propagates to executor."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(side_effect=BudgetExhausted("Cost exhausted", workflow.budget))),
            mock_el=mock_event_log,
        ):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.success is False
        assert result.status == "failed"


# ═══════════════════════════════════════════════════════════════════════════
# Circuit Breaker Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration in the executor."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_failure_doesnt_poison_execution(self, mock_db, mock_event_log):
        """Circuit breaker failure is caught and doesn't stop execution.

        The real _ensure_circuit_breaker wraps its DB ops in a savepoint
        and catches all exceptions.  We verify the executor still succeeds
        even when the circuit breaker's DB calls raise.
        """
        from app.services.circuit_breaker_service import CircuitBreakerService

        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)
        # Don't override _ensure_circuit_breaker — let the real method run.
        # Instead, make the CircuitBreakerService.get_or_create raise.

        with (
            _patch_budget_and_event_log(
                mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
                mock_el=mock_event_log,
            ),
            patch.object(
                CircuitBreakerService,
                "get_or_create",
                side_effect=Exception("FK violation: mission_id not in missions"),
            ),
        ):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_check_circuit_breaker_returns_allowed_on_error(self, mock_db):
        """check_circuit_breaker returns (True, '') when service fails."""
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        allowed, reason = await executor.check_circuit_breaker(mock_db, "fake-mission")
        assert allowed is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_record_circuit_breaker_call_silently_fails(self, mock_db):
        """record_circuit_breaker_call doesn't raise on errors."""
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        await executor.record_circuit_breaker_call(mock_db, "fake-mission", "llm", 0.01)


# ═══════════════════════════════════════════════════════════════════════════
# _find_resume_point Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestFindResumePoint:
    """Test _find_resume_point helper."""

    def test_resume_from_first_node(self):
        workflow = _make_dag_workflow()
        state = MagicMock()
        state.completed_tasks = set()
        state.failed_tasks = set()
        assert _find_resume_point(workflow, state) == "fetch"

    def test_resume_from_middle(self):
        workflow = _make_dag_workflow()
        state = MagicMock()
        state.completed_tasks = {"fetch"}
        state.failed_tasks = set()
        assert _find_resume_point(workflow, state) == "summarize"

    def test_all_completed_returns_none(self):
        workflow = _make_dag_workflow()
        state = MagicMock()
        state.completed_tasks = {"fetch", "summarize"}
        state.failed_tasks = set()
        assert _find_resume_point(workflow, state) is None

    def test_skip_failed_nodes(self):
        workflow = _make_dag_three_layer()
        state = MagicMock()
        state.completed_tasks = {"a"}
        state.failed_tasks = {"b"}
        assert _find_resume_point(workflow, state) == "c"


# ═══════════════════════════════════════════════════════════════════════════
# Post-Hook Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestPostHooks:
    """Test _run_post_hooks silently handles failures."""

    @pytest.mark.asyncio
    async def test_post_hooks_dont_raise_on_failure(self, mock_db, mock_event_log):
        """Post-execution hooks silently catch all exceptions."""
        workflow = _make_solo_workflow()
        executor = _make_executor(event_log=mock_event_log)
        result = StrategyResult(success=True, status="completed", data={})
        await executor._run_post_hooks(mock_db, workflow, result)


# ═══════════════════════════════════════════════════════════════════════════
# Strategy Registration & Type Routing
# ═══════════════════════════════════════════════════════════════════════════


class TestStrategyRegistration:
    """Test strategy loading and routing."""

    def test_all_strategies_loaded(self):
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        executor._load_strategies()

        # 6 live strategies; META is fully de-registered (Q8).
        assert len(executor._strategies) == 6
        assert WorkflowType.SOLO in executor._strategies
        assert WorkflowType.DAG in executor._strategies
        assert WorkflowType.GRAPH in executor._strategies
        assert WorkflowType.SWARM in executor._strategies
        assert WorkflowType.PIPELINE in executor._strategies
        assert WorkflowType.META not in executor._strategies
        assert WorkflowType.LANGGRAPH in executor._strategies

    def test_meta_not_registered(self):
        """Regression guard: MetaStrategy must be de-registered (Q8)."""
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        executor._load_strategies()
        assert WorkflowType.META not in executor._strategies
        # Class still importable, just not wired into the executor.
        from app.services.substrate.strategies.meta import MetaStrategy

        assert MetaStrategy is not None

    def test_strategy_loading_is_idempotent(self):
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        executor._load_strategies()
        first_strategies = {k: type(v) for k, v in executor._strategies.items()}
        executor._load_strategies()
        second_strategies = {k: type(v) for k, v in executor._strategies.items()}
        assert first_strategies == second_strategies
        assert executor._strategies_loaded is True

    def test_get_strategy_for_unknown_type_raises(self):
        executor = UnifiedExecutor(event_log=AsyncMock(), replay_engine=AsyncMock())
        with pytest.raises(ValueError, match="No strategy registered"):
            executor._get_strategy("unknown_type")

    def test_solo_strategy_handles_solo(self):
        strategy = SoloStrategy()
        assert strategy.can_handle(WorkflowType.SOLO) is True
        assert strategy.can_handle(WorkflowType.DAG) is False

    def test_dag_strategy_handles_dag(self):
        strategy = DAGStrategy()
        assert strategy.can_handle(WorkflowType.DAG) is True
        assert strategy.can_handle(WorkflowType.SOLO) is False


# ═══════════════════════════════════════════════════════════════════════════
# UnifiedExecutor Singleton
# ═══════════════════════════════════════════════════════════════════════════


class TestUnifiedExecutorSingleton:
    """Test get_unified_executor() singleton."""

    def test_singleton_returns_same_instance(self):
        from app.services.substrate.executor import get_unified_executor

        e1 = get_unified_executor()
        e2 = get_unified_executor()
        assert e1 is e2

    def test_singleton_is_unified_executor(self):
        from app.services.substrate.executor import get_unified_executor

        executor = get_unified_executor()
        assert isinstance(executor, UnifiedExecutor)


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases & Error Handling
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_node_with_fallback_strategy_field(self, mock_db, mock_event_log):
        """Node with fallback_strategy set executes normally."""
        node = _make_llm_node(max_retries=0)
        node.fallback_strategy = "human_escalate"
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            strategy = SoloStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_workflow_without_user_id(self, mock_db, mock_event_log):
        """Workflow without user_id still executes."""
        workflow = _make_solo_workflow(user_id=None)
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            result = await executor.execute(db=mock_db, workflow=workflow)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_node_output_data_populated_on_success(self, mock_db, mock_event_log):
        """Node.output_data is populated after successful execution."""
        node = _make_llm_node()
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response(content="Hello world"))),
            mock_el=mock_event_log,
        ):
            strategy = SoloStrategy()
            await strategy.execute(workflow, {}, executor, mock_db)

        assert node.output_data is not None
        assert node.output_data["text"] == "Hello world"
        assert node.tokens_used == 150
        assert node.cost == 0.001
        assert node.status == "completed"

    @pytest.mark.asyncio
    async def test_budget_tracks_iterations(self, mock_db, mock_event_log):
        """BudgetEnforcer.call() receives the budget and is invoked for LLM nodes."""
        node = _make_llm_node()
        budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50, max_wall_time_seconds=120)
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        mock_enforcer = AsyncMock(call=AsyncMock(return_value=_mock_llm_response()))

        with _patch_budget_and_event_log(
            mock_enforcer=mock_enforcer,
            mock_el=mock_event_log,
        ):
            await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

        # The mocked enforcer.call() was invoked with the budget object.
        # The real enforcer increments iterations_used, but since it's mocked,
        # we verify the call was made with the correct budget.
        assert mock_enforcer.call.call_count == 1
        call_kwargs = mock_enforcer.call.call_args.kwargs
        assert call_kwargs["budget"] is budget

    @pytest.mark.asyncio
    async def test_llm_node_exception_in_dispatch_returns_failure(self, mock_db, mock_event_log):
        """Generic exception from _handle_llm dispatch is caught by NodeExecutor."""
        node = _make_llm_node(max_retries=0)
        budget = Budget(max_cost_usd=Decimal("5.00"), max_iterations=50)
        run_id = str(uuid4())
        workflow = _make_solo_workflow(node=node)
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(side_effect=RuntimeError("Connection reset"))),
            mock_el=mock_event_log,
        ):
            result = await executor.execute_node(
                db=mock_db,
                node=node,
                context={},
                budget=budget,
                run_id=run_id,
                workflow=workflow,
            )

        assert result["success"] is False
        assert "Connection reset" in result["error"]


# ═══════════════════════════════════════════════════════════════════════════
# GraphStrategy Tests (Phase 0.2 — Task 1)
# ═══════════════════════════════════════════════════════════════════════════


def _make_graph_workflow(
    nodes: list[WorkflowNode] | None = None,
    edges: list[WorkflowEdge] | None = None,
    *,
    workflow_id: str | None = None,
    user_id: str = "42",
) -> Workflow:
    """Create a GRAPH workflow for testing."""
    nodes = nodes or [_make_llm_node("n1"), _make_llm_node("n2")]
    edges = edges or [WorkflowEdge(source="n1", target="n2")]
    return Workflow(
        id=workflow_id or str(uuid4()),
        type=WorkflowType.GRAPH,
        title="Graph Workflow",
        description="Test graph",
        nodes=nodes,
        edges=edges,
        budget=Budget(
            max_cost_usd=Decimal("10.00"),
            max_wall_time_seconds=300,
            max_iterations=50,
            max_depth=5,
        ),
        user_id=user_id,
        metadata={"substrate_run_id": str(uuid4())},
    )


def _mock_node_result(
    success: bool = True,
    output: dict | None = None,
    tokens: int = 150,
    cost: float = 0.001,
    error: str | None = None,
) -> dict:
    """A node execution result as returned by executor.execute_node()."""
    if success:
        return {
            "success": True,
            "output": output or {"text": "node output"},
            "tokens": tokens,
            "cost": cost,
        }
    return {
        "success": False,
        "error": error or "Node failed",
    }


class TestGraphStrategy:
    """Test GraphStrategy execution — conditional edges, interpolation, subgraph."""

    @pytest.mark.asyncio
    async def test_graph_two_nodes_unconditional_edge(self, mock_db, mock_event_log):
        """Two nodes with one unconditional edge — both execute."""
        workflow = _make_graph_workflow()
        executor = _make_executor(event_log=mock_event_log)
        executor.execute_node = AsyncMock(return_value=_mock_node_result())

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert result.status == "completed"
        assert "n1" in result.completed_nodes
        assert "n2" in result.completed_nodes
        assert len(result.completed_nodes) == 2
        assert result.total_tokens == 300  # 150 per node

    @pytest.mark.asyncio
    async def test_graph_conditional_edge_false_skips_downstream(self, mock_db, mock_event_log):
        """Edge condition evaluates to False — downstream node is skipped."""
        n1 = _make_llm_node("n1")
        n2 = _make_llm_node("n2")
        edge = WorkflowEdge(source="n1", target="n2", condition="{{n1.output.passed}}")
        workflow = _make_graph_workflow(nodes=[n1, n2], edges=[edge])
        executor = _make_executor(event_log=mock_event_log)

        # n1 returns output with passed=False
        n1_result = _mock_node_result(output={"text": "done", "passed": False})
        executor.execute_node = AsyncMock(return_value=n1_result)

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert "n1" in result.completed_nodes
        assert "n2" not in result.completed_nodes  # skipped — condition was False
        assert executor.execute_node.call_count == 1  # only n1 executed

    @pytest.mark.asyncio
    async def test_graph_context_interpolation_resolves_string_truthy(self, mock_db, mock_event_log):
        """{{n1.output.score}} resolves string 'true' -> condition passes."""
        n1 = _make_llm_node("n1")
        n2 = _make_llm_node("n2")
        n3 = _make_llm_node("n3")
        edges = [
            WorkflowEdge(source="n1", target="n2", condition="{{n1.output.score}}"),
            WorkflowEdge(source="n2", target="n3"),
        ]
        workflow = _make_graph_workflow(nodes=[n1, n2, n3], edges=edges)
        executor = _make_executor(event_log=mock_event_log)

        # n1 returns output with nested output.score='true' (string truthy)
        # Template {{n1.output.score}} resolves via node_outputs["n1"]["output"]["score"]
        async def _exec_side_effect(*args, **kwargs):
            node = kwargs.get("node") or args[1]
            if node.id == "n1":
                return _mock_node_result(output={"text": "ok", "output": {"score": "true"}})
            return _mock_node_result()

        executor.execute_node = AsyncMock(side_effect=_exec_side_effect)

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert "n1" in result.completed_nodes
        assert "n2" in result.completed_nodes  # condition resolved to True
        assert "n3" in result.completed_nodes  # unconditional edge from n2
        assert len(result.completed_nodes) == 3

    @pytest.mark.asyncio
    async def test_graph_subgraph_filter_via_start_node_id(self, mock_db, mock_event_log):
        """start_node_id filters to reachable subgraph only."""
        # Diamond: n1 -> n2, n1 -> n3, n2 -> n4, n3 -> n4
        n1 = _make_llm_node("n1")
        n2 = _make_llm_node("n2")
        n3 = _make_llm_node("n3")
        n4 = _make_llm_node("n4")
        edges = [
            WorkflowEdge(source="n1", target="n2"),
            WorkflowEdge(source="n1", target="n3"),
            WorkflowEdge(source="n2", target="n4"),
            WorkflowEdge(source="n3", target="n4"),
        ]
        workflow = _make_graph_workflow(nodes=[n1, n2, n3, n4], edges=edges)
        executor = _make_executor(event_log=mock_event_log)
        executor.execute_node = AsyncMock(return_value=_mock_node_result())

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {"start_node_id": "n2"}, executor, mock_db)

        assert result.success is True
        # Only n2 and n4 are reachable from n2 (n1 and n3 excluded)
        executed_ids = set(result.completed_nodes)
        assert "n2" in executed_ids
        assert "n4" in executed_ids
        assert "n1" not in executed_ids
        assert "n3" not in executed_ids

    @pytest.mark.asyncio
    async def test_graph_condition_missing_node_defaults_to_false(self, mock_db, mock_event_log):
        """Condition referencing a nonexistent node resolves to None (falsy) — edge skipped."""
        n1 = _make_llm_node("n1")
        n2 = _make_llm_node("n2")
        edge = WorkflowEdge(source="n1", target="n2", condition="{{nonexistent.output.field}}")
        workflow = _make_graph_workflow(nodes=[n1, n2], edges=[edge])
        executor = _make_executor(event_log=mock_event_log)
        executor.execute_node = AsyncMock(return_value=_mock_node_result())

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        # n1 executes (no incoming edges). n2's condition resolves to None (falsy).
        assert result.success is True
        assert "n1" in result.completed_nodes
        assert "n2" not in result.completed_nodes
        assert executor.execute_node.call_count == 1

    @pytest.mark.asyncio
    async def test_graph_condition_interpolation_exception_defaults_to_true(self, mock_db, mock_event_log):
        """If _resolve_interpolation raises internally, _evaluate_condition catches
        the exception and defaults to True (edge passes anyway)."""
        n1 = _make_llm_node("n1")
        n2 = _make_llm_node("n2")
        edge = WorkflowEdge(source="n1", target="n2", condition="{{n1.output.data}}")
        workflow = _make_graph_workflow(nodes=[n1, n2], edges=[edge])
        executor = _make_executor(event_log=mock_event_log)
        executor.execute_node = AsyncMock(return_value=_mock_node_result())

        # Patch _resolve_interpolation on the class so the try/except in
        # _evaluate_condition catches the exception and returns True.
        original_resolve = GraphStrategy._resolve_interpolation

        def _raising_resolve(self_inner, template, outputs):
            if "n1.output.data" in (template or ""):
                raise RuntimeError("Simulated interpolation crash")
            return original_resolve(self_inner, template, outputs)

        with patch.object(GraphStrategy, "_resolve_interpolation", _raising_resolve):
            strategy = GraphStrategy()
            result = await strategy.execute(workflow, {}, executor, mock_db)

        # Exception in _resolve_interpolation -> _evaluate_condition catches -> True -> n2 runs
        assert result.success is True
        assert "n1" in result.completed_nodes
        assert "n2" in result.completed_nodes

    @pytest.mark.asyncio
    async def test_graph_pause_output_returns_paused(self, mock_db, mock_event_log):
        """Node output with pause=True stops execution and returns paused status."""
        n1 = _make_llm_node("n1")
        n2 = _make_llm_node("n2")
        workflow = _make_graph_workflow(nodes=[n1, n2], edges=[WorkflowEdge(source="n1", target="n2")])
        executor = _make_executor(event_log=mock_event_log)

        # n1 returns a pause signal in its output
        pause_result = _mock_node_result(
            output={
                "text": "need approval",
                "pause": True,
                "reason": "waiting for approval",
            }
        )
        executor.execute_node = AsyncMock(return_value=pause_result)

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert result.status == "paused"
        assert "n1" in result.completed_nodes
        assert "n2" not in result.completed_nodes  # never reached

    @pytest.mark.asyncio
    async def test_graph_node_failure_recorded_in_output(self, mock_db, mock_event_log):
        """Failed node is tracked in failed_nodes and error stored in node_outputs."""
        n1 = _make_llm_node("n1", max_retries=0)
        n2 = _make_llm_node("n2")
        # Use a conditional edge so n2 is skipped when n1 fails (no valid output)
        edge = WorkflowEdge(source="n1", target="n2", condition="{{n1.output.text}}")
        workflow = _make_graph_workflow(nodes=[n1, n2], edges=[edge])
        executor = _make_executor(event_log=mock_event_log)

        call_count = 0

        async def _fail_n1(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            node = kwargs.get("node") or args[1]
            if node.id == "n1":
                return _mock_node_result(success=False, error="API timeout")
            return _mock_node_result()

        executor.execute_node = AsyncMock(side_effect=_fail_n1)

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        # n1 failed -> node_outputs["n1"] = {"error": "API timeout"}
        # n2's condition {{n1.output.text}} resolves to None (no "output" key in error dict)
        # -> condition is falsy -> n2 skipped
        assert "n1" in result.failed_nodes
        assert "n2" not in result.completed_nodes
        assert result.success is False

    @pytest.mark.asyncio
    async def test_graph_node_exception_gather_returns_failure(self, mock_db, mock_event_log):
        """Exception from execute_node is caught and node marked as failed."""
        n1 = _make_llm_node("n1")
        workflow = _make_graph_workflow(
            nodes=[n1],
            edges=[],
        )
        executor = _make_executor(event_log=mock_event_log)
        executor.execute_node = AsyncMock(side_effect=RuntimeError("Connection broken"))

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert "n1" in result.failed_nodes
        assert "Connection broken" in (
            result.data.get("n1", {}).get("error", "") if isinstance(result.data, dict) else ""
        )

    @pytest.mark.asyncio
    async def test_graph_parallel_layer_execution(self, mock_db, mock_event_log):
        """Nodes in the same topological layer execute in parallel."""
        # n1 -> n2, n1 -> n3 (n2 and n3 are in the same layer)
        n1 = _make_llm_node("n1")
        n2 = _make_llm_node("n2")
        n3 = _make_llm_node("n3")
        edges = [
            WorkflowEdge(source="n1", target="n2"),
            WorkflowEdge(source="n1", target="n3"),
        ]
        workflow = _make_graph_workflow(nodes=[n1, n2, n3], edges=edges)
        executor = _make_executor(event_log=mock_event_log)
        executor.execute_node = AsyncMock(return_value=_mock_node_result())

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert len(result.completed_nodes) == 3
        assert result.total_tokens == 450  # 3 * 150


class TestGraphStrategyValidation:
    """Test GraphStrategy.validate()."""

    @pytest.mark.asyncio
    async def test_validate_accepts_valid_graph(self):
        workflow = _make_graph_workflow()
        strategy = GraphStrategy()
        errors = await strategy.validate(workflow)
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_graph(self):
        workflow = Workflow(
            id=str(uuid4()),
            type=WorkflowType.GRAPH,
            title="Empty",
            nodes=[],
            edges=[],
        )
        strategy = GraphStrategy()
        errors = await strategy.validate(workflow)
        assert any("at least 1 node" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_invalid_edge_source(self):
        workflow = _make_graph_workflow()
        workflow.edges.append(WorkflowEdge(source="ghost", target="n1"))
        strategy = GraphStrategy()
        errors = await strategy.validate(workflow)
        assert any("Edge source" in e and "ghost" in e for e in errors)

    @pytest.mark.asyncio
    async def test_graph_handles_abort_signal(self, mock_db, mock_event_log):
        """Graph strategy checks abort between layers."""
        n1 = _make_llm_node("n1")
        n2 = _make_llm_node("n2")
        workflow = _make_graph_workflow(nodes=[n1, n2], edges=[WorkflowEdge(source="n1", target="n2")])
        executor = _make_executor(event_log=mock_event_log)
        run_id = workflow.metadata["substrate_run_id"]

        call_count = 0

        async def _abort_after_n1(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                executor._abort_signals[run_id] = asyncio.Event()
                executor._abort_signals[run_id].set()
            return _mock_node_result()

        executor.execute_node = AsyncMock(side_effect=_abort_after_n1)

        strategy = GraphStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert result.status == "aborted"


# ═══════════════════════════════════════════════════════════════════════════
# PipelineStrategy Tests (Phase 0.2 — Task 2)
# ═══════════════════════════════════════════════════════════════════════════


def _make_phase_node(phase: str, node_id: str | None = None) -> WorkflowNode:
    """Create a PHASE_GATE node for a pipeline phase."""
    return WorkflowNode(
        id=node_id or f"phase-{phase}",
        type=NodeType.PHASE_GATE,
        title=f"Phase: {phase}",
        description=f"Phase gate for {phase}",
        config={"phase": phase, "prompt": f"Execute {phase}"},
    )


def _make_pipeline_workflow(
    phases: list[str] | None = None,
    overrides: dict[str, WorkflowNode] | None = None,
) -> Workflow:
    """Create a PIPELINE workflow with all 7 phase nodes."""
    from app.services.substrate.strategies.pipeline import PHASES as PIPELINE_PHASES

    phases = phases or PIPELINE_PHASES
    nodes = []
    for p in phases:
        if overrides and p in overrides:
            nodes.append(overrides[p])
        else:
            nodes.append(_make_phase_node(p))
    return Workflow(
        id=str(uuid4()),
        type=WorkflowType.PIPELINE,
        title="Pipeline Workflow",
        description="7-phase pipeline",
        nodes=nodes,
        edges=[],
        budget=Budget(
            max_cost_usd=Decimal("10.00"),
            max_wall_time_seconds=300,
            max_iterations=50,
            max_depth=5,
        ),
        metadata={"substrate_run_id": str(uuid4())},
    )


class TestPipelineStrategy:
    """Test PipelineStrategy execution — 7 phases, review retry loop."""

    @pytest.mark.asyncio
    async def test_pipeline_full_success_review_passes(self, mock_db, mock_event_log):
        """Full 7-phase pipeline, review returns PASS -> clean completion."""
        # Review node returns verdict=PASS
        review_node = _make_phase_node("review")
        workflow = _make_pipeline_workflow(overrides={"review": review_node})
        executor = _make_executor(event_log=mock_event_log)
        executor.ws_manager = MagicMock()
        executor.ws_manager.broadcast_phase = AsyncMock()

        async def _exec_node(*args, **kwargs):
            node = kwargs.get("node") or args[1]
            if node.config.get("phase") == "review":
                return _mock_node_result(output={"verdict": "PASS", "summary": "All good"})
            return _mock_node_result()

        executor.execute_node = AsyncMock(side_effect=_exec_node)

        strategy = PipelineStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert result.status == "completed"
        assert len(result.completed_nodes) == 7
        assert result.total_tokens > 0

    @pytest.mark.asyncio
    async def test_pipeline_review_revise_triggers_retry_then_passes(self, mock_db, mock_event_log):
        """Review returns REVISE -> retry from debate, then PASS on second attempt."""
        workflow = _make_pipeline_workflow()
        executor = _make_executor(event_log=mock_event_log)
        executor.ws_manager = MagicMock()
        executor.ws_manager.broadcast_phase = AsyncMock()

        review_calls = 0

        async def _exec_node(*args, **kwargs):
            nonlocal review_calls
            node = kwargs.get("node") or args[1]
            if node.config.get("phase") == "review":
                review_calls += 1
                if review_calls == 1:
                    return _mock_node_result(output={"verdict": "REVISE", "feedback": "Needs work"})
                return _mock_node_result(output={"verdict": "PASS"})
            return _mock_node_result()

        executor.execute_node = AsyncMock(side_effect=_exec_node)

        strategy = PipelineStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert review_calls == 2  # review ran twice
        # debate, consensus, synthesis, review all ran twice
        # dispatch, research, draft ran once = 7 + 4 = 11 total calls
        assert executor.execute_node.call_count == 11

    @pytest.mark.asyncio
    async def test_pipeline_review_fails_four_times_exceeded(self, mock_db, mock_event_log):
        """Review returns REVISE 4 times -> max retries exceeded."""
        workflow = _make_pipeline_workflow()
        executor = _make_executor(event_log=mock_event_log)
        executor.ws_manager = MagicMock()
        executor.ws_manager.broadcast_phase = AsyncMock()

        async def _exec_node(*args, **kwargs):
            node = kwargs.get("node") or args[1]
            if node.config.get("phase") == "review":
                return _mock_node_result(output={"verdict": "REVISE", "feedback": "Still needs work"})
            return _mock_node_result()

        executor.execute_node = AsyncMock(side_effect=_exec_node)

        strategy = PipelineStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert "Max review retries exceeded" in (result.error or "")

    @pytest.mark.asyncio
    async def test_pipeline_phase_failure_returns_immediately(self, mock_db, mock_event_log):
        """A non-review phase fails -> pipeline returns failed immediately."""
        workflow = _make_pipeline_workflow()
        executor = _make_executor(event_log=mock_event_log)
        executor.ws_manager = MagicMock()
        executor.ws_manager.broadcast_phase = AsyncMock()

        async def _exec_node(*args, **kwargs):
            node = kwargs.get("node") or args[1]
            if node.config.get("phase") == "draft":
                return _mock_node_result(success=False, error="Draft generation failed")
            return _mock_node_result()

        executor.execute_node = AsyncMock(side_effect=_exec_node)

        strategy = PipelineStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert "Phase draft failed" in (result.error or "")
        # Only dispatch, research, draft ran (3 calls)
        assert executor.execute_node.call_count == 3

    @pytest.mark.asyncio
    async def test_pipeline_abort_signal_stops_execution(self, mock_db, mock_event_log):
        """Abort signal between phases stops the pipeline."""
        workflow = _make_pipeline_workflow()
        executor = _make_executor(event_log=mock_event_log)
        run_id = workflow.metadata["substrate_run_id"]
        executor.ws_manager = MagicMock()
        executor.ws_manager.broadcast_phase = AsyncMock()

        call_count = 0

        async def _exec_node_and_abort(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                executor._abort_signals[run_id] = asyncio.Event()
                executor._abort_signals[run_id].set()
            return _mock_node_result()

        executor.execute_node = AsyncMock(side_effect=_exec_node_and_abort)

        strategy = PipelineStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert result.status == "aborted"


class TestPipelineStrategyValidation:
    """Test PipelineStrategy.validate()."""

    @pytest.mark.asyncio
    async def test_validate_accepts_valid_pipeline(self):
        workflow = _make_pipeline_workflow()
        strategy = PipelineStrategy()
        errors = await strategy.validate(workflow)
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_rejects_missing_phase(self):
        from app.services.substrate.strategies.pipeline import PHASES as PIPELINE_PHASES

        # Drop 'debate' from the phases
        incomplete_phases = [p for p in PIPELINE_PHASES if p != "debate"]
        workflow = _make_pipeline_workflow(phases=incomplete_phases)
        strategy = PipelineStrategy()
        errors = await strategy.validate(workflow)
        assert any("debate" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_non_phase_gate_node(self):
        """Pipeline with an LLM_CALL node instead of PHASE_GATE is rejected."""
        bad_node = _make_llm_node("bad-node")
        bad_node.config["phase"] = "dispatch"  # wrong type but has phase config
        workflow = _make_pipeline_workflow(overrides={"dispatch": bad_node})
        strategy = PipelineStrategy()
        errors = await strategy.validate(workflow)
        assert any("PHASE_GATE" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_empty_pipeline(self):
        workflow = Workflow(
            id=str(uuid4()),
            type=WorkflowType.PIPELINE,
            title="Empty",
            nodes=[],
            edges=[],
        )
        strategy = PipelineStrategy()
        errors = await strategy.validate(workflow)
        assert any("at least 1 node" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════════════
# SwarmStrategy Tests (Phase 0.2 — bonus coverage)
# ═══════════════════════════════════════════════════════════════════════════


def _make_swarm_workflow() -> Workflow:
    """Create a SWARM workflow with FAN_OUT + FAN_IN nodes."""
    fan_out = WorkflowNode(
        id="fan-out",
        type=NodeType.FAN_OUT,
        title="Decompose",
        config={},
    )
    fan_in = WorkflowNode(
        id="fan-in",
        type=NodeType.FAN_IN,
        title="Synthesize",
        config={},
    )
    return Workflow(
        id=str(uuid4()),
        type=WorkflowType.SWARM,
        title="Swarm Workflow",
        description="Multi-agent swarm",
        nodes=[fan_out, fan_in],
        edges=[],
        budget=Budget(
            max_cost_usd=Decimal("10.00"),
            max_wall_time_seconds=300,
            max_iterations=50,
            max_depth=5,
        ),
        user_id="42",
        metadata={"substrate_run_id": str(uuid4())},
    )


class TestSwarmStrategy:
    """Test SwarmStrategy — decompose, dispatch, synthesize."""

    @pytest.mark.asyncio
    async def test_swarm_full_decompose_dispatch_synthesize(self, mock_db, mock_event_log):
        """Full swarm: decompose goal -> dispatch tasks -> synthesize."""
        workflow = _make_swarm_workflow()
        executor = _make_executor(event_log=mock_event_log)

        decomposition = {
            "subtasks": [
                {
                    "id": "task_1",
                    "description": "Research topic",
                    "task_type": "research",
                },
                {
                    "id": "task_2",
                    "description": "Write summary",
                    "task_type": "analysis",
                },
            ]
        }

        call_count = 0

        async def _mock_call_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Decomposition call — return valid JSON with subtasks
                return _mock_llm_response(content=json.dumps(decomposition))
            # Synthesis call — return successful synthesis
            return _mock_llm_response(content="Synthesized result from all agents")

        executor.call_llm = AsyncMock(side_effect=_mock_call_llm)
        executor.execute_node = AsyncMock(
            return_value=_mock_node_result(
                output={"text": "Agent output"},
                tokens=200,
                cost=0.002,
            )
        )

        strategy = SwarmStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is True
        assert result.status == "completed"
        assert len(result.completed_nodes) == 2  # swarm_task_0, swarm_task_1
        assert result.total_tokens == 400  # 2 * 200
        assert "synthesis" in result.data

    @pytest.mark.asyncio
    async def test_swarm_decompose_failure_falls_back_to_single_task(self, mock_db, mock_event_log):
        """LLM decomposition fails -> falls back to single-task execution.

        When call_llm returns {success: False}, the decompose response has
        no 'response' key, so parsed content is '' -> JSONDecodeError ->
        fallback to single task. But synthesis also gets {success: False}
        (same mock), so synthesis_text is '' and overall result is False.
        """
        workflow = _make_swarm_workflow()
        executor = _make_executor(event_log=mock_event_log)

        call_count = 0

        async def _mock_call_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Decomposition fails — no 'response' key -> empty content
                return _mock_llm_failure("Decomposition LLM unavailable")
            # Synthesis succeeds
            return _mock_llm_response(content="Synthesized despite fallback")

        executor.call_llm = AsyncMock(side_effect=_mock_call_llm)
        executor.execute_node = AsyncMock(return_value=_mock_node_result())

        strategy = SwarmStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        # Falls back to single task with the goal as description
        assert executor.execute_node.call_count == 1
        assert result.success is True  # synthesis succeeded

    @pytest.mark.asyncio
    async def test_swarm_decompose_invalid_json_falls_back(self, mock_db, mock_event_log):
        """LLM returns invalid JSON for decomposition -> falls back to single task."""
        workflow = _make_swarm_workflow()
        executor = _make_executor(event_log=mock_event_log)

        async def _mock_call_llm(*args, **kwargs):
            return _mock_llm_response(content="This is not valid JSON at all")

        executor.call_llm = AsyncMock(side_effect=_mock_call_llm)
        executor.execute_node = AsyncMock(return_value=_mock_node_result())

        strategy = SwarmStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert executor.execute_node.call_count == 1  # fallback single task
        assert result.success is True

    @pytest.mark.asyncio
    async def test_swarm_synthesis_failure_returns_failed(self, mock_db, mock_event_log):
        """Synthesis LLM call fails -> swarm reports failure."""
        workflow = _make_swarm_workflow()
        executor = _make_executor(event_log=mock_event_log)

        decomposition = {"subtasks": [{"id": "t1", "description": "Do thing"}]}
        call_count = 0

        async def _mock_call_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Decomposition succeeds
                return _mock_llm_response(content=json.dumps(decomposition))
            # Synthesis fails — response has success=False
            return _mock_llm_failure("Synthesis model unavailable")

        executor.call_llm = AsyncMock(side_effect=_mock_call_llm)
        executor.execute_node = AsyncMock(return_value=_mock_node_result())

        strategy = SwarmStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        assert result.success is False
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_swarm_task_dispatch_exception_handled(self, mock_db, mock_event_log):
        """Exception during task dispatch is caught by asyncio.gather(return_exceptions=True)
        and reported as error output. Synthesis still runs."""
        workflow = _make_swarm_workflow()
        executor = _make_executor(event_log=mock_event_log)

        decomposition = {"subtasks": [{"id": "t1", "description": "Do thing"}]}

        call_count = 0

        async def _mock_call_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_llm_response(content=json.dumps(decomposition))
            return _mock_llm_response(content="Synthesized despite errors")

        executor.call_llm = AsyncMock(side_effect=_mock_call_llm)
        executor.execute_node = AsyncMock(side_effect=RuntimeError("Dispatch crashed"))

        strategy = SwarmStrategy()
        result = await strategy.execute(workflow, {}, executor, mock_db)

        # Task failed (exception caught by gather) but synthesis still runs
        assert result.success is True  # synthesis LLM call succeeded
        assert result.total_tokens == 0  # task produced 0 tokens (exception, not result)


class TestSwarmStrategyValidation:
    """Test SwarmStrategy.validate()."""

    @pytest.mark.asyncio
    async def test_validate_accepts_valid_swarm(self):
        workflow = _make_swarm_workflow()
        strategy = SwarmStrategy()
        errors = await strategy.validate(workflow)
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_rejects_missing_fan_out(self):
        fan_in = WorkflowNode(id="fi", type=NodeType.FAN_IN, title="In")
        workflow = Workflow(
            id=str(uuid4()),
            type=WorkflowType.SWARM,
            title="Bad Swarm",
            nodes=[fan_in],
            edges=[],
        )
        strategy = SwarmStrategy()
        errors = await strategy.validate(workflow)
        assert any("FAN_OUT" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_rejects_missing_fan_in(self):
        fan_out = WorkflowNode(id="fo", type=NodeType.FAN_OUT, title="Out")
        workflow = Workflow(
            id=str(uuid4()),
            type=WorkflowType.SWARM,
            title="Bad Swarm",
            nodes=[fan_out],
            edges=[],
        )
        strategy = SwarmStrategy()
        errors = await strategy.validate(workflow)
        assert any("FAN_IN" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════════════
# RunService Integration Test (Phase 0.2 — Task 3)
# ═══════════════════════════════════════════════════════════════════════════


class TestRunServiceIntegration:
    """Verify RunService wiring: blueprint_to_workflow -> UnifiedExecutor."""

    @pytest.mark.asyncio
    async def test_blueprint_to_workflow_to_executor(self, mock_db, mock_event_log):
        """Full pipeline: blueprint snapshot -> adapter -> executor -> result."""
        from app.services.substrate.adapters import blueprint_to_workflow

        # 1. Build a solo blueprint snapshot (as RunService.execute() would)
        snapshot = {
            "blueprint_type": "solo",
            "title": "Test Blueprint",
            "description": "E2E integration test",
            "nodes": [
                {
                    "id": "n1",
                    "type": "llm_call",
                    "title": "Summarize",
                    "config": {"prompt": "Hello world", "model_id": "deepseek-chat"},
                }
            ],
            "edges": [],
            "budget": {"max_cost_usd": "5.00"},
        }

        # 2. Adapter produces a valid Workflow
        bp_id = str(uuid4())
        workflow = blueprint_to_workflow(snapshot, blueprint_id=bp_id, user_id="42")
        assert workflow.type == WorkflowType.SOLO
        assert len(workflow.nodes) == 1
        assert workflow.nodes[0].id == "n1"
        assert workflow.title == "Test Blueprint"

        # 3. Execute through UnifiedExecutor
        executor = _make_executor(event_log=mock_event_log)

        with _patch_budget_and_event_log(
            mock_enforcer=AsyncMock(call=AsyncMock(return_value=_mock_llm_response())),
            mock_el=mock_event_log,
        ):
            result = await executor.execute(
                db=mock_db,
                workflow=workflow,
                run_id="run-1",
                blueprint_id=bp_id,
            )

        # 4. Verify result
        assert result.success is True
        assert result.status == "completed"

        # 5. Verify blueprint_id was passed to event log
        first_call_kwargs = mock_event_log.append.call_args_list[0].kwargs
        assert first_call_kwargs.get("blueprint_id") == bp_id

    @pytest.mark.asyncio
    async def test_blueprint_to_workflow_dag_type(self, mock_db, mock_event_log):
        """DAG blueprint snapshot produces correct Workflow with edges."""
        from app.services.substrate.adapters import blueprint_to_workflow

        snapshot = {
            "blueprint_type": "dag",
            "title": "DAG Blueprint",
            "nodes": [
                {
                    "id": "a",
                    "type": "llm_call",
                    "title": "Step A",
                    "config": {"prompt": "A"},
                    "dependencies": [],
                },
                {
                    "id": "b",
                    "type": "llm_call",
                    "title": "Step B",
                    "config": {"prompt": "B"},
                    "dependencies": [],
                },
            ],
            "edges": [{"source": "a", "target": "b"}],
            "budget": {"max_cost_usd": "10.00"},
        }

        workflow = blueprint_to_workflow(snapshot, blueprint_id="bp-dag")
        assert workflow.type == WorkflowType.DAG
        assert len(workflow.nodes) == 2
        assert len(workflow.edges) == 1
        assert workflow.edges[0].source == "a"
        assert workflow.edges[0].target == "b"
