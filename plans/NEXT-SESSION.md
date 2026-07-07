# FlowManner — NEXT SESSION HANDOFF
**Last updated:** 2026-07-07
**Status:** P1 Sprint COMPLETE — Q3/Q4 Execution Plan COMPLETE

---

## What Was Completed This Session

### P1 Sprint — ALL ITEMS DONE

| Item | Status | Commit |
|------|--------|--------|
| P1-3: Nginx SSE (`proxy_buffering off`) | ✅ Deployed to VPS | `205a99d2` (backend), deployed to `flowmanner-nginx` |
| P1-1: Dual-write cleanup | ✅ Scripts deleted, docs updated | `340e61d8` (backend) |
| P1-2: Strategy viability UX (backend) | ✅ `GET /api/strategies` | `9ac22f83` (backend) |
| P1-2: Strategy viability UX (frontend) | ✅ Strategy selector UI | `c99c715a` (frontend repo) |

### P1 Sprint Commits

**Backend (origin/main):**
| Commit | Description |
|--------|-------------|
| `205a99d2` | fix(nginx): add proxy_buffering off for SSE streaming support |
| `340e61d8` | chore(cleanup): P1-1 dual-write cleanup — delete dead scripts, mark EXECUTED |
| `9ac22f83` | feat(api): add GET /api/strategies endpoint with DEPRECATED flag |

**Frontend (origin/master — FlowmannerV2-frontend):**
| Commit | Description |
|--------|-------------|
| `c99c715a` | feat(chat): add strategy selector UI with deprecated flag support |

### Deployments

- ⏸️ Backend needs redeploy to make `/api/strategies` live — run `bash /opt/flowmanner/deploy-backend.sh`
- ⏸️ Frontend NOT deployed — strategy selector committed on `master` but not deployed yet

---

## What's Next — Future Work

### Immediate (Next Session)

1. **Deploy frontend** — Run `bash /opt/flowmanner/deploy-frontend.sh` to make the strategy selector UI live (~4 min)
2. **Deploy backend** — Run `bash /opt/flowmanner/deploy-backend.sh` to make `/api/strategies` endpoint live (~2 min)
3. **Smoke test strategy selector** — Open Chat Settings → General tab → verify dropdown shows 7 strategies, deprecated ones grayed out
4. **Verify eval dashboard** — Load `/eval`, check console errors, verify tabs work
5. **Check /metrics endpoint** — Verify `cache_hits_total` and `cache_misses_total` Prometheus counters

### Short-Term (Next 1–2 Weeks)

5. ~~**Dual-write removal**~~ ✅ DONE — Per `docs/DUAL-WRITE-DECISION.md`, dual-write layer removed, dead scripts cleaned up (2026-07-07).
6. ~~**Strategy viability UX**~~ ✅ DONE — `GET /api/strategies` + frontend selector with deprecated flag support (2026-07-07).
7. **wt/w2-t6-wire-deploy branch cleanup** — Cherry-pick the 6 deploy-related commits onto main, then delete the branch (per execution plan §5)
7. **Instrument Redis cache usage sites** — The `workflow_cache.py` is instrumented, but other Redis usage sites (`redis.get`/`redis.set` in services like `memory_service.py`, `dashboard_service.py`) could also benefit from metrics

### Medium-Term (Next 1–2 Months)

8. **v2 API completion** — The `/api/v2/` surface is incomplete. Migrate high-value endpoints from v1 to v2 with proper versioning
9. **Plugin system hardening** — Phase 9 (Plugin System) was marked complete but could benefit from sandboxing improvements and a public plugin API
10. **Improvement loop evaluation** — Phase 1B cut most improvement loop phases (3–6). Evaluate whether the remaining `causal_decomposer.py`, `failure_types.py`, `improvement_loop_v2.py` provide value or should be pruned
11. **Frontend fetch() migration** — 15 remaining `fetch()` calls are legitimate edge cases, but could be migrated to `apiClient` for consistency
12. **E2E test expansion** — 22 Playwright specs exist but could cover more critical paths (auth flows, mission execution, chat tool calling)

### Long-Term (Q4 2026+)

13. **Blueprint+Run promotion** — When v2 API adoption justifies it, promote Blueprint+Run from read model to canonical (per dual-write decision)
14. **Multi-model evaluation** — Use the eval dashboard to benchmark multiple models (local 27B, DeepSeek, OpenRouter) and build a model selection strategy
15. **Performance profiling** — Use Jaeger traces to identify bottlenecks in the mission execution pipeline
16. **Scalability testing** — Use the existing k6 load tests (`tests/load/`) to establish baseline performance and identify scaling limits

---

## Gotchas for Next Agent

1. **STRATEGY_EXPERIMENTAL defaults to false** — swarm/pipeline/meta/langgraph missions will fail with ValueError unless set to true in `.env`
2. **audit_log_perf_001 migration** — Already applied via Alembic and psql. The indexes exist. Don't try to re-apply.
3. **Frontend is on a separate repo** — The frontend at `/home/glenn/FlowmannerV2-frontend/` pushes to `origin/master` (not `main`). Deployed via `deploy-frontend.sh`. There may be pre-existing unstaged changes that are NOT from this session.
4. **Full backend pytest OOM** — The full `pytest -q` suite is killed (exit 137). Use targeted tests: `pytest tests/test_lifespan_hydration.py tests/test_agent_api.py tests/test_plan_scorer.py tests/test_health.py -q`
5. **docker compose exec vs docker exec** — `docker compose exec -T workflow-postgres` may fail intermittently. Use `docker exec workflow-postgres` as a fallback.
6. **Cache metrics** — Both `inprocess.py` and `workflow_cache.py` now report to Prometheus via `record_cache_hit`/`record_cache_miss`. Check `/metrics` to verify.

---

## Key Files Reference

| What | Path |
|------|------|
| Execution plan | `docs/EXECUTION-PLAN-Q3-Q4-2026.md` |
| DeepSeek prompt | `docs/DEEPSEEK-PROMPT-Q3-Q4-2026.md` |
| Dual-write decision | `docs/DUAL-WRITE-DECISION.md` |
| Strategy profiling results | `docs/strategy-profiling-results.json` |
| Exit audit (this session) | `.sisyphus/exit-audit-2026-07-04-session2-r5-r6.md` |
| Exit audit (previous session) | `.sisyphus/exit-audit-2026-07-04-q3-q4-execution.md` |
| Alembic migration | `backend/alembic/versions/20260704_audit_log_indexes.py` |
| Cache metrics (inprocess) | `backend/app/cache/inprocess.py` |
| Cache metrics (Redis) | `backend/app/cache/workflow_cache.py` |
| Eval dashboard | `/home/glenn/FlowmannerV2-frontend/src/app/[locale]/(dashboard)/eval/` |
| Nav config | `/home/glenn/FlowmannerV2-frontend/src/components/layout/nav-config.ts` |
