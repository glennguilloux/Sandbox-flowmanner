# EXIT AUDIT — 2026-07-03

## WHAT CHANGED (one bullet per file, what + why)

- `backend/app/services/sentry/sentry_integration.py`: Added DNS pre-flight check before `sentry_sdk.init()` using `socket.getaddrinfo()`. If the Sentry ingest hostname can't be resolved, logs one warning and disables Sentry gracefully instead of letting urllib3 spam retries every cycle. Also added `# type: ignore[no-redef]` for pre-existing mypy errors on conditional import pattern.
- `backend/app/services/sentry/__init__.py`: No change — already re-exports `init_sentry`.
- `backend/tests/test_sentry_integration.py`: Added 3 new tests for DNS validation path: `test_initialize_returns_false_on_dns_failure`, `test_initialize_logs_warning_on_dns_failure`, `test_initialize_no_dns_check_when_dsn_has_no_hostname`.
- `backend/app/models/__init__.py`: Added `MissionPlanCandidate` to the import from `mission_advanced_models`. The model was defined but never imported, so it was missing from `Base.metadata`.
- `backend/scripts/model_snapshot.json`: Regenerated to include `mission_plan_candidates` table (147→148 tables). Fixes migration gate test drift.
- `nginx/default.conf`: Added missing proxy headers (`Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`) to the `/ws` WebSocket location block. All other location blocks had these.
- `scripts/wg-watchdog.sh`: New WireGuard tunnel watchdog script. Monitors the WG tunnel from the VPS side every 2 minutes via cron. If last handshake exceeds 5 minutes AND the peer is unreachable, restarts the WG interface and verifies the fix.

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- None (all changes were committed)

## TESTS RUN + RESULT

```
$ cd /opt/flowmanner/backend && python -m pytest tests/ -m 'not integration' -q --tb=no
3200 passed, 53 skipped, 722 deselected, 235 warnings in 259.92s (0:04:19)

$ python -m pytest tests/test_validate_migration_gate.py -q --tb=no
5 passed in 7.46s

$ python -m pytest tests/test_sentry_integration.py -q --tb=no
11 passed in 3.32s
```

## STATUS (raw output)

```
$ git status
On branch main
Your branch is ahead of 'origin/main' by 5 commits.
  (use "git push" to publish your local commits)

nothing to commit, working tree clean
```

```
$ git fetch origin && git log --oneline origin/main..main
b549ff1 test: add DNS validation tests for Sentry integration
2ac277d fix: register MissionPlanCandidate in Base.metadata and regenerate snapshot
5dfbac4 feat: add WireGuard tunnel watchdog (auto-restart on stale handshake)
9a5dd53 fix: add missing proxy headers to nginx /ws location block
455a575 fix: validate Sentry DSN DNS before init to prevent urllib3 log spam
```

```
$ docker compose exec -T backend alembic current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
20260630_plan_candidates (head)
```

```
$ docker compose exec -T backend bash -c "pytest -q" 2>&1 | tail -20
(skipped — runs inside container, tests run from host instead — see above)
```

## NEXT SESSION HANDOFF

This session fixed 4 issues discovered during a production debugging session:

1. **Sentry DNS log spam**: The backend container couldn't resolve Sentry's ingest endpoint, causing urllib3 to spam 3 retries per event every cycle. Added a `socket.getaddrinfo()` pre-flight check that fails fast with one warning. The DNS issue was transient (resolved after WireGuard restart), but the guard remains for future failures.

2. **WireGuard tunnel failure (root cause of WS errors)**: The VPS peer lost its endpoint mapping (`0.0.0.0:0`, last handshake 1+ day ago), breaking ALL VPS→homelab traffic. This caused the WebSocket connection errors the user reported. Restarted WG on VPS to restore. Created `scripts/wg-watchdog.sh` deployed to VPS cron (every 2 min) to auto-detect and fix this in the future.

3. **Nginx /ws proxy missing headers**: The WebSocket location block was missing `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` headers. Deployed updated config to VPS.

4. **Migration snapshot drift**: `MissionPlanCandidate` model existed but wasn't imported in `__init__.py`, so it was missing from `Base.metadata` and the migration gate tests failed. Fixed the import and regenerated the snapshot.

**Next steps**: Push these 5 commits to origin, then deploy backend (`deploy-backend.sh`) to pick up the Sentry DNS fix and model import. The nginx config is already deployed. The WG watchdog is already running on VPS. The user should verify WebSocket connectivity works in the browser.

**Gotchas**: The WireGuard tunnel can go stale if the homelab's ISP/router resets the NAT mapping. The watchdog (cron every 2 min on VPS) should catch this, but if it doesn't, manual fix is `ssh VPS 'systemctl restart wg-quick@wg0'`.

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- Untracked files: none
- Deleted files: none
