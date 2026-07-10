# Exit Audit — 2026-06-27 Phase 4: Interactive Playground + Deploy Fix

## WHAT CHANGED (one bullet per file, what + why)

### Backend (`flowmanner` main, `0ce4fa0` + `d56e864`)

- `backend/app/core/demo_credentials.py` — Demo credential vault loading sandbox tokens from env vars (Slack, GitHub, Discord, Notion, Apiflow). Falls back to mock when no credentials set.
- `backend/app/services/integration_playground_service.py` — Playground service: real API dispatch (Slack channels/messages, GitHub repos, Notion pages, Discord channels) + high-fidelity mock responses for all 7 integrations. In-memory rate limiter (5/min/user/integration).
- `backend/app/api/v1/integrations.py` — Two new endpoints: `POST /{slug}/playground/{action}` (execute demo action) + `GET /{slug}/playground/actions` (list available actions). Feature-flagged via `integration_playground_v1`.
- `backend/alembic/versions/20260627_integration_playground_flag.py` — Seeds `integration_playground_v1` feature flag (disabled by default). Chains from `integration_usage_logs_001`.
- `backend/integrations/manifests/*.json` (5 files) — `playground.enabled` flipped to `true` for Slack, GitHub, Notion, Discord, Apiflow. Google/Google Drive remain disabled (no sandbox tenant).
- `backend/app/tests/test_integration_playground.py` — 27 tests covering credentials, service mocks, rate limiting, endpoints, manifest validation.
- `deploy-backend.sh` — **Deploy script race condition fix.** Added readiness gate (`check_health` after container recreate) + alembic retry (5s delay, one retry). Root cause: `build_and_deploy()` returned immediately after `--force-recreate`, causing `run_migrations()` to fire alembic against a container that Docker reported "up" but whose DB connection wasn't ready. Alembic silently no-op'd, head verification saw old ≠ new → auto-rollback. This race hit Phase 2 and Phase 3 deploys. **Phase 4 deploy with `--migrate` succeeded first try — fix confirmed.**

### Frontend (`FlowmannerV2-frontend` master, `6b05ef8`)

- `src/components/integrations/integration-playground.tsx` — New component: action selector buttons, description, execute button, response viewer with "Preview" vs "Live" badges, error display.
- `src/lib/integrations-api.ts` — `executePlaygroundAction()` and `fetchPlaygroundActions()` API functions.
- `src/app/[locale]/dashboard/settings/integrations/integrations-page-content.tsx` — Wired playground component into Available Integrations cards with "Try {name}" toggle.

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- None.

## TESTS RUN + RESULT

```
cd /opt/flowmanner/backend && .venv/bin/python -m pytest app/tests/test_integration_playground.py -q
27 passed, 1 warning in 0.08s

cd /opt/flowmanner/backend && ruff check app/core/demo_credentials.py app/services/integration_playground_service.py app/tests/test_integration_playground.py app/api/v1/integrations.py alembic/versions/20260627_integration_playground_flag.py
All checks passed!

cd /home/glenn/FlowmannerV2-frontend && npx tsc --noEmit
EXIT: 0

cd /opt/flowmanner/backend && docker compose exec -T backend bash -c "cd /app && python -m pytest app/tests/ -q"
1013 passed, 3 skipped, 16 warnings in 17.39s

bash -n /opt/flowmanner/deploy-backend.sh
SYNTAX OK
```

Pre-commit hooks: all passed (ruff, ruff-format, mypy, gitleaks, trim trailing whitespace, fix end of files).

## DEPLOY ACTIONS TAKEN

### 1. Backend deploy — `--migrate` worked first try

```bash
bash /opt/flowmanner/deploy-backend.sh --migrate
```

This is the first time `--migrate` completed successfully without the race condition. The readiness gate + alembic retry fix (`d56e864`) eliminated the need for the two-step workaround (deploy without --migrate, then manual `alembic upgrade head`).

### 2. Frontend deploy

```bash
bash /opt/flowmanner/deploy-frontend.sh
```

### 3. Feature flag status

```
integration_playground_v1: disabled (needs manual enable to activate playground)
```

To activate:
```sql
UPDATE feature_flags SET enabled_globally=true WHERE key='integration_playground_v1';
```

## STATUS

### flowmanner (main)

```
$ git status
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean

$ git fetch origin && git log --oneline origin/main..main
(empty — all pushed)
```

### FlowmannerV2-frontend (master)

```
$ git status
On branch master
Your branch is up to date with 'origin/master'.
nothing to commit, working tree clean

$ git fetch origin && git log --oneline origin/master..master
(empty — all pushed)
```

### Live deployment

```
$ docker compose exec -T backend alembic current
integration_playground_flag_001 (head)
```

| Component | Status |
|-----------|--------|
| backend | Deployed with `--migrate` (first successful one-shot migrate) |
| frontend | Deployed |
| Migration head | `integration_playground_flag_001` |
| `integration_playground_v1` flag | **disabled** (needs enable to activate) |
| `integration_usage_v1` flag | enabled |
| `integration_health_v1` flag | enabled |
| `integration_manifests_v1` flag | disabled |
| Deploy script race fix | Live (`d56e864`) |

## NEXT SESSION HANDOFF

**Where we are:** All 4 phases of the marketplace plan (`.sisyphus/plans/PLAN-marketplace-ux-trust-infrastructure.md`) are fully shipped and deployed. The deploy script's `--migrate` race condition — which plagued Phase 2 and Phase 3 — is permanently fixed. The `integration_playground_v1` flag is seeded but not yet enabled (Glenn's call).

**What's next:**

1. **Phase 5** of the marketplace plan (per `.sisyphus/plans/PLAN-marketplace-ux-trust-infrastructure.md`) — the natural next move. Glenn is starting a new session for this.
2. **Enable `integration_playground_v1`** flag when ready:
   ```sql
   UPDATE feature_flags SET enabled_globally=true WHERE key='integration_playground_v1';
   ```
3. **Demo credentials** — currently all env vars are unset, so playground returns mock responses. To enable live playground actions, set sandbox-scoped env vars (`SLACK_DEMO_BOT_TOKEN`, `GITHUB_DEMO_TOKEN`, `DISCORD_DEMO_BOT_TOKEN`, `NOTION_DEMO_TOKEN`, `APIFLOW_DEMO_API_KEY`) and restart backend.

**Gotchas:**

1. **`--migrate` race is fixed.** No more two-step workaround needed. The fix adds a health check after container recreation + an alembic retry. Confirmed working on Phase 4 deploy.
2. **60-second in-process flag cache** still applies to `integration_playground_v1`.
3. **Google/Google Drive** playground remains disabled (no sandbox tenant available).

## SESSION CHAIN

- **Hermes (prior session)** — shipped Phase 3 (usage analytics), verified Phase 4 code in working tree
- **Hermes (this session)** — verified Phase 4 (27 tests, ruff, tsc), committed both repos, fixed deploy script race condition (`d56e864`), deployed backend+frontend with `--migrate` (first successful one-shot), wrote exit audit

## END
