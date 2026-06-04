# FlowManner Roadmap — V1 Production to V2 Memory/HITL

**Author:** Hermes (synthesis of DeepSeek architectural analysis + OMEGA-H1/H2 audits + system state)
**Date:** 2026-06-01
**Purpose:** Concrete, executable plan for Glenn + DeepSeek. Every task is sized for 1-2 hours of focused work. Every phase has a "stop and verify" gate.
**Source material:**
- `/opt/flowmanner/Docs/FLOWMANNER_ARCHITECTURAL_ANALYSIS.md` (DeepSeek's V3 vision)
- `/opt/flowmanner/Docs/OMEGA-H1-COMPLETION-ASSESSMENT.md` (H1 status)
- `/opt/flowmanner/Docs/OMEGA-H2-READINESS-AUDIT.md` (H2 status)
- `/opt/flowmanner/Docs/FLOWMANNER-CANONICAL-KNOWLEDGE.md` (current state)
- `/opt/flowmanner/Docs/flowmanner-compressed-knowledge.md` (operational reference)

---

## Sequencing Principle

> **Fix what blocks > Test what exists > Build what's missing.**

Don't build V3 (federation, DSL, Neo4j). Most of V3 is already done as the **substrate module** (`/opt/flowmanner/backend/app/substrate/`). The gap is **verification + tests + finishing**, not more code.

---

## PHASE 1 — Unblock H1 Exit Gate
**Goal:** Ship what's already built. Close the 1 critical bug that blocks H1.
**Duration:** 0.5 week (≈15 hours, single focused push)
**Why first:** Everything else is blocked on a production-grade foundation. 31% of pages are broken. A single frontend auth bug causes infinite client-side retry loops.

### P1.1 — Fix `/api/auth/session` 401 infinite loop ✅ DONE (2026-06-01)
**Files:**
- `src/app/api/auth/[...nextauth]/route.ts` (canonical, no custom 401)
- `src/auth.ts` (JWT strategy, session callback returns null for unauth)
- `src/middleware.ts` (matcher excludes `/api/`)
- `e2e/auth-session-no-loop.spec.ts` (new regression test)

**Verification (2026-06-01):**
- Production: `GET https://flowmanner.com/api/auth/session` → 200 + null ✓
- E2E B.1: `GET /api/auth/session` returns 200 + "null" ✓
- E2E B.2: Homepage load produces zero 401 responses ✓
- E2E B.3: 14 calls to /api/auth/session per page load (FAIL, see P1.1b) ⚠️
- Regression: 32 pre-existing test failures, all unrelated to this change (test setup / react-flow / session mocks)

**H1 exit gate: MET at HTTP level.** 401 infinite loop is fixed. Polling concern deferred (see P1.1b).

### P1.1b — Reduce session polling from 14→≤2 calls per page load (POLISH)
**Status:** DEFERRED to P5. Not blocking H1. Likely 30-60 min fix.
**File:** `src/lib/get-auth-token.ts` (already has 30s in-memory cache + in-flight dedup, but something is bypassing it)
**Likely cause:** Server-side `auth()` calls in RSC, or per-component `useSession()` mounts bypassing the cache
**Proposed fix:** Route all session reads through `getAuthToken()` (which has the cache) or refactor to single-session-source pattern

### P1.2 — Diagnose 6 broken pages
**Per DeepSeek audit:** Models, Templates, Analytics, Blog, Profile, Admin fail to render.

- [ ] **For each of the 6 pages, capture the error** — load page in browser with DevTools open, copy first console error and network 500 response
- [ ] **Grep for missing imports/types** in the touched files (per memory: this is the typical root cause after refactors)
- [ ] **Batch the fixes** — fix all 6 in one pass, do not iterate
- [ ] **Build + deploy once** — `bash /opt/flowmanner/deploy-frontend.sh` (use `timeout=300`)
- [ ] **Verify all 19 pages** — load each one in browser, screenshot, no 500s
- [ ] **Definition of done:** All 19 pages render in browser with no 500/401 infinite loops. QA health score improves from 56.8/100 to ≥75/100

### P1.3 — Remove `fm_tokens` references (cleanup)
**Per OMEGA-H1.2:** The dual-auth is unified; remaining refs are 3 (2 in `.bak` files, 1 in test comment).

- [ ] **Delete `.bak` files** that contain `fm_tokens` — `find /home/glenn/FlowmannerV2-frontend/ -name "*.bak" -exec grep -l "fm_tokens" {} \; | xargs rm`
- [ ] **Update test comment** to not reference the removed key
- [ ] **Definition of done:** `grep -r "fm_tokens" /home/glenn/FlowmannerV2-frontend/ /opt/flowmanner/backend/` returns zero hits

### 🚦 P1 STOP GATE
**Do not proceed to P2 until:**
- [ ] All 19 pages render without 500/401
- [ ] `flowmanner.com` homepage loads cleanly in browser
- [ ] QA health score ≥75/100
- [ ] No idle retries in browser DevTools

**Verification command:** Manually load each of the 19 pages and confirm. Screenshot each. Then proceed.

---

## PHASE 2 — Test the Substrate
**Goal:** The substrate module is 80% built but has ZERO tests. Add the test suite that proves it works.
**Duration:** 2 weeks
**Why second:** Untested code is a liability. Every other phase depends on the substrate being reliable.

### P2.1 — Substrate event log tests
**File:** `/opt/flowmanner/backend/tests/test_substrate_event_log.py` (create)

- [ ] **Test append-only enforcement** — call `event_log.append()`, then attempt `UPDATE` and `DELETE` via raw SQL, expect DB error from trigger
- [ ] **Test SERIALIZABLE isolation** — concurrent appends from 2 threads, verify no sequence_num collisions
- [ ] **Test payload size limits** — append 1MB payload, 10MB payload, verify behavior matches spec
- [ ] **Test causal_parent linking** — append event with parent_id, verify query by parent returns children in order
- [ ] **Definition of done:** `pytest tests/test_substrate_event_log.py -v` passes, ≥10 test cases

### P2.2 — Replay engine tests
**File:** `/opt/flowmanner/backend/tests/test_substrate_replay.py` (create)

- [ ] **Test deterministic replay** — record a 10-event mission, replay with same model+seed, verify identical RunState
- [ ] **Test replay from checkpoint** — replay from event 5, verify state matches full replay from event 0
- [ ] **Test replay with different model** — verify state differs predictably when model changes mid-replay
- [ ] **Definition of done:** `pytest tests/test_substrate_replay.py -v` passes, ≥5 test cases

### P2.3 — Executor V2 tests
**File:** `/opt/flowmanner/backend/tests/test_substrate_executor_v2.py` (create)

- [ ] **Test mission state transitions** — CREATED → PLANNING → DECOMPOSED → IN_PROGRESS → COMPLETED, verify each emits correct event
- [ ] **Test crash recovery** — start mission, kill worker mid-execution, restart, verify `_resume_run()` picks up from last event
- [ ] **Test CIRCUIT_BROKEN state** — exceed max_cost, verify state transitions to CIRCUIT_BROKEN
- [ ] **Test all 7 strategies** — solo, dag, swarm, pipeline, graph, langgraph, meta — each gets a smoke test
- [ ] **Definition of done:** `pytest tests/test_substrate_executor_v2.py -v` passes, ≥15 test cases

### P2.4 — Chaos test (THE H2 EXIT CRITERION)
**File:** `/opt/flowmanner/backend/tests/chaos/test_kill_worker_mid_mission.py` (create)

- [ ] **Setup** — start a long-running mission (100 nodes) in a worker
- [ ] **Kill the worker** — `docker kill celery-worker --signal=SIGKILL` at event 50
- [ ] **Verify** — restart worker, mission resumes from event 50, completes successfully, event log is continuous
- [ ] **Definition of done:** Test passes locally. H2 exit criterion `test_kill_worker_mid_mission passes locally` is met

### P2.5 — Capability lattice tests
**File:** `/opt/flowmanner/backend/tests/test_capability_lattice.py` (create)

- [ ] **Test max_depth enforcement** — try to compose depth-4 loop, expect rejection
- [ ] **Test string-based exit rejection** — try loop with `if x == "done"`, expect rejection
- [ ] **Test 3 acceptable termination types** — explicit max_iterations, typed field match, strict subtype — all pass
- [ ] **Definition of done:** `pytest tests/test_capability_lattice.py -v` passes, ≥8 test cases

### P2.6 — Error class budget tests
**File:** `/opt/flowmanner/backend/tests/test_failure_analyzer.py` (create or extend)

- [ ] **Test `can_retry` for each of 9 error classes** — TIMEOUT, VALIDATION, RESOURCE, LOGIC, NETWORK, PERMISSION, NOT_FOUND, RATE_LIMIT, UNKNOWN
- [ ] **Test wall-clock budget exhaustion** — start retry loop, exceed `max_wall_clock_seconds`, expect stop
- [ ] **Test cost budget exhaustion** — accumulate costs, exceed `max_cost_usd`, expect stop
- [ ] **Definition of done:** All 9 error classes have passing budget tests

### 🚦 P2 STOP GATE
**Do not proceed to P3 until:**
- [ ] All substrate tests pass: `pytest tests/test_substrate* -v` shows green
- [ ] Chaos test passes: `pytest tests/chaos/ -v` shows green
- [ ] Test coverage on substrate module: ≥70% (`pytest --cov=app.substrate`)
- [ ] CI runs the test suite on every push (GitHub Actions or similar — see P2.7)

### P2.7 — CI pipeline
**File:** `/opt/flowmanner/.github/workflows/test.yml` (create)

- [ ] **Backend tests on push** — run `pytest tests/` on every push to main
- [ ] **Frontend tests on push** — run `npm test` on every push to main
- [ ] **Substrate tests block merge** — PR cannot merge if substrate tests fail
- [ ] **Definition of done:** Pushing a failing test to main blocks the merge in GitHub UI

---

## PHASE 3 — Wire & Harden the Substrate
**Goal:** Close the remaining H2 gaps: DB trigger migration, orchestrator budget wiring, sub-second trigger dispatch.
**Duration:** 1.5 weeks
**Why third:** Now that tests exist, finish the substrate work. After this, H2 is "shipped."

### P3.1 — DB trigger migration for append-only
**File:** `/opt/flowmanner/backend/alembic/versions/XXXX_substrate_append_only.py` (create)

- [ ] **Verify the claim** — read `event_log.py:10` comment, confirm `BEFORE UPDATE OR DELETE` trigger is supposed to exist
- [ ] **Check if migration exists** — `grep -r "BEFORE UPDATE OR DELETE" /opt/flowmanner/backend/alembic/`
- [ ] **Create the migration** if missing:
  ```sql
  CREATE TRIGGER substrate_events_append_only
  BEFORE UPDATE OR DELETE ON substrate_events
  FOR EACH ROW EXECUTE FUNCTION reject_modification();
  ```
- [ ] **Test on staging** — `alembic upgrade head`, attempt UPDATE, expect error
- [ ] **Apply to production** — `alembic upgrade head` against homelab PG
- [ ] **Definition of done:** `UPDATE substrate_events SET ...` raises DB error. Trigger is in PG catalog.

### P3.2 — Wire MetaLoopOrchestrator → failure_analyzer budgets
**File:** `/opt/flowmanner/backend/app/orchestration/meta_loop_orchestrator.py`

- [ ] **Find retry loop** — locate the `while attempts < max_attempts:` (or similar) in MetaLoopOrchestrator
- [ ] **Add budget check** — before each retry, call `failure_analyzer.can_retry(error_class, mission_id)` and `failure_analyzer.check_budget(mission_id, cost_increment, duration_increment)`
- [ ] **Wire CIRCUIT_BROKEN state** — when budget exhausted, set mission state to CIRCUIT_BROKEN
- [ ] **Test** — extend P2.6 tests to verify orchestrator actually consults budgets (mock `can_retry` and assert call)
- [ ] **Definition of done:** Orchestrator calls budget checks. Tests verify the calls happen. P2.6 tests still pass.

### P3.3 — Replace 2s polling with PG LISTEN/NOTIFY
**File:** `/opt/flowmanner/backend/app/scheduler/trigger_bridge.py`

- [ ] **Current state** — 2-second polling loop reads triggers table
- [ ] **Replace with** — `psycopg` async connection that issues `LISTEN trigger_inserted`
- [ ] **Publish on insert** — add trigger or application-level NOTIFY on INSERT to `triggers` table
- [ ] **Test latency** — insert a trigger with `scheduled_at = NOW() + 0.5s`, verify it fires within 1.0s
- [ ] **Feature flag** — keep polling as fallback, gate LISTEN/NOTIFY behind `FLOWMANNER_LISTEN_NOTIFY=enabled`
- [ ] **Definition of done:** Trigger fires within 1s of scheduled time in test. Polling fallback works if LISTEN/NOTIFY disabled.

### 🚦 P3 STOP GATE
**Do not proceed to P4 until:**
- [ ] DB trigger migration applied to homelab PG
- [ ] MetaLoopOrchestrator tests verify budget calls happen
- [ ] Trigger fires within 1s in benchmark test
- [ ] All P2 tests still pass
- [ ] H2 readiness audit is GREEN on all 4 items (H2.1, H2.2, H2.3, H2.4)

---

## PHASE 4 — Observability That Works
**Goal:** SLOs defined. Now make them actionable. Real alerts, real dashboards.
**Duration:** 1 week
**Why fourth:** A production-grade system has to page you when it breaks.

### P4.1 — ntfy integration
**File:** `/opt/flowmanner/backend/app/observability/alerting.py`

- [ ] **Read current alerting.py** — confirm PagerDuty is supported, ntfy is missing
- [ ] **Add ntfy notifier class** — POST to `https://ntfy.sh/flowmanner-alerts` (or self-hosted ntfy if you have one)
- [ ] **Test channels** — accept `NOTIFY_CHANNELS=ntfy,pagerduty,email` env var
- [ ] **Wire to SLOs** — when SLO budget burn rate exceeds threshold, send to configured channels
- [ ] **Definition of done:** Triggering a test SLO breach sends a real notification to ntfy topic

### P4.2 — Langfuse dashboards live
**Per OMEGA-H1.5:** Dashboards are "unclear if deployed"

- [ ] **Verify Langfuse is reachable** — `curl -i http://10.0.4.x:3000/api/public/health` (whatever the Langfuse endpoint is)
- [ ] **List existing dashboards** — read Langfuse config or doc, find the dashboard definitions
- [ ] **Confirm 4 SLO dashboards exist** — p99 SSE, mission success rate, fallback rate, deploy success rate
- [ ] **Document URL** — save Langfuse dashboard URL to `/opt/flowmanner/Docs/OBSERVABILITY.md`
- [ ] **Definition of done:** Glenn can open a browser, see real metrics from the last 24h

### P4.3 — Backup cron jobs
**Per W4:** Only `langfuse-backup.sh` exists. Missing: PG, Qdrant, RabbitMQ, configs.

- [ ] **PG backup** — `pg_dump` to `/opt/flowmanner/backups/postgres/YYYY-MM-DD.sql.gz`, retain 7 daily + 4 weekly
- [ ] **Qdrant backup** — snapshot API call, retain 7 daily
- [ ] **RabbitMQ backup** — definitions export + persistent volume snapshot, retain 7 daily
- [ ] **Config backup** — tar of `/opt/flowmanner/.env`, `/opt/flowmanner/docker-compose.yml`, retain 30 daily
- [ ] **Schedule** — daily 03:00 UTC, via `crontab -e` or systemd timer
- [ ] **Test restore** — once per month, restore to staging, verify
- [ ] **Definition of done:** `ls -lh /opt/flowmanner/backups/` shows files from the last 7 days. `pg_restore --list` works on a recent dump.

### 🚦 P4 STOP GATE
**Do not proceed to P5 until:**
- [ ] ntfy notification received on test SLO breach
- [ ] Langfuse dashboard URL documented and accessible
- [ ] Backup cron running, recent backups exist, restore test passed

---

## PHASE 5 — V1 Polish
**Goal:** Clean up the operational debt that has accumulated.
**Duration:** 1 week
**Why fifth:** Once the foundation is solid, the cleanup is cheap and high-leverage.

### P5.1 — Audit 14 idle Docker services
**Per W7:** 50GB+ of pulled images never started.

- [ ] **List** — `docker images --format "{{.Repository}}:{{.Tag}} {{.Size}}" | sort -k2 -h` on homelab
- [ ] **Categorize** — for each image, decide: KEEP (used in any compose), REMOVE (orphan), or ACTIVATE (planned use within 4 weeks)
- [ ] **Remove orphans** — `docker rmi <orphan_images>`
- [ ] **Activate planned** — for images you're committed to using in next 4 weeks, add to `docker-compose.yml` with health checks
- [ ] **Definition of done:** `docker images` shows only images that are either running or planned for use in next 4 weeks. Disk freed: ~30GB.

### P5.2 — Fix nginx-static unhealthy
**Per W9:** Container running but health check failing.

- [ ] **Read healthcheck** — `docker inspect workflows-static | jq '.[0].State.Health'`
- [ ] **Diagnose** — most common: wrong path, wrong port, missing file
- [ ] **Fix** — correct the healthcheck command in `docker-compose.yml`
- [ ] **Verify** — `docker compose ps` shows `(healthy)` for nginx-static
- [ ] **Definition of done:** `docker compose ps` shows all services `(healthy)` or `(running)` with no `(unhealthy)`

### P5.3 — Kill 3,000+ failed systemd units on ops machine
**Per W8:** Qt platform plugin crashes in restart loop.

- [ ] **Identify culprit** — `journalctl -p err -b | head -50` on ops machine (172.16.1.2)
- [ ] **Stop the unit** — `systemctl stop <culprit> && systemctl disable <culprit>`
- [ ] **Mask if persistent** — `systemctl mask <culprit>` to prevent restart
- [ ] **Definition of done:** `systemctl list-units --state=failed` shows ≤5 failures (the normal noise level)

### P5.4 — fail2ban on homelab
**Per W6:** SSH open to brute force.

- [ ] **Install** — `pacman -S fail2ban` (Arch) or `apt install fail2ban` (Debian)
- [ ] **Configure** — `/etc/fail2ban/jail.local` with `[sshd] enabled = true, maxretry = 3, bantime = 3600`
- [ ] **Enable** — `systemctl enable --now fail2ban`
- [ ] **Test** — fail SSH 4 times, verify ban
- [ ] **Definition of done:** `fail2ban-client status sshd` shows jail active, banned IPs

### 🚦 P5 STOP GATE
**V1 PRODUCTION-GRADE IS COMPLETE when:**
- [ ] All P1-P5 tasks complete
- [ ] All tests pass
- [ ] H1 + H2 exit criteria met
- [ ] QA health score ≥85/100
- [ ] No critical or high weaknesses from DeepSeek audit remain open (W1-W4, W6 closed)
- [ ] Glenn can run a real mission end-to-end (browser agent, code reviewer, or similar) and see it logged in Jaeger + Langfuse

---

## PHASE 6 — V2: Memory + HITL + Cost Attribution
**Goal:** Build the architectural gaps that DeepSeek's V3 vision correctly identified as missing.
**Duration:** 4-6 weeks
**Why deferred:** Building on untested substrate is wasted work. Now substrate is tested and shipped, the V2 features have a solid foundation.

### P6.1 — Episodic memory consolidation worker
**File:** `/opt/flowmanner/backend/app/memory/consolidation_worker.py` (create)

- [ ] **Subscribe to mission.completed events** — listen on RabbitMQ
- [ ] **Extract episodes** — from event log, pull (context, action, outcome) tuples
- [ ] **Summarize** — call DeepSeek API to summarize each episode
- [ ] **Embed** — Qdrant `embed` on summary
- [ ] **Store** — Qdrant collection `mission_episodes` with metadata: mission_id, agent_id, success, tags
- [ ] **Forget policy** — episodes older than 90 days get archived to cold storage (S3-compatible or local)
- [ ] **Test** — run 10 missions, verify 10 episodes indexed, verify retrieval by similarity works
- [ ] **Definition of done:** Agent context assembly pulls relevant past episodes for the mission type. Memory isn't just RAG — it's retrieval + consolidation + forgetting.

### P6.2 — Human-in-the-loop primitives
**File:** `/opt/flowmanner/backend/app/orchestration/human_interrupt.py` (create)

- [ ] **Define HumanInterrupt exception class** — with `interrupt_type: Literal["approval", "clarification", "escalation"]`, `context`, `proposed_action`, `confidence`, `deadline`
- [ ] **Wire to mission executor** — when tool call matches `approval_required_for` list, raise HumanInterrupt
- [ ] **Persist to Inbox model** — `HumanInterrupt` records saved as `inbox_items` table rows
- [ ] **WebSocket push** — emit `HUMAN_INTERRUPT_RAISED` event, frontend Inbox component renders
- [ ] **Frontend Inbox UI** — `/home/glenn/FlowmannerV2-frontend/src/app/[locale]/(app)/inbox/` — list pending interrupts, Approve/Deny buttons
- [ ] **Test** — run mission with `approval_required_for: ["github.merge_pr"]`, verify the agent pauses at that step, UI shows pending interrupt, approve → mission resumes
- [ ] **Definition of done:** One agent with HITL works end-to-end. Approval gates are visible in the UI.

### P6.3 — Cost attribution engine
**File:** `/opt/flowmanner/backend/app/observability/cost_engine.py` (create)

- [ ] **Tag every LLM event** — extend substrate event payload with `cost: {provider, model, input_tokens, output_tokens, cost_usd, agent_id, mission_id, user_id, workspace_id}`
- [ ] **Compute on event write** — `cost_engine.compute(event) → cost` uses provider pricing tables
- [ ] **Aggregate queries** — by agent, by mission, by user, by workspace, by time period
- [ ] **Dashboard** — Langfuse or custom frontend: cost per agent, cost per workspace, cost per day
- [ ] **Test** — run 5 missions, verify cost totals match expected (DeepSeek API pricing)
- [ ] **Definition of done:** Can answer "How much did the Code Review Agent cost this month?" in one query.

### P6.4 — Circuit breaker wiring
**File:** `/opt/flowmanner/backend/app/orchestration/circuit_breaker.py` (create or extend)

- [ ] **Per-mission limits** — `max_llm_calls=100`, `max_cost_usd=5.00`, `max_duration_seconds=600`
- [ ] **Per-agent limits** — `max_tool_calls=50`
- [ ] **Destructive action policy** — `destructive_actions_require_approval=True` (DELETE, DROP, etc.)
- [ ] **Wire to executor** — check breakers before each tool call
- [ ] **Test** — set `max_cost_usd=0.01`, run mission, verify it stops and transitions to CIRCUIT_BROKEN
- [ ] **Definition of done:** Runaway agent is impossible. Mission either completes, fails cleanly, or hits a circuit breaker.

### 🚦 P6 STOP GATE
**V2 IS COMPLETE when:**
- [ ] Episodic memory works (past missions inform future ones)
- [ ] HITL works (one agent has approval gates, UI is usable)
- [ ] Cost attribution works (per-agent billing queryable)
- [ ] Circuit breakers work (no runaway agents possible)
- [ ] All P1-P5 tests still pass

---

## DEFERRED (V3+ / Never)

These are DeepSeek's V3 vision items that we are **explicitly NOT building**:

- ❌ **Federation protocol** (4 weeks) — YAGNI. No marketplace revenue, no multi-instance need.
- ❌ **Neo4j graph DB** — Postgres + Qdrant suffice. Don't add infra.
- ❌ **YAML agent DSL** — Python is fine. DSL pays off at 5+ external publishers.
- ❌ **Procedural memory** — agent capability registry works as-is.
- ❌ **Multi-modal agent input pipeline** — text-only is fine for V1. Reassess post-PMF.
- ❌ **Agent-to-human rich output** (charts, widgets) — chat interface is fine for V1.

**Revisit these in 2027 if you have 5+ paying users and 5+ external agent publishers.**

---

## DEEP SEEK TASK ASSIGNMENT TEMPLATE

When delegating to DeepSeek, use this template:

```
TASK: [Phase].[Task] — [One-line description]
PHASE: [P1-P6]
FILE(S): [absolute paths]
CONTEXT: [relevant prior work, what exists, what doesn't]
CONSTRAINTS:
  - Do not break existing tests
  - Do not pull in new dependencies without asking
  - Match existing code style in [reference file]
EXIT CRITERIA: [How to verify done — specific command or check]
RESPOND IN ENGLISH.
```

**Example:**

```
TASK: P1.1 — Verify /api/auth/session 401 fix is in place
PHASE: P1
FILE(S):
  - /home/glenn/FlowmannerV2-frontend/src/app/api/auth/session/route.ts (should not exist)
  - /home/glenn/FlowmannerV2-frontend/src/app/api/auth/[...nextauth]/route.ts (canonical)
CONTEXT: A previous fix (2026-05-23) deleted the shadowed session route. We need to verify this is still in place and the canonical route returns 200 for unauth.
CONSTRAINTS:
  - Do not modify any auth code unless tests fail
  - Do not change NextAuth configuration
EXIT CRITERIA:
  - `ls /home/glenn/FlowmannerV2-frontend/src/app/api/auth/session/` returns "No such file or directory"
  - `curl -i http://10.99.0.3:8000/api/auth/session` returns 200 with `null` body
  - New playwright test passes
RESPOND IN ENGLISH.
```

---

## CRITICAL RULES (for the entire roadmap)

1. **NO code without tests** — every backend change ships with a test (per memory: deploy bugfix pattern)
2. **NO deploys without verification** — always `docker compose ps` first, never retry blindly
3. **NO new dependencies without asking** — prefer stdlib + existing libs
4. **NO mid-architecture pivots** — stay on the phase you're in
5. **BATCH fixes** — when multiple bugs surface, fix all, build once (per memory: backend deploy bugfix pattern)
6. **DEEP SEEK executes, you and I decide** — don't ask DeepSeek what to build
7. **EACH phase has a STOP GATE** — do not skip verification before moving on
8. **CHMOD 644 new .py files** — `write_file` creates chmod 600, fix before `docker build`

---

## EFFORT ESTIMATE (realistic)

| Phase | Duration | Cumulative |
|-------|----------|------------|
| P1 | 0.5 week | 0.5 week |
| P2 | 2 weeks | 2.5 weeks |
| P3 | 1.5 weeks | 4 weeks |
| P4 | 1 week | 5 weeks |
| P5 | 1 week | 6 weeks |
| P6 | 4-6 weeks | 10-12 weeks |
| **V1** | **6 weeks** | — |
| **V2** | **+4-6 weeks** | — |
| **V3** | **2027 problem** | — |

**DeepSeek estimated 15 weeks to V3 MVP. We estimate 10-12 weeks to V2, and V3 deferred to 2027.** The difference: DeepSeek was planning from a blank slate. We have 80% of the code already. The remaining work is verification and finishing.

---

## NEXT STEP

Run P1.1 today. Fix the auth/session bug. Unblock H1. Then run P1.2 (the 6 broken pages) in the same push. You'll have V1's foundation in 15 hours of focused work.

When delegating to DeepSeek, start with P1.1 using the template above. Report back when done.
