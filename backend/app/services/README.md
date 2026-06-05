# Mission Execution Services

> Phase 3.1 refactor — decomposed from `MissionExecutor` (was 1,362 lines)

Five focused modules extracted from the `MissionExecutor` god-class, each with a single responsibility and constructor-based dependency injection.

## Modules

### `cost_tracker.py` — CostTracker
LLM cost estimation and call recording.

| Method | Description |
|--------|-------------|
| `estimate_cost(model_id, total_tokens)` | USD cost for a model + token count |
| `record_llm_call(db, ...)` | Write to `LLMCallRecord` table + Prometheus metrics |

**Dependencies**: `settings.MISSION_COST_DIVISOR`, `record_llm_request` (Prometheus), `LLMCallRecord` (DB model)

**Key invariant**: `db.add()` but never `db.commit()` — the parent transaction owns the lifecycle.

### `llm_executor.py` — LlmExecutor
LLM task execution with agent system prompt resolution and cost tracking.

| Method | Description |
|--------|-------------|
| `execute_llm(task, input_data, mission, db)` | Route through ModelRouter, record cost, return normalized result |
| `_build_llm_messages(task, prompt)` | Build `[system, user]` messages with agent prompt |
| `_resolve_agent_system_prompt(task)` | Query `AgentTemplate` by `template_id` → slug fallback |

**Dependencies**: `CostTracker`, `ModelRouter` (callable), `AgentTemplate` (DB)

**Error handling**: Retryable re-raised; permanent caught with `permanent=True`; general exceptions recorded but returned as failures.

### `browser_task_runner.py` — BrowserTaskRunner
Browser automation dispatch (navigate, click, type, scroll, screenshot, snapshot, close).

| Constant / Method | Description |
|-------------------|-------------|
| `BROWSER_TASK_TYPES` | List of 7 supported browser task type strings |
| `execute_browser_tool(task, input_data, mission)` | Dispatch to registered tool by `task.task_type` |

**Dependencies**: Tool registry (lazy import via `_import_browser_tools()`)

**Key design**: Lazy imports avoid circular dependencies — tool classes are imported only when `execute_browser_tool` is called.

### `mission_planner.py` — MissionPlanner
LLM-driven plan generation (pending → planning → planned lifecycle).

| Method | Description |
|--------|-------------|
| `plan_mission(mission_id)` | Fetch mission, generate tasks via LLM, create `MissionTask` records |
| `_build_plan_prompt(mission)` | Construct structured planning prompt from mission fields |
| `_generate_plan(prompt, ...)` | Call LLM (ModelRouter → httpx fallback), extract JSON array from response |

**Dependencies**: `CostTracker`, `ModelRouter` (callable), `learning_service`, callbacks (`log_callback`, `transition_callback`)

**Key design**: Uses callback pattern for log/transition to avoid depending on `MissionExecutor`. Falls back to a single default task if LLM planning returns nothing.

### `task_executor.py` — TaskExecutor
Task execution dispatch across all backends with fallback strategies.

| Method | Description |
|--------|-------------|
| `execute_task(db, mission, task, task_map)` | Set RUNNING, resolve deps, match-case dispatch by `task_type` |
| `_execute_tool(task, input_data, mission, db)` | Route to named tool handler (web_search, code_executor, etc.) |
| `_execute_rag(task, input_data)` | RAG document retrieval |
| `_execute_web_search(task, input_data, ...)` | Web scrape or LLM semantic search fallback |
| `_execute_code(task, input_data, ...)` | Python sandbox execution or LLM fallback |
| `_execute_file(task, input_data, ...)` | File read/write/list in workspace |
| `_request_human_input(db, mission, task)` | Pause for human review |
| `_apply_fallback(db, mission, task, error)` | Apply fallback strategy (escalate, abort, skip, retry) |
| `_resolve_input(task, task_map)` | Merge `input_data` with resolved dependency outputs |
| `_aggregate_results(tasks)` | Summary across all tasks |

**Dependencies**: `LlmExecutor`, `BrowserTaskRunner`, `CostTracker`, RAG (callable), sandbox, workspace path

## Dependency Injection Pattern

All modules use **constructor injection**. Dependencies that need late binding (ModelRouter, RAGService) are passed as callables rather than concrete instances.

```python
from app.services.cost_tracker import CostTracker
from app.services.llm_executor import LlmExecutor
from app.services.mission_planner import MissionPlanner
from app.services.browser_task_runner import BrowserTaskRunner
from app.services.task_executor import TaskExecutor

# Wire the full tree
cost_tracker = CostTracker()
llm_exec = LlmExecutor(
    cost_tracker=cost_tracker,
    get_model_router=lambda: get_app_state().model_router,  # callable for late binding
)
browser_runner = BrowserTaskRunner()
planner = MissionPlanner(
    cost_tracker=cost_tracker,
    get_model_router=lambda: get_app_state().model_router,
    log_callback=my_log_fn,          # callback → no circular import
    transition_callback=my_trans_fn,  # callback → no circular import
)
task_exec = TaskExecutor(
    llm_executor=llm_exec,
    browser_runner=browser_runner,
    cost_tracker=cost_tracker,
    get_rag_service=lambda: get_app_state().rag_service,  # callable for late binding
    workspace="/data/missions/workspace",
    resource_limits={"max_memory_mb": 256, "timeout_seconds": 30},
    log_callback=my_log_fn,
)
```

### Why callables instead of instances?

- **Late binding**: `ModelRouter` and `RAGService` are initialized after app startup. Passing a callable avoids ordering constraints.
- **Hot reload**: If the router is reconfigured at runtime, the callable returns the new instance without re-wiring.
- **Testability**: Tests can inject mocks by passing `lambda: mock_router`.

### Why callbacks instead of direct imports?

`MissionPlanner` needs to log and transition status, but importing `MissionExecutor` would create a circular dependency. Instead, the executor passes `_log` and `_transition_status` as callbacks — the planner calls them without knowing who owns them.

## Error Hierarchy

All modules share errors from `app.services.mission_errors`:

```
MissionError (base)
├── RetryableMissionError   → re-raised, caller retries with back-off
└── PermanentMissionError   → caught, returned with permanent=True
```

## Testing

Each module has a dedicated test file in `app/tests/`:

| Test file | Tests |
|-----------|-------|
| `test_cost_tracker.py` | 16 |
| `test_llm_executor.py` | 20 |
| `test_mission_planner.py` | 22 |
| `test_browser_task_runner.py` | 20 |
| `test_task_executor.py` | 50 |
| **Total** | **128** |

Run with: `python -m pytest app/tests/test_cost_tracker.py app/tests/test_llm_executor.py app/tests/test_mission_planner.py app/tests/test_browser_task_runner.py app/tests/test_task_executor.py`

## Related Docs

- `docs/mission-architecture.md` — Full system architecture overview
- `docs/adr/001-mission-executor-decomposition.md` — Architecture Decision Record
