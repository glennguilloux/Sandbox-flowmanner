# EXIT AUDIT — 2026-07-08 — Item #5 Calibration + Item #7 v3 OIDC & Webhooks

## WHAT CHANGED (one bullet per file, what + why)

### Commit 1: `f95ca0fb` — feat(calibration): plan-selection calibration with strategy profiling data (Item #5)
- `backend/app/services/plan_selection/calibration.py` (NEW): Loads strategy-profiling JSON, predicts execution strategy from task structure, computes profiling-grounded risk penalties. Calibrated normalizing constants (50k tokens, 30s latency).
- `backend/app/services/plan_selection/plan_scorer.py`: Added strategy-risk penalty (up to -0.25). Replaced arbitrary normalizing constants with calibrated values.
- `backend/app/services/plan_selection/plan_selector.py`: `min_cost` policy now uses `estimated_tokens` instead of `estimated_cost_usd` (local LLM is free).
- `backend/app/services/plan_selection/plan_candidate.py`: Added `predicted_strategy` field, auto-populated via `__post_init__`, serialized in `to_dict`/`from_dict`.
- `backend/tests/test_calibration.py` (NEW): 19 tests for calibration module.
- `backend/tests/test_cost_aware_plan_selection_e2e.py`: Updated for token-based min_cost.

### Commit 2: `58e434aa` — feat(oidc): v3 OIDC PKCE + webhooks with HMAC delivery and auth event emission (Item #7)
- `backend/app/api/v3/auth_oidc.py`: Wired to existing `oidc_service.py` — list providers, PKCE login with authorization URL, callback with session creation + httpOnly cookie redirect, logout. 4 routes, feature-flagged behind `AUTH_V3_OIDC`.
- `backend/app/api/v3/auth_webhooks.py`: Full webhook implementation — Pydantic body (`CreateWebhookBody`), HMAC-SHA256 signing (`compute_webhook_signature`/`verify_webhook_signature`), inline httpx delivery with exponential backoff retry (10s/60s/300s/900s), delivery logs endpoint, `emit_auth_webhook_event` helper. 4 routes, feature-flagged behind `AUTH_V3_WEBHOOKS`.
- `backend/app/api/v3/auth.py`: Wired `_emit_auth_event` into 6 auth flows — `user.created`, `session.created` (register, login, 2FA verify), `session.refreshed`, `session.revoked` (logout, password change), `user.updated`. Fixed 4 pre-existing lint errors (unused `remaining` vars, list comprehension).
- `backend/app/api/v3/AGENTS.md`: Updated OIDC and webhook sections from stub/warning to ✅ stable.
- `backend/tests/test_auth_v3_oidc.py` (NEW): 14 tests for v3 OIDC routes.
- `backend/tests/test_auth_v3_webhooks.py` (NEW): 33 tests for v3 webhook routes.

## WHAT DID NOT CHANGE BUT WAS TOUCHED:
- None — all edits are in the final commits.

## TESTS RUN + RESULT

```
$ cd /opt/flowmanner/backend && python -m pytest tests/test_auth_v3_oidc.py tests/test_auth_v3_webhooks.py tests/test_calibration.py tests/test_cost_aware_plan_selection_e2e.py -q
80 passed, 5 warnings in 11.07s

$ cd /opt/flowmanner/backend && python -m pytest tests/test_baseline_extractor.py tests/test_assertion_engine.py tests/test_substrate_circuit_breaker.py -q
85 passed, 2 warnings in 3.98s

$ cd /opt/flowmanner/backend && ruff check app/api/v3/auth_oidc.py app/api/v3/auth_webhooks.py app/api/v3/auth.py app/services/plan_selection/calibration.py app/services/plan_selection/plan_scorer.py app/services/plan_selection/plan_selector.py app/services/plan_selection/plan_candidate.py
All checks passed!
```

## STATUS

### git status
```
On branch main
Your branch is ahead of 'origin/main' by 2 commits.
  (use "git push" to publish your local commits)

nothing to commit, working tree clean
```

### git log --oneline origin/main..main
```
58e434aa feat(oidc): v3 OIDC PKCE + webhooks with HMAC delivery and auth event emission (Item #7)
f95ca0fb feat(calibration): plan-selection calibration with strategy profiling data (Item #5)
```

### docker compose exec backend alembic current
_(No new migrations — no model changes requiring Alembic in this session.)_

## NEXT SESSION HANDOFF

This session completed two roadmap items:

**Item #5 — Plan-selection calibration** is done. The `calibration.py` module loads the existing `strategy-profiling-results.json` and uses it to compute risk penalties and calibrated normalizing constants for plan scoring. The `min_cost` policy now uses token count (not USD cost) since the local LLM is free. 19 new tests.

**Item #7 — v3 OIDC + webhooks** is done. The OIDC v3 stubs are fully wired to the existing `oidc_service.py` (PKCE, callback, session creation, logout). The webhook stubs now have HMAC-SHA256 signing, httpx delivery with exponential backoff retry, delivery logs, and an `emit_auth_webhook_event` helper that's wired into all 6 auth flows (register, login, 2FA verify, refresh, revoke, update). 47 new tests total.

**Both commits are unpushed** — push to origin before deploying.

**Next items on the roadmap:**
- Items remaining in the Q3-Q4 execution plan (see `docs/EXECUTION-PLAN-Q3-Q4-2026.md`)
- No Alembic migrations needed for this session's changes
- The `_emit_auth_event` helper in `auth.py` is fire-and-forget — it silently logs failures at debug level. If webhook delivery needs reliability guarantees, a Celery task queue approach would be the next step.

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

- Untracked files: (none — all new files were committed)
- Deleted files: (none)

## END
