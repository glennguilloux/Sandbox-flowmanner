# CONTINUE: Fix graph integration test + decide migration path

You are continuing work on the FlowManner backend after a crash interrupted the
last session. You are a frontier model working on a self-hosted, AI-native
workflow orchestration platform. You are running on the **homelab** machine
(172.16.1.1 / 10.99.0.3) at `/opt/flowmanner/backend/`.

---

## 1. WHAT HAPPENED (context from previous session)

A deep-dive report was produced on 2026-07-03
(`docs/DEEP-DIVE-REPORT-2026-07-03.md`). The report identified 5 key issues and
a prioritized action plan (P0–P5). Since then:

**Completed:**
- P0: `/inbox` auth gap fixed — middleware rewritten to opt-out model (frontend)
- P1: `llm_judge.py` + `eval_runner.py` routed through `BudgetEnforcer` (C1)
- P1: Cloud model refs in `causal_decomposer.py` STRATEGY_MAP replaced with
  local model identifiers (C2)
- Plugin Manager: `p99_latency_ms` field added, deprecated `/api/extensions`
  endpoint removed, audio format converter fixes
- HITL inbox SSE stream endpoint added (`/api/inbox/stream`)

**In-flight when crash hit (the immediate task):**
The last 5 commits (`dc7ddab` → `7206368`) were all fixing
`backend/tests/test_classify_route_workflow.py` — an integration test that
creates a classify-and-route graph workflow and executes it end-to-end through
the OLD `GraphInterpreter` executor. The test fixture was reworked to use a
test-local engine with NullPool and monkeypatch `AsyncSessionLocal` so the
background task gets the test engine. **3 of 4 tests are still failing.**

---

## 2. WHAT'S BROKEN RIGHT NOW

Run this to see the current state:

```bash
docker compose exec -T backend python -m pytest tests/test_classify_route_workflow.py -v --timeout=30
```

**Current result: 1 passed, 3 failed.** Two root causes:

### Bug 1: FK constraint — `workflow_states.execution_id` → `workflow_executions`

The background task `_execute_graph_async` in `graph_service.py` (line ~430)
opens a NEW `AsyncSessionLocal` session and tries to insert `workflow_states`
rows referencing an `execution_id` that was created in the test fixture's
session but **not yet committed** when the background task fires.

The test fixture's `override_get_db` auto-commits on success, but
`create_graph_execution` (line ~243) does `db.add(execution)` + `db.flush()`
then immediately fires `asyncio.create_task(_execute_graph_async(...))`. The
background task's separate session can't see the uncommitted row.

The monkeypatching of `AsyncSessionLocal` (commit `7206368`) was supposed to
fix this by making the background task use the test engine, but the test-local
engine creates a **new connection** (NullPool = no sharing), so the background
session still can't see uncommitted data from the fixture session.

**This is the core problem: the background task pattern is fundamentally
incompatible with test transaction isolation.** The test needs to either:
- Wait for the background task to complete before asserting (the task runs in
  the same event loop, so `await asyncio.sleep(0)` or an explicit wait should
  work), OR
- Use a shared session/connection so the background task sees uncommitted data,
  OR
- Commit the execution row before firing the background task (but that changes
  production behavior — the `create_graph_execution` function currently
  doesn't commit; the caller's session auto-commits on context exit).

### Bug 2: `ModelRouter.route_request()` missing required argument `messages`

The error in the test output:
```
"output": {"success": false, "error": "ModelRouter.route_request() missing 1 required positional argument: 'messages'"}
```

The `GraphInterpreter` (old executor in `graph_executor.py`) is calling
`ModelRouter.route_request()` without passing `messages` as a positional
argument. The signature is:
```python
async def route_request(self, messages: list, user_id=None, db_session=None, ...)
```

Look at `graph_executor.py` for where it calls route_request — it may be using
a stale calling convention or passing kwargs only. **This bug is in the old
executor code**, not the test.

---

## 3. THE BIGGER PICTURE (why this test matters)

The test `test_classify_route_workflow.py` exercises the **old `GraphInterpreter`
executor** (`graph_executor.py`, ~293 LOC). This is one of the 7 old executors
identified in the deep-dive report (recommendation A2) that should be migrated
to the substrate's `GraphStrategy` (`substrate/strategies/graph.py`).

The 6 v1 routers that still import old executors are:
1. `mission_decomposition_routes.py` → `dag_executor`
2. `flow_compat.py` → `GraphInterpreter`
3. `graph.py` → `graph_executor`
4. `swarm.py` → `SwarmOrchestrator`
5. `swarm_protocol.py` → debate/escalation/handoff protocols
6. `orchestration.py` → `nexus/meta_loop_orchestrator`

**This test directly exercises the `graph.py` → `graph_executor.py` path.**
If you can make the test pass, that's progress. But the real question is:
**should you fix the old executor's bugs, or migrate `graph.py` to the substrate
`GraphStrategy` and update the test to use the new path?**

The report's recommendation is to migrate first (A2), then delete old executors
(A1). But the migration is L effort. For this session, the decision is:

- **Option A (pragmatic):** Fix the 2 bugs in the old executor path so the test
  passes. This is S effort and unblocks CI. The migration to substrate can
  happen in a later session.
- **Option B (architectural):** Migrate `graph.py` API router to use
  `substrate/strategies/graph.py` (GraphStrategy) and update the test to use
  the new path. This is M-L effort but is the right long-term move.

**Recommendation: Option A this session.** Fix the bugs, make the test green,
and create a follow-up task for the substrate migration. Don't attempt the full
migration in one session — it risks touching too many files.

---

## 4. GLenn's Answers to Open Questions (from the report)

These decisions are already made — respect them:

1. **Blueprint+Run vs Mission:** "Not intended — DeepSeek did start the work on
   blueprint too early!" → The dual-write should be paused/rolled back. Do NOT
   push the Blueprint+Run model further. Mission is still canonical for now.

2. **i18n locales:** "Keep all languages" → Do not drop de/es/fr/ja.

3. **21 webhook integrations:** "Yes of course — use a generic webhook router
   instead" → Consolidate to a generic webhook router in a future session.

4. **Improvement loop Phases 3–6:** "Be careful here, needs big investigation
   first" → Do NOT cut the improvement loop. Investigate before acting.

5. **Target user:** "5 / 10" (ambiguous — may mean still deciding).

6. **Extensions vs plugins:** "Please deep-dive in it first before merging" →
   Do NOT merge yet. Investigate first.

7. **Jaeger + Langfuse:** "I am not using any of those two" → They can be
   dropped/consolidated in a future session (F2 recommendation).

8. **Sentry webhook:** "Configure a Sentry webhook signing secret" → This was
   already done in the P1 fixes (Sentry webhook hardening).

---

## 5. YOUR TASK (this session)

### Step 1: Fix the integration test (Bug 1 + Bug 2)

**Bug 1 (FK constraint):** The background task `_execute_graph_async` in
`graph_service.py` is fired via `asyncio.create_task()` with a new session that
can't see uncommitted data. Fix the test so the background task's session can
see the execution row. Options:
- Make `create_graph_execution` commit before firing the background task
  (simplest — `graph_service.py` line ~248-253). This changes production
  behavior slightly but is actually more correct: the execution should be
  persisted before the background task starts.
- OR have the test await the background task before asserting.

**Bug 2 (ModelRouter.route_request):** Find where `GraphInterpreter` in
`graph_executor.py` calls `route_request()` and fix the argument passing. The
signature is `route_request(self, messages: list, ...)` — check if the interpreter
is calling it without the `messages` positional arg or with a wrong kwarg name.

Key files:
- `backend/tests/test_classify_route_workflow.py` — the test
- `backend/app/services/graph_service.py` — `create_graph_execution` (line ~230)
  and `_execute_graph_async` (line ~430)
- `backend/app/services/graph_executor.py` — `GraphInterpreter` class, find the
  `route_request` call
- `backend/app/services/model_router.py` — `ModelRouter.route_request` signature
  (line ~427)
- `backend/app/services/llm_router.py` — second `ModelRouter` class (check which
  one is imported by `graph_executor.py`)

### Step 2: Verify the test passes

```bash
docker compose exec -T backend python -m pytest tests/test_classify_route_workflow.py -v --timeout=30
```

All 4 tests must pass.

### Step 3: Run the broader test suite to check for regressions

```bash
docker compose exec -T backend python -m pytest app/tests/ tests/ -v --timeout=60 -x -q 2>&1 | tail -30
```

If anything breaks that wasn't broken before, fix it. If pre-existing failures
are found, note them in the handoff but don't fix them (scope control).

### Step 4: Check lint and types

```bash
docker compose exec -T backend ruff check app/services/graph_service.py app/services/graph_executor.py tests/test_classify_route_workflow.py
docker compose exec -T backend mypy app/services/graph_service.py app/services/graph_executor.py --ignore-missing-imports
```

### Step 5: Write exit audit

Write to `docs/EXIT-AUDIT-2026-07-04.md` following the format in
`SESSION-RITUAL.md`. Include:
- What changed (one bullet per file)
- Tests run + result (paste output, don't paraphrase)
- git status
- What's next

---

## 6. STOP RULES

1. **DO NOT** rewrite the old executors or migrate to the substrate in this
   session. That's a separate L-effort task.
2. **DO NOT** touch the dual-write / Blueprint+Run system. Glenn said it was
   started too early.
3. **DO NOT** cut the improvement loop. It needs investigation first.
4. **DO NOT** merge extensions and plugins. Deep-dive first.
5. **DO NOT** write meta-handoff documents instead of code. Implement, don't
   philosophize. If the output is only .md files with no code changes, that's
   a failed session.
6. **DO NOT** auto-commit. Write code, run tests, and report. Glenn reviews →
   Hermes verifies → commits.
7. **DO NOT** edit files on the VPS.
8. **DO NOT** push to git. Glenn will commit and push after review.
9. If you find something you believe is a genuine security vulnerability, flag
   it prominently at the top of the exit audit.

---

## 7. CONSTRAINTS

1. **Self-hosted LLM only.** The primary is llama.cpp on 2x RTX 5060 Ti. Never
   recommend OpenAI/Google/Anthropic/DeepSeek as the LLM provider.
2. **1-person team.** Recommendations must be achievable by one developer.
3. **No deploy without human review.** Glenn deploys himself.
4. **27B model ceiling.** Agent protocols with more than 3 phases confuse the
   model. Keep changes within this constraint.
5. **Async-first.** All DB calls must use `AsyncSession`. No sync DB calls in
   service code.
6. **No `db.commit()` inside sub-modules that don't own the transaction.**
   Only the top-level route handler commits. Sub-modules do `db.add()` /
   `db.flush()` and let the parent commit. EXCEPTION: `_execute_graph_async`
   is a background task with its own session — it MUST commit (it already does).
7. **Backward compatible.** Don't break existing v1 API contracts. The v1
   routes carry deprecation headers but are supported forever.

---

## 8. KEY FILES

- `backend/tests/test_classify_route_workflow.py` — the failing test
- `backend/app/services/graph_service.py` — graph CRUD + background execution
- `backend/app/services/graph_executor.py` — old `GraphInterpreter` executor
- `backend/app/services/model_router.py` — `ModelRouter.route_request()`
- `backend/app/services/llm_router.py` — second `ModelRouter` (check imports)
- `backend/app/api/v1/graph.py` — v1 graph API router (uses graph_service)
- `backend/app/services/substrate/strategies/graph.py` — substrate GraphStrategy
- `backend/app/services/substrate/executor.py` — UnifiedExecutor (the new path)
- `backend/app/database.py` — `AsyncSessionLocal`, engine setup
- `backend/AGENTS.md` — backend contract (Docker, testing, deploy)
- `backend/app/services/AGENTS.md` — services layer contract (all clusters)
- `docs/DEEP-DIVE-REPORT-2026-07-03.md` — the full report
- `SESSION-RITUAL.md` — exit audit process

---

## 9. VERIFY BEFORE COMMITTING

Before claiming any fix works, paste the actual command output. Do not
paraphrase or summarize test results. "Tests pass" without the output is a
failed audit. "I fixed it" without running the test is a failed audit.

The backend Docker container is already running. Use:
```bash
docker compose exec -T backend <command>
```

All code changes are in `/opt/flowmanner/backend/`. The working tree is clean
(verified at session start). Nothing was lost in the crash.

---

## SUMMARY

1. Fix Bug 1 (FK constraint) in `graph_service.py` so the background task can
   see the committed execution row.
2. Fix Bug 2 (ModelRouter.route_request missing `messages`) in
   `graph_executor.py` so the old GraphInterpreter calls route_request correctly.
3. Make all 4 tests in `test_classify_route_workflow.py` pass.
4. Check for regressions, lint, types.
5. Write exit audit.
6. Do NOT commit. Report for Glenn to review.
