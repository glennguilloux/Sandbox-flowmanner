# DeepSeek Execution Prompt — Q3/Q4 2026 Phases

**Date:** 2026-07-04
**Companion to:** `docs/EXECUTION-PLAN-Q3-Q4-2026.md`
**Purpose:** Self-contained prompt for DeepSeek (or any coding agent) to execute each phase of the remaining roadmap.

---

## CRITICAL RULES (read before starting ANY phase)

1. **DO NOT write meta-docs, handoff docs, or planning docs. IMPLEMENT CODE.**
   - If `git diff --name-only` shows only `.md` files after your work, you have FAILED.
   - The only `.md` file you may create is the exit-audit at the very end of a phase.

2. **Verify against the actual filesystem, not prior docs.**
   - Prior phase docs (`PHASE-1A`, `PHASE-1B`, `PHASE-2`, `EXIT-AUDIT-2026-07-04-phase4-pruning`) describe work that was planned — much of it is ALREADY DONE. Read `docs/EXECUTION-PLAN-Q3-Q4-2026.md` §0 for what's actually left.
   - Before starting a task, `ls` the files you plan to edit. If a file is already GONE, skip that task.

3. **Run tests after every change.** Paste the test output in your response.
   - Backend: `cd /opt/flowmanner/backend && python -m pytest <path> -v`
   - Frontend: `cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit && npx vitest run`

4. **Commit per task.** Show `git log --oneline -3` after each commit.
   - Commit message format: `refactor(phase): <description>`
   - Do NOT commit `.env` files or secrets.

5. **Do NOT pull in new dependencies without asking.** Use stdlib + existing packages only.

6. **Match the project's existing code style.** Read a neighboring file before editing.
   - Backend: async-first, SQLAlchemy 2.0, structlog, ruff + mypy
   - Frontend: Next.js 16 App Router, React 19, `apiClient` from `@/lib/api-client.ts`, React Query from `@tanstack/react-query`

7. **Do NOT deploy.** All changes stay on the local working tree. Glenn deploys.

8. **If a test fails, fix the root cause.** Do not skip, mock around, or delete the test.

9. **Do NOT do unrequested batched work.** Only touch the files listed in the task. No drive-by refactors, no reformatting, no renames.

10. **CHMOD 644 new .py files.** `write_file` creates chmod 600. Fix before committing.

---

## PHASE R4 — Codebase Pruning Completion (START HERE, lowest risk)

**Why first:** 1–2 days, pure deletions, finishes Phase 4.

### Task R4a — Delete `domain_agents/`

**Files to delete:**
- `backend/app/services/domain_agents/` (entire directory: `__init__.py`, `base_domain_agent.py`, `biotech/`, `finance/`, `legal/`)

**Steps:**
1. `grep -rn 'domain_agents' backend/app/ --include='*.py' | grep -v __pycache__ | grep -v test`
   - If any non-test file imports domain_agents, remove the import and any code that references it.
   - If `backend/app/api/v1/domain_agents.py` or a router registration exists in `v1/__init__.py`, remove it.
2. `rm -rf backend/app/services/domain_agents/`
3. Remove any domain_agents router from `backend/app/api/v1/__init__.py` (search for `domain_agents` in that file)
4. `cd /opt/flowmanner/backend && ruff check app/api/v1/__init__.py`
5. `cd /opt/flowmanner/backend && python -m pytest app/tests/ -q --tb=short -x`
6. Commit: `refactor(phase4): delete domain_agents/ (447 LOC thin wrappers with unimplemented tools)`

**Verify:**
```bash
ls backend/app/services/domain_agents/ 2>&1  # must say "No such file or directory"
grep -rn 'domain_agents' backend/app/ --include='*.py' | grep -v __pycache__ | grep -v test  # must be 0
git diff --name-only  # must show .py files, not just .md
```

### Task R4b — Delete `marketplace.py`

**Files to delete:**
- `backend/app/api/v1/marketplace.py` (851 LOC)

**Steps:**
1. `grep -rn 'marketplace' backend/app/ --include='*.py' | grep -v __pycache__ | grep -v test`
   - Find the router registration in `v1/__init__.py` and remove it.
   - If any service imports `marketplace_service` or the marketplace router, remove the import.
2. `rm backend/app/api/v1/marketplace.py`
3. Remove the marketplace router import and registration from `backend/app/api/v1/__init__.py`
4. `cd /opt/flowmanner/backend && ruff check app/api/v1/__init__.py`
5. `cd /opt/flowmanner/backend && python -m pytest app/tests/ -q --tb=short -x`
6. Commit: `refactor(phase4): delete marketplace.py (851 LOC, no frontend, no usage)`

**Verify:**
```bash
ls backend/app/api/v1/marketplace.py 2>&1  # must say "No such file"
grep -rn 'marketplace' backend/app/api/ --include='*.py' | grep -v __pycache__ | grep -v test  # must be 0 (or only in __init__.py if it's OPTIONAL tier comment)
git diff --stat  # must show ~850 LOC removed
```

---

## PHASE R3 — Frontend Standardization Completion

**Why second:** 1 week, independent of backend work, mechanical migration.

### Task R3a — Migrate 16 remaining raw `fetch()` calls

**Context:** The frontend is at `/home/glenn/FlowmannerV2-frontend/`. The `apiClient` (`src/lib/api-client.ts`) already handles JWT injection from NextAuth. React Query is already installed (`@tanstack/react-query`). 87 files already use `apiClient`, 16 still use raw `fetch()`.

**Steps:**
1. Find the 16 files:
   ```bash
   cd /home/glenn/FlowmannerV2-frontend
   grep -rl 'fetch(' src/ --include='*.ts' --include='*.tsx' | grep -v node_modules | grep -v api-client.ts | sort
   ```
2. For EACH file:
   a. Read the file to understand what API calls it makes
   b. Replace `fetch('/api/v1/...')` with `apiClient.get/post/put/delete(...)`
   c. If it's a GET query: wrap in `useQuery(['key'], () => apiClient.get(...))`
   d. If it's a mutation (POST/PUT/DELETE): wrap in `useMutation`
   e. Add imports: `import { useQuery, useMutation } from '@tanstack/react-query'` and `import { apiClient } from '@/lib/api-client'`
   f. Remove any manual `Authorization` header injection (apiClient does this)
3. After all 16 are done:
   ```bash
   grep -rl 'fetch(' src/ --include='*.ts' --include='*.tsx' | grep -v node_modules | grep -v api-client.ts | wc -l
   # MUST be 0
   ```
4. Typecheck:
   ```bash
   npx tsc --noEmit 2>&1
   # MUST be 0 errors
   ```
5. Run vitest:
   ```bash
   npx vitest run 2>&1 | tail -10
   ```
6. Commit: `refactor(phase3): migrate 16 raw fetch() calls to apiClient + React Query`

### Task R3b — E2E critical path verification

**Context:** 22 Playwright spec files exist in `e2e/`. Check if they cover the 3 critical paths.

**Steps:**
1. `cd /home/glenn/FlowmannerV2-frontend && grep -rl 'login\|dashboard' e2e/ --include='*.spec.ts' | head -5`
2. `grep -rl 'mission.*create\|create.*mission' e2e/ --include='*.spec.ts' | head -5`
3. `grep -rl 'chat.*tool\|tool.*call' e2e/ --include='*.spec.ts' | head -5`
4. If any of the 3 critical paths are uncovered, write a new spec file:
   - `e2e/critical-login-dashboard.spec.ts` — login → see dashboard with no console errors
   - `e2e/critical-mission-create.spec.ts` — create mission → execute → see results
   - `e2e/critical-chat-tool-calling.spec.ts` — send chat message → see tool call result
5. Run all affected E2E tests:
   ```bash
   npx playwright test e2e/ --reporter=list 2>&1 | tail -30
   ```
6. Fix any broken tests (do NOT skip or .skip() them)
7. Commit: `test(phase3): verify E2E critical path coverage`

**Verify:**
```bash
npx tsc --noEmit 2>&1 | head -3  # 0 errors
grep -rl 'fetch(' src/ | grep -v node_modules | grep -v api-client.ts | wc -l  # 0
npx playwright test e2e/ --reporter=list 2>&1 | tail -5  # all pass
git diff --name-only  # must show .ts/.tsx files
```

---

## PHASE R1 — Strategy Profiling + Plan Scorer Fix

**Why third:** 2–3 days, needs the live 27B model running for R1a. R1b is pure code.

### Task R1b — Fix plan scorer cost model (do this FIRST, no model dependency)

**File:** `backend/app/services/plan_selection/plan_scorer.py`

**Problem:** Line 147 uses `candidate.estimated_cost_usd` — this is a no-op because the local LLM (llama.cpp) is free. The scorer should penalize token count and latency instead.

**Steps:**
1. Read `plan_scorer.py` and `plan_candidate.py` (the model class)
2. In `PlanCandidate` (or wherever the model is defined): add `estimated_tokens: int = 0` and `estimated_latency_ms: int = 0` fields. Keep `estimated_cost_usd` for backward compat but default to 0.
3. In `plan_scorer.py` line ~147: replace the cost penalty:
   ```python
   # OLD:
   cost = candidate.estimated_cost_usd
   # NEW:
   token_penalty = min(candidate.estimated_tokens / 100_000, 1.0) * 0.30
   latency_penalty = min(candidate.estimated_latency_ms / 60_000, 1.0) * 0.20
   cost = token_penalty + latency_penalty
   ```
4. Update `test_plan_scorer.py` to use the new fields
5. `cd /opt/flowmanner/backend && python -m pytest tests/test_plan_scorer.py -v`
6. Commit: `fix(phase1): replace dollar-cost with token/latency cost in plan_scorer`

### Task R1a — Runtime strategy profiling (needs live 27B model)

**Context:** The code analysis in `docs/PHASE-1A-STRATEGY-PROFILING.md` identified likely suitability. Runtime profiling confirms it.

**Steps:**
1. Create `backend/scripts/profile_strategies.py`:
   ```python
   """Profile all 7 strategies with identical prompts against the live 27B model."""
   import asyncio, json, time, httpx

   API_BASE = "http://127.0.0.1:8000/api/v1"
   TEST_PROMPT = "Summarize the following text in 3 bullet points: FlowManner is a self-hosted AI workflow orchestration platform..."
   STRATEGIES = ["solo", "dag", "graph", "pipeline", "meta", "swarm", "langgraph"]

   async def profile_strategy(strategy: str) -> dict:
       # Create a mission with this strategy
       # Execute it
       # Record: success, latency_ms, token_count, llm_judge_score
       ...

   async def main():
       results = {}
       for strategy in STRATEGIES:
           results[strategy] = await profile_strategy(strategy)
       with open("docs/strategy-profiling-results.json", "w") as f:
           json.dump(results, f, indent=2)

   asyncio.run(main())
   ```
2. Run it: `cd /opt/flowmanner/backend && python scripts/profile_strategies.py`
3. Read `docs/strategy-profiling-results.json`
4. For any strategy with success rate <60%:
   - Add `DEPRECATED = True` class attribute to the strategy class
   - Add a comment: `# DEPRECATED: <40% success rate with 27B model per strategy profiling 2026-07-04`
5. For pipeline, meta, swarm: add `STRATEGY_EXPERIMENTAL = True` and gate behind `if not settings.STRATEGY_EXPERIMENTAL: raise ValueError("...")`
6. Commit: `feat(phase1): strategy runtime profiling results + DEPRECATED flags`
7. Commit: `feat(phase1): gate experimental strategies behind STRATEGY_EXPERIMENTAL env var`

**Verify:**
```bash
cd /opt/flowmanner/backend
python -m pytest tests/test_plan_scorer.py -v
cat docs/strategy-profiling-results.json | python -m json.tool | head -30
git diff --name-only  # must show .py files
```

---

## PHASE R2 — Backend Cleanup Completion (3 remaining routers)

**Why fourth:** 1 week. Old executors are already deleted — these routers just need rewiring to the substrate.

### Task R2a — Migrate `swarm_protocol.py` → substrate

**Files:** `backend/app/api/v1/swarm_protocol.py` (338 LOC)

**Steps:**
1. Read `swarm_protocol.py`. Identify which endpoints inline `DebateProtocol`, `EscalationChain`, `HandoffProtocol`.
2. Read `backend/app/services/substrate/strategies/swarm.py` to understand the substrate's SwarmStrategy API.
3. Rewrite each endpoint to call:
   ```python
   from app.services.substrate.executor import get_unified_executor
   from app.services.substrate.adapters import mission_to_workflow
   workflow = mission_to_workflow(mission, tasks)
   result = await get_unified_executor().execute(db, workflow)
   ```
4. If the protocol classes (`DebateProtocol`, etc.) are still needed as configuration shapes, keep them as dataclasses and pass to the strategy.
5. `cd /opt/flowmanner/backend && python -m pytest tests/ -k "swarm" -v`
6. `ruff check app/api/v1/swarm_protocol.py && mypy app/api/v1/swarm_protocol.py`
7. Commit: `refactor(phase2): migrate swarm_protocol.py to substrate SwarmStrategy`

### Task R2b — Migrate `orchestration.py` → substrate

**Files:** `backend/app/api/v1/orchestration.py` (577 LOC)

**Steps:**
1. Read `orchestration.py`. Identify endpoints that inline orchestration logic (the old `meta_loop_orchestrator` is already deleted — find what's still inlined).
2. Rewrite each endpoint to use `get_unified_executor().execute()` with the appropriate `WorkflowType`.
3. `cd /opt/flowmanner/backend && python -m pytest tests/ -k "orchestration" -v`
4. `ruff check app/api/v1/orchestration.py && mypy app/api/v1/orchestration.py`
5. Commit: `refactor(phase2): migrate orchestration.py to substrate executor`

### Task R2c — Migrate `mission_advanced_routes.py` → CQRS

**Files:** `backend/app/api/v1/mission_advanced_routes.py` (567 LOC)

**Steps:**
1. Read `mission_advanced_routes.py`. Identify endpoints: templates, node groups, versions, export/import.
2. Move business logic to `_mission_cqrs/commands.py` (for mutations) or `_mission_cqrs/queries.py` (for reads).
3. Make `mission_advanced_routes.py` a thin DI shell — follow the pattern of `mission.py` (25 refs to `get_mission_commands` / `get_mission_queries`).
4. `cd /opt/flowmanner/backend && python -m pytest tests/ -k "mission_advanced" -v`
5. `ruff check app/api/v1/mission_advanced_routes.py && mypy app/api/v1/mission_advanced_routes.py`
6. Commit: `refactor(phase2): migrate mission_advanced_routes.py to CQRS pattern`

### Task R2d — Dual-write decision doc

**Steps:**
1. Write `docs/DUAL-WRITE-DECISION.md`
2. Options:
   - (a) Mission canonical, Blueprint+Run optional → remove dual-write, keep Blueprint+Run as read model
   - (b) Blueprint+Run canonical → Mission becomes a view
3. Glenn said "DeepSeek started too early." Recommend (a) and explain: the dual-write was premature, Mission is the working production model, removing it reduces complexity without losing the Blueprint/Run read model.
4. This is a RECOMMENDATION doc for Glenn's review — do NOT make code changes based on it.
5. Commit: `docs(phase2): dual-write decision recommendation`

**Verify:**
```bash
cd /opt/flowmanner/backend
python -m pytest tests/ -k "swarm or orchestration or mission_advanced" -v
git diff --name-only  # must show .py files
ruff check app/api/v1/swarm_protocol.py app/api/v1/orchestration.py app/api/v1/mission_advanced_routes.py
```

---

## PHASE R5 — Product Depth Features (GATED on R1 + R3)

**Why fifth:** 2–3 weeks. Depends on knowing which strategies work (R1) and having React Query standardized (R3).

### Task R5a — Workflow Templates Gallery

**Steps:**
1. Check if templates page exists: `ls /home/glenn/FlowmannerV2-frontend/src/app/\[locale\]/\(dashboard\)/templates/ 2>&1`
   - If it exists (may be on `origin/master` at commit `2c89b448`), verify it works: load the page, check for console errors, verify "create from template" works end-to-end.
   - If it doesn't exist, build it:
     - Create `src/app/[locale]/(dashboard)/templates/page.tsx`
     - Grid of template cards: name, description, strategy type, estimated tokens
     - "Create from template" button → `POST /api/v1/missions` with the template's definition
     - Use `useQuery` to fetch templates from `GET /api/v1/templates`
2. Add 5+ seed templates to `seed_templates.py`:
   - "Summarize GitHub Issue"
   - "Research a Topic with RAG"
   - "Monitor Sentry and Create Linear Issue"
   - "Code Review Agent"
   - "Daily Standup Summary"
3. Run `seed_templates.py` to populate the database (if not already seeded)
4. i18n: add keys in all 5 locales (de, en, es, fr, ja) under `templates` namespace
5. `npx tsc --noEmit && npx vitest run`
6. Commit: `feat(phase5): workflow templates gallery + seed data`

### Task R5b — Eval Results Dashboard

**Steps:**
1. Check if eval page exists: `ls /home/glenn/FlowmannerV2-frontend/src/app/\[locale\]/\(dashboard\)/eval/ 2>&1`
2. If not, build it:
   - Create `src/app/[locale]/(dashboard)/eval/page.tsx`
   - Fetch eval run history from `GET /api/v1/evaluation/runs` via `useQuery`
   - Display: run history table (run ID, model, score, date), score trends chart (line chart), model comparison view
   - Use `recharts` for charts (check package.json first; if not installed, ASK before adding)
3. i18n keys in all 5 locales under `eval` namespace
4. `npx tsc --noEmit && npx vitest run`
5. Commit: `feat(phase5): eval results dashboard`

### Task R5c — Mission Timeline

**Steps:**
1. Create `/home/glenn/FlowmannerV2-frontend/src/app/[locale]/(dashboard)/missions/[id]/timeline/page.tsx`
2. Fetch substrate events: `apiClient.get('/api/v1/substrate/events', { params: { mission_id: id } })` via `useQuery`
3. Render interactive vertical timeline:
   - Each event: timestamp, type (color-coded), duration, tokens, cost
   - Click to expand full payload (JSON viewer or formatted)
   - Color codes: green (success), yellow (LLM call), blue (tool call), red (failure), purple (HITL pause), orange (circuit breaker trip)
4. Import a timeline component — check if one exists in the project. If not, use a simple CSS-based vertical list (do NOT add a new dep without asking).
5. i18n keys in all 5 locales under `timeline` namespace
6. `npx tsc --noEmit && npx vitest run`
7. Commit: `feat(phase5): mission timeline UI — substrate event visualization`

**Verify:**
```bash
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit 2>&1 | head -3  # 0 errors
npx vitest run 2>&1 | tail -5
npx playwright test e2e/ --reporter=list 2>&1 | tail -10
git diff --name-only  # must show .tsx files
```

---

## PHASE R6 — Hardening & Performance (parallel to R5)

### Task R6a — DB index audit

**Steps:**
1. Identify the top 20 most-used queries by reading the API endpoints that are hit most:
   - Mission list: `GET /api/v1/missions`
   - Chat threads: `GET /api/v1/chat/threads`
   - Dashboard stats: `GET /api/v1/dashboard`
   - Analytics rollups: `GET /api/v1/analytics`
2. Run `EXPLAIN ANALYZE` on each via:
   ```bash
   docker compose exec backend python -c "
   import asyncio
   from app.core.database import async_engine
   from sqlalchemy import text
   async def main():
       async with async_engine.connect() as conn:
           result = await conn.execute(text('EXPLAIN ANALYZE SELECT * FROM missions WHERE workspace_id = ... LIMIT 20'))
           print(result.fetchall())
   asyncio.run(main())
   "
   ```
3. Identify missing indexes (Seq Scan on large tables = missing index)
4. Create an Alembic migration: `alembic revision -m "add_missing_indexes"`
5. Use `op.execute("CREATE INDEX CONCURRENTLY ...")` for each missing index
6. `cd /opt/flowmanner/backend && alembic upgrade head`
7. Re-run `EXPLAIN ANALYZE` — verify Index Scan instead of Seq Scan
8. Commit: `perf(phase6): add missing DB indexes for top 20 queries`

### Task R6b — CI workflow audit

**Steps:**
1. `ls .github/workflows/`
2. Read each workflow file
3. Actions:
   - If `load-test.yml` doesn't reference `tests/load/*.js` scripts that exist → remove it
   - If `publish-sdk-testpypi.yml` publishes on every push → gate to tags: change `on: [push]` to `on: [push]` with `tags: ['v*']`
   - If `pr-check.yml` duplicates `ci.yml` → merge into `ci.yml` and delete `pr-check.yml`
4. Commit: `chore(phase6): audit CI workflows — remove duplicates, gate SDK publish to tags`

### Task R6c — Per-provider circuit breaker

**File:** `backend/app/services/circuit_breaker_service.py`

**Steps:**
1. Read `circuit_breaker_service.py` — currently per-mission
2. Add a Redis-backed per-provider breaker:
   ```python
   class ProviderCircuitBreaker:
       def __init__(self, redis):
           self.redis = redis
       async def is_tripped(self, provider: str) -> bool:
           return await self.redis.exists(f"breaker:{provider}")
       async def trip(self, provider: str, ttl: int = 300):
           await self.redis.setex(f"breaker:{provider}", ttl, "1")
       async def reset(self, provider: str):
           await self.redis.delete(f"breaker:{provider}")
   ```
3. Wire into `BudgetEnforcer.call()` — check the provider's breaker before making the LLM call
4. Fall back to per-mission breaker if Redis is unavailable (catch `ConnectionError`)
5. Tests: `cd /opt/flowmanner/backend && python -m pytest tests/ -k "circuit_breaker" -v`
6. Commit: `feat(phase6): per-provider Redis-backed circuit breaker`

### Task R6d — Cache hit rate monitoring

**Files:** `backend/app/services/cache/`, `backend/app/core/metrics.py`

**Steps:**
1. Read `core/metrics.py` — find existing Prometheus metrics
2. Add counters:
   ```python
   cache_hits_total = Counter('cache_hits_total', 'Cache hit count', ['cache_name'])
   cache_misses_total = Counter('cache_misses_total', 'Cache miss count', ['cache_name'])
   cache_sets_total = Counter('cache_sets_total', 'Cache set count', ['cache_name'])
   ```
3. Instrument `cache/inprocess.py` — increment counters on get/set/hit/miss
4. Instrument Redis cache usage sites (search for `redis.get` / `redis.set` in the codebase)
5. Verify via `/metrics` endpoint: `curl http://127.0.0.1:8000/metrics | grep cache`
6. Commit: `feat(phase6): cache hit rate Prometheus metrics`

**Verify:**
```bash
cd /opt/flowmanner/backend
python -m pytest tests/ -k "circuit_breaker or cache" -v
ruff check app/services/circuit_breaker_service.py app/core/metrics.py
git diff --name-only  # must show .py files
```

---

## FINAL CHECKLIST (run before claiming a phase is done)

```
□ git diff --name-only    → shows .py and/or .tsx files (NOT only .md)
□ git diff --stat         → shows expected LOC changes
□ ruff check              → 0 errors on touched files
□ mypy (backend)          → 0 errors on touched files
□ npx tsc --noEmit (frontend) → 0 errors
□ pytest / vitest         → all pass (paste output)
□ git log --oneline -3    → shows your commits
□ No new dependencies added without asking
□ No .env files committed
□ CHMOD 644 on new .py files
```

If ANY of these fail, do NOT claim the phase is done. Fix the issue first.

---

## RESPONSE FORMAT

After completing each task, respond with:

```
## Task <ID> — <title>

### What changed:
- <file1>: <one-line description>
- <file2>: <one-line description>

### Tests run + result:
<paste actual test output>

### Git status:
<paste git diff --name-only output>
<paste git log --oneline -3>

### Next task: <task ID>
```

Do NOT write essays. Do NOT write planning docs. Do NOT write meta-commentary. Just code, test output, and git state.
