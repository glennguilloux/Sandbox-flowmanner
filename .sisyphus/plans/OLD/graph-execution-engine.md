# Flowmanner — Graph Execution Engine

## TL;DR

> **Quick Summary**: Build the actual graph execution engine that interprets saved flows and runs them. Currently `execute_graph_workflow()` just creates a "pending" record — no traversal, no node execution, no state management. This connects the FlowEditor UI to real backend execution.
> 
> **Deliverables**:
> - Graph interpreter with topological sort + node dispatch
> - Node type handlers (task, webhook, condition, loop, parallel, approval, transform, delay, subflow, log)
> - Execution API wired to the engine
> - Execution history/results UI integration
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 3 waves
> **Critical Path**: Schemas → Interpreter → Node Handlers → API → UI

---

## Context

### Original Request
"Plan the natural next steps" after completing canvas improvements, version control UI, backend schema validation, and E2E verification.

### Research Findings

**The Gap**: `execute_graph_workflow()` in `graph_service.py` (line 95-112) creates a `GraphExecution` record with `status="pending"` and returns immediately. **Nothing executes.**

```python
async def execute_graph_workflow(db, workflow_id, user_id, input_data=None):
    execution = GraphExecution(
        id=str(uuid4()),
        workflow_id=str(workflow_id),
        user_id=user_id,
        status="pending",  # ← Just sets status, never changes it
        input_data=input_data,
        started_at=datetime.now(timezone.utc),
    )
    db.add(execution)
    await db.flush()
    await db.refresh(execution)
    return execution  # ← Returns immediately, no execution happens
```

**What exists to build on**:
- `dag_executor.py` — Kahn's algorithm topological sort, cycle detection, ready task detection
- `mission_executor.py` — LLM routing, tool execution, RAG, code execution, browser tools, retry logic
- `llm_router.py` — Model routing with BYOK support
- `GraphState` model — Already exists for tracking execution state
- `GraphExecution` model — Already has `output_data`, `error_message`, `completed_at` fields
- Frontend `FlowEditor.tsx` — Already saves flows with all 12 node types and their fields

**What's missing**:
- Graph interpreter (traverse nodes, dispatch by type, pass state)
- Node type handlers (12 types need executors)
- State management between nodes (shared context)
- Execution lifecycle (pending → running → completed/failed)
- Error handling and retry at graph level
- API endpoint that actually calls the engine
- UI trigger (Run button) and progress display

### Metis Review
N/A — direct analysis from codebase research.

---

## Work Objectives

### Core Objective
Build a production-ready graph execution engine that interprets saved flow definitions, executes nodes in dependency order, routes each node type to the appropriate handler, and tracks execution state.

### Concrete Deliverables
- `app/services/graph_executor.py` — GraphInterpreter class
- `app/services/graph_node_handlers.py` — Node handler registry + 12 handlers
- Updated `app/services/graph_service.py` — Wire execute_graph_workflow to engine
- Updated `app/api/v1/graph.py` — Add execution status/results endpoints
- Updated `FlowEditor.tsx` — Add Run button + execution status display

### Definition of Done
- [ ] POST `/api/graphs/{id}/execute` triggers real execution
- [ ] GET `/api/graphs/{id}/executions/{eid}` returns live status
- [ ] All 12 node types execute correctly
- [ ] State passes between nodes
- [ ] Errors handled gracefully with retries
- [ ] Frontend can trigger execution and see results

### Must Have
- Topological sort for execution order (reuse dag_executor)
- Node dispatch by type (match frontend node types)
- Shared state/context between nodes
- Execution state tracking (GraphState records)
- Error handling with retry fallback
- Async execution (non-blocking API response)

### Must NOT Have (Guardrails)
- No new database models — reuse GraphExecution, GraphState
- No changes to existing mission executor — keep separate
- No WebSocket real-time updates in this phase (polling is fine)
- No new external dependencies
- No changes to node type definitions in frontend

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (pytest, backend tests)
- **Automated tests**: TDD
- **Framework**: pytest (existing backend test setup)
- **If TDD**: Each handler gets unit tests before implementation

### QA Policy
Every task includes agent-executed QA scenarios:
- **Backend**: pytest unit tests + integration tests
- **API**: curl endpoints, assert status + response fields
- **Frontend**: Playwright scenarios for Run button + status display

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation):
├── Task 1: GraphInterpreter core (traverse + dispatch skeleton) [deep]
├── Task 2: Node handler registry + base handler class [quick]
├── Task 3: Execution lifecycle service (status transitions) [quick]
├── Task 4: Graph execution API endpoints [quick]
├── Task 5: Shared state/context manager [quick]
└── Task 6: Unit test scaffolding + fixtures [quick]

Wave 2 (After Wave 1 — node handlers, MAX PARALLEL):
├── Task 7: Task node handler (LLM via ModelRouter) [deep]
├── Task 8: Webhook node handler (HTTP requests) [quick]
├── Task 9: Condition node handler (expression eval) [quick]
├── Task 10: Parallel node handler (concurrent execution) [deep]
├── Task 11: Loop node handler (iteration logic) [deep]
├── Task 12: Approval/Delay/Transform/Log handlers [quick]
└── Task 13: Subflow node handler (nested execution) [deep]

Wave 3 (After Wave 2 — integration + UI):
├── Task 14: Wire execute_graph_workflow to GraphInterpreter [deep]
├── Task 15: Execution status/results API endpoints [quick]
├── Task 16: Frontend Run button + execution status panel [visual-engineering]
├── Task 17: Integration tests (full graph execution) [deep]
└── Task 18: Deploy + E2E verification [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix
- **1-6**: No deps — all start immediately
- **7**: Depends on 2, 5, 6
- **8**: Depends on 2, 5
- **9**: Depends on 2, 5
- **10**: Depends on 1, 2, 5
- **11**: Depends on 1, 2, 5
- **12**: Depends on 2, 5
- **13**: Depends on 1, 2, 5
- **14**: Depends on 1, 3, 4, 7-13
- **15**: Depends on 3, 14
- **16**: Depends on 15
- **17**: Depends on 14, 15
- **18**: Depends on 16, 17

### Agent Dispatch Summary
- **Wave 1**: 6 tasks — T1→`deep`, T2-T6→`quick`
- **Wave 2**: 7 tasks — T7→`deep`, T8→`quick`, T9→`quick`, T10→`deep`, T11→`deep`, T12→`quick`, T13→`deep`
- **Wave 3**: 5 tasks — T14→`deep`, T15→`quick`, T16→`visual-engineering`, T17→`deep`, T18→`quick`
- **FINAL**: 4 tasks — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [ ] 1. GraphInterpreter Core

  **What to do**:
  - Create `app/services/graph_executor.py`
  - Implement `GraphInterpreter` class with:
    - `__init__(db, workflow, execution)` — load graph_definition
    - `execute()` — main entry point: topological sort → dispatch → collect results
    - `_traverse()` — BFS/DFS through nodes respecting edges
    - `_dispatch_node(node, context)` — route to handler by node type
    - `_build_context()` — initialize shared state with input_data
  - Use `dag_executor.topological_sort()` for execution order
  - Track each node's result in GraphState records

  **Must NOT do**:
  - Implement node handlers here (delegated to Task 2+)
  - Create new database models
  - Change existing graph_service.py yet

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core architecture, needs careful design of dispatch pattern and state flow
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2-6)
  - **Blocks**: Tasks 10, 11, 13, 14
  - **Blocked By**: None

  **References**:
  - `app/services/dag_executor.py` — Kahn's algorithm, topological_sort(), get_ready_tasks()
  - `app/services/mission_executor.py:execute_mission()` — execution loop pattern, dependency resolution
  - `app/models/graph.py` — GraphExecution, GraphState models
  - `app/services/graph_service.py:execute_graph_workflow()` — current stub to replace

  **Acceptance Criteria**:
  - [ ] GraphInterpreter class exists with execute() method
  - [ ] Topological sort produces correct execution layers
  - [ ] _dispatch_node() routes to handler by node type string
  - [ ] Context object initialized with input_data
  - [ ] GraphState records created for each node execution

  **QA Scenarios**:
  ```
  Scenario: Simple linear graph (start → task → end)
    Tool: Bash (pytest)
    Steps:
      1. Create mock GraphWorkflow with 3-node linear graph_definition
      2. Call GraphInterpreter.execute()
      3. Assert 3 GraphState records created
      4. Assert execution order matches topological sort
    Expected: 3 states, correct order, no errors
    Evidence: .sisyphus/evidence/task-1-linear-graph.txt

  Scenario: Graph with cycle detection
    Tool: Bash (pytest)
    Steps:
      1. Create graph_definition with A→B→C→A cycle
      2. Call GraphInterpreter.execute()
    Expected: Raises ValueError or returns error status
    Evidence: .sisyphus/evidence/task-1-cycle-detection.txt
  ```

- [ ] 2. Node Handler Registry + Base Class

  **What to do**:
  - Create `app/services/graph_node_handlers.py`
  - Implement `BaseNodeHandler` abstract class:
    - `async def execute(node, context) -> dict`
    - `async def validate(node) -> list[str]` — pre-execution validation
  - Implement `NodeHandlerRegistry`:
    - `register(node_type, handler)` — register handler for type
    - `get(node_type) -> BaseNodeHandler` — lookup
    - Auto-register all handlers on module import
  - Skeleton handlers for all 12 types (raise NotImplementedError)

  **Must NOT do**:
  - Implement actual handler logic (delegated to Tasks 7-13)
  - Import ModelRouter or other services yet

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple registry pattern, abstract base class, boilerplate
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3-6)
  - **Blocks**: Tasks 7-13
  - **Blocked By**: None

  **References**:
  - `app/services/mission_executor.py:execute_task()` — task type dispatch pattern
  - `app/tools/base.py` — ToolRegistry pattern for reference
  - `app/services/graph_executor.py` — will import NodeHandlerRegistry

  **Acceptance Criteria**:
  - [ ] BaseNodeHandler abstract class with execute() and validate()
  - [ ] NodeHandlerRegistry with register/get
  - [ ] 12 skeleton handlers registered
  - [ ] Import of graph_node_handlers auto-registers all handlers

  **QA Scenarios**:
  ```
  Scenario: Registry lookup returns correct handler
    Tool: Bash (pytest)
    Steps:
      1. Import NodeHandlerRegistry
      2. registry.get("task") returns TaskNodeHandler
      3. registry.get("webhook") returns WebhookNodeHandler
      4. registry.get("unknown") raises KeyError
    Expected: Correct handlers returned, unknown raises
    Evidence: .sisyphus/evidence/task-2-registry-lookup.txt
  ```

- [ ] 3. Execution Lifecycle Service

  **What to do**:
  - Add execution state machine to `graph_service.py` (or new file):
    - `pending` → `running` → `completed` | `failed` | `paused`
    - `update_execution_status(db, execution_id, status, **kwargs)`
    - `record_node_state(db, execution_id, workflow_id, node_id, state_data)`
    - `complete_execution(db, execution_id, output_data)`
    - `fail_execution(db, execution_id, error_message)`
  - Each status transition updates timestamps

  **Must NOT do**:
  - Call GraphInterpreter here (that's Task 14)
  - Change API routes yet

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple CRUD operations, state machine, timestamp management
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4-6)
  - **Blocks**: Tasks 14, 15
  - **Blocked By**: None

  **References**:
  - `app/models/graph.py:GraphExecution` — status field, timestamps
  - `app/models/graph.py:GraphState` — state_data, execution_id, workflow_id
  - `app/services/mission_executor.py` — status transitions for reference

  **Acceptance Criteria**:
  - [ ] update_execution_status() changes status and timestamps
  - [ ] record_node_state() creates GraphState record
  - [ ] complete_execution() sets status=completed, completed_at, output_data
  - [ ] fail_execution() sets status=failed, error_message

  **QA Scenarios**:
  ```
  Scenario: Full lifecycle transition
    Tool: Bash (pytest)
    Steps:
      1. Create GraphExecution with status="pending"
      2. update_execution_status(exec_id, "running")
      3. Assert status="running", started_at set
      4. complete_execution(exec_id, {"result": "ok"})
      5. Assert status="completed", completed_at set, output_data set
    Expected: All transitions correct, timestamps populated
    Evidence: .sisyphus/evidence/task-3-lifecycle.txt
  ```

- [ ] 4. Graph Execution API Endpoints

  **What to do**:
  - Update `app/api/v1/graph.py`:
    - Modify `POST /{workflow_id}/execute` — trigger async execution, return execution_id
    - Add `GET /{workflow_id}/executions/{execution_id}` — return execution status + output
    - Add `GET /{workflow_id}/executions/{execution_id}/states` — already exists, verify it works
    - Add `GET /{workflow_id}/executions` — list all executions for workflow
  - Use `BackgroundTasks` or `asyncio.create_task()` for non-blocking execution

  **Must NOT do**:
  - Implement execution logic (delegated to Task 14)
  - Add WebSocket endpoints (out of scope)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard FastAPI route patterns, follows existing graph.py structure
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-3, 5-6)
  - **Blocks**: Tasks 15, 16
  - **Blocked By**: None

  **References**:
  - `app/api/v1/graph.py` — existing routes, router setup
  - `app/api/v1/mission.py` — async execution pattern for reference
  - `app/api/deps.py` — get_current_user, get_db dependencies

  **Acceptance Criteria**:
  - [ ] POST /graphs/{id}/execute returns {"execution_id": "...", "status": "pending"}
  - [ ] GET /graphs/{id}/executions/{eid} returns execution with status
  - [ ] GET /graphs/{id}/executions returns list of executions
  - [ ] All endpoints require authentication

  **QA Scenarios**:
  ```
  Scenario: Execute endpoint returns execution_id
    Tool: Bash (curl)
    Steps:
      1. Create a graph workflow via POST /graphs/
      2. POST /graphs/{id}/execute with {"input_data": {"test": true}}
      3. Assert 201 response with execution_id field
    Expected: 201, execution_id is UUID string
    Evidence: .sisyphus/evidence/task-4-execute-endpoint.txt

  Scenario: Status endpoint returns pending
    Tool: Bash (curl)
    Steps:
      1. Use execution_id from previous scenario
      2. GET /graphs/{id}/executions/{eid}
      3. Assert status field exists
    Expected: 200, status is "pending" or "running"
    Evidence: .sisyphus/evidence/task-4-status-endpoint.txt
  ```

- [ ] 5. Shared State/Context Manager

  **What to do**:
  - Create `ExecutionContext` class (in graph_executor.py or separate):
    - `__init__(input_data)` — initialize with workflow input
    - `get(key)` / `set(key, value)` — shared key-value store
    - `get_node_output(node_id)` — get previous node's output
    - `set_node_output(node_id, output)` — store node result
    - `to_dict()` — serialize for GraphState storage
    - `from_dict(data)` — deserialize
  - Support variable interpolation: `"{{node_id.output.field}}"` → resolved value

  **Must NOT do**:
  - Implement node handlers
  - Persist to database (that's Task 3)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple dict wrapper with interpolation, no complex logic
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-4, 6)
  - **Blocks**: Tasks 7-13
  - **Blocked By**: None

  **References**:
  - `app/services/mission_executor.py:_resolve_input()` — dependency output resolution
  - `app/services/dag_executor.py:get_ready_tasks()` — dependency checking pattern

  **Acceptance Criteria**:
  - [ ] ExecutionContext.set/get works for arbitrary keys
  - [ ] get_node_output returns output from previous node
  - [ ] Variable interpolation resolves "{{node_id.output}}" correctly
  - [ ] to_dict/from_dict round-trips correctly

  **QA Scenarios**:
  ```
  Scenario: Context passes data between nodes
    Tool: Bash (pytest)
    Steps:
      1. ctx = ExecutionContext({"input": "hello"})
      2. ctx.set_node_output("node1", {"result": "world"})
      3. ctx.set("greeting", "{{node1.output.result}}")
      4. Assert ctx.get("greeting") == "world"
    Expected: Variable interpolation resolves correctly
    Evidence: .sisyphus/evidence/task-5-context.txt
  ```

- [ ] 6. Unit Test Scaffolding + Fixtures

  **What to do**:
  - Create `app/tests/test_graph_executor.py`
  - Add pytest fixtures:
    - `mock_db_session` — async mock session
    - `sample_workflow` — GraphWorkflow with test graph_definition
    - `sample_execution` — GraphExecution record
    - `simple_graph` — 3-node linear graph (start → task → end)
    - `branching_graph` — graph with parallel branches
    - `all_nodes_graph` — graph with all 12 node types
  - Configure test database (reuse existing conftest.py patterns)

  **Must NOT do**:
  - Write actual test logic (each task has its own tests)
  - Change production code

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Test fixtures, mock setup, follows existing test patterns
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-5)
  - **Blocks**: Tasks 7-13, 17
  - **Blocked By**: None

  **References**:
  - `app/tests/conftest.py` — existing fixture patterns
  - `app/tests/test_mission_executor.py` — mission executor test patterns
  - `app/tests/test_mission_api.py` — API test patterns

  **Acceptance Criteria**:
  - [ ] All fixtures import without errors
  - [ ] pytest can discover and run test_graph_executor.py
  - [ ] Fixtures create valid test data in test database

  **QA Scenarios**:
  ```
  Scenario: Test fixtures load correctly
    Tool: Bash (pytest)
    Steps:
      1. Run pytest app/tests/test_graph_executor.py --collect-only
      2. Assert test collection succeeds
      3. Run pytest app/tests/test_graph_executor.py -v
    Expected: Tests collected, fixtures resolve
    Evidence: .sisyphus/evidence/task-6-fixtures.txt
  ```

- [ ] 7. Task Node Handler (LLM)

  **What to do**:
  - Implement `TaskNodeHandler` in `graph_node_handlers.py`
  - Calls ModelRouter with node's prompt/description
  - Passes context variables into prompt
  - Returns LLM response as node output
  - Handles model_preference from node data
  - Supports timeout and retry from node config

  **Must NOT do**:
  - Modify ModelRouter
  - Handle non-LLM task types

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Integrates with ModelRouter, handles async LLM calls, error recovery
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8-13)
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 2, 5

  **References**:
  - `app/services/mission_executor.py:_execute_llm()` — LLM execution pattern
  - `app/services/llm_router.py` — ModelRouter interface
  - `app/services/graph_node_handlers.py` — BaseNodeHandler to extend

  **Acceptance Criteria**:
  - [ ] TaskNodeHandler.execute() calls ModelRouter.route_request()
  - [ ] Context variables interpolated into prompt
  - [ ] Returns {"text": response, "tokens": count}
  - [ ] Handles ModelRouter failure gracefully
  - [ ] Respects node timeout config

  **QA Scenarios**:
  ```
  Scenario: Task node executes LLM call
    Tool: Bash (pytest with mocked ModelRouter)
    Steps:
      1. Create mock ModelRouter that returns {"success": True, "response": "Hello", "cost": {"input_tokens": 10, "output_tokens": 5}}
      2. ctx = ExecutionContext({"question": "What is 2+2?"})
      3. node = {"data": {"nodeType": "task", "description": "Answer: {{question}}"}}
      4. result = await TaskNodeHandler().execute(node, ctx)
      5. Assert result["success"] is True, result["output"]["text"] == "Hello"
    Expected: LLM called, response returned, tokens tracked
    Evidence: .sisyphus/evidence/task-7-task-handler.txt

  Scenario: Task node handles LLM failure
    Tool: Bash (pytest)
    Steps:
      1. Mock ModelRouter to return {"success": False, "error": "Rate limited"}
      2. Execute task node
    Expected: Returns {"success": False, "error": "Rate limited"}
    Evidence: .sisyphus/evidence/task-7-task-failure.txt
  ```

- [ ] 8. Webhook Node Handler

  **What to do**:
  - Implement `WebhookNodeHandler`
  - Makes HTTP request using node's url, method, headers, body
  - Supports auth types (none, basic, bearer, api_key)
  - Interpolates context variables into URL, headers, body
  - Returns response status, headers, body

  **Must NOT do**:
  - Implement new HTTP client (use httpx, already available)
  - Handle webhook receiving (that's a different feature)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Straightforward HTTP call with auth, uses existing httpx
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 9-13)
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 2, 5

  **References**:
  - `app/services/mission_executor.py:_execute_web_request()` — HTTP request pattern
  - `app/services/mission_executor.py:_execute_web_scrape()` — httpx usage
  - `src/lib/mission-types.ts:NodeDataExtra` — webhook node fields (url, method, headers, body, authType)

  **Acceptance Criteria**:
  - [ ] WebhookNodeHandler makes HTTP request with correct method
  - [ ] Auth headers added based on authType
  - [ ] Context variables interpolated into URL/body
  - [ ] Returns {status_code, headers, body}
  - [ ] Handles network errors gracefully

  **QA Scenarios**:
  ```
  Scenario: Webhook node makes GET request
    Tool: Bash (pytest with httpx mock)
    Steps:
      1. Mock httpx to return 200 with {"status": "ok"}
      2. node = {"data": {"nodeType": "webhook", "url": "https://api.example.com/data", "method": "GET"}}
      3. result = await WebhookNodeHandler().execute(node, ctx)
      4. Assert result["output"]["status_code"] == 200
    Expected: HTTP GET made, response returned
    Evidence: .sisyphus/evidence/task-8-webhook-get.txt

  Scenario: Webhook node handles 404
    Tool: Bash (pytest)
    Steps:
      1. Mock httpx to return 404
      2. Execute webhook node
    Expected: Returns status_code=404, not an error (404 is valid response)
    Evidence: .sisyphus/evidence/task-8-webhook-404.txt
  ```

- [ ] 9. Condition Node Handler

  **What to do**:
  - Implement `ConditionNodeHandler`
  - Evaluates node's expression against context
  - Returns {"result": True/False, "expression": "..."}
  - Expression supports: comparison operators, logical operators, context variable access
  - Use Python's `eval()` with restricted globals OR a simple expression parser

  **Must NOT do**:
  - Allow arbitrary code execution (security risk)
  - Use external expression library

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Expression evaluation, simple logic, no external deps
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-8, 10-13)
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 2, 5

  **References**:
  - `src/lib/mission-types.ts:NodeDataExtra` — condition node fields (expression)
  - `app/services/mission_executor.py` — expression handling patterns

  **Acceptance Criteria**:
  - [ ] ConditionNodeHandler evaluates expression against context
  - [ ] Supports: ==, !=, >, <, >=, <=, and, or, not
  -   - Supports context variable access: `ctx.get("variable")`
  - [ ] Returns boolean result
  - [ ] Rejects dangerous expressions (import, exec, etc.)

  **QA Scenarios**:
  ```
  Scenario: Condition evaluates to True
    Tool: Bash (pytest)
    Steps:
      1. ctx = ExecutionContext({"count": 5})
      2. node = {"data": {"nodeType": "condition", "expression": "ctx.get('count') > 3"}}
      3. result = await ConditionNodeHandler().execute(node, ctx)
      4. Assert result["output"]["result"] is True
    Expected: Expression evaluates correctly
    Evidence: .sisyphus/evidence/task-9-condition-true.txt

  Scenario: Condition rejects dangerous expression
    Tool: Bash (pytest)
    Steps:
      1. node = {"data": {"nodeType": "condition", "expression": "__import__('os').system('rm -rf /')"}}
      2. Execute condition node
    Expected: Raises ValueError or returns error
    Evidence: .sisyphus/evidence/task-9-condition-security.txt
  ```

- [ ] 10. Parallel Node Handler

  **What to do**:
  - Implement `ParallelNodeHandler`
  - Executes all downstream branches concurrently using `asyncio.gather()`
  - Supports joinMode: "all" (wait for all) or "any" (first to complete)
  - Collects outputs from all branches into context
  - Handles partial failures (some branches fail, others succeed)

  **Must NOT do**:
  - Use threading (use asyncio)
  - Create new execution threads

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Concurrent execution, error aggregation, complex state management
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-9, 11-13)
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 1, 2, 5

  **References**:
  - `app/services/mission_executor.py:execute_mission()` — concurrent task execution pattern
  - `src/lib/mission-types.ts:NodeDataExtra` — parallel node fields (branches, joinMode)
  - `app/services/dag_executor.py:topological_sort()` — execution layer pattern

  **Acceptance Criteria**:
  - [ ] ParallelNodeHandler executes branches concurrently
  - [ ] joinMode="all" waits for all branches
  - [ ] joinMode="any" returns first completed branch
  - [ ] All branch outputs collected into context
  - [ ] Partial failures handled (failed branches logged, successful ones continue)

  **QA Scenarios**:
  ```
  Scenario: Parallel branches all complete
    Tool: Bash (pytest with async mocks)
    Steps:
      1. Create 2 mock branch handlers that return after different delays
      2. Execute parallel node with joinMode="all"
      3. Assert both branch outputs in context
    Expected: Both branches complete, outputs collected
    Evidence: .sisyphus/evidence/task-10-parallel-all.txt

  Scenario: Parallel with joinMode="any"
    Tool: Bash (pytest)
    Steps:
      1. Create 2 mock branches, one fast (0.1s), one slow (1s)
      2. Execute parallel node with joinMode="any"
      3. Assert only fast branch output used
    Expected: Returns after first branch completes
    Evidence: .sisyphus/evidence/task-10-parallel-any.txt
  ```

- [ ] 11. Loop Node Handler

  **What to do**:
  - Implement `LoopNodeHandler`
  - Supports loopMode: "count" (N iterations), "foreach" (iterate over array), "while" (condition-based)
  - For "count": iterate N times (loopCount), maxIterations safety limit
  - For "foreach": iterate over array from context, expose current item as `ctx.get("item")`
  - For "while": evaluate loopExpression each iteration, stop when false
  - Collects iteration outputs into array
  - Enforces maxIterations (default 100) to prevent infinite loops

  **Must NOT do**:
  - Allow infinite loops (always enforce maxIterations)
  - Use threading

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Iteration logic, state management per iteration, safety limits
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-10, 12-13)
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 1, 2, 5

  **References**:
  - `src/lib/mission-types.ts:NodeDataExtra` — loop node fields (loopMode, loopCount, loopExpression, maxIterations)
  - `app/services/mission_executor.py:execute_mission()` — iteration loop pattern

  **Acceptance Criteria**:
  - [ ] LoopNodeHandler executes N iterations for loopMode="count"
  - [ ] LoopNodeHandler iterates over array for loopMode="foreach"
  - [ ] LoopNodeHandler evaluates condition for loopMode="while"
  - [ ] maxIterations enforced (default 100)
  - [ ] All iteration outputs collected

  **QA Scenarios**:
  ```
  Scenario: Loop count mode iterates N times
    Tool: Bash (pytest)
    Steps:
      1. node = {"data": {"nodeType": "loop", "loopMode": "count", "loopCount": 3}}
      2. Mock downstream handler to return {"iteration": n}
      3. Execute loop node
      4. Assert 3 outputs collected
    Expected: 3 iterations, outputs array has 3 items
    Evidence: .sisyphus/evidence/task-11-loop-count.txt

  Scenario: Loop respects maxIterations
    Tool: Bash (pytest)
    Steps:
      1. node = {"data": {"nodeType": "loop", "loopMode": "count", "loopCount": 999}}
      2. Execute loop node (maxIterations defaults to 100)
    Expected: Stops at 100 iterations, returns warning
    Evidence: .sisyphus/evidence/task-11-loop-max.txt
  ```

- [ ] 12. Approval/Delay/Transform/Log Handlers

  **What to do**:
  - Implement 4 simpler handlers in `graph_node_handlers.py`:
    - `ApprovalNodeHandler`: Sets execution to "paused", returns approval request metadata (approverRole, escalationPolicy)
    - `DelayNodeHandler`: asyncio.sleep for delayMs (or exponential backoff), returns {"delayed_ms": actual_delay}
    - `TransformNodeHandler`: Applies transform (jq-like expression, template, or script) to context data
    - `LogNodeHandler`: Logs message with level to context and returns {"logged": True, "level": level, "message": "..."}

  **Must NOT do**:
  - Implement actual approval workflow UI (just pause execution)
  - Use external jq library (simple Python string/template ops)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: 4 simple handlers, each <50 lines, straightforward logic
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-11, 13)
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 2, 5

  **References**:
  - `src/lib/mission-types.ts:NodeDataExtra` — all 4 node type fields
  - `app/services/mission_executor.py:_request_human_input()` — approval pause pattern

  **Acceptance Criteria**:
  - [ ] ApprovalNodeHandler returns paused status with approver metadata
  - [ ] DelayNodeHandler sleeps for correct duration
  - [ ] TransformNodeHandler applies transformation to data
  - [ ] LogNodeHandler logs message with level

  **QA Scenarios**:
  ```
  Scenario: Delay node waits correct duration
    Tool: Bash (pytest)
    Steps:
      1. node = {"data": {"nodeType": "delay", "delayMs": 100}}
      2. Measure execution time
      3. Assert ~100ms elapsed
    Expected: Sleeps for ~100ms
    Evidence: .sisyphus/evidence/task-12-delay.txt

  Scenario: Log node records message
    Tool: Bash (pytest)
    Steps:
      1. node = {"data": {"nodeType": "log", "level": "info", "message": "Test log"}}
      2. result = await LogNodeHandler().execute(node, ctx)
      3. Assert result["output"]["logged"] is True
    Expected: Message logged, output returned
    Evidence: .sisyphus/evidence/task-12-log.txt
  ```

- [ ] 13. Subflow Node Handler

  **What to do**:
  - Implement `SubFlowNodeHandler`
  - Loads referenced workflow by missionId from database
  - Creates nested GraphInterpreter for subflow
  - Passes context to subflow execution
  - Collects subflow outputs back into parent context
  - Handles subflow errors (propagate to parent)

  **Must NOT do**:
  - Create new database queries (reuse graph_service.py functions)
  - Allow infinite recursion (add depth limit)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Nested execution, recursion, context passing, depth limiting
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-12)
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 1, 2, 5

  **References**:
  - `app/services/graph_service.py:get_graph_workflow()` — load workflow by ID
  - `app/services/graph_executor.py:GraphInterpreter` — will recursively instantiate
  - `src/lib/mission-types.ts:NodeDataExtra` — subflow node fields (missionId, missionName)

  **Acceptance Criteria**:
  - [ ] SubFlowNodeHandler loads subflow workflow from DB
  - [ ] Creates nested GraphInterpreter
  - [ ] Subflow outputs merged into parent context
  - [ ] Depth limit enforced (max 5 levels)
  - [ ] Subflow errors propagated to parent

  **QA Scenarios**:
  ```
  Scenario: Subflow executes nested workflow
    Tool: Bash (pytest with mocked DB)
    Steps:
      1. Mock get_graph_workflow to return a simple 2-node workflow
      2. node = {"data": {"nodeType": "subflow", "missionId": "sub-123"}}
      3. Execute subflow node
      4. Assert subflow outputs in parent context
    Expected: Subflow executed, outputs merged
    Evidence: .sisyphus/evidence/task-13-subflow.txt

  Scenario: Subflow depth limit enforced
    Tool: Bash (pytest)
    Steps:
      1. Create chain of 6 subflows (A→B→C→D→E→F)
      2. Execute top-level subflow
    Expected: Stops at depth 5, returns error
    Evidence: .sisyphus/evidence/task-13-subflow-depth.txt
  ```

- [ ] 14. Wire execute_graph_workflow to GraphInterpreter

  **What to do**:
  - Update `app/services/graph_service.py:execute_graph_workflow()`:
    - Load workflow and graph_definition
    - Create GraphExecution record
    - Start async execution via `asyncio.create_task(_execute_graph_async(...))`
    - Return execution record immediately (non-blocking)
  - Implement `_execute_graph_async(db, execution_id, workflow_id, user_id, input_data)`:
    - Load workflow
    - Create GraphInterpreter
    - Call interpreter.execute()
    - Update execution status on completion/failure
    - Record all node states

  **Must NOT do**:
  - Block the API response waiting for execution
  - Change GraphInterpreter interface

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Async task management, error handling, database session lifecycle
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (sequential after Wave 2)
  - **Blocks**: Tasks 15, 17, 18
  - **Blocked By**: Tasks 1-13

  **References**:
  - `app/services/graph_service.py:execute_graph_workflow()` — current stub to replace
  - `app/services/graph_executor.py:GraphInterpreter` — engine to wire up
  - `app/services/graph_service.py` — lifecycle functions from Task 3

  **Acceptance Criteria**:
  - [ ] execute_graph_workflow() returns immediately with execution_id
  - [ ] Background task starts execution
  - [ ] Execution status updates to "running" → "completed"/"failed"
  - [ ] GraphState records created for each node
  - [ ] Errors caught and recorded in execution error_message

  **QA Scenarios**:
  ```
  Scenario: Full graph execution via API
    Tool: Bash (pytest integration test)
    Steps:
      1. Create workflow with simple graph (start → task → end)
      2. Call execute_graph_workflow()
      3. Assert execution record returned with status="pending"
      4. Wait for background task (asyncio.sleep)
      5. Reload execution, assert status="completed"
      6. Assert GraphState records exist for each node
    Expected: Async execution completes, states recorded
    Evidence: .sisyphus/evidence/task-14-full-execution.txt

  Scenario: Execution failure recorded
    Tool: Bash (pytest)
    Steps:
      1. Create workflow with invalid graph_definition
      2. Call execute_graph_workflow()
      3. Wait for background task
      4. Assert execution status="failed", error_message set
    Expected: Failure caught, error recorded
    Evidence: .sisyphus/evidence/task-14-failure.txt
  ```

- [ ] 15. Execution Status/Results API Endpoints

  **What to do**:
  - Update `app/api/v1/graph.py`:
    - Enhance `GET /{workflow_id}/executions/{execution_id}` to include:
      - execution status, started_at, completed_at
      - output_data, error_message
      - node_states (list of GraphState records)
    - Add `GET /{workflow_id}/executions/{execution_id}/nodes` — detailed per-node results
    - Add `POST /{workflow_id}/executions/{execution_id}/resume` — resume paused execution (for approval nodes)

  **Must NOT do**:
  - Add WebSocket endpoints
  - Change execution logic

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard FastAPI routes, data formatting, follows existing patterns
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 14, 16-18)
  - **Blocks**: Task 16
  - **Blocked By**: Tasks 3, 14

  **References**:
  - `app/api/v1/graph.py` — existing route patterns
  - `app/schemas/graph.py` — response schemas to update

  **Acceptance Criteria**:
  - [ ] GET execution returns status + output + node_states
  - [ ] GET execution/nodes returns per-node detail
  - [ ] POST resume works for paused executions
  - [ ] All endpoints authenticated

  **QA Scenarios**:
  ```
  Scenario: Get execution with node states
    Tool: Bash (curl)
    Steps:
      1. Execute a graph (from Task 14)
      2. GET /graphs/{id}/executions/{eid}
      3. Assert response has status, output_data, node_states array
    Expected: 200, full execution detail
    Evidence: .sisyphus/evidence/task-15-execution-detail.txt
  ```

- [ ] 16. Frontend Run Button + Execution Status Panel

  **What to do**:
  - Update `FlowEditor.tsx`:
    - Add "Run" button to FlowActions (bottom bar)
    - On click: POST /api/graphs/{savedId}/execute
    - Show execution status indicator (running spinner, completed check, failed X)
    - Add execution results panel (slide-in sidebar, similar to VersionHistoryPanel)
    - Panel shows: execution status, node-by-node results, output data, errors
    - Auto-refresh every 2s while running (polling)
    - Add "Resume" button for paused executions (approval nodes)

  **Must NOT do**:
  - Add WebSocket real-time updates
  - Change canvas rendering
  - Modify node components

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: UI component, follows existing FlowEditor patterns, needs polished UX
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 14, 15, 17-18)
  - **Blocks**: Task 18
  - **Blocked By**: Task 15

  **References**:
  - `src/components/mission-builder/FlowEditor.tsx` — existing component, FlowActions, Panel patterns
  - `src/components/mission-builder/VersionHistoryPanel.tsx` — sidebar panel pattern to follow
  - `src/lib/mission-builder/api.ts` — API client patterns

  **Acceptance Criteria**:
  - [ ] Run button in bottom action bar
  - [ ] Clicking Run triggers POST to execute endpoint
  - [ ] Status indicator shows running/completed/failed
  - [ ] Execution results panel slides in from right
  - [ ] Panel auto-refreshes every 2s while running
  - [ ] Resume button shown for paused executions

  **QA Scenarios**:
  ```
  Scenario: Run button triggers execution
    Tool: Playwright
    Steps:
      1. Navigate to /en/missions/builder
      2. Create a simple flow (start → task → end)
      3. Save flow
      4. Click Run button
      5. Assert execution status indicator appears
    Expected: Run button works, status shown
    Evidence: .sisyphus/evidence/task-16-run-button.png

  Scenario: Execution results panel shows results
    Tool: Playwright
    Steps:
      1. Execute a flow (from previous scenario)
      2. Wait for completion
      3. Assert execution panel shows node results
      4. Assert output data displayed
    Expected: Panel shows results
    Evidence: .sisyphus/evidence/task-16-results-panel.png
  ```

- [ ] 17. Integration Tests (Full Graph Execution)

  **What to do**:
  - Create comprehensive integration tests in `app/tests/test_graph_executor.py`:
    - Test full graph execution with mocked ModelRouter
    - Test branching graph (condition → two paths → merge)
    - Test loop graph (count mode, foreach mode)
    - Test parallel graph (concurrent branches)
    - Test error recovery (node failure → retry → fallback)
    - Test subflow execution (nested workflow)
    - Test large graph (20+ nodes, performance)

  **Must NOT do**:
  - Mock at too low a level (test real service integration)
  - Skip error cases

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Complex test scenarios, async testing, comprehensive coverage
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 14-16, 18)
  - **Blocks**: Task 18
  - **Blocked By**: Tasks 14, 15

  **References**:
  - `app/tests/test_graph_executor.py` — test file from Task 6
  - `app/tests/test_mission_executor.py` — integration test patterns
  - `app/tests/conftest.py` — fixtures

  **Acceptance Criteria**:
  - [ ] 10+ integration test cases
  - [ ] All node types tested
  - [ ] Error scenarios covered
  - [ ] Tests pass against test database
  - [ ] Test execution < 30 seconds total

  **QA Scenarios**:
  ```
  Scenario: Run all integration tests
    Tool: Bash (pytest)
    Steps:
      1. Run pytest app/tests/test_graph_executor.py -v
      2. Assert all tests pass
      3. Assert coverage > 80% for graph_executor.py
    Expected: All tests pass, good coverage
    Evidence: .sisyphus/evidence/task-17-integration-tests.txt
  ```

- [ ] 18. Deploy + E2E Verification

  **What to do**:
  - Deploy backend to homelab:
    - `cd /opt/flowmanner/backend && docker build -t workflows-backend:latest .`
    - `docker compose up -d --no-deps --force-recreate backend`
  - Deploy frontend to VPS:
    - rsync from homelab to VPS
    - `docker compose build frontend && docker compose up -d --no-deps frontend`
  - Run E2E tests against production:
    - `npx playwright test --config=playwright.config.production.ts`
  - Verify:
    - Run button works on flowmanner.com
    - Execution completes successfully
    - Results panel shows correct data

  **Must NOT do**:
  - Modify production database directly
  - Skip backend health checks

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard deploy + smoke test, follows existing deployment patterns
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (final task)
  - **Blocks**: Nothing
  - **Blocked By**: Tasks 14, 16, 17

  **References**:
  - `AGENTS.md` — deployment commands, SSH patterns
  - `playwright.config.ts` — existing Playwright config
  - `e2e/mission-builder.spec.ts` — existing E2E tests

  **Acceptance Criteria**:
  - [ ] Backend container healthy on homelab
  - [ ] Frontend container healthy on VPS
  - [ ] https://flowmanner.com loads
  - [ ] Run button visible and functional
  - [ ] Execution completes, results shown
  - [ ] E2E tests pass against production

  **QA Scenarios**:
  ```
  Scenario: Full E2E execution on production
    Tool: Playwright
    Steps:
      1. Navigate to https://flowmanner.com/en/missions/builder
      2. Create simple flow
      3. Save flow
      4. Click Run
      5. Wait for completion
      6. Assert results panel shows output
    Expected: Full execution works on production
    Evidence: .sisyphus/evidence/task-18-e2e-production.png
  ```

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search codebase for forbidden patterns. Check evidence files exist. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run type checks + linter + pytest. Review all changed files for: async correctness, error handling, AI slop patterns. Check no `eval()` without sandboxing, no infinite loops without limits.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill if UI)
  Start from clean state. Execute EVERY QA scenario from EVERY task. Test cross-task integration. Test edge cases. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 compliance. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **1-6**: `feat(graph-exec): add graph interpreter foundation` — graph_executor.py, graph_node_handlers.py, test fixtures
- **7-13**: `feat(graph-exec): implement all 12 node handlers` — graph_node_handlers.py (handlers), tests
- **14-15**: `feat(graph-exec): wire execution engine to API` — graph_service.py, graph.py routes, schemas
- **16**: `feat(graph-exec): add Run button and execution panel to FlowEditor` — FlowEditor.tsx
- **17**: `test(graph-exec): add integration tests` — test_graph_executor.py
- **18**: `ci: deploy and verify graph execution on production` — deploy scripts, E2E tests

---

## Success Criteria

### Verification Commands
```bash
# Backend
cd /opt/flowmanner/backend && pytest app/tests/test_graph_executor.py -v  # All pass
cd /opt/flowmanner/backend && python -c "from app.services.graph_executor import GraphInterpreter; print('OK')"  # Imports clean

# API
curl -X POST https://flowmanner.com/api/graphs/{id}/execute -H "Cookie: ..."  # Returns execution_id
curl https://flowmanner.com/api/graphs/{id}/executions/{eid} -H "Cookie: ..."  # Returns status + results

# Frontend
npx playwright test --config=playwright.config.production.ts  # All pass
```

### Final Checklist
- [ ] All 12 node types execute correctly
- [ ] Graph execution is async (non-blocking API)
- [ ] State passes between nodes
- [ ] Errors handled with retries
- [ ] Frontend can trigger and monitor execution
- [ ] No new database models created
- [ ] No changes to mission executor
- [ ] All tests pass
- [ ] Deployed and verified on production
