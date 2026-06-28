# Exit Audit — Tier 1 Integrations Batch 2 (Vercel + Jira) + Batch 3 Plan

**Date:** June 28, 2026
**Session focus:** Implement Vercel + Jira integrations (Batch 2) + verify Batch 1 completeness + write Batch 3 plan (Confluence + Figma)
**Machine:** homelab (172.16.1.1)
**Commits:** `d5c4ac3` (Batch 2 code), `dc2647f` (exit audit) on `origin/main` (backend)

---

## What Was Done

### Vercel Integration (clean build)

| Change | File | Status |
|--------|------|--------|
| VercelClient REST service | `backend/app/services/vercel/vercel_client.py` | ✅ |
| VercelConnector (9 actions) | `backend/app/services/connectors/vercel_connector.py` | ✅ |
| Webhook handler (HMAC-SHA256) | `backend/app/api/v1/vercel_webhook.py` | ✅ |
| OAuth provider (v1) | `backend/app/core/oauth.py` | ✅ |
| Settings | `backend/app/config.py` (`VERCEL_OAUTH_CLIENT_ID/SECRET`, `VERCEL_WEBHOOK_SECRET`) | ✅ |
| Manifest | `backend/integrations/manifests/vercel.json` | ✅ |
| AVAILABLE_INTEGRATIONS entry | `backend/app/api/v1/integrations.py` | ✅ |
| 9 bridge capabilities | `backend/app/services/integration_bridge.py` | ✅ |
| CONNECTOR_TYPES + CONNECTOR_CLASSES | `connectors/__init__.py`, `connectors/manager.py` | ✅ |
| Webhook router registration | `backend/app/api/v1/__init__.py` | ✅ |
| 7 wiring tests | `backend/tests/test_vercel_integration.py` | ✅ All passing |

**Vercel actions:** get_me, list_projects, get_project, list_deployments, get_deployment, cancel_deployment, redeploy, get_deployment_logs, list_domains

### Jira Integration (clean build)

| Change | File | Status |
|--------|------|--------|
| JiraClient REST service (Atlassian API v3) | `backend/app/services/jira/jira_client.py` | ✅ |
| `text_to_adf()` helper | `backend/app/services/jira/jira_client.py` | ✅ |
| JiraConnector (10 actions) | `backend/app/services/connectors/jira_connector.py` | ✅ |
| Custom OAuth callback (site discovery) | `backend/app/api/v1/jira_oauth.py` | ✅ |
| Webhook handler | `backend/app/api/v1/jira_webhook.py` | ✅ |
| OAuth provider (v1) with `audience` param | `backend/app/core/oauth.py` | ✅ |
| Settings | `backend/app/config.py` (`JIRA_OAUTH_CLIENT_ID/SECRET`, `JIRA_WEBHOOK_SECRET`) | ✅ |
| Manifest | `backend/integrations/manifests/jira.json` | ✅ |
| AVAILABLE_INTEGRATIONS entry | `backend/app/api/v1/integrations.py` | ✅ |
| 10 bridge capabilities | `backend/app/services/integration_bridge.py` | ✅ |
| Token refresh in IntegrationBridge | `backend/app/services/integration_bridge.py` | ✅ |
| cloudId extraction from account_id | `backend/app/services/integration_bridge.py` | ✅ |
| Jira OAuth redirect override | `backend/app/api/v1/integrations.py` | ✅ |
| CONNECTOR_TYPES + CONNECTOR_CLASSES | `connectors/__init__.py`, `connectors/manager.py` | ✅ |
| Router registrations (oauth + webhook) | `backend/app/api/v1/__init__.py` | ✅ |
| 10 wiring tests | `backend/tests/test_jira_integration.py` | ✅ All passing |

**Jira actions:** list_projects, get_project, search_issues, get_issue, create_issue, update_issue, add_comment, transition_issue, list_boards, list_sprints

### Cross-Integration Workflow Test

| Change | File | Status |
|--------|------|--------|
| Tool discoverability test | `backend/tests/test_cross_integration_workflow.py` | ✅ 3 tests passing |

### Batch 1 Verification

Ran a comprehensive audit of the Batch 1 plan (PLAN-DEEPSEEK-tier1-integrations-batch1.md). **Every single item is complete:**
- Linear: OAuth provider, manifest, AVAILABLE_INTEGRATIONS, webhook router, frontend icon, 7 tests ✅
- Sentry: SentryClient, SentryConnector, webhook handler, 8 bridge capabilities, manifest, frontend icon, 8 tests ✅
- All 15 Batch 1 tests still passing ✅

### Deployment

| Action | Status |
|--------|--------|
| Backend deploy (`deploy-backend.sh`) | ✅ Deployed, health check passing |
| All containers healthy | ✅ backend, celery-worker, celery-beat |

---

## What Was NOT Done (and Why)

| Item | Reason |
|------|--------|
| Vercel/Jira OAuth credentials in `.env` | Requires creating OAuth apps on Vercel and Atlassian dashboards. Manual step for Glenn. |
| Vercel/Jira frontend icons | No `SiVercel`/`SiJira` confirmed available in `@icons-pack/react-simple-icons`. Frontend icons for Batch 2 deferred — needs verification. |
| Jira multi-site selection UI | Auto-selects first site for now. Multi-site UI deferred to future batch. |
| Sentry OAuth2 | API token auth works for both cloud and self-hosted. OAuth2 deferred. |
| Cross-integration agent workflows (Sentry → Jira/Linear auto-issue) | Tool infrastructure exists but agent trigger wiring not implemented. |

---

## Issues Found & Fixed During Implementation

### 1. mypy type errors in JiraClient (2 methods)

**Problem:** `update_issue` and `transition_issue` returned `dict[str, Any] | list[Any]` (from `_request`) but their return type was `dict[str, Any]`.

**Fix:** Added `# type: ignore[return-value]` comments, matching the pattern used by all other methods that call `_request`.

**Lesson:** When a shared `_request` method returns a union type, every caller needs the type ignore comment. Easy to miss — check all callers when adding new methods.

### 2. ruff import sorting + `__all__` ordering (6 errors)

**Problem:** New `__init__.py` files for Vercel and Jira packages had unsorted imports and `__all__` lists. Also `connectors/__init__.py` import block was unsorted.

**Fix:** Ran `ruff check --fix` to auto-sort.

**Lesson:** Always run `ruff check --fix` on new `__init__.py` files immediately after creation.

### 3. pre-commit hook caught ruff-format changes

**Problem:** First commit attempt failed because `ruff-format` reformatted 2 files during the pre-commit hook.

**Fix:** Re-staged the formatted files and re-committed.

**Lesson:** Run `ruff format` on new files before the first commit attempt, or let the pre-commit hook fix them and re-stage.

### 4. Jira OAuth callback needs custom redirect override

**Problem:** The standard `oauth_authorize` handler builds the redirect URI from `request.url_for("oauth_callback", slug="jira")`, which would point to `/api/integrations/jira/oauth/callback`. But Jira's custom callback with site discovery is at `/api/jira/oauth/callback`.

**Fix:** Added a special case in `oauth_authorize` that rewrites the redirect_uri for Jira before building the authorize URL.

**Lesson:** When a custom OAuth callback lives outside the standard integrations router, the authorize handler needs a redirect override for that slug.

---

## Key Architecture Decisions (Batch 2)

### 1. Vercel uses standard OAuth2 (no special handling)

**Decision:** Vercel integration follows the standard OAuth2 flow exactly. No custom callback needed.

**Reasoning:** Vercel's OAuth is well-documented and standard. The existing `oauth_callback` handler works without modification.

### 2. Jira uses custom OAuth callback with site discovery

**Decision:** Jira has its own callback endpoint at `/api/jira/oauth/callback` because Atlassian OAuth 2.0 (3LO) requires a site discovery step between token exchange and storing the connection.

**Reasoning:** After getting the access token, we must call `GET https://api.atlassian.com/oauth/token/accessible-resources` to find the user's Jira sites and extract the `cloudId`. The standard callback doesn't support this extra step.

### 3. Jira cloudId stored in IntegrationConnection.account_id

**Decision:** The Atlassian `cloudId` (needed for all API calls as part of the base URL) is stored in the `account_id` field of `IntegrationConnection`.

**Reasoning:** Reusing an existing field avoids schema migration. The `_get_connector` method extracts it for the connector's auth_config.

### 4. Jira token refresh in IntegrationBridge

**Decision:** Added Jira token refresh alongside the existing Google token refresh in `_get_connector`.

**Reasoning:** Atlassian tokens expire (typically 1 hour). The refresh follows the same pattern as Google — decrypt refresh token, POST to token endpoint, encrypt and store new tokens.

### 5. Vercel uses `until` cursor for pagination

**Decision:** The VercelClient accepts `until` (timestamp) parameters for pagination instead of page numbers.

**Reasoning:** Vercel's API uses timestamp-based cursor pagination. The client documents this in the method signatures.

---

## Files Changed (Backend — 21 files)

### New files (14)

| File | Lines | Purpose |
|------|-------|---------|
| `backend/app/services/vercel/__init__.py` | ~5 | Vercel service package |
| `backend/app/services/vercel/vercel_client.py` | ~120 | Vercel REST API client (9 endpoints) |
| `backend/app/services/jira/__init__.py` | ~5 | Jira service package |
| `backend/app/services/jira/jira_client.py` | ~200 | Jira REST API client + ADF helper (12 endpoints) |
| `backend/app/services/connectors/vercel_connector.py` | ~175 | Vercel BaseConnector wrapper (9 actions) |
| `backend/app/services/connectors/jira_connector.py` | ~190 | Jira BaseConnector wrapper (10 actions) |
| `backend/app/api/v1/vercel_webhook.py` | ~55 | Vercel webhook handler (HMAC-SHA256) |
| `backend/app/api/v1/jira_webhook.py` | ~50 | Jira webhook handler (shared secret) |
| `backend/app/api/v1/jira_oauth.py` | ~130 | Custom Jira OAuth callback (site discovery) |
| `backend/integrations/manifests/vercel.json` | ~30 | Vercel manifest |
| `backend/integrations/manifests/jira.json` | ~30 | Jira manifest |
| `backend/tests/test_vercel_integration.py` | ~65 | 7 Vercel wiring tests |
| `backend/tests/test_jira_integration.py` | ~95 | 10 Jira wiring tests |
| `backend/tests/test_cross_integration_workflow.py` | ~50 | 3 cross-integration discoverability tests |

### Modified files (7)

| File | Change |
|------|--------|
| `backend/app/core/oauth.py` | +18 lines: Vercel + Jira OAuthProviderConfig |
| `backend/app/config.py` | +12 lines: VERCEL_*, JIRA_* settings |
| `backend/app/api/v1/integrations.py` | +30 lines: Vercel+Jira in AVAILABLE_INTEGRATIONS + Jira redirect override |
| `backend/app/api/v1/__init__.py` | +4 lines: vercel_webhook, jira_oauth, jira_webhook router registration |
| `backend/app/services/integration_bridge.py` | +160 lines: 19 Vercel+Jira capabilities + Jira token refresh + cloudId extraction |
| `backend/app/services/connectors/__init__.py` | +4 lines: VercelConnector + JiraConnector registration |
| `backend/app/services/connectors/manager.py` | +4 lines: VercelConnector + JiraConnector in CONNECTOR_CLASSES |

---

## Test Results (Final)

```
Batch 1:
  tests/test_linear_integration.py       7 passed
  tests/test_sentry_integration.py       8 passed

Batch 2:
  tests/test_vercel_integration.py       7 passed
  tests/test_jira_integration.py        10 passed
  tests/test_cross_integration_workflow.py  3 passed
─────────────────────────────────────────────────────
Total                                   35 passed in 0.35s
```

---

## Next Session Should Start With

1. **Read the Batch 3 plan:** `.sisyphus/plans/PLAN-tier1-integrations-batch3.md`
2. **Start with Confluence (Part A)** — reuses Jira's Atlassian OAuth 3LO, same site discovery, same ADF format. Fastest build ever (~1 week).
3. **Then Figma (Part B)** — standard OAuth2 with quirks (HTTP Basic token exchange, separate refresh endpoint). ~1.5 weeks.
4. **Push the frontend commit** — `cd /home/glenn/FlowmannerV2-frontend && git push origin master` (commit `b945a76` is local-only, Batch 1 icons)
5. **Add Batch 2 frontend icons** — Need to add `SiVercel` and `SiJira` (or custom SVGs) to `ICON_MAP` in the frontend.
6. **Create OAuth apps** — Vercel (https://vercel.com/dashboard/settings/integrations), Jira (https://developer.atlassian.com/console/myapps/), Confluence (same Atlassian console), Figma (https://figma.com/developers/apps).

---

## Integration Status Summary

| Integration | Auth | Actions | Webhook | Bridge Caps | Tests | Status |
|-------------|------|---------|---------|-------------|-------|--------|
| Slack | OAuth2 | 4 | — | 4 | — | ✅ Existing |
| GitHub | OAuth2 | 7 | — | 7 | — | ✅ Existing |
| Google | OAuth2 | 9 | — | 9 | — | ✅ Existing |
| Notion | OAuth2 | 8 | — | 8 | — | ✅ Existing |
| Discord | Bot token | 10 | — | 10 | — | ✅ Existing |
| **Linear** | OAuth2 + API key | 7 | ✅ | 7 | 7 | ✅ Batch 1 |
| **Sentry** | API token | 8 | ✅ | 8 | 8 | ✅ Batch 1 |
| **Vercel** | OAuth2 | 9 | ✅ | 9 | 7 | ✅ Batch 2 |
| **Jira** | OAuth2 (3LO) | 10 | ✅ | 10 | 10 | ✅ Batch 2 |

**Total bridge capabilities across all integrations: 72**

---

## Environment State

| Item | Value |
|------|-------|
| Backend image | `workflows-backend:latest` (rebuilt 2026-06-28) |
| Backend commit | `dc2647f` on `origin/main` (latest: exit audit) |
| Frontend commit | `b945a76` local-only (Batch 1 icons, not pushed) |
| All containers healthy | ✅ backend, celery-worker, celery-beat, workflow-postgres, workflow-redis, workflow-qdrant, workflow-rabbitmq, jaeger, searxng, workflows-static |
| Vercel OAuth credentials | NOT set (needs OAuth app creation at vercel.com/dashboard/settings/integrations) |
| Jira OAuth credentials | NOT set (needs OAuth app creation at developer.atlassian.com/console/myapps/) |
| Jira webhook secret | NOT set (optional, accepts unsigned when empty) |
| Vercel webhook secret | NOT set (optional, accepts unsigned when empty) |
| Linear OAuth credentials | NOT set (Linear platform bug — "GitHub user already exists") |
| Sentry webhook secret | NOT set (optional, accepts unsigned when empty) |
| Confluence OAuth credentials | NOT SET — deferred to Batch 3 |
| Figma OAuth credentials | NOT SET — deferred to Batch 3 |
