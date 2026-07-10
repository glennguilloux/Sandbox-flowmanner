# Exit Audit — Tier 1 Integrations Batch 1 (Linear + Sentry)

**Date:** June 28, 2026
**Session focus:** Complete Linear integration wiring + build user-facing Sentry integration + plan Batch 2
**Machine:** homelab (172.16.1.1)
**Commits:** `8a15ddb` on `origin/main` (backend), `b945a76` on `FlowmannerV2-frontend` (frontend)

---

## What Was Done

### Linear Integration (wiring existing infra — 70% already built)

| Change | File | Status |
|--------|------|--------|
| Add OAuth provider to v1 | `backend/app/core/oauth.py` | ✅ |
| Create manifest | `backend/integrations/manifests/linear.json` | ✅ |
| Add to AVAILABLE_INTEGRATIONS | `backend/app/api/v1/integrations.py` | ✅ |
| Add OAuth settings | `backend/app/config.py` (`LINEAR_OAUTH_CLIENT_ID`, `LINEAR_OAUTH_CLIENT_SECRET`) | ✅ |
| Frontend icon | `integrations-page-content.tsx` (`SiLinear` in ICON_MAP) | ✅ |
| 7 wiring tests | `backend/tests/test_linear_integration.py` | ✅ All passing |

### Sentry User-Facing Integration (new — built from scratch)

| Change | File | Status |
|--------|------|--------|
| SentryClient REST API | `backend/app/services/sentry/sentry_client.py` | ✅ |
| SentryConnector | `backend/app/services/connectors/sentry_connector.py` | ✅ |
| Webhook handler | `backend/app/api/v1/sentry_webhook.py` | ✅ |
| 8 bridge capabilities | `backend/app/services/integration_bridge.py` | ✅ |
| `_NON_OAUTH_CONFIGS` entry | `backend/app/services/integration_bridge.py` | ✅ |
| Manifest | `backend/integrations/manifests/sentry.json` | ✅ |
| AVAILABLE_INTEGRATIONS + connect handler | `backend/app/api/v1/integrations.py` | ✅ |
| CONNECTOR_TYPES + ConnectorManager registration | `connectors/__init__.py`, `connectors/manager.py` | ✅ |
| Webhook router registration | `backend/app/api/v1/__init__.py` | ✅ |
| Settings | `backend/app/config.py` (`SENTRY_WEBHOOK_SECRET`, `SENTRY_USER_OAUTH_CLIENT_ID/SECRET`) | ✅ |
| Frontend icon | `integrations-page-content.tsx` (`SiSentry` in ICON_MAP) | ✅ |
| 8 wiring tests | `backend/tests/test_sentry_integration.py` | ✅ All passing |

### Batch 2 Plan (Vercel + Jira)

| Deliverable | File | Status |
|-------------|------|--------|
| Comprehensive plan document | `.sisyphus/plans/PLAN-tier1-integrations-batch2.md` | ✅ Written |

### Deployment

| Action | Status |
|--------|--------|
| Backend deploy (`deploy-backend.sh`) | ✅ Deployed, health check passing |
| Frontend deploy (`deploy-frontend.sh`) | ✅ Deployed, `flowmanner.com` returning 200 |
| API through VPS (`flowmanner.com/api/health`) | ✅ 200 OK |

---

## What Was NOT Done (and Why)

| Item | Reason |
|------|--------|
| Linear OAuth credentials in `.env` | Linear's OAuth app creation UI is broken ("GitHub user already exists" error). API key path works. OAuth deferred until Linear fixes their platform. |
| Deploy frontend commit to origin | Frontend commit `b945a76` exists locally in `/home/glenn/FlowmannerV2-frontend/` but was not pushed. Glenn should push manually. |
| Vercel + Jira implementation | Deferred to Batch 2. Plan written at `.sisyphus/plans/PLAN-tier1-integrations-batch2.md`. |

---

## Issues Found & Fixed During Implementation

### 1. mypy type errors in SentryConnector (3 rounds to fix)

**Problem:** `self._client` initialized as `None` caused mypy errors ("None has no attribute").

**Fix applied:**
1. First attempt: string annotation `"SentryClient | None"` → ruff rejected (UP037: remove quotes)
2. Second attempt: `from __future__ import annotations` + direct import → syntax error (import block mangled)
3. Final fix: `from __future__ import annotations` + `TYPE_CHECKING` import + `assert self._client is not None` guards in all action methods

**Lesson:** Always use the `TYPE_CHECKING` pattern for forward references in connector files. The `from __future__ import annotations` + `TYPE_CHECKING` import is the canonical solution.

### 2. Test assertion mismatch (router paths)

**Problem:** Tests asserted `/webhook` in router paths but FastAPI router with prefix produces `/linear/webhook` and `/sentry/webhook`.

**Fix:** Changed assertions to use full paths (`/linear/webhook`, `/sentry/webhook`).

**Lesson:** When testing FastAPI routers with prefixes, the `router.routes` list includes the prefix in the path. Always check the actual path format.

### 3. SentryConnector not registered in ConnectorManager

**Problem:** Code reviewer caught that `SentryConnector` was added to `connectors/__init__.py` CONNECTOR_TYPES but not to `manager.py` CONNECTOR_CLASSES. The `_get_non_oauth_connector` uses `manager.get_connector_class()` which reads from CONNECTOR_CLASSES.

**Fix:** Added import + entry in both `__init__.py` and `manager.py`.

**Lesson:** When registering a new connector, always update BOTH registries: `CONNECTOR_TYPES` in `__init__.py` AND `CONNECTOR_CLASSES` in `manager.py`.

### 4. SentryConnector `_validate_credentials` auth_config key

**Problem:** The non-OAuth factory creates connectors with empty `auth_config={}`. The connector read `auth_config.get("token", "")` which was always empty. The OAuth bridge path uses `auth_config.get("access_token", "")`.

**Fix:** Support both keys: `auth_config.get("token", "") or auth_config.get("access_token", "")`. Return `True` when no token available (graceful degradation).

**Lesson:** Connectors that can be used via both the non-OAuth factory and the OAuth bridge need to check multiple auth_config key names.

### 5. `__all__` sort order in `connectors/__init__.py`

**Problem:** `ruff check` flagged `RUF022: __all__ is not sorted` after adding `SentryConnector`.

**Fix:** Sorted `__all__` alphabetically. Removed section comments (`# Base classes`, `# Manager`, `# Connectors`) since they broke sort order.

**Lesson:** When adding to `__all__`, insert alphabetically. Don't use section comments that group items — ruff requires pure alphabetical order.

---

## Linear OAuth Status

**Problem:** Linear's OAuth app creation at `linear.app/settings/api/applications/new` fails with "GitHub user already exists" error. This is a Linear platform bug — not related to our code.

**Impact:** The Linear integration page entry shows Linear with an "Connect" button, but clicking it will fail until `LINEAR_OAUTH_CLIENT_ID` and `LINEAR_OAUTH_CLIENT_SECRET` are set in `.env`.

**Workaround:** The existing `LINEAR_API_KEY` in `.env` already powers all agent actions (create issues, list teams, etc.) via the connector. OAuth is only needed for per-user connections through the integrations page.

**Next step:** When Linear fixes their bug, create the OAuth app, add credentials to `.env`, and restart the backend. No code changes needed.

---

## Key Architecture Decisions (Batch 1)

### 1. Sentry uses API token auth (not OAuth2)

**Decision:** Sentry integration uses API token auth (like Apiflow), stored encrypted in `IntegrationConnection`. Not OAuth2.

**Reasoning:** Works for both sentry.io and self-hosted Sentry. OAuth2 can be added later but adds complexity without blocking value.

### 2. Sentry has no global API key in settings

**Decision:** Unlike Linear (which has `LINEAR_API_KEY` as a workspace-wide fallback), Sentry has no global API key. The token is always per-user from `IntegrationConnection`.

**Reasoning:** The existing `SENTRY_API_TOKEN` in config is for Flowmanner's internal SDK monitoring, not for user-facing integration. Mixing them would be a security issue.

### 3. SentryConnector registered in both CONNECTOR_TYPES and CONNECTOR_CLASSES

**Decision:** Register in both places (same as all other connectors).

**Reasoning:** `__init__.py` `get_connector_class()` and `manager.py` `get_connector_class()` are separate methods used by different code paths.

---

## Files Changed (Backend — 14 files)

### New files (7)

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/services/sentry/sentry_client.py` | ~130 | Sentry REST API client |
| `backend/app/services/connectors/sentry_connector.py` | ~180 | Sentry BaseConnector wrapper |
| `backend/app/api/v1/sentry_webhook.py` | ~95 | Sentry webhook handler |
| `backend/integrations/manifests/linear.json` | ~30 | Linear manifest |
| `backend/integrations/manifests/sentry.json` | ~35 | Sentry manifest |
| `backend/tests/test_linear_integration.py` | ~65 | 7 Linear wiring tests |
| `backend/tests/test_sentry_integration.py` | ~70 | 8 Sentry wiring tests |

### Modified files (7)

| File | Change |
|------|--------|
| `backend/app/core/oauth.py` | +9 lines: Linear OAuthProviderConfig |
| `backend/app/config.py` | +8 lines: LINEAR_OAUTH_*, SENTRY_WEBHOOK_SECRET, SENTRY_USER_OAUTH_* |
| `backend/app/api/v1/integrations.py` | +22 lines: Linear+Sentry in AVAILABLE_INTEGRATIONS + Sentry connect handler |
| `backend/app/api/v1/__init__.py` | +2 lines: sentry_webhook_router registration |
| `backend/app/services/integration_bridge.py` | +55 lines: 8 Sentry capabilities + _NON_OAUTH_CONFIGS entry |
| `backend/app/services/connectors/__init__.py` | +3 lines: SentryConnector registration |
| `backend/app/services/connectors/manager.py` | +3 lines: SentryConnector in CONNECTOR_CLASSES |

### Frontend (1 file, separate repo)

| File | Change |
|------|--------|
| `src/app/[locale]/integrations/integrations-page-content.tsx` | +3 lines: SiLinear, SiSentry imports + ICON_MAP entries |

---

## Test Results

```
backend/tests/test_linear_integration.py     7 passed
backend/tests/test_sentry_integration.py     8 passed
─────────────────────────────────────────────────────
Total                                        15 passed in 0.19s
```

---

## Next Session Should Start With

1. **Read the Batch 2 plan:** `.sisyphus/plans/PLAN-tier1-integrations-batch2.md`
2. **Start with Vercel (Part A)** — standard OAuth2, quick win, proves the pattern
3. **Then Jira (Part B)** — complex OAuth with site discovery, ADF, token refresh
4. **Push the frontend commit** — `cd /home/glenn/FlowmannerV2-frontend && git push origin master` (commit `b945a76` is local-only)

---

## Environment State

| Item | Value |
|------|-------|
| Backend image | `workflows-backend:restored` (rebuilt 2026-06-28) |
| Frontend image | `flowmanner-frontend` (rebuilt 2026-06-28) |
| Backend commit | `8a15ddb` on `origin/main` |
| Frontend commit | `b945a76` local-only (not pushed) |
| Linear OAuth credentials | NOT set (Linear platform bug) |
| Sentry webhook secret | NOT set (optional, accepts unsigned when empty) |
| All containers healthy | ✅ backend, celery-worker, celery-beat, flowmanner-frontend, flowmanner-nginx |
