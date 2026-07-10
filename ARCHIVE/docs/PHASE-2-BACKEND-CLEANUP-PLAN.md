# Phase 2 — Backend Cleanup & Executor Removal

**Date:** 2026-07-04
**Status:** PLAN (ready to execute)
**Estimate:** 3 weeks
**Depends on:** Phase 1A (strategy profiling complete)

---

## Goal

Migrate 6 v1 routers that inline old executor logic to substrate strategies, then delete 6 dead executors. Decide dual-write fate. Upgrade langgraph.

---

## Scope

### Executors to delete (3,189 LOC total)

| Executor | LOC | External imports | Risk |
|----------|-----|-----------------|------|
| `nexus/meta_loop_orchestrator.py` | 287 | 1 test file | **Lowest** |
| `swarm/orchestrator.py` | 416 | 1 router + 1 test | Low |
| `dag_executor.py` | 171 | `decomposition_service.py` + 2 tests | Low |
| `graph_executor.py` | 312 | 3 services + 2 routers + 2 tests | Medium |
| `langgraph/agent.py` | 832 | `a2a_agent_wrapper.py` + strategy fallback | Medium |
| `mission_executor.py` | 1,171 | Celery task + CQRS + 20+ tests | **Highest** |

### V1 Routers to migrate (2,282 LOC total)

| Router | LOC | Target strategy | Executor used |
|--------|-----|----------------|---------------|
| `flow_compat.py` | 144 | GraphStrategy | `graph_executor.GraphInterpreter` |
| `graph.py` | 374 | GraphStrategy | `graph_executor.GraphInterpreter` |
| `swarm.py` | 162 | SwarmStrategy | `swarm.orchestrator.SwarmOrchestrator` |
| `swarm_protocol.py` | 338 | SwarmStrategy | `swarm.orchestrator.SwarmOrchestrator` |
| `orchestration.py` | 577 | substrate | `meta_loop_orchestrator` |
| `mission_decomposition_routes.py` | 120 | DAGStrategy | `dag_executor` |
| `mission_advanced_routes.py` | 567 | CQRS | `mission_executor` |

---

## Migration Order (6 steps, least risk to most)

### Step 1: Meta Strategy — `orchestration.py` → substrate

**Why first:** `meta_loop_orchestrator.py` has only 1 test file referencing it. Lowest coupling.

**Actions:**
1. Migrate `orchestration.py` endpoints to use `get_unified_executor().execute()` with `WorkflowType.META`
2. Update `test_meta_loop_orchestrator_budgets.py` to use UnifiedExecutor
3. Delete `nexus/meta_loop_orchestrator.py`
4. Run full test suite

**Files touched:** `api/v1/orchestration.py`, `tests/test_meta_loop_orchestrator_budgets.py`
**Files deleted:** `services/nexus/meta_loop_orchestrator.py`

---

### Step 2: Swarm Strategy — `swarm.py` + `swarm_protocol.py` → substrate

**Why second:** `swarm/orchestrator.py` is only imported by 1 router + 1 test.

**Actions:**
1. Migrate `swarm.py` endpoints to use `get_unified_executor().execute()` with `WorkflowType.SWARM`
2. Migrate `swarm_protocol.py` endpoints similarly
3. Update `test_h1_3_observability_abort.py` (3 SwarmOrchestrator imports)
4. Delete `swarm/orchestrator.py`
5. Run full test suite

**Files touched:** `api/v1/swarm.py`, `api/v1/swarm_protocol.py`, `tests/test_h1_3_observability_abort.py`
**Files deleted:** `services/swarm/orchestrator.py`

**Note:** SwarmStrategy has LLM dependency (2 direct calls) — per Phase 1A, gate behind `STRATEGY_EXPERIMENTAL=1` or keep the old orchestrator as fallback.

---

### Step 3: Graph Strategy — `flow_compat.py` + `graph.py` → substrate

**Third:** `graph_executor.py` is used by 3 services + 2 routers, but the services (`graph_node_handlers.py`, `graph_service.py`) can be updated to use the substrate strategy.

**Actions:**
1. Migrate `flow_compat.py` to use `get_unified_executor().execute()` with `WorkflowType.GRAPH`
2. Migrate `graph.py` endpoints similarly
3. Update `plugins.py` (line 477 — imports `ExecutionContext` from `graph_executor`)
4. Update `graph_node_handlers.py` and `graph_service.py` to use substrate's node execution
5. Update `test_close_missions.py`, `test_graph_executor.py`
6. Delete `graph_executor.py`
7. Run full test suite

**Files touched:** `api/v1/flow_compat.py`, `api/v1/graph.py`, `api/v1/plugins.py`, `services/graph_node_handlers.py`, `services/graph_service.py`
**Files deleted:** `services/graph_executor.py`

---

### Step 4: DAG Strategy — `mission_decomposition_routes.py` → substrate

**Fourth:** `dag_executor.py` is used by `decomposition_service.py` + 2 tests.

**Actions:**
1. Migrate `mission_decomposition_routes.py` to use `get_unified_executor().execute()` with `WorkflowType.DAG`
2. Update `decomposition_service.py` to use substrate's topological sort
3. Update `test_dag_executor.py` (2 files — `tests/` and `app/tests/`)
4. Delete `dag_executor.py`
5. Run full test suite

**Files touched:** `api/v1/mission_decomposition_routes.py`, `services/decomposition_service.py`
**Files deleted:** `services/dag_executor.py`

---

### Step 5: LangGraph — upgrade + delete old agent

**Fifth:** `langgraph/agent.py` is used by `a2a_agent_wrapper.py` and the strategy fallback.

**Actions:**
1. Upgrade `langgraph` in `requirements.txt` from 0.0.40 → 0.2+
2. Wire `LangGraphStrategy._execute_langgraph_node()` to actually use LangGraph (currently returns "not yet wired")
3. Update `a2a_agent_wrapper.py` to use the new LangGraph integration
4. Update `test_langgraph_strategy.py`
5. Delete old `langgraph/agent.py`
6. Run full test suite

**Files touched:** `requirements.txt`, `services/substrate/strategies/langgraph.py`, `services/a2a/a2a_agent_wrapper.py`
**Files deleted:** `services/langgraph/agent.py`

**Risk:** LangGraph 0.2+ may have breaking API changes from 0.0.40. Need careful testing.

---

### Step 6: Mission Executor — THE BOSS (last, hardest)

**Last:** `mission_executor.py` is the production mission runner with 20+ test file dependencies.

**Actions:**
1. **Migrate the Celery task:** Update `tasks/mission_execution.py` to use:
   ```python
   from app.services.substrate.adapters import mission_to_workflow
   from app.services.substrate.executor import get_unified_executor

   workflow = mission_to_workflow(mission, tasks)
   result = await get_unified_executor().execute(db, workflow)
   ```
2. **Migrate CQRS:** Update `api/_mission_cqrs/commands.py` to use UnifiedExecutor
3. **Migrate `mission_advanced_routes.py`** to CQRS pattern
4. **Bulk-update 20+ test files** to patch `UnifiedExecutor.execute` instead of `MissionExecutor`
5. Delete `mission_executor.py`
6. Run full test suite (this is the big one)

**Files touched:** `tasks/mission_execution.py`, `api/_mission_cqrs/commands.py`, `api/v1/mission_advanced_routes.py`, 20+ test files
**Files deleted:** `services/mission_executor.py` (1,171 LOC)

**Critical:** The Celery task is the production mission runner. This migration must be tested thoroughly before deploy. Consider a feature flag (`USE_UNIFIED_EXECUTOR=1`) for gradual rollout.

---

## Dual-Write Decision (Deferred)

Glenn said "DeepSeek started too early." The dual-write question (Mission canonical vs Blueprint+Run canonical) needs an investigation doc before committing. This is gated on Step 6 — once MissionExecutor is migrated, the dual-write architecture becomes clearer.

**Recommendation:** Produce the dual-write decision doc as part of Step 6. Options:
- (a) Mission is canonical, Blueprint+Run is optional → remove dual-write, keep Blueprint+Run as read model
- (b) Blueprint+Run is canonical → Mission becomes a view

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Breaking v1 routes during migration | Migrate one router at a time, run full test suite after each |
| Celery task migration breaks production | Feature flag `USE_UNIFIED_EXECUTOR=1` for gradual rollout |
| LangGraph 0.2+ breaking changes | Test upgrade in isolation first, keep 0.0.40 fallback |
| 20+ test files coupled to MissionExecutor | Bulk-update with sed/script, verify each test passes |
| SwarmStrategy LLM dependency | Gate behind `STRATEGY_EXPERIMENTAL=1` per Phase 1A |

---

## Provenance

Based on code analysis at commit `42f8064`. Executor LOC counts from `wc -l`. Import analysis from ripgrep. Migration order from thinker-with-files-gemini analysis.
