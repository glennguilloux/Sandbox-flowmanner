# Flowmanner — Close Missions Feature

## TL;DR

> **Quick Summary**: The graph execution engine is complete and deployed. 5 final items remain to close the Missions feature: (1) execution history page, (2) resume button for paused approvals, (3) graphs list/management page, (4) trigger-to-graph connection, (5) production E2E verification.
> 
> **Deliverables**:
> - Execution history page (list + detail + re-run)
> - Resume button in ExecutionStatusPanel for paused executions
> - Graphs list page (CRUD management)
> - Wire triggers to execute graphs (not just missions)
> - Production E2E test run
> 
> **Estimated Effort**: Short
> **Parallel Execution**: YES — 2 waves
> **Critical Path**: UI pages → Trigger wiring → E2E verify

---

## Context

### What's Done (Verified)
- Graph execution engine with 12 handlers ✅
- All 4 handler gaps fixed (subflow, parallel, approval, loop) ✅
- Run/Stop buttons + ExecutionStatusPanel with polling ✅
- Live execution overlay (node highlighting) ✅
- Analytics API with real data ✅
- 47 backend + 44 frontend tests passing ✅
- Deployed on flowmanner.com ✅

### What's Missing to Close Missions

1. **No execution history page** — Can't view past executions, re-run, or compare results
2. **No resume button** — Approval nodes pause execution but no UI to resume
3. **No graphs list page** — Can't see all saved workflows, delete, or manage them
4. **Triggers don't fire graphs** — Triggers exist but only fire missions, not graph workflows
5. **No production E2E verification** — Tests exist but never run against flowmanner.com

---

## Work Objectives

### Core Objective
Complete the Missions feature by adding the missing UI pages, resume functionality, trigger integration, and production verification.

### Concrete Deliverables
- `/en/graphs` page — list all workflows with status, execute, delete
- `/en/graphs/[id]/executions` page — execution history with detail + re-run
- Resume button in ExecutionStatusPanel for paused executions
- Trigger-to-graph execution endpoint
- Production E2E test run

### Definition of Done
- [ ] User can see all saved graphs in a list page
- [ ] User can view execution history for any graph
- [ ] User can resume paused executions from UI
- [ ] Triggers can fire graph workflows
- [ ] E2E tests pass against production

### Must Have
- Graph list page with execute/delete
- Execution history page with detail view
- Resume button for paused approvals
- Trigger graph execution endpoint
- Production E2E verification

### Must NOT Have (Guardrails)
- No new database models
- No WebSocket
- No changes to mission executor
- No new external dependencies

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: YES (pytest, Playwright)
- **Automated tests**: Tests-after (add tests after implementation)
- **Framework**: pytest + Playwright

### QA Policy
Every task includes agent-executed QA scenarios.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — UI pages + resume):
├── Task 1: Graphs list page (/en/graphs) [visual-engineering]
├── Task 2: Execution history page (/en/graphs/[id]/executions) [visual-engineering]
├── Task 3: Resume button in ExecutionStatusPanel [quick]
├── Task 4: Trigger-to-graph execution endpoint [quick]
└── Task 5: Integration tests for new features [deep]

Wave 2 (After Wave 1 — deploy + verify):
└── Task 6: Deploy + production E2E verification [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix
- **1-5**: No deps — all start immediately (except 5 depends on 1-4)
- **6**: Depends on 1-5

### Agent Dispatch Summary
- **Wave 1**: 5 tasks — T1-T2→`visual-engineering`, T3-T4→`quick`, T5→`deep`
- **Wave 2**: 1 task — T6→`quick`
- **FINAL**: 4 tasks — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

- [ ] 1. Graphs List Page (`/en/graphs`)

  **What to do**:
  - Create `src/app/en/graphs/page.tsx` (Next.js App Router)
  - Fetch workflows from `GET /api/graphs/`
  - Show table: name, description, status, created_at, actions
  - Actions: Execute, Edit (navigate to builder), Delete
  - Add "Create New" button (navigate to builder with empty flow)
  - Add search/filter by name
  - Follow existing UI patterns from mission-builder

  **Must NOT do**:
  - Create new API endpoints (use existing `/api/graphs/`)
  - Change graph models

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: UI page, follows existing patterns, needs polished UX
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2-5)
  - **Blocks**: Task 6
  - **Blocked By**: None

  **References**:
  - `app/api/v1/graph.py:list_items()` — existing GET /api/graphs/ endpoint
  - `src/components/mission-builder/FlowEditor.tsx` — UI patterns
  - `src/components/analytics/AnalyticsDashboard.tsx` — dashboard patterns

  **Acceptance Criteria**:
  - [ ] Page lists all user's workflows
  - [ ] Execute button triggers graph execution
  - [ ] Edit button navigates to builder
  - [ ] Delete button removes workflow
  - [ ] Create New button opens empty builder

  **QA Scenarios**:
  ```
  Scenario: Graphs list page loads
    Tool: Playwright
    Steps:
      1. Navigate to /en/graphs
      2. Assert table shows workflows
      3. Assert Execute, Edit, Delete buttons visible
    Expected: Page loads with workflow list
    Evidence: .sisyphus/evidence/task-1-graphs-list.png
  ```

- [ ] 2. Execution History Page (`/en/graphs/[id]/executions`)

  **What to do**:
  - Create `src/app/en/graphs/[id]/executions/page.tsx`
  - Fetch executions from `GET /api/graphs/{id}/executions`
  - Show list: status badge, started_at, duration, output summary
  - Click execution to see detail: node-by-node results, timing, errors
  - Add "Re-run" button (POST /api/graphs/{id}/execute)
  - Add filters: status, date range

  **Must NOT do**:
  - Create new API endpoints
  - Add WebSocket

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: UI page, follows existing patterns
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3-5)
  - **Blocks**: Task 6
  - **Blocked By**: None

  **References**:
  - `app/api/v1/graph.py:list_executions()` — existing endpoint
  - `app/api/v1/graph.py:get_execution()` — execution detail with node_states
  - `src/components/mission-builder/FlowEditor.tsx:ExecutionStatusPanel` — existing panel

  **Acceptance Criteria**:
  - [ ] Page lists executions with status/timing
  - [ ] Click execution shows node detail
  - [ ] Re-run button triggers new execution
  - [ ] Filters work

  **QA Scenarios**:
  ```
  Scenario: Execution history page loads
    Tool: Playwright
    Steps:
      1. Navigate to /en/graphs/{id}/executions
      2. Assert execution list shows
      3. Click execution, assert detail shows
    Expected: Page loads with execution history
    Evidence: .sisyphus/evidence/task-2-execution-history.png
  ```

- [ ] 3. Resume Button in ExecutionStatusPanel

  **What to do**:
  - Update `FlowEditor.tsx` ExecutionStatusPanel:
    - Detect `executionStatus === "paused"`
    - Show "Resume" button when paused
    - On click: POST `/api/graphs/{savedId}/resume/{executionId}`
    - Update status to "running", resume polling
    - Show toast "Execution resumed"
  - Update `graph.py` API if resume endpoint needs adjustment

  **Must NOT do**:
  - Change backend resume logic
  - Add new models

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple button addition, follows existing patterns
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-2, 4-5)
  - **Blocks**: Task 6
  - **Blocked By**: None

  **References**:
  - `src/components/mission-builder/FlowEditor.tsx` — ExecutionStatusPanel, polling logic
  - `app/api/v1/graph.py:resume_graph()` — existing resume endpoint
  - `app/services/graph_service.py:resume_graph_execution()` — backend logic

  **Acceptance Criteria**:
  - [ ] Resume button shows when status="paused"
  - [ ] Click resume calls POST /graphs/{id}/resume/{eid}
  - [ ] Status updates to "running", polling resumes
  - [ ] Toast shows "Execution resumed"

  **QA Scenarios**:
  ```
  Scenario: Resume button works for paused execution
    Tool: Playwright
    Steps:
      1. Execute graph with approval node (pauses)
      2. Assert Resume button visible
      3. Click Resume
      4. Assert status changes to "running"
    Expected: Execution resumes
    Evidence: .sisyphus/evidence/task-3-resume-button.png
  ```

- [ ] 4. Trigger-to-Graph Execution Endpoint

  **What to do**:
  - Add `POST /api/triggers/{trigger_id}/fire-graph` endpoint in `triggers.py`
  - Or update existing `fire_trigger` to support graph_type triggers
  - When fired, execute the linked graph workflow via `execute_graph_workflow()`
  - Log execution in trigger logs
  - Update trigger schema to support `trigger_type: "graph"`

  **Must NOT do**:
  - Create new trigger models
  - Change existing mission trigger behavior

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple endpoint addition, follows existing trigger patterns
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-3, 5)
  - **Blocks**: Task 6
  - **Blocked By**: None

  **References**:
  - `app/api/v1/triggers.py` — existing trigger endpoints
  - `app/services/trigger_service.py` — trigger service
  - `app/services/graph_service.py:execute_graph_workflow()` — graph execution

  **Acceptance Criteria**:
  - [ ] POST /triggers/{id}/fire-graph executes linked graph
  - [ ] Execution logged in trigger logs
  - [ ] Works with cron and webhook triggers

  **QA Scenarios**:
  ```
  Scenario: Trigger fires graph execution
    Tool: Bash (pytest)
    Steps:
      1. Create trigger linked to graph workflow
      2. POST /triggers/{id}/fire-graph
      3. Assert graph execution started
    Expected: Graph executes
    Evidence: .sisyphus/evidence/task-4-trigger-graph.txt
  ```

- [ ] 5. Integration Tests

  **What to do**:
  - Add tests for:
    - Graphs list page API
    - Execution history page API
    - Resume execution flow
    - Trigger-to-graph execution
  - Update existing test files

  **Must NOT do**:
  - Mock at too low a level

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Comprehensive test coverage
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-4)
  - **Blocks**: Task 6
  - **Blocked By**: Tasks 1-4

  **References**:
  - `app/tests/test_graph_executor.py` — existing tests
  - `app/tests/conftest.py` — fixtures

  **Acceptance Criteria**:
  - [ ] 10+ new integration tests
  - [ ] All tests pass
  - [ ] Coverage maintained

  **QA Scenarios**:
  ```
  Scenario: Run all integration tests
    Tool: Bash (pytest)
    Steps:
      1. Run pytest app/tests/test_graph_executor.py -v
      2. Assert all tests pass
    Expected: All tests pass
    Evidence: .sisyphus/evidence/task-5-integration-tests.txt
  ```

- [ ] 6. Deploy + Production E2E Verification

  **What to do**:
  - Deploy backend to homelab
  - Deploy frontend to VPS
  - Run E2E tests against flowmanner.com
  - Verify all new features work on production

  **Must NOT do**:
  - Modify production database directly

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard deploy + smoke test
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (final task)
  - **Blocks**: Nothing
  - **Blocked By**: Tasks 1-5

  **References**:
  - `AGENTS.md` — deployment commands
  - `playwright.config.ts` — Playwright config

  **Acceptance Criteria**:
  - [ ] Backend container healthy
  - [ ] Frontend container healthy
  - [ ] https://flowmanner.com loads
  - [ ] All new features work on production
  - [ ] E2E tests pass

  **QA Scenarios**:
  ```
  Scenario: Full E2E on production
    Tool: Playwright
    Steps:
      1. Navigate to https://flowmanner.com/en/graphs
      2. Create graph, execute, view history
      3. Verify all features work
    Expected: Everything works on production
    Evidence: .sisyphus/evidence/task-6-e2e-production.png
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

- **1-2**: `feat(ui): add graphs list and execution history pages`
- **3**: `feat(ui): add resume button for paused executions`
- **4**: `feat(triggers): add trigger-to-graph execution endpoint`
- **5**: `test(graphs): add integration tests for new features`
- **6**: `ci: deploy and verify on production`

---

## Success Criteria

### Verification Commands
```bash
# Backend
cd /opt/flowmanner/backend && pytest app/tests/test_graph_executor.py -v  # All pass

# API
curl https://flowmanner.com/api/graphs -H "Cookie: ..."  # Returns workflow list
curl https://flowmanner.com/api/graphs/{id}/executions -H "Cookie: ..."  # Returns executions

# Frontend
npx playwright test --config=playwright.config.production.ts  # All pass
```

### Final Checklist
- [ ] Graphs list page functional
- [ ] Execution history page functional
- [ ] Resume button works for paused executions
- [ ] Triggers can fire graphs
- [ ] All tests pass
- [ ] Deployed and verified on production
- [ ] MISSIONS FEATURE COMPLETE ✅
