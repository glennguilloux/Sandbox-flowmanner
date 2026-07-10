# Exit Audit — 2026-06-27 Phase 3: Usage Analytics Deploy (Hermes session)

## WHAT CHANGED (one bullet per file, what + why)

### Backend (`flowmanner` main, `2496ecb`)

- `backend/app/models/integration_models.py` — Added `IntegrationUsageLog` model (per-user, per-integration action tracking: slug, action, status, latency, error). No PII.
- `backend/app/models/__init__.py` — Registered `IntegrationUsageLog` in model exports.
- `backend/app/services/integration_usage_service.py` — New service: `record_call()`, `get_usage_stats()` (total/success/failed, avg/p95 latency, top actions), `cleanup_old_records()` (90-day retention).
- `backend/app/services/action_registry.py` — `execute_action()` now records every action call fire-and-forget (success + failure paths).
- `backend/app/api/v1/integrations.py` — `GET /{slug}/usage` endpoint, gated by `integration_usage_v1` flag.
- `backend/alembic/versions/20260627_integration_usage_logs.py` — Table + 3 indexes + seeds `integration_usage_v1` flag (disabled). Chains from `integration_health_records_001`.
- `backend/app/tests/test_integration_usage.py` — 21 tests (model, service, action registry hook, endpoint, migration).
- `backend/scripts/model_snapshot.json` — Refreshed (145 → 146 tables).

### Frontend (`FlowmannerV2-frontend` master, `7d328d4`)

- `src/types/integration-manifest.ts` — `IntegrationUsageStats`, `IntegrationUsageTopAction` types.
- `src/lib/integrations-api.ts` — `fetchIntegrationUsage(slug, period)`.
- `src/app/[locale]/dashboard/settings/integrations/integrations-page-content.tsx` — Inline usage display (calls, success rate, avg latency) for active connections.

### Docs (`flowmanner` main, `0ed08f9`)

- `AGENTS.md` — Critical Rule #6: path-aware verification scoping (skip make test/lint/build for doc-only changes).

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- None. DeepSeek's code was cleaned (10 ruff violations fixed: import sorting, `list(...)[0]` → `next(iter(...))`) before commit.

## TESTS RUN + RESULT

```
cd /opt/flowmanner/backend && .venv/bin/python -m pytest app/tests/test_integration_usage.py -q
21 passed, 1 warning in 0.15s

cd /opt/flowmanner/backend && ruff check app/tests/test_integration_usage.py app/services/integration_usage_service.py app/models/integration_models.py app/api/v1/integrations.py app/services/action_registry.py
All checks passed!

cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit
EXIT: 0
```

Pre-commit hooks: all passed (ruff, ruff-format, mypy, gitleaks, trim trailing whitespace, fix end of files).

## DEPLOY ACTIONS TAKEN

### 1. Deploy race condition (recurring — same as Phase 2)

`deploy-backend.sh --migrate` failed: migration verification step (`Expected head: integration_usage_logs_001, Actual head: integration_health_records_001`) ran before alembic could apply the migration. Auto-rollback triggered (reverted to old image).

Resolution: `deploy-backend.sh` (without `--migrate`), then `docker compose exec -T backend alembic upgrade head` manually — applied cleanly.

### 2. Feature flag enabled

```sql
UPDATE feature_flags SET enabled_globally=true, updated_at=NOW() WHERE key='integration_usage_v1';
-- integration_usage_v1: enabled=t
```

### 3. End-to-end live verification

- Route registered: `/api/integrations/{slug}/usage` → 401 (auth required, not 404)
- Service probe via `IntegrationUsageService.record_call()` + `get_usage_stats()`:
  - Recorded `send_message` call (42ms latency)
  - Queried stats: `total_calls=1, success_rate=100.0, avg_latency=42ms, p95=42ms, top_actions=[{action: send_message, count: 1}]`

### 4. Frontend deployed

`deploy-frontend.sh` — image built, container recreated, nginx restarted. `https://flowmanner.com` → 200.

## STATUS

### flowmanner (main)

```
$ git log --oneline origin/main..main
2496ecb feat(integrations): Phase 3 usage analytics per integration
0ed08f9 docs: path-aware verification scoping rule for doc-only changes

$ git status
nothing to commit, working tree clean
```

### FlowmannerV2-frontend (master)

```
$ git log --oneline origin/master..master
7d328d4 feat(integrations): Phase 3 usage analytics UI

$ git status
nothing to commit, working tree clean
```

### Live deployment

| Component | Status |
|-----------|--------|
| backend | Up 12 min, healthy |
| celery-worker | Up 12 min, healthy |
| celery-beat | Up 12 min, healthy |
| flowmanner-frontend (VPS) | Recreated, healthy |
| Migration head | `integration_usage_logs_001` |
| `integration_usage_v1` flag | enabled |
| `integration_health_v1` flag | enabled |
| `integration_manifests_v1` flag | disabled |

## NEXT SESSION HANDOFF

**Where we are:** Phases 1–3 of the marketplace plan fully shipped and verified live. Usage analytics recording real data (probe confirmed).

**What's next:**

1. **Phase 4: Interactive Playground** (per `.sisyphus/plans/PLAN-marketplace-ux-trust-infrastructure.md` lines 459+)
   - Interactive integration testing UI — let users try an integration before connecting
   - Likely needs a backend sandbox endpoint + frontend playground component
2. **Circuit breaker wiring** (still deferred from Phase 2) — `record_failure()` / `record_outage()` have zero callers. Usage analytics benefits from the same failure-event stream.
3. **Push both repos to origin** — 2 backend + 1 frontend commits unpushed. Glenn usually does this.

**Gotchas:**

1. **Deploy script race condition is now confirmed recurrent.** Phase 2 and Phase 3 both hit it. The workaround is reliable: `deploy-backend.sh` (no `--migrate`) → manual `alembic upgrade head`. This is saved as a skill (`flowmanner-integration-phase-deploy`) for token efficiency.
2. **60-second in-process flag cache** still applies to `integration_usage_v1`.
3. **Phase 3 migration had no gitleaks false-positive** (confirmed in handoff prediction — no SQL string literals that look like secrets).

## SESSION CHAIN

- **DeepSeek (prior session)** — implemented Phase 3, left everything uncommitted, claimed "Complete ✅"
- **Hermes (this session)** — verified claims, fixed 10 ruff violations, committed both repos, deployed backend+frontend, applied migration, enabled flag, verified end-to-end with service probe.

## END
