# Mission Architecture

> **Status**: v2 — Phase 3 refactor (June 2026)
> **Author**: Codebuff (via Phase 3.1–3.4)

## Overview

The mission execution system is the core workflow engine of Flowmanner. It accepts user-defined missions, plans them into task sequences via LLM, executes tasks across multiple execution backends (LLM, browser, RAG, code sandbox, files), and records observability data at every step.

## System Design

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                             │
│  v1/mission.py  │  v2/missions.py  │  _mission_handlers.py  │
├─────────────────────────────────────────────────────────────┤
│                    MissionExecutor                           │
│  (orchestrator — ~580 LOC)                                  │
│  ┌──────────┬──────────┬──────────┬──────────┬───────────┐ │
│  │CostTracker│LlmExecutor│MissionPlanner│BrowserRunner│TaskExecutor│
│  └──────────┴──────────┴──────────┴──────────┴───────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Support Services                          │
│  mission_errors.py  │  mission_tools.py  │  mission_service │
│  model_router       │  rag_service       │  code_sandbox    │
│  learning_service   │  browser_service   │  metrics         │
├─────────────────────────────────────────────────────────────┤
│                    Persistence                                │
│  PostgreSQL (missions, tasks, logs)  │  Prometheus (metrics) │
└─────────────────────────────────────────────────────────────┘
```

## Sub-Modules

### `CostTracker` (`cost_tracker.py`)
- **Responsibility**: LLM cost estimation and call recording
- **Dependencies**: `settings.MISSION_COST_DIVISOR`, `record_llm_request` (Prometheus), `LLMCallRecord` (DB model)
- **Public API**: `estimate_cost(model_id, total_tokens) → float`, `record_llm_call(db, ...) → None`
- **Key invariant**: DB records are added via `db.add()` but commit is owned by the parent transaction

### `LlmExecutor` (`llm_executor.py`)
- **Responsibility**: LLM-based task execution with cost tracking and error classification
- **Dependencies**: `CostTracker`, `ModelRouter` (via callable), `AgentTemplate` (DB)
- **Public API**: `execute_llm(task, input_data, mission, db) → dict`
- **Key invariant**: All LLM responses are recorded regardless of outcome (finally block)
- **Error handling**: Retryable errors re-raised; permanent errors caught and returned with `permanent=True`

### `BrowserTaskRunner` (`browser_task_runner.py`)
- **Responsibility**: Browser automation (navigate, click, type, scroll, screenshot, snapshot, close)
- **Dependencies**: Tool registry (lazy import), browser tool classes
- **Public API**: `execute_browser_tool(task, input_data, mission) → dict`
- **Key design**: Lazy imports via `_import_browser_tools()` to avoid circular dependencies

### `MissionPlanner` (`mission_planner.py`)
- **Responsibility**: LLM-driven mission plan generation (task sequence creation)
- **Dependencies**: `CostTracker`, `ModelRouter`, `learning_service`, callbacks (`log_callback`, `transition_callback`)
- **Public API**: `plan_mission(mission_id) → dict`
- **Key design**: Uses callback pattern for log/transition to avoid depending on `MissionExecutor`
- **Fallback**: Creates a single default task if LLM planning fails

### `TaskExecutor` (`task_executor.py`)
- **Responsibility**: Dispatch and execute individual tasks across all backends
- **Dependencies**: `LlmExecutor`, `BrowserTaskRunner`, `CostTracker`, RAG service, sandbox
- **Public API**: `execute_task(db, mission, task, task_map) → dict`
- **Key design**: Match-case dispatch with fallback strategies; dependency output resolution
- **Backends**: LLM, tool, browser, RAG, web_search, code, file_operation, review, report_generator

## Error Model

All sub-modules share a common error hierarchy from `mission_errors.py`:

```
MissionError (base)
├── RetryableMissionError   — re-raised up the call stack
└── PermanentMissionError   — caught, returned with permanent=True
```

The `MissionExecutor` orchestrator catches both and applies the appropriate fallback strategy (retry, skip, escalate, abort).

## Dependency Injection

All sub-modules use constructor injection. Dependencies that require lazy binding (e.g., `ModelRouter`, `RAGService`) are passed as callables rather than concrete instances:

```python
executor = TaskExecutor(
    llm_executor=LlmExecutor(
        cost_tracker=CostTracker(),
        get_model_router=lambda: get_app_state().model_router,
    ),
    browser_runner=BrowserTaskRunner(),
    get_rag_service=lambda: get_app_state().rag_service,
)
```

No module creates its own dependencies — only `MissionPlanner` and `LlmExecutor` open DB sessions internally for specific queries (agent template resolution, plan generation).

## Concurrency Model

- **Pessimistic locking**: `SELECT ... FOR UPDATE` in `execute_mission()` and `handle_abort_mission()` prevents double-execution
- **Post-lock validation**: After acquiring the lock, status is re-checked to reject non-runnable missions
- **Atomic batch operations**: `handle_batch_abort()` uses `FOR UPDATE` across multiple rows

## Lifecycle State Machine

```
                    ┌──────────┐
                    │  PENDING  │
                    └────┬─────┘
                         │ plan
                    ┌────▼─────┐
                    │ PLANNING  │
                    └────┬─────┘
                         │ tasks generated
                    ┌────▼─────┐
              ┌─────│ PLANNED  │─────┐
              │     └────┬─────┘     │
              │          │ execute   │
              │     ┌────▼─────┐     │
              │     │  QUEUED  │     │
              │     └────┬─────┘     │
              │          │ run       │
              │     ┌────▼─────┐     │
              │     │ RUNNING  │     │
              │     └─┬───┬───┘     │
              │  pause│   │abort    │retry (from FAILED)
              │       │   │         │
        ┌─────▼──┐ ┌──▼───▼───┐ ┌──▲─────┐
        │ PAUSED │ │ ABORTED  │ │ FAILED │
        └────┬───┘ └──────────┘ └───┬────┘
             │ resume               │ retry
             ▼                      │
          QUEUED ◄──────────────────┘
```

All transitions are logged via `_transition_status()`. Terminal states (COMPLETED, FAILED, ABORTED) set `completed_at`.
