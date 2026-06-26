# Blueprint+Run Cutover — Phase 3.5

**Status:** Planning (no code yet)
**Created:** 2026-06-25
**Owner:** Glenn (decisions), coding agents (execution, sequenced)
**Supersedes:** §3.5 of `docs/REBUILD-BACKEND.md` (graduated from prose prescription to a sequenced plan)
**Sequence marker:** This plan has 12 phases (A-L), all gated. Do not skip phases or merge them.

---

## 0. Status Assessment (where we are right now)

### What is shipped and live

- ✅ **Phase 10.1 (`phase101_blueprints_runs`) applied.** Tables `blueprints`, `runs`, `blueprint_versions` exist; `substrate_events.blueprint_id` FK in place. Alembic head is `fix_playground_ws_fk_type` (subsequent migration).
- ✅ **CQRS dual-write layer live.** `backend/app/api/_mission_cqrs/commands.py` (1054 lines) writes to BOTH old (`missions`/`mission_tasks`/etc.) and new (`blueprints`/`runs`) on every mission mutation. Five dual-write sites: create (L112), update (L175), soft-delete (L218), execute (L350), abort (L666).
- ✅ **Read-from-new feature flag exists.** `backend/app/api/_mission_cqrs/compat.py` (602 lines) provides `list_missions_from_blueprints`, `get_mission_from_blueprint`, `list_active_from_blueprints`, `active_missions_from_blueprints`, plus `MissionShim` dataclass. Toggled by env `USE_NEW_READS` ∈ {`1`,`true`,`yes`}. Default = FALSE (legacy reads).
- ✅ **v2 API on new tables exists.** `backend/app/api/v2/blueprints.py` with prefix `/blueprints`, tags `blueprints-v2`.

### What is held

- ⛔ **Phase 10.2 (`phase102_compat_views`) gated** by `PHASE10_SOAK_COMPLETE=1`. Creates `missions_compat`, `workflows_compat`, `workflow_executions_compat` views mapping old table names to new tables.
- ⛔ **Phase 10.3 (`phase103_drop_old_tables`) gated** by `PHASE10_SOAK_COMPLETE=1`. Drops 16 old tables. NO DOWNGRADE EXISTS — rollback requires DB backup restore.
- ⛔ **Phase 10.4 (`phase104_retarget_aux_tables`) gated** by `PHASE10_SOAK_COMPLETE=1`. Adds `run_id`/`blueprint_id` FK columns to three aux tables.

### Critical bugs found before cutover can begin

These are the obstacles that BLOCK moving from "code is dual-writing" to "we can safely drop old tables." Each is a fix-before-cutover item.

| # | Bug | File | Impact | Fix strategy |
|---|---|---|---|---|
| **B1** | **`backfill_blueprints_runs.py` is NOT idempotent.** Generates fresh `str(uuid4())` for `Blueprint.id` on every run. Re-runs create duplicate blueprints for every mission. | `backend/scripts/backfill_blueprints_runs.py:99-117` | Running backfill twice doubles Blueprint count. Plus, BP discovers backfilled blueprints can never match to missions again (no shared ID). | Set `Blueprint.id = str(mission.id)` AND set `Blueprint.definition["_source_mission_id"] = str(mission.id)`. Then "already backfilled" check becomes: `WHERE definition['_source_mission_id'] = mission.id`. |
| **B2** | **`phase104_retarget_aux_tables.py` has dead-code retarget.** Tries to add `run_id` to `mission_improvements`, but **`phase103_drop_old_tables` DROPS `mission_improvements`**. The `_table_exists()` guard prevents the migration from erroring, but the retarget is silently skipped — mission_improvements rows lose their FK entirely. | `backend/alembic/versions/20260609_phase104_retarget_aux_tables.py:79-99` | Mission improvements orphaned post-cut (no path back to the run). | **Option B2-A (preferred):** remove the mission_improvements `if _table_exists` block entirely. Accept that mission_improvements dies with phase103 (it's an internal audit table; substrate events remain the canonical trace). **Option B2-B:** insert a new *pre-103* migration that adds `run_id` to mission_improvements AND populates from query history. (More work; only if mission_improvements is product-visible.) |
| **B3** | **`compat.py` `active_missions_from_blueprints` reads `MissionTask` (old table) for progress/ETA.** Phase 103 drops mission_tasks. When `USE_NEW_READS=1` and phase 103 is applied, this code crashes with `UndefinedTableError`. | `backend/app/api/_mission_cqrs/compat.py:241-253` | Critical read path breaks as soon as phase 103 fires. | **B3-A:** Compute progress from `substrate_events` for the run (count `TASK_COMPLETED` events vs nodes in `blueprint.definition.nodes`). **B3-B:** Add a denormalized `runs.node_progress` JSONB updated by the executor on each node completion (more efficient). **B3-C:** Temporarily return `progress=0, eta=None` and file as a known break in the cutover change log. Pick **B3-A** (observable substrate events are already the audit source). |
| **B4** | **`commands.py` dual-write is fire-and-forget with silent failures.** `dual_write_sync_run_status_failed mission_id=...` logs at DEBUG level only. If parent mission transaction commits but fire-and-forget coroutine fails, Blueprint/Run table diverges silently with no operational signal. | `backend/app/api/_mission_cqrs/commands.py:118-134, 350-398, 666` | `verify_backfill_consistency.py` count check passes but content can diverge quietly. | Promote log to WARNING. Add a Prometheus counter `dual_write_failures_total{site}` (sites: create/update/execute/abort). Add daily reconciliation script `scripts/reconcile_dual_write.py` that re-syncs from missions→blueprints when divergence detected. Schedule via cron 04:00 UTC. |
| **B5** | **`run_service.execute_async` falls back to `asyncio.create_task` if Celery dispatch fails.** Orphaned tasks die with the worker process; no retry queue. Acceptable for transient Celery hiccups but masks real outages. | `backend/app/services/run_service.py:124-141` | Background-task fallback is risky in production under load. | Either (a) fail loudly when Celery dispatch fails (no silent fallback), or (b) wrap in a durable retry on RabbitMQ/pg_worker. Pick (a) for cutover — the cutover is not the moment to fix this in (b). |

---

## 1. Cutover Sequencing (12 phases, all gated)

### Phase A — Fix pre-cutover bugs (B1-B5) — estimate 1 week

**Goal:** Eliminate every blocker to a safe cutover. Tests before code. Tests must be merged first.

| Step | Action | Files | Verification |
|---|---|---|---|
| A.1 | Add regression tests for `backfill_blueprints_runs.py` idempotency (B1) | `backend/tests/test_backfill_blueprints_runs.py` (NEW) | `python -m pytest backend/tests/test_backfill_blueprints_runs.py -v` — verify backfill twice creates no duplicates |
| A.2 | Add regression test for `phase104` skipping mission_improvements (B2) | `backend/tests/test_phase104_migration.py` (NEW) | Test that migration succeeds when `mission_improvements` is absent |
| A.3 | Add regression test for `compat.py` progress calculation post-mission_task-drop (B3) | extend `backend/tests/integration/test_new_reads_compat.py` | With `USE_NEW_READS=1` AND a fake blueprint whose run has substrate_events, progress should compute from event count, not crash on MissionTask |
| A.4 | Add Prometheus counter tests for `dual_write_failures_total` (B4) | extend `backend/tests/integration/test_new_reads_compat.py` | Inject a failure into the dual-write path; assert counter increments AND log line is at WARNING |
| A.5 | Add test for `execute_async` no-silent-fallback (B5) | `backend/tests/test_run_service.py` | Mock Celery dispatch to raise; assert `execute_async` raises (does not silently create_task) |
| A.6 | Implement B1-B5 fixes (one PR, each commit addresses one bug + drops corresponding NEW tests first) | per-bug | Each commit passes its own test before next commit |
| A.7 | Run full substrate regression suite, confirm no NEW failures | — | `pytest backend/tests -q` matches baseline (151+5 PENDING=156, 10 pre-existing failures) |

**Stop-gate A:** All 5 regression tests added BEFORE any fix code is written. Fixes land in small atomic commits. Substrate baseline preserved.

---

### Phase B — Dual-write parity verification (live) — estimate 3-5 days

**Goal:** Prove every mission create/execute/update/soft-delete/abort is mirrored in the Blueprint/Run tables. The 2-week soak is meaningless without this proven first.

| Step | Action | Verification |
|---|---|---|
| B.1 | Enable WARNING-level dual_write log lines via env (use the fix from A.6) | `grep dual_write_sync_run_status_failed backend/$(docker compose ps -q backend)/var/log/stdout/*.log` returns expected WARNING count |
| B.2 | Run live mission-create stream for 24 hours: create 100 missions, 50 executions, 30 updates, 20 soft-deletes, 10 aborts across 5 test users | Manual exercise returns exactly 100 Blueprints + 50 Runs + 30 updated BPs + 20 soft-deleted BPs + 10 aborted Runs |
| B.3 | Run `verify_backfill_consistency.py` post-exercise | Report prints no issues. If issues: stop, fix dual-write, repeat B.2 |
| B.4 | Reconcile: dump all missions+blueprints and confirm 1-to-1 ID correspondence | New script `scripts/prove_dual_write_complete.py` counts (Mission.id == Blueprint.id AND Blueprint.definition['_source_mission_id'] == str(Mission.id)) for each mission. Target: 100% |
| B.5 | Capture dual-write failure rate for the 24h window | `promtool query instant dual_write_failures_total` shows 0 in dev environment (acceptable 0.5% threshold for prod) |

**Stop-gate B:** Dual-write failure rate = 0 in dev, ≤0.5% in production. 1-to-1 ID correspondence between missions and blueprints is provable.

---

### Phase C — Stabilize dual-write reliability (production) — estimate 1 week

**Goal:** Production dual-write is reliable enough to trust for the soak period.

| Step | Action | Verification |
|---|---|---|
| C.1 | Land the `reconcile_dual_write.py` cron script (from fix B4) | Cron installed but DISABLED. Manual run shows expected reconciliation logic on a 1k-row sample. |
| C.2 | Run dual-write in production for 7 days | Daily metric: `dual_write_failures_total / (mission_creates_total) < 0.5%`. Daily scan: any blueprint missing mission_id? any run missing blueprint_id? |
| C.3 | Investigate every failure >0.1% | Specific bug, fix, document in `.sisyphus/evidence/phase-c-failure-investigation.md` |
| C.4 | Activate the cron with `ENABLE=1` env, schedule 04:00 UTC daily | First scheduled run shows 0 divergences |

**Stop-gate C:** 7 production days with dual-write failure rate ≤ 0.5% AND zero blueprints missing source_mission_id.

---

### Phase D — Backfill historic data — estimate 1-2 days

**Goal:** Pre-cutover blueprints cover the full historical mission base (including missions created BEFORE dual-write was deployed).

| Step | Action | Verification |
|---|---|---|
| D.1 | Deploy the idempotent `backfill_blueprints_runs.py` (from fix B1) | Unit test: re-running twice = same row count |
| D.2 | Dry-run on production read replica: `python -m scripts.backfill_blueprints_runs --dry-run` | Reports `(N missions to backfill, M executions to backfill)` |
| D.3 | Estimate: `tasks = N + M` at 100/batch → `ceil((N+M)/100)` iterations; each iteration ~5s | Document estimated wall-time in plan |
| D.4 | Schedule backfill off-hours via `pg_dump` → backup → run → verify | `pg_dump` taken. Backfill runs in batches of 100 with progress logs. |
| D.5 | Run `verify_backfill_consistency.py` | Reports no issues. Run a second time: STILL no issues (idempotency proven at scale) |
| D.6 | Run `scripts/prove_dual_write_complete.py` post-backfill | All historical missions now have corresponding blueprints |

**Stop-gate D:** `bp_count ≥ mission_count`, `run_count ≥ workflow_execution_count + orchestrator_execution_count`. Backfill is idempotent (verified by running twice).

---

### Phase E — Compatibility views (apply phase102) — estimate 1 day

**Goal:** Old API endpoints read from new tables via views. Zero-downtime transition path.

| Step | Action | Verification |
|---|---|---|
| E.1 | Set `PHASE10_SOAK_COMPLETE=1` env var on the deploy environment, with explicit justification record at `.sisyphus/evidence/phase-e-justify-soak-complete.md` referencing: (i) dual-write failure rate over Phase C < 0.5%; (ii) backfill coverage 100%; (iii) Phase D stop-gate passed | Justification file includes metrics + commit hashes |
| E.2 | Run `alembic upgrade head` with `PHASE10_SOAK_COMPLETE=1` | Migration applies; alembic head moves to `phase102_compat_views` |
| E.3 | Verify views exist with correct shape | `psql -c "\\d missions_compat"` returns columns. `SELECT count(*) FROM missions_compat` matches `SELECT count(*) FROM blueprints WHERE deleted_at IS NULL` |
| E.4 | Smoke test OLD v1 mission list endpoint (NOW reads via view, not via `missions` table) | `curl /api/v1/missions` returns identical response shape as before |
| E.5 | Smoke test `MissionShim` (USE_NEW_READS=1 + mission reads via compat views) | Cross-check 100 missions: response fields match between USE_NEW_READS=0 and USE_NEW_READS=1 |

**Stop-gate E:** Views exist. `missions_compat` row count = `blueprints` row count. v1 mission list endpoint response shape unchanged. View query latency P95 ≤ 50ms (comparable to direct `missions` table read).

---

### Phase F — Enable USE_NEW_READS=1 in production (gradual) — estimate 1 week

**Goal:** Switch the read traffic from `missions` table to `blueprints+runs` tables. No frontend change yet.

| Step | Action | Verification |
|---|---|---|
| F.1 | Set `USE_NEW_READS=1` for staging env only. Monitor for 24h | No customer-visible regressions. Read latency similar. |
| F.2 | Same env: 1% production traffic via feature-flag router | `:1%` of users see new reads. Compare error/timeout rates for the cohort. |
| F.3 | Increment to 10% over 3 days, monitoring daily | Latency P95 within 10% of v1 path. Error rate within 0.1%. |
| F.4 | Increment to 100% | Full cutover for read traffic. |
| F.5 | Set `ENABLE_V1_MISSION_LEGACY_REMOVAL=0` (keeps old code path callable but unused) | — |

**Stop-gate F:** 7 days at 100% USE_NEW_READS=1 with: (i) zero customer-visible error reports; (ii) latency P95 within 10% of legacy; (iii) consistent substrate event coverage on the new tables.

---

### Phase G — Frontend route migration — estimate 1 week

**Goal:** Frontend stops hitting `/missions` and `/graphs` and starts hitting `/blueprints` (v2 API).

| Step | Action | Verification |
|---|---|---|
| G.1 | Map all frontend routes calling v1: `grep -r '/api/v1/missions\|/api/v1/flows\|/api/v1/graphs' frontend/src/` (in FlowmannerV2-frontend repo) | Surface list of files needing migration |
| G.2 | Migrate frontend to v2 routes: `/api/v2/blueprints`, `/api/v2/blueprints/{id}/run`, `/api/v2/blueprints/{id}/versions`, `/api/v2/runs/{id}` | Files updated; typecheck passes; component tests green |
| G.3 | Add `Deprecation: true` + `Sunset: <date>` + `Link: </api/v2/blueprints>; rel="successor-version"` headers to v1 mission/flow/flow_compat responses | Headers visible in `curl -I /api/v1/missions` |
| G.4 | Ship frontend via `deploy-frontend.sh` | Deploy succeeds |
| G.5 | Monitor frontend analytics: legacy route traffic should fall to 0 over 7 days | At Day 7: legacy route traffic = 0 (modulo known test users) |

**Stop-gate G:** 100% of frontend feature paths use v2 routes. v1 endpoints receive 0% of customer traffic. Deprecated headers in place.

---

### Phase H — Backend v1 endpoint removal — estimate 1 day

**Goal:** Strip the old mission/flow/flow_compat code paths now that no traffic uses them.

| Step | Action | Verification |
|---|---|---|
| H.1 | Remove `backend/app/api/v1/mission.py` and `backend/app/api/v1/flow_compat.py` route handlers | Reduce from 68→66 routes (or as discovered) |
| H.2 | Remove `backend/app/services/_mission_cqrs/queries.py` legacy path (keep compat.py for compat views debugging) | — |
| H.3 | Verify no internal callers of v1 mission endpoints | `grep -r "from app.api.v1.mission\|from app.api.v1.flow_compat" backend/` returns 0 hits |
| H.4 | Ship backend via `deploy-backend.sh` | — |

**Stop-gate H:** Backend has no duplicate mission-read code paths. USE_NEW_READS env var can be retired.

---

### Phase I — Drop old tables (apply phase103) — estimate 1 day

**Goal:** Cut the dependency on the old schemas. **POINT OF NO RETURN.**

| Step | Action | Verification |
|---|---|---|
| I.1 | Confirm `compat.py` no longer reads `MissionTask` or other dropped tables (B3 fix verified in Phase A) | Code search |
| I.2 | Full database backup: `bash scripts/backup_pg.sh` (existing infra) AND `pg_dump --schema-only` AND `pg_dump --data-only` separate | Backup files exist + sizes match expectations |
| I.3 | Verify no live code paths reference any of the 16 old tables: `grep -r 'missions\|workflow_executions\|swarm_pipelines\|orchestrator_executions\|mission_tasks\|mission_logs\|workflow_states\|workflow_versions\|orchestrator_tasks\|execution_events\|swarm_consensus_rounds\|swarm_tasks\|swarm_agents\|mission_versions\|mission_templates\|mission_improvements' backend/app/` | Zero hits |
| I.4 | Run `PHASE10_SOAK_COMPLETE=1 alembic upgrade head` | Migration applies (drops views, drops FKs, drops tables) |
| I.5 | Verify drops: `psql -c "\\d missions"` returns "Did not find any relation named missions" (and same for the other 15) | All 16 tables gone |
| I.6 | Smoke test: substrate event replay works (replay reads `substrate_events` which we did NOT drop) | `curl /api/missions/{id}/replay-state` returns 200 with expected event types |
| I.7 | Monitor for 4 hours: any 500 errors mentioning dropped table? | Zero hits |

**Stop-gate I:** All 16 old tables dropped. Zero 500 errors for 4 hours post-drop. Backup verified restorable (on a test DB instance).

---

### Phase J — Apply phase104 retargeting (only the alive-from-103 tables) — estimate 1 day

**Goal:** Apply the auxiliary-table FK retargeting for tables that survived phase 103.

| Step | Action | Verification |
|---|---|---|
| J.1 | Per B2 fix, verify phase104 only targets mission_triggers + mission_circuit_breakers (mission_improvements block removed) | Code review |
| J.2 | Run `PHASE10_SOAK_COMPLETE=1 alembic upgrade head` | Migration applies; new `run_id` and `blueprint_id` columns added to the two surviving tables |
| J.3 | Backfill: for each existing mission_trigger and mission_circuit_breaker row, look up the run/blueprint via the mission_id stored in substrate_events | New script `scripts/backfill_aux_fks.py` |
| J.4 | Update application code that writes to mission_triggers / mission_circuit_breakers to ALSO write the new FK columns during the write | Diff + tests |
| J.5 | Update application code that reads mission_triggers / mission_circuit_breakers to JOIN through new FKs where natural | Diff + tests |

**Stop-gate J:** New FK columns populated for ≥95% of existing rows. Application write paths populate new FKs.

---

### Phase K — Final verification — estimate 2 days

**Goal:** Prove everything is on new tables and there's no hidden dependency on old.

| Step | Action | Verification |
|---|---|---|
| K.1 | `grep -r "Mission\|WorkflowExecution\|OrchestratorExecution\|SwarmPipeline\|MissionTask" backend/app/` | Hits should be only in schema/APIs that don't perform live read/write |
| K.2 | Run full backend pytest suite in container | Baseline preserved (or improved) |
| K.3 | Run end-to-end smoke test: create mission → execute → abort retry → replay → diff | All 5 operations succeed |
| K.4 | Update `docs/BLUEPRINT-RUN-IMPLEMENTATION-PLAN.md` status to "✅ COMPLETE" | File updated, commit message references this plan |

**Stop-gate K:** Zero new test failures. End-to-end smoke test green. Plan marked complete in docs.

---

### Phase L — Retire Phase 10 track (cleanup) — estimate 1 day

| Step | Action | Verification |
|---|---|---|
| L.1 | Remove `PHASE10_SOAK_COMPLETE=1` env var requirement from any remaining migration | Migration files updated |
| L.2 | Mark phase 10 migration files in `docs/` as historical (`<!-- ARCHIVED 2026-MM-DD -->`) | — |
| L.3 | Update ONBOARDING for new devs: only blueprints + runs tables are the execution model | doc edited |

---

## 2. Soak Protocol — Definitions

**"Soak complete" requires ALL of the following over the 14-day window:**

| Metric | Target | Measurement | Failure action |
|---|---|---|---|
| **M1: Dual-write failure rate** | < 0.5% of mission-write operations | `dual_write_failures_total{site} / mission_writes_total` daily | If > 0.5% for 2+ consecutive days: extend soak by 7 days. If > 1%: stop and fix. |
| **M2: Divergence rate** | 0 blueprints without mission_id, 0 runs without blueprint_id | `scripts/reconcli_mission_to_blueprint.py` daily cron at 04:00 UTC | Any divergence > 24h before fix: stop and reconcile |
| **M3: Read latency P95 (USE_NEW_READS=1)** | within 10% of legacy path | Prometheus request_duration_seconds histogram | If P95 grows > 20%: investigate; within 50%: extend soak by 7 days |
| **M4: Customer error reports mentioning "blueprint" or "phase10"** | 0 per week | Manual scan of Sentry/error logs | Any single customer-visible error: hot-fix within 24h or rollback |
| **M5: Substrate event coverage** | every existing mission has ≥1 blueprint_id on its events | `SELECT count(*) FROM substrate_events WHERE mission_id IS NOT NULL AND blueprint_id IS NULL` returns 0 | Any non-zero > 7 days: re-attach; reject the cutover |

**Soak-window start conditions:**
- Phase A stop-gate passed (all 5 regression tests added and fixes shipped)
- Phase B stop-gate passed (dual-write parity proven in dev)
- Phase C stop-gate passed (production dual-write rate ≤ 0.5% over 7+ days)
- Phase D stop-gate passed (backfill coverage 100%)

**Re-decision trigger:** Any M1-M4 failure OR M5 > 0 → extend soak by 7 days. After one extension, failure → STOP, fix, restart from Phase B.

**Soak authority:** Glenn decides whether to abort, extend, or proceed at every checkpoint.

---

## 3. Cutover Day Checklist (Phase I specifically — point of no return)

**T-7 days before cutover (Phase I):**
- [ ] Glenn approves proceed
- [ ] Backup verified restorable on a scratch DB
- [ ] All 16 old-table references removed from `backend/app/` (grep clean)
- [ ] `compat.py` no longer reads `MissionTask` (B3 fixed)
- [ ] Reconciliation cron active and reporting 0 divergences
- [ ] Team notified of cutover window
- [ ] Rollback runbook printed and pinned in team chat

**T-1 day before cutover:**
- [ ] Customer-facing feature under extra Sentry alert for the 24h window
- [ ] Stuck-active-missions drained: every active mission either completes, fails cleanly, or is paused by user
- [ ] Database backup taken even a second time and uploaded off-host (`s3` or equivalent)

**T-0 (cutover day) — recommended window: 04:00-08:00 UTC (off-peak US/EU):**
- [ ] `T+0min:`   Last `pg_dump` taken; size verified; checksum recorded
- [ ] `T+5min:`   Set `PHASE10_SOAK_COMPLETE=1` in deploy environment
- [ ] `T+10min:`  Run `alembic upgrade head` for phase102+103+104 stack
- [ ] `T+15min:`  Verify alembic head = `phase104_retarget_aux_tables`
- [ ] `T+20min:`  Verify views dropped: `psql -c "SELECT viewname FROM pg_views WHERE viewname LIKE '%_compat'"` returns 0
- [ ] `T+25min:`  Verify old tables dropped: `psql -c "\\dt"` returns no missions/workflows/etc.
- [ ] `T+30min:`  Smoke test: substrate event replay on a sample mission
- [ ] `T+45min:`  Smoke test: create new mission end-to-end (POST /api/v2/blueprints → GET /api/v2/blueprints/{id})
- [ ] `T+60min:`  Smoke test: execute new blueprint, verify run event flow
- [ ] `T+90min:`  Monitor dashboard: any 500-error spike vs. baseline? Confirm substrate_event append-only trigger still works
- [ ] `T+4h:`    Customer Sentry alerts scan
- [ ] `T+24h:`   Day-1 post: zero drops, no rollback needed

**Rollback procedure (if invoked within 4h T+0):**
1. Stop backend container (so no new reads/write attempts hit dropped tables).
2. Restore DB from backup taken at T+0min.
3. Bring backend up. **NOTE:** the dual-write code paths will be present in the code (the DROP didn't reverse the application code), so restored DB will see both old AND new tables. This is OK for read traffic recovery.
4. Investigate the cutover failure (root cause), fix, re-test in dev, re-do Phase B before retrying.

**Rollback is NOT POSSIBLE after T+4h** without manual forensic DB reconstruction (the dropped tables can't be recovered except from backup). Make sure you're really ready.

---

## 4. Risk Register

| # | Risk | Probability | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | Pre-cutover bug B3 (`compat.py` progress reading MissionTask) is shipped accidentally | High | High (whole read path crashes) | Phase A adds test FIRST then fixes; Phase E verifies views only; don't enable USE_NEW_READS=1 in prod until B3 fixed |
| R2 | Fire-and-forget dual-write silent failures stay silent | High | High (data divergence) | Phase A adds Prometheus counter; Phase C reconciliation cron |
| R3 | Backfill creates duplicates due to B1 idempotency bug | Critical | High (overcounts) | Phase A test-first; Phase D verifies run-twice idempotency |
| R4 | Migration phase104 ordering bug causes mission_improvements data loss | Medium | Low (internal audit table) | Phase A removes dead code OR inserts pre-103 migration; verified by integration test |
| R5 | Soak-mask metric (everything green but real issues hidden) | Medium | Critical | Glenn reviews daily metrics; M1-M5 explicit + signed-off by Glenn +4644 |
| R6 | Phase 103 drop is irreversible | Already known | Catastrophic | Mandatory backup; rollback runbook; T+0 to T+4h window for rollback |
| R7 | Frontend route migration breaks user flows | Medium | High | Deprecation headers; Phase G takes 1 week; G.5 7-day traffic analysis |
| R8 | read-vs-write latency asymmetry surfaces only at production scale | Medium | Medium | Phase F gradual rollout: 1% → 10% → 100%; pause at 10% if P95 grows > 20% |
| R9 | Phase C reconciles blueprints that shouldn't have been dual-written (false positives) | Low | Medium | Reconcile script must dry-run report, only auto-reconcile on exact ID match, escalate near-matches to humans |
| R10 | Pre-existing drift (559 grandfathered items in snapshot) interacts badly with the cutover | High | Medium | After Phase J, run `make validate-migration` — expected to still show 559 baseline items, but ensure no NEW drift introduced |

---

## 5. Success Criteria — Plan Complete When ALL Are True

- [ ] All 12 phases (A-L) have stop-gates passed and committed
- [ ] Phase I cutover completed cleanly: zero rollback, zero unresolved errors after T+24h
- [ ] Phase J aux-table FKs populated and application code uses them
- [ ] 14-day soak completed after Phase E with all 5 metrics (M1-M5) green every day
- [ ] No `grep` hit on any old mission/workflow/swarm/orchestrator table name in `backend/app/` (excluding historical comments in migrations and docs)
- [ ] `backend/app/api/v1/mission.py` and `backend/app/api/v1/flow_compat.py` removed
- [ ] `backend/app/api/_mission_cqrs/queries.py` legacy paths removed (compat.py stays for compat-view debugging only)
- [ ] Documentation: `docs/BLUEPRINT-RUN-IMPLEMENTATION-PLAN.md` marked "✅ COMPLETE 2026-MM-DD" with link to this plan
- [ ] `docs/REBUILD-BACKEND.md` §3.5 stop-gate checkbox checked, link to this plan
- [ ] `.sisyphus/boulder.json` updated: phase 10 marked complete; phase 3.5 cutover listed as a separate completed work item

---

## 6. Notes / Linkage

- **Tests before code:** Every Phase A bugfix must start with the test, then the fix. This mirrors chunk 1's stop-gate rule and prevents the chunk-2 asyncpg-multi-statement bug class (which introduced regression on the bugfix commit itself).
- **No `docker cp`:** Backend image has no volume mount. Use `bash /opt/flowmanner/deploy-backend.sh` for every binary change. (Documented in AGENTS.md.)
- **Deploy timings:** Backend deploy ≈ 2 min. Frontend deploy ≈ 4 min. Phase G plan accordingly.
- **AGENTS.md applies:** Every agent running this plan must run the SESSION-RITUAL.md exit audit, commit and push to origin after each phase. (Already standard practice for this repo.)
- **No bypass of `PHASE10_SOAK_COMPLETE=1`:** Three migrations (102, 103, 104) gate on this env var. The justification file is mandatory and must be reviewed by Glenn before applying each.

---

## 7. What I Did NOT Plan For

These would be follow-up initiatives but are out of scope for this cutover:

- Migrate `community.py` from raw `_ensure_table()` SQL to CommunityTemplate ORM (separate cleanup)
- Fix the 559 pre-existing drift items in `scripts/model_snapshot.json` (separate initiative per chunk 9 follow-up)
- Convert `_mission_cqrs/queries.py` legacy path into a Builder-pattern consumer for the new EPC API
- Update the `sdk-python/` SDK to talk to v2 blueprints endpoints (depends on downstream consumers)
- Multi-tenant budget pools (single-currency budget tracking was a v3 concern)

---

## 8. Provenance

Inputs:
- `docs/REBUILD-BACKEND.md` §3 (Phase 3.5 prose)
- `backend/alembic/versions/20260609_phase101|phase102|phase103|phase104_*.py`
- `backend/scripts/backfill_blueprints_runs.py`
- `backend/scripts/verify_backfill_consistency.py`
- `backend/app/api/_mission_cqrs/{commands,queries,compat}.py`
- `backend/app/services/{blueprint_service,run_service}.py`
- `backend/app/models/{blueprint_models,mission_models,graph}.py`
- `.sisyphus/boulder.json` chunks 1-9 evidence § "deferred_to_followup" + "stop_gates_verified_post_deploy"
- Q2-Q3 chunks 5-9 already shipped dual-write + substrate foundation

Decisions:
- Plan adopts the REBUILD-BACKEND.md §3.5 structure (dual-write → backfill → soak → cut) but adds explicit pre-cutover bug-fixing phase (Phase A) because the current dual-write infrastructure has 5 concrete bugs that make a naive 2-week soak more risky than necessary.
- Plan adds a gradual frontend read migration (Phase F-G) before backend v1 removal (Phase H) before drop (Phase I). The current single-step "drop tables" approach underestimates the read-path coordination required.
- Plan splits the criterion "2 weeks elapsed" into 5 explicit metrics (M1-M5). Calendar time alone is a weak signal — divergence rate and read latency matter more.
