"""Integration tests for the example backend blueprints.

These tests load each blueprint YAML, convert it to a substrate Workflow via
``blueprint_to_workflow``, and execute it through ``UnifiedExecutor`` with a
fake ``NodeExecutor``.  External services (LLM, sandbox, Qdrant, Redis,
webhook, human review inbox) are mocked, so the tests run quickly and
offline while still exercising the full strategy/executor path.

Run with:
    pytest tests/integration/test_blueprint_integration.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from app.services.substrate.adapters import blueprint_to_workflow
from app.services.substrate.executor import UnifiedExecutor
# HITLPaused intentionally not imported here; the graph-strategy pause contract
# uses output["pause"] in these integration tests.
from app.services.substrate.workflow_models import NodeType
import app.services.substrate.node_executor as node_executor_mod


# ---------------------------------------------------------------------------
# In-memory substrate infrastructure (no DB required)
# ---------------------------------------------------------------------------
class InMemoryEventLog:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def append(self, db, run_id, events, *, blueprint_id=None, **kwargs):
        for ev in events:
            self.events.append({"run_id": run_id, "blueprint_id": blueprint_id, "event": ev})

    async def get_events(self, db, run_id, event_type=None, **kwargs):
        evs = [e for e in self.events if e["run_id"] == run_id]
        if event_type:
            evs = [e for e in evs if (e["event"].get("type") == event_type)]
        return evs

    async def get_latest_sequence(self, db, run_id):
        return len([e for e in self.events if e["run_id"] == run_id])

    async def run_exists(self, db, run_id):
        return any(e["run_id"] == run_id for e in self.events)

    async def find_by_idempotency_key(self, db, key):
        return None


class InMemoryReplayEngine:
    async def rebuild_state(self, db, run_id, *, up_to_sequence=None):
        class State:
            status = "pending"
            completed_tasks: list[str] = []
            failed_tasks: list[str] = []
            total_tokens = 0
            total_cost_usd = 0.0
            current_sequence = 0
            error_message = None

        return State()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_workflow(blueprint_name: str, *, remove_edges: list[tuple[str, str]] | None = None) -> Any:
    """Load one of the backend blueprints and convert it to a Workflow.

    ``remove_edges`` is a list of (source, target) tuples to drop from the
    blueprint before conversion.  This lets tests exercise an acyclic view of
    a blueprint that contains a conditional retry edge the current graph
    strategy cannot place in a topological order.
    """
    path = Path(__file__).parent.parent.parent / f"{blueprint_name}.yaml"
    raw = yaml.safe_load(path.read_text())
    snapshot = raw["definition"]
    snapshot.setdefault("title", raw.get("name", blueprint_name))
    snapshot.setdefault("description", raw.get("description", ""))

    if remove_edges:
        edges = snapshot.get("edges", [])
        snapshot["edges"] = [
            e for e in edges
            if (e.get("source"), e.get("target")) not in remove_edges
        ]

    return blueprint_to_workflow(
        snapshot,
        blueprint_id="00000000-0000-0000-0000-000000000001",
        user_id="test",
    )


def _get(context: dict[str, Any], key: str, default: Any = None) -> Any:
    """Safe getter matching the substrate's builtin ``get()`` for varExpr."""
    if context is None:
        return default
    if isinstance(context, dict):
        return context.get(key, default)
    return default


# ---------------------------------------------------------------------------
# Fake NodeExecutor that mocks every external-service node type
# ---------------------------------------------------------------------------
class FakeNodeExecutor:
    """Records calls and returns deterministic outputs for blueprint tests.

    ⚠️ CAVEAT — These fake handlers are MORE LENIENT than the real substrate:

    1. The real _handle_split resolves splitOn from context["input"], NOT from
       context["inputs"]. The inject_queries variable_set node bridges this
       gap in both the blueprint and this fake.
    2. The real _handle_validate_schema uses ValidateSchemaHandler with full
       JSON Schema validation (types, properties, required). This fake only
       checks that required field names exist in the payload.
    3. The real _handle_variable_set uses _safe_eval (AST whitelist, no dict
       attribute access). This fake uses eval() which is more permissive.
    4. The real _handle_human_review raises HITLPaused. This fake returns
       output["pause"]=True to test the graph pause contract.

    Passing these tests does NOT guarantee the blueprint will run correctly
    on the real substrate. Always review blueprint YAML against the real
    handler source in node_executor.py before deploying.
    """

    calls: list[dict[str, Any]] = []
    sandbox_calls: list[dict[str, Any]] = []
    webhook_calls: list[dict[str, Any]] = []

    def __init__(self, *args, **kwargs) -> None:
        self.rag_context = ["RAG context item 1", "RAG context item 2"]
        self.synthetic_report = {
            "title": "Test Report",
            "summary": "This is a test summary.",
            "key_points": ["Point A", "Point B"],
            "recommendations": ["Rec 1"],
        }

    async def execute(self, db, node, context, budget, run_id, workflow=None):
        FakeNodeExecutor.calls.append({
            "node_id": node.id,
            "node_type": node.type.value,
            "context_inputs": context.get("inputs") if isinstance(context, dict) else None,
        })

        handler = getattr(self, f"_handle_{node.type.value}", self._handle_unknown)
        return await handler(node, context)

    async def _handle_unknown(self, node, context):
        raise NotImplementedError(f"FakeNodeExecutor has no handler for node type {node.type.value!r}")

    async def _handle_split(self, node, context):
        # Mirrors the real _handle_split resolution logic:
        # 1. "input"          → context["input"]
        # 2. "input.<key>"    → context["input"][<key>]
        # 3. "inputs.<key>"   → context["inputs"][<key>]
        # 4. bare key         → context[<key>]
        split_on = node.config.get("splitOn", "input")
        mode = node.config.get("mode", "item")

        inputs = context.get("inputs") or {}
        data = context.get("input", context)

        if split_on == "input":
            collection = data
        elif split_on.startswith("input."):
            key = split_on.split(".", 1)[1]
            collection = data.get(key) if isinstance(data, dict) else None
        elif split_on.startswith("inputs."):
            key = split_on.split(".", 1)[1]
            collection = inputs.get(key) if isinstance(inputs, dict) else None
        else:
            collection = context.get(split_on) if isinstance(context, dict) else None

        if collection is None:
            items = []
        elif isinstance(collection, (list, tuple, set)):
            items = list(collection)
        elif isinstance(collection, dict):
            items = list(collection.values())
        else:
            items = [collection]

        return {
            "success": True,
            "task_id": node.id,
            "output": {"items": items, "count": len(items), "empty": len(items) == 0, "split_on": split_on, "mode": mode},
            "tokens": 0,
            "cost": 0.0,
        }

    async def _handle_sandbox(self, node, context):
        FakeNodeExecutor.sandbox_calls.append({
            "node_id": node.id,
            "input": context.get("input"),
            "inputs": _get(context, "inputs"),
        })
        return {
            "success": True,
            "task_id": node.id,
            "output": {"source": "fake-sandbox", "query": context.get("input")},
            "tokens": 0,
            "cost": 0.0,
        }

    async def _handle_log(self, node, context):
        return {
            "success": True,
            "task_id": node.id,
            "output": {"logged": True, "message": node.config.get("message")},
            "tokens": 0,
            "cost": 0.0,
        }

    async def _handle_rag_query(self, node, context):
        return {
            "success": True,
            "task_id": node.id,
            "output": {"query": node.config.get("query"), "context": self.rag_context, "collection": node.config.get("collection")},
            "tokens": 0,
            "cost": 0.0,
        }

    async def _handle_llm_call(self, node, context):
        # Return the synthetic report wrapped in {"output": ...} so downstream
        # variable_set expressions like get(get(previous_outputs, 'synthesize'), 'output')
        # resolve correctly.
        return {
            "success": True,
            "task_id": node.id,
            "output": {"output": self.synthetic_report},
            "tokens": 50,
            "cost": 0.001,
        }

    async def _handle_variable_set(self, node, context):
        config = node.config
        var_name = config.get("varName")
        var_value = config.get("varValue")

        if var_value is not None:
            result = var_value
        else:
            # Minimal safe-eval for the expressions used by the blueprints.
            # The real _safe_eval uses an AST whitelist; this fake uses eval()
            # with a restricted namespace that mirrors the real _SAFE_BUILTINS.
            expr = config.get("varExpr", "")
            previous_outputs = context.get("previous_outputs", {})
            inputs = context.get("inputs", {})
            try:
                result = eval(  # noqa: S307
                    expr,
                    {"__builtins__": {}},
                    {
                        "get": _get,
                        "previous_outputs": previous_outputs,
                        "inputs": inputs,
                        "dict": dict,
                        "list": list,
                        "str": str,
                        "int": int,
                        "float": float,
                        "bool": bool,
                    },
                )
            except Exception as exc:
                raise ValueError(f"Failed to evaluate varExpr for {node.id}: {expr}") from exc

        # Write the variable into the run-scoped inputs dict so downstream nodes
        # can reference it via {{ inputs.<varName> }}.
        if context is not None and isinstance(context, dict):
            inputs = context.setdefault("inputs", {})
            if isinstance(inputs, dict):
                inputs[var_name] = result

        return {
            "success": True,
            "task_id": node.id,
            "output": {var_name: result},
            "tokens": 0,
            "cost": 0.0,
        }

    async def _handle_validate_schema(self, node, context):
        import copy

        inputs = _get(context, "inputs", {})
        previous_outputs = _get(context, "previous_outputs", {})
        payload_key = node.config.get("payload_key", "payload")
        payload = inputs.get(payload_key) or previous_outputs.get(payload_key)
        # If the payload is wrapped inside a variable_set result, unwrap it.
        if isinstance(payload, dict) and len(payload) == 1 and payload_key in payload:
            payload = payload[payload_key]

        schema = node.config.get("schema", {})
        required = schema.get("required", [])
        errors = [f"missing {key}" for key in required if not (payload and key in payload)]

        return {
            "success": True,
            "task_id": node.id,
            "output": {
                "valid": len(errors) == 0,
                "route": "default" if not errors else "on_invalid",
                "errors": errors,
                "payload": copy.deepcopy(payload),
            },
            "tokens": 0,
            "cost": 0.0,
        }

    async def _handle_human_review(self, node, context):
        # The graph strategy pauses a run when a node returns output["pause"]
        # == True.  The real _handle_human_review raises HITLPaused, which the
        # graph strategy currently catches as a failure.  For this blueprint
        # integration test we honour the graph pause contract so we can verify
        # that the review gate is reached and halts execution before publish.
        return {
            "success": True,
            "task_id": node.id,
            "output": {"pause": True, "interrupt_type": "human_review", "title": node.title},
            "tokens": 0,
            "cost": 0.0,
        }

    async def _handle_webhook(self, node, context):
        FakeNodeExecutor.webhook_calls.append({
            "node_id": node.id,
            "url": node.config.get("url"),
            "inputs": _get(context, "inputs"),
        })
        return {
            "success": True,
            "task_id": node.id,
            "output": {"delivered": True},
            "tokens": 0,
            "cost": 0.0,
        }

    async def _handle_memory_read(self, node, context):
        return {
            "success": True,
            "task_id": node.id,
            "output": {"query": node.config.get("query"), "collection": node.config.get("collection"), "results": []},
            "tokens": 0,
            "cost": 0.0,
        }

    async def _handle_memory_write(self, node, context):
        return {
            "success": True,
            "task_id": node.id,
            "output": {"stored": True},
            "tokens": 0,
            "cost": 0.0,
        }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def event_log():
    return InMemoryEventLog()


@pytest.fixture
def replay_engine():
    return InMemoryReplayEngine()


@pytest.fixture
def executor(event_log, replay_engine, monkeypatch):
    # Post-hooks (audit, linear sync, analytics, etc.) run async tasks that can
    # outlive the test event loop and trigger "Event loop is closed" errors
    # during teardown. Disable them for blueprint-structure tests.
    ex = UnifiedExecutor(event_log=event_log, replay_engine=replay_engine)
    monkeypatch.setattr(ex, "_run_post_hooks", AsyncMock(return_value=None))
    return ex


@pytest.fixture
def fake_node_executor(monkeypatch):
    """Patch NodeExecutor in the substrate module so all node calls go through FakeNodeExecutor."""
    FakeNodeExecutor.calls.clear()
    FakeNodeExecutor.sandbox_calls.clear()
    FakeNodeExecutor.webhook_calls.clear()
    monkeypatch.setattr(node_executor_mod, "NodeExecutor", FakeNodeExecutor)
    return FakeNodeExecutor


@pytest.fixture
def db():
    """Return an AsyncMock DB session that supports ``async with db.begin_nested()`` cleanly."""
    db_ = AsyncMock()
    # Prevent SQLAlchemy async pool teardown issues by giving begin_nested a
    # no-op async context manager.
    db_.begin_nested = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=None),
        )
    )
    return db_


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_institutional_memory_blueprint(executor, fake_node_executor, db):
    """The solo institutional-memory blueprint runs its single sandbox node."""
    workflow = _load_workflow("flowmanner-institutional-memory")

    result = await executor.execute(
        db=db,
        workflow=workflow,
        run_id="test-institutional-memory-001",
        blueprint_id="00000000-0000-0000-0000-000000000001",
        context={"inputs": {"topic": "codebase health", "repo_url": "https://example.com/repo.git"}},
    )

    assert result.success is True
    assert result.status == "completed"
    assert "institutional_memory_audit" in result.completed_nodes
    assert result.failed_nodes == []


@pytest.mark.asyncio
async def test_rag_report_blueprint_pauses_at_human_review(executor, fake_node_executor, db):
    """The graph rag-report blueprint runs up to human_review and pauses.

    The blueprint routes validate → review (valid) or validate → schema_invalid
    (invalid). No cyclic back-edge is used — the graph strategy cannot
    schedule cycles.
    """
    workflow = _load_workflow("flowmanner-rag-report")

    result = await executor.execute(
        db=db,
        workflow=workflow,
        run_id="test-rag-report-001",
        blueprint_id="00000000-0000-0000-0000-000000000001",
        context={"inputs": {"topic": "codebase health", "webhook_url": "https://example.com/webhook"}},
    )

    assert result.success is False
    assert result.status == "paused"

    # All pre-review nodes should have completed.
    pre_review = {"retrieve", "store_context", "synthesize", "store_report", "validate"}
    assert pre_review.issubset(set(result.completed_nodes))
    # Webhook should NOT run because human review paused the run.
    assert "publish" not in result.completed_nodes


@pytest.mark.asyncio
async def test_cache_warmer_blueprint_splits_and_runs_per_item(executor, fake_node_executor, db):
    """The dag cache-warmer blueprint splits queries and runs a sandbox per item."""
    workflow = _load_workflow("flowmanner-cache-warmer")
    queries = ["codebase summary", "API endpoint list", "test coverage report"]

    result = await executor.execute(
        db=db,
        workflow=workflow,
        run_id="test-cache-warmer-001",
        blueprint_id="00000000-0000-0000-0000-000000000001",
        context={"inputs": {"queries": queries, "repo_url": "https://example.com/repo.git"}},
    )

    assert result.success is True
    assert result.status == "completed"
    assert "split_queries" in result.completed_nodes
    assert "warm_entry" in result.completed_nodes
    assert "log_summary" in result.completed_nodes

    # FakeNodeExecutor.sandbox_calls is class-level, so it accumulates across
    # all per-item sandbox instances created by the DAG fan-out.
    warm_entries = [c for c in FakeNodeExecutor.sandbox_calls if c["node_id"] == "warm_entry"]
    assert len(warm_entries) == len(queries), "Expected one warm_entry invocation per query"
    assert sorted(c["input"] for c in warm_entries) == sorted(queries)
