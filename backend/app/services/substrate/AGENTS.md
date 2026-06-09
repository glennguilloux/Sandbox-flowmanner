# Flowmanner — `app/services/substrate` Agent Instructions

## Purpose

This is the local contract for `backend/app/services/substrate/` — the **unified execution substrate** (H5.1, GA). It is the single durable entry point for every workflow in Flowmanner, replacing the 7 separate executors (mission, DAG, graph, swarm, swarm-pipeline, langgraph, meta) that used to each carry their own task loop, retry logic, abort handling, and observability.

An agent landing here for any workflow-execution question should be able to:
1. Identify which substrate component owns the concern (event log, replay, executor, strategy, node executor, adapter, assertion, baseline, trigger).
2. Understand the 4 substrate guarantees and which file enforces each.
3. Know the migration state and the feature flag (whether the old executors still serve any traffic).

## Ownership

| Concern | Owner file |
|---------|------------|
| Single entry point for all workflow execution | `executor.py` (`UnifiedExecutor`) |
| Strategy interface + ABC | `strategies/base.py` (`ExecutionStrategy`, `WorkflowWSManager`) |
| Strategy registry / lazy import | `strategies/__init__.py` (`StrategyRegistry`) |
| Solo / DAG / Graph / Swarm / Pipeline / Meta / LangGraph strategies | `strategies/{solo,dag,graph,swarm,pipeline,meta,langgraph}.py` |
| Shared node execution (LLM, tool, code, RAG, web, file, browser, sandbox, HITL, sub-workflow) | `node_executor.py` (`NodeExecutor`) |
| Append-only event log | `event_log.py` (`EventLog`) |
| State reconstruction from the event log | `replay_engine.py` (`ReplayEngine`) |
| ORM → canonical `Workflow` adapters | `adapters.py` (`mission_to_workflow`, `flow_to_workflow`, `graph_to_workflow`, `blueprint_to_workflow`) |
| Canonical workflow models | `workflow_models.py` (`Workflow`, `WorkflowNode`, `WorkflowEdge`, `NodeType`, `WorkflowType`, `StrategyResult`) |
| Replay assertions (regression checks) | `assertion_engine.py` (`ReplayAssertionEngine`) |
| Auto-extract expected behaviors from a known-good run | `baseline_extractor.py` (`BaselineExtractor`) |
| Near-real-time cron trigger dispatcher (2s polling) | `trigger_bridge.py` (`TriggerBridge`) |
| Original H5.1 design rationale (pre-impl) | `H5-1-DESIGN.md` — **read once, then prefer this AGENTS.md for daily work** |
| Public exports | `__init__.py` |

## Local Contracts

These rules apply to the substrate specifically, in addition to `backend/AGENTS.md` and `backend/app/services/AGENTS.md`.

1. **The 4 guarantees are non-negotiable.** Every execution through `UnifiedExecutor` must satisfy:
   - **Durable** — every state transition emits a substrate event (`SubstrateEvent` row in `substrate_events`).
   - **Type-checked** — input/output validated through Pydantic models in `workflow_models.py`.
   - **Capability-bounded** — tool calls require a `CapabilityToken` issued by `CapabilityEngine`.
   - **Bounded** — every LLM call goes through `BudgetEnforcer.call()`.
2. **The event log is the source of truth for workflow state.** No strategy mutates `Mission` / `WorkflowRun` status without also appending a substrate event. The DB BEFORE-UPDATE-OR-DELETE trigger on `substrate_events` enforces append-only.
3. **`event_log.append()` requires `mission_id` (or `blueprint_id`) and a non-empty `events` list.** Sequence is monotonic per `run_id`; safety limit is 100,000 events per run (`EventLog.MAX_EVENTS_PER_RUN`).
4. **All LLM calls go through `UnifiedExecutor.call_llm()`** (which delegates to `BudgetEnforcer.call()`). Strategies MUST NOT call `httpx` or `AsyncOpenAI` directly. The old `mission_executor` / `swarm/orchestrator` direct-HTTP paths are gone.
5. **All tool calls go through `CapabilityEngine.issue()` + `verify_and_require()`.** `NodeExecutor._handle_tool` is the canonical implementation. Attenuate for sub-workflows.
6. **Strategies receive the API route's `AsyncSession`** — they MUST NOT open their own session. This preserves transactional integrity. `substrate/strategies/base.py` documents this contract.
7. **Abort propagation is via `asyncio.Event`, not polling.** Set via `UnifiedExecutor.abort(run_id)`, checked between node executions in `NodeExecutor.execute()` and at layer boundaries in `DAGStrategy.execute()`.
8. **Sub-workflow depth is bounded.** `NodeExecutor._MAX_SUB_WORKFLOW_DEPTH = 5`. Sub-workflows share the parent budget (child spends from the same pool).
9. **Phase 6.4 circuit breaker is per-mission.** Lazily created on `UnifiedExecutor.execute()`; checked before LLM and tool calls; updated after each call. See `_ensure_circuit_breaker`, `check_circuit_breaker`, `record_circuit_breaker_call` in `executor.py`.
10. **Crash recovery is automatic.** Pass a known `run_id` to `UnifiedExecutor.execute()` and the replay engine rebuilds state; if the run is already terminal the result is returned without re-execution.
11. **Replay assertions are first-class.** `ReplayAssertionEngine.evaluate()` checks tool sequence, cost ceiling, latency, task completion, and circuit-breaker-trip counts against a known-good run. `BaselineExtractor.extract_from_run()` auto-generates the `expected_behaviors` list from a successful run with default 1.5× cost headroom and 2.0× latency headroom.
12. **Public re-exports live in `__init__.py`.** Don't add new top-level imports; extend the `__all__` list instead. The current public surface is: `EventLog`, `ReplayEngine`, `UnifiedExecutor`, `Workflow`, `WorkflowNode`, `WorkflowEdge`, `NodeType`, `WorkflowType`, `StrategyResult`, and the three adapters.

## Work Guidance

### Architecture: 7 strategies on 1 executor

The H5.1 collapse replaced 7 separate executors with a single `UnifiedExecutor` that dispatches to a typed `ExecutionStrategy`. Each old executor's responsibilities split into **shared base** (the executor) and **strategy-specific code** (the strategy):

| Old executor | LOC (was) | Strategy now | What moved to base |
|--------------|-----------|--------------|---------------------|
| `mission_executor.py` | 1,387 | `strategies/solo.py` | Task loop, retry, abort, event logging, LLM/tool dispatch, cost recording, post-hooks |
| `dag_executor.py` | 179 | `strategies/dag.py` | Kahn's topo sort (shared), layer-parallel dispatch |
| `graph_executor.py` | 293 | `strategies/graph.py` | Topo sort, conditional edges, `{{node_id.output.field}}` interpolation |
| `swarm/orchestrator.py` | 331 | `strategies/swarm.py` | LLM calls, agent matching, event logging |
| `swarm_pipeline/orchestrator.py` | ~1,700 | `strategies/pipeline.py` | 7 phase modules (preserved as helpers), abort/pause/resume |
| `langgraph/agent.py` | ~900 | `strategies/langgraph.py` | Tool execution, event logging, session persistence |
| `nexus/meta_loop_orchestrator.py` | 225 | `strategies/meta.py` | Budget enforcement, depth clamping, failure analysis |

**The deletion is the value.** When a strategy grows past its target line count, that is a signal the base needs more functionality — extract it; do not bloat the strategy.

### Migration state and feature flag

Per `H5-1-DESIGN.md §5`, the rollout was planned in three phases:

- **Phase A — `off` (default) / `run` / `all`** — gated by `FLOWMANNER_UNIFIED_EXECUTOR` env var.
- **Phase B — verification** (2–4 weeks parallel run + parity tests).
- **Phase C — cleanup** — flip to `all`, delete old executors.

**Current state (as of this writing):** The substrate is GA. `executor.py` docstring states "UnifiedExecutor — single durable executor (H5.1). GA release." All 7 strategies are implemented. The old executors are still in the tree (e.g. `mission_executor.py` at the services root) and are still wired up by their legacy routes, but new code MUST target the substrate.

**Before deleting an old executor**, confirm:
1. The `FLOWMANNER_UNIFIED_EXECUTOR=all` flag has been on in production for ≥2 weeks.
2. Parity tests in `backend/app/tests/test_substrate_*` and `test_unified_executor_*` are green.
3. No route in `backend/app/api/v1/` (or v2/v3) still imports the old executor.
4. The chaos suite (`backend/app/tests/chaos/`) passes against `UnifiedExecutor` (8 tests: kill worker, revoke capability, exhaust budget, type violation, replay determinism, attenuation, no ambient authority, plus phase-specific).

### Adding a new workflow type

1. Add a value to `WorkflowType` in `workflow_models.py`.
2. Add a strategy module `strategies/<name>.py` implementing `ExecutionStrategy` (validate, execute, can_handle).
3. Register it in `strategies/__init__.py` lazy import list.
4. If it introduces a new node behavior, add the `NodeType` value and the corresponding handler in `node_executor.py` (or delegate to a strategy-specific handler if the behavior is opaque to the base).
5. Add a unit test in `backend/app/tests/test_substrate_*.py`.
6. Update the H4 / Workflow consolidation adapter if a new ORM model needs to map in.

### Adding a new node type

1. Add the value to `NodeType` in `workflow_models.py` and document the config keys.
2. Add a handler method `_<name>` on `NodeExecutor`.
3. Add the match-case arm in `NodeExecutor._dispatch`.
4. If the handler needs a substrate event type, add it to `SubstrateEventType` in `app/models/substrate_models.py` (and to the alembic migration chain).
5. Test the handler with a synthetic `WorkflowNode` and the unit test pattern in `test_node_executor.py`.

### Adding a new strategy-specific event

Use `SubstrateEventType` (enum in `app/models/substrate_models.py`) and append via `event_log.append()`. The append-only trigger will reject any UPDATE/DELETE on `substrate_events` at the DB level.

### Crash recovery

Always pass a stable `run_id` for long-running workflows that may outlive a worker process. The replay engine (`replay_engine.py`) rebuilds state from the event log and resumes from the first incomplete node. Without a stable `run_id`, you get the default UUID-per-execute and no crash recovery.

### Replay-based regression checks

`ReplayAssertionEngine` + `BaselineExtractor` form the "regression test" loop:
1. Run a known-good mission → capture `run_id`.
2. `BaselineExtractor.extract_from_run()` returns a list of `expected_behaviors` (with default 1.5× cost headroom, 2.0× latency headroom).
3. Save the behaviors to a template / regression fixture.
4. On any future run, call `ReplayAssertionEngine.evaluate()` and assert `passed == True` for severity=`failure` results.

Use this whenever you change a strategy or a base component and want to detect behavior drift.

## Verification

```bash
# Run all substrate unit + integration tests
docker compose exec backend pytest app/tests/test_substrate_event_log.py \
                                 app/tests/test_substrate_event_log_integration_pg.py \
                                 app/tests/test_substrate_replay.py \
                                 app/tests/test_node_executor.py \
                                 app/tests/test_node_executor_handlers.py \
                                 app/tests/test_unified_executor.py \
                                 app/tests/test_unified_executor_all_strategies.py \
                                 app/tests/test_unified_executor_crash_recovery.py \
                                 app/tests/test_unified_executor_deterministic_replay.py \
                                 app/tests/test_assertion_engine.py \
                                 app/tests/test_baseline_extractor.py \
                                 app/tests/test_trigger_bridge.py -v

# Run strategy-specific tests
docker compose exec backend pytest app/tests/test_solo_strategy.py \
                                 app/tests/test_dag_strategy.py \
                                 app/tests/test_graph_strategy.py \
                                 app/tests/test_swarm_strategy.py \
                                 app/tests/test_langgraph_strategy.py \
                                 app/tests/test_meta_strategy.py \
                                 app/tests/test_pipeline_strategy.py -v

# Run the chaos suite (the 8 contract tests in H5-1-DESIGN.md §6.3)
docker compose exec backend pytest app/tests/chaos/ -v

# Run the full backend test suite
docker compose exec backend pytest app/tests/ -v --timeout=30

# Lint
docker compose exec backend ruff check app/services/substrate/
docker compose exec backend ruff format app/services/substrate/
```

Manual smoke test for new code:

```bash
# Exercise the public surface from a Python REPL inside the backend container
docker compose exec backend python -c "
from app.services.substrate import (
    UnifiedExecutor, get_unified_executor,
    Workflow, WorkflowNode, WorkflowType, NodeType,
    mission_to_workflow, flow_to_workflow,
    EventLog, ReplayEngine,
    get_event_log, get_replay_engine, get_ws_manager,
)
print('substrate public surface OK')
"
```

## Child DOX Index

This subtree has no subdirectories that themselves deserve a child AGENTS.md today. The `strategies/` package is flat (7 files + base + `__init__`); its conventions are documented in **Work Guidance → Adding a new strategy** above.

When a strategy grows past its target LOC and acquires its own helpers (the way `pipeline.py` carries the 7 phase modules), split those helpers into a subpackage and create a child AGENTS.md for it.
