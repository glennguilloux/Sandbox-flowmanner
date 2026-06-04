# Flowmanner — Execution Monitoring & Analytics

## TL;DR

> **Quick Summary**: The graph execution engine works but has 4 handler gaps (subflow deferred, parallel stub, approval doesn't pause, loop doesn't execute downstream). Analytics endpoints return zeros. Dashboard has UI but no data. The natural next step is: (1) fix execution gaps, (2) build real analytics for graph executions, (3) add execution monitoring UI on the canvas, (4) build execution history dashboard.
> 
> **Deliverables**:
> - Fix 4 graph handler gaps (subflow, parallel, approval, loop)
> - Analytics API with real graph execution data
> - Canvas execution overlay (live node highlighting during execution)
> - Execution history dashboard page
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 2 waves
> **Critical Path**: Handler fixes → Analytics API → Dashboard UI → Canvas overlay

---

## Context

### Current State (Verified)

**Graph Execution Engine** — EXISTS with gaps:
- `graph_executor.py` (226 lines) — GraphInterpreter + ExecutionContext with interpolation ✅
- `graph_node_handlers.py` (376 lines) — 12 handlers registered ✅
- `graph_service.py` — Lifecycle functions ✅
- `graph.py` API — 13 routes ✅
- `FlowEditor.tsx` — Run/Stop buttons + ExecutionStatusPanel ✅
- Tests: 37 backend + 44 frontend passing ✅

**Handler Gaps Found**:
1. **SubFlowNodeHandler** — Returns `"status": "deferred"` with note "requires database access from interpreter"
2. **ParallelNodeHandler** — Returns empty `branch_outputs: {}` with note "handled by interpreter traversal"
3. **ApprovalNodeHandler** — Returns `"status": "paused"` but doesn't actually pause execution
4. **LoopNodeHandler** — Records iteration metadata but doesn't execute downstream nodes in the loop

**Analytics** — STUBBED:
- `GET /api/v1/analytics/runs` → returns `[]`
- `GET /api/v1/analytics/usage` → returns all zeros
- `GET /api/v1/analytics/stats` → works (mission counts only, no graph data)

**Dashboard** — UI EXISTS, NO DATA:
- `AnalyticsDashboard.tsx` component exists
- Backend returns zeros, so dashboard shows empty state

**Triggers** — COMPLETE:
- Full CRUD + webhook + fire/pause/resume
- But triggers fire missions, not graphs

### What's Missing

1. **Graph execution analytics** — No data about graph runs, success rates, timing
2. **Execution history** — No way to see past graph executions
3. **Live execution visualization** — No node highlighting during execution on canvas
4. **Handler gaps** — 4 handlers don't fully work

---

## Work Objectives

### Core Objective
Complete the graph execution engine by fixing handler gaps, then build analytics and monitoring so users can see execution history, success rates, and live execution progress.

### Concrete Deliverables
- Fix 4 handler gaps in `graph_node_handlers.py`
- Add graph execution analytics endpoints
- Build execution history dashboard page
- Add live execution overlay on canvas (node highlighting)

### Definition of Done
- [ ] All 12 node handlers execute correctly (not just return metadata)
- [ ] Analytics endpoints return real graph execution data
- [ ] Execution history page shows past executions with status/timing
- [ ] Canvas highlights nodes during live execution
- [ ] Dashboard shows real analytics data

### Must Have
- Subflow handler loads and executes nested workflow
- Parallel handler executes branches concurrently
- Approval handler actually pauses execution (sets status, waits for resume)
- Loop handler executes downstream nodes for each iteration
- Analytics: total runs, success rate, avg duration, top workflows
- Execution history: list, detail, re-run
- Live execution: node highlighting on canvas

### Must NOT Have (Guardrails)
- No new database models (reuse GraphExecution, GraphState)
- No WebSocket (polling is sufficient)
- No changes to mission executor
- No new external dependencies
- No changes to node type definitions

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (pytest, Playwright)
- **Automated tests**: TDD
- **Framework**: pytest for backend, Playwright for frontend

### QA Policy
Every task includes agent-executed QA scenarios:
- **Backend**: pytest unit tests
- **API**: curl endpoints, assert status + response fields
- **Frontend**: Playwright scenarios

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — fix handler gaps + analytics foundation):
├── Task 1: Fix SubFlowNodeHandler (load + execute nested workflow) [deep]
├── Task 2: Fix ParallelNodeHandler (concurrent branch execution) [deep]
├── Task 3: Fix ApprovalNodeHandler (actual pause/resume) [deep]
├── Task 4: Fix LoopNodeHandler (execute downstream nodes per iteration) [deep]
├── Task 5: Graph analytics service (aggregate execution data) [quick]
└── Task 6: Analytics API endpoints [quick]

Wave 2 (After Wave 1 — UI + monitoring):
├── Task 7: Execution history dashboard page [visual-engineering]
├── Task 8: Live execution overlay on canvas [visual-engineering]
├── Task 9: Analytics dashboard data wiring [quick]
├── Task 10: Integration tests (full execution + analytics) [deep]
└── Task 11: Deploy + E2E verification [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix
- **1-6**: No deps — all start immediately
- **7**: Depends on 5, 6
- **8**: Depends on 1-4 (needs working execution)
- **9**: Depends on 5, 6
- **10**: Depends on 1-9
- **11**: Depends on 7-10

### Agent Dispatch Summary
- **Wave 1**: 6 tasks — T1-T4→`deep`, T5-T6→`quick`
- **Wave 2**: 5 tasks — T7→`visual-engineering`, T8→`visual-engineering`, T9→`quick`, T10→`deep`, T11→`quick`
- **FINAL**: 4 tasks — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [ ] 1. Fix SubFlowNodeHandler

  **What to do**:
  - Update `SubFlowNodeHandler.execute()` in `graph_node_handlers.py`
  - Accept `db` session via context or handler init
  - Load subflow workflow by missionId using `get_graph_workflow()`
  - Create nested `GraphInterpreter` with same db session
  - Pass parent context to subflow (with depth tracking)
  - Collect subflow outputs and merge into parent context
  - Enforce MAX_DEPTH=5 (already exists)

  **Must NOT do**:
  - Create new database queries
  - Allow infinite recursion

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Nested execution, context passing, depth limiting, DB session management
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2-6)
  - **Blocks**: Tasks 8, 10
  - **Blocked By**: None

  **References**:
  - `app/services/graph_node_handlers.py:SubFlowNodeHandler` — current stub (line 353-376)
  - `app/services/graph_executor.py:GraphInterpreter` — nested instantiation
  - `app/services/graph_service.py:get_graph_workflow()` — load workflow by ID

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
    Evidence: .sisyphus/evidence/task-1-subflow.txt

  Scenario: Subflow depth limit enforced
    Tool: Bash (pytest)
    Steps:
      1. Create chain of 6 subflows (A→B→C→D→E→F)
      2. Execute top-level subflow
    Expected: Stops at depth 5, returns error
    Evidence: .sisyphus/evidence/task-1-subflow-depth.txt
  ```

- [ ] 2. Fix ParallelNodeHandler

  **What to do**:
  - Update `ParallelNodeHandler.execute()` in `graph_node_handlers.py`
  - Find downstream nodes from graph edges (nodes connected from this parallel node)
  - Execute downstream branches concurrently using `asyncio.gather()`
  - Support joinMode: "all" (wait for all) or "any" (first to complete)
  - Collect outputs from all branches into context
  - Handle partial failures

  **Must NOT do**:
  - Use threading (use asyncio)
  - Modify GraphInterpreter traversal logic

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Concurrent execution, edge traversal, error aggregation
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3-6)
  - **Blocks**: Tasks 8, 10
  - **Blocked By**: None

  **References**:
  - `app/services/graph_node_handlers.py:ParallelNodeHandler` — current stub (line 194-209)
  - `app/services/graph_executor.py:GraphInterpreter.execute()` — layer-based traversal
  - `app/models/graph.py:GraphWorkflow` — graph_definition contains nodes + edges

  **Acceptance Criteria**:
  - [ ] ParallelNodeHandler finds downstream nodes from edges
  - [ ] Executes branches concurrently with asyncio.gather()
  - [ ] joinMode="all" waits for all branches
  - [ ] joinMode="any" returns first completed branch
  - [ ] All branch outputs collected into context

  **QA Scenarios**:
  ```
  Scenario: Parallel branches execute concurrently
    Tool: Bash (pytest with async mocks)
    Steps:
      1. Create graph with parallel node → 2 downstream task nodes → end
      2. Execute graph
      3. Assert both task nodes executed
      4. Assert both outputs in context
    Expected: Both branches execute, outputs collected
    Evidence: .sisyphus/evidence/task-2-parallel.txt

  Scenario: Parallel with joinMode="any"
    Tool: Bash (pytest)
    Steps:
      1. Create parallel node with joinMode="any"
      2. Execute with 2 branches (one fast, one slow)
    Expected: Returns after first branch completes
    Evidence: .sisyphus/evidence/task-2-parallel-any.txt
  ```

- [ ] 3. Fix ApprovalNodeHandler

  **What to do**:
  - Update `ApprovalNodeHandler.execute()` in `graph_node_handlers.py`
  - Set execution status to "paused" via graph_service lifecycle
  - Store approval request metadata in GraphState
  - Return `{"pause": True}` signal to interpreter
  - Update `GraphInterpreter.execute()` to detect pause signal and stop traversal
  - Ensure `resume_graph_execution()` can continue from paused state

  **Must NOT do**:
  - Implement approval UI (just pause execution)
  - Change database models

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: State machine integration, pause/resume lifecycle, interpreter modification
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-2, 4-6)
  - **Blocks**: Tasks 8, 10
  - **Blocked By**: None

  **References**:
  - `app/services/graph_node_handlers.py:ApprovalNodeHandler` — current implementation (line 261-275)
  - `app/services/graph_service.py` — pause_execution, resume_graph_execution
  - `app/services/graph_executor.py:GraphInterpreter.execute()` — needs pause detection

  **Acceptance Criteria**:
  - [ ] ApprovalNodeHandler sets execution status to "paused"
  - [ ] GraphInterpreter detects pause signal and stops
  - [ ] resume_graph_execution() continues from paused node
  - [ ] Approval metadata stored in GraphState

  **QA Scenarios**:
  ```
  Scenario: Approval node pauses execution
    Tool: Bash (pytest)
    Steps:
      1. Create graph: start → approval → end
      2. Execute graph
      3. Assert execution status="paused" after approval node
      4. Assert end node NOT executed
    Expected: Execution pauses at approval node
    Evidence: .sisyphus/evidence/task-3-approval-pause.txt

  Scenario: Resume continues from paused state
    Tool: Bash (pytest)
    Steps:
      1. Execute graph with approval node (pauses)
      2. Call resume_graph_execution()
      3. Assert execution completes, end node executed
    Expected: Execution resumes and completes
    Evidence: .sisyphus/evidence/task-3-approval-resume.txt
  ```

- [ ] 4. Fix LoopNodeHandler

  **What to do**:
  - Update `LoopNodeHandler.execute()` in `graph_node_handlers.py`
  - Find downstream nodes from graph edges (nodes connected from this loop node)
  - For each iteration, execute downstream nodes with loop context
  - Support loopMode: "count", "foreach", "while"
  - Collect iteration outputs into array
  - Enforce maxIterations (default 100)

  **Must NOT do**:
  - Allow infinite loops
  - Use threading

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Iteration logic, downstream node execution, context management per iteration
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-3, 5-6)
  - **Blocks**: Tasks 8, 10
  - **Blocked By**: None

  **References**:
  - `app/services/graph_node_handlers.py:LoopNodeHandler` — current implementation (line 212-258)
  - `app/services/graph_executor.py:GraphInterpreter` — node dispatch pattern
  - `src/lib/mission-types.ts:NodeDataExtra` — loop node fields

  **Acceptance Criteria**:
  - [ ] LoopNodeHandler executes downstream nodes for each iteration
  - [ ] Loop context (index, item) available to downstream nodes
  - [ ] maxIterations enforced
  - [ ] All iteration outputs collected

  **QA Scenarios**:
  ```
  Scenario: Loop executes downstream nodes
    Tool: Bash (pytest)
    Steps:
      1. Create graph: start → loop(count=3) → task → end
      2. Execute graph
      3. Assert task node executed 3 times
      4. Assert 3 outputs collected
    Expected: Downstream nodes execute per iteration
    Evidence: .sisyphus/evidence/task-4-loop-execution.txt

  Scenario: Loop respects maxIterations
    Tool: Bash (pytest)
    Steps:
      1. Create loop with loopCount=999
      2. Execute (maxIterations defaults to 100)
    Expected: Stops at 100 iterations
    Evidence: .sisyphus/evidence/task-4-loop-max.txt
  ```

- [ ] 5. Graph Analytics Service

  **What to do**:
  - Create `app/services/graph_analytics.py`
  - Implement functions:
    - `get_execution_stats(db, user_id)` — total runs, success rate, avg duration, failed count
    - `get_workflow_stats(db, user_id)` — top workflows by execution count, success rate per workflow
    - `get_recent_executions(db, user_id, limit=20)` — recent executions with status/timing
    - `get_execution_detail(db, execution_id)` — full execution detail with node-level timing
    - `get_usage_stats(db, user_id, period="30d")` — tokens used, cost, executions by type

  **Must NOT do**:
  - Create new database models
  - Change existing analytics endpoints

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: SQL queries, data aggregation, follows existing analytics patterns
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-4, 6)
  - **Blocks**: Tasks 6, 7, 9
  - **Blocked By**: None

  **References**:
  - `app/api/v1/analytics.py` — existing analytics patterns
  - `app/models/graph.py` — GraphExecution, GraphState models
  - `app/services/mission_analytics.py` — mission analytics patterns for reference

  **Acceptance Criteria**:
  - [ ] get_execution_stats returns real data from graph_executions table
  - [ ] get_workflow_stats returns per-workflow breakdown
  - [ ] get_recent_executions returns sorted list with status
  - [ ] get_usage_stats returns tokens/cost for period

  **QA Scenarios**:
  ```
  Scenario: Analytics returns real data
    Tool: Bash (pytest)
    Steps:
      1. Create test graph executions with various statuses
      2. Call get_execution_stats(db, user_id)
      3. Assert total_runs, success_rate, avg_duration are correct
    Expected: Real aggregation from test data
    Evidence: .sisyphus/evidence/task-5-analytics.txt
  ```

- [ ] 6. Analytics API Endpoints

  **What to do**:
  - Update `app/api/v1/analytics.py`:
    - Replace `GET /analytics/runs` stub with real graph execution data
    - Replace `GET /analytics/usage` stub with real usage stats
    - Add `GET /analytics/graphs` — graph-specific analytics
    - Add `GET /analytics/graphs/{workflow_id}` — per-workflow analytics
    - Add `GET /analytics/graphs/executions` — recent executions list

  **Must NOT do**:
  - Change mission analytics
  - Add new models

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard FastAPI routes, follows existing patterns
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-5)
  - **Blocks**: Tasks 7, 9
  - **Blocked By**: Task 5

  **References**:
  - `app/api/v1/analytics.py` — existing endpoints to update
  - `app/services/graph_analytics.py` — service functions from Task 5
  - `app/api/deps.py` — auth dependencies

  **Acceptance Criteria**:
  - [ ] GET /analytics/runs returns real graph execution list
  - [ ] GET /analytics/usage returns real usage data
  - [ ] GET /analytics/graphs returns graph analytics summary
  - [ ] All endpoints authenticated

  **QA Scenarios**:
  ```
  Scenario: Analytics endpoints return real data
    Tool: Bash (curl)
    Steps:
      1. Execute some graphs to create data
      2. GET /analytics/runs
      3. Assert non-empty list with execution data
    Expected: Real execution data returned
    Evidence: .sisyphus/evidence/task-6-analytics-api.txt
  ```

- [ ] 7. Execution History Dashboard Page

  **What to do**:
  - Create `src/app/en/graphs/[id]/executions/page.tsx` (Next.js App Router)
  - Or add executions tab to existing graph detail page
  - Show list of executions with: status badge, started_at, duration, output summary
  - Click execution to see detail: node-by-node results, timing, errors
  - Add "Re-run" button to re-execute a workflow
  - Add filters: status, date range, workflow

  **Must NOT do**:
  - Add WebSocket real-time updates
  - Change canvas rendering

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: UI page, follows existing Next.js patterns, needs polished UX
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8-11)
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 5, 6

  **References**:
  - `src/components/mission-builder/FlowEditor.tsx` — existing UI patterns
  - `src/components/analytics/AnalyticsDashboard.tsx` — dashboard patterns
  - `src/lib/mission-builder/api.ts` — API client patterns

  **Acceptance Criteria**:
  - [ ] Execution history page lists executions with status/timing
  - [ ] Click execution shows node-by-node detail
  - [ ] Re-run button triggers new execution
  - [ ] Filters work (status, date range)

  **QA Scenarios**:
  ```
  Scenario: Execution history page loads with data
    Tool: Playwright
    Steps:
      1. Navigate to graph executions page
      2. Assert execution list shows with status badges
      3. Click an execution
      4. Assert node detail panel opens
    Expected: Page loads, detail shows
    Evidence: .sisyphus/evidence/task-7-execution-history.png
  ```

- [ ] 8. Live Execution Overlay on Canvas

  **What to do**:
  - Update `FlowEditor.tsx`:
    - During execution, poll for execution status every 1s
    - Highlight currently executing node (glow/border animation)
    - Show completed nodes with checkmark
    - Show failed nodes with X
    - Show execution progress bar (nodes completed / total nodes)
    - Add "View Execution Detail" link to open execution panel

  **Must NOT do**:
  - Add WebSocket
  - Change node components
  - Modify graph definition

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Canvas overlay, animation, real-time state updates
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 9-11)
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 1-4

  **References**:
  - `src/components/mission-builder/FlowEditor.tsx` — existing execution state, polling
  - `@xyflow/react` — node styling, custom node rendering
  - `src/components/mission-builder/CustomNode.tsx` — node component to enhance

  **Acceptance Criteria**:
  - [ ] Currently executing node highlighted with animated border
  - [ ] Completed nodes show checkmark
  - [ ] Failed nodes show X
  - [ ] Progress bar shows execution progress
  - [ ] View Execution Detail link works

  **QA Scenarios**:
  ```
  Scenario: Live execution highlights nodes
    Tool: Playwright
    Steps:
      1. Navigate to builder with saved graph
      2. Click Run
      3. Assert executing node gets highlighted
      4. Assert completed nodes show checkmark
      5. Assert progress bar updates
    Expected: Nodes highlight during execution
    Evidence: .sisyphus/evidence/task-8-live-overlay.png
  ```

- [ ] 9. Analytics Dashboard Data Wiring

  **What to do**:
  - Update `src/components/analytics/AnalyticsDashboard.tsx`:
    - Replace mock data with real API calls to `/analytics/graphs`
    - Show: total graph runs, success rate, avg duration, top workflows
    - Add chart: executions over time
    - Add chart: success rate by workflow
    - Add table: recent executions with status/timing

  **Must NOT do**:
  - Add new chart libraries (use existing)
  - Change backend analytics

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Data wiring, follows existing dashboard patterns
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-8, 10-11)
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 5, 6

  **References**:
  - `src/components/analytics/AnalyticsDashboard.tsx` — existing component
  - `app/api/v1/analytics.py` — analytics endpoints from Task 6

  **Acceptance Criteria**:
  - [ ] Dashboard shows real graph execution data
  - [ ] Charts render with real data
  - [ ] Recent executions table populated

  **QA Scenarios**:
  ```
  Scenario: Dashboard shows real data
    Tool: Playwright
    Steps:
      1. Navigate to analytics dashboard
      2. Assert charts show real data (not zeros)
      3. Assert recent executions table populated
    Expected: Real analytics data displayed
    Evidence: .sisyphus/evidence/task-9-dashboard-data.png
  ```

- [ ] 10. Integration Tests

  **What to do**:
  - Add integration tests for:
    - Full graph execution with all 12 node types
    - Execution analytics aggregation
    - Pause/resume workflow
    - Subflow nested execution
    - Parallel branch execution
    - Loop iteration execution
  - Update `app/tests/test_graph_executor.py` with new tests

  **Must NOT do**:
  - Mock at too low a level
  - Skip error cases

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Complex test scenarios, comprehensive coverage
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-9, 11)
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 1-9

  **References**:
  - `app/tests/test_graph_executor.py` — existing test file
  - `app/tests/conftest.py` — fixtures

  **Acceptance Criteria**:
  - [ ] 20+ integration test cases
  - [ ] All node types tested end-to-end
  - [ ] Analytics tests verify aggregation
  - [ ] Tests pass against test database

  **QA Scenarios**:
  ```
  Scenario: Run all integration tests
    Tool: Bash (pytest)
    Steps:
      1. Run pytest app/tests/test_graph_executor.py -v
      2. Assert all tests pass
    Expected: All tests pass
    Evidence: .sisyphus/evidence/task-10-integration-tests.txt
  ```

- [ ] 11. Deploy + E2E Verification

  **What to do**:
  - Deploy backend to homelab
  - Deploy frontend to VPS
  - Run E2E tests against production
  - Verify:
    - All 12 node types execute
    - Analytics show real data
    - Execution history page works
    - Live execution overlay works

  **Must NOT do**:
  - Modify production database directly
  - Skip health checks

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard deploy + smoke test
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (final task)
  - **Blocks**: Nothing
  - **Blocked By**: Tasks 7-10

  **References**:
  - `AGENTS.md` — deployment commands
  - `playwright.config.ts` — Playwright config

  **Acceptance Criteria**:
  - [ ] Backend container healthy
  - [ ] Frontend container healthy
  - [ ] https://flowmanner.com loads
  - [ ] Analytics show real data
  - [ ] Execution history page works
  - [ ] Live execution overlay works

  **QA Scenarios**:
  ```
  Scenario: Full E2E on production
    Tool: Playwright
    Steps:
      1. Navigate to https://flowmanner.com
      2. Create and execute a graph
      3. Verify analytics update
      4. Verify execution history shows
    Expected: Everything works on production
    Evidence: .sisyphus/evidence/task-11-e2e-production.png
  ```

---

## Final Verification Wave

> 4 review agents run in PARALLEL. ALL must APPROVE.

- [ ] F1. **Plan Compliance Audit** — `oracle`
- [ ] F2. **Code Quality Review** — `unspecified-high`
- [ ] F3. **Real Manual QA** — `unspecified-high`
- [ ] F4. **Scope Fidelity Check** — `deep`

---

## Commit Strategy

- **1-4**: `fix(graph-exec): complete 4 handler gaps (subflow, parallel, approval, loop)`
- **5-6**: `feat(analytics): add graph execution analytics API`
- **7**: `feat(ui): add execution history dashboard page`
- **8**: `feat(ui): add live execution overlay on canvas`
- **9**: `feat(ui): wire analytics dashboard to real data`
- **10**: `test(graph-exec): add integration tests for handlers + analytics`
- **11**: `ci: deploy and verify on production`

---

## Success Criteria

### Verification Commands
```bash
# Backend
cd /opt/flowmanner/backend && pytest app/tests/test_graph_executor.py -v  # All pass

# API
curl https://flowmanner.com/api/analytics/graphs -H "Cookie: ..."  # Returns real data
curl https://flowmanner.com/api/analytics/runs -H "Cookie: ..."  # Returns execution list

# Frontend
npx playwright test --config=playwright.config.production.ts  # All pass
```

### Final Checklist
- [ ] All 12 node handlers execute correctly
- [ ] Analytics endpoints return real data
- [ ] Execution history page functional
- [ ] Live execution overlay works
- [ ] Dashboard shows real analytics
- [ ] All tests pass
- [ ] Deployed and verified on production
