# EXIT AUDIT — 2026-06-28 — Batch 4 (Stripe + PagerDuty) + Batch 5 (Datadog + Airtable)

**Session:** Buffy (mimo-v2.5-pro) on homelab
**Scope:** Tier 1 Integrations Batch 4 + Batch 5 implementation, deployment

---

## WHAT CHANGED (one bullet per file, what + why)

### Backend — New files (22)

**Batch 4 — Stripe (13 actions):**
- `backend/app/services/stripe/__init__.py`: Stripe service package
- `backend/app/services/stripe/stripe_client.py`: Async REST client for Stripe API v1 (form-encoded POST bodies, `starting_after` cursor pagination, 13 endpoints)
- `backend/app/services/connectors/stripe_connector.py`: Stripe BaseConnector wrapper (13 actions, follows vercel_connector pattern)
- `backend/app/api/v1/stripe_webhook.py`: Stripe webhook handler with HMAC-SHA256 signature verification (`Stripe-Signature` header, `t=timestamp,v1=signature` format, 5-min replay protection)
- `backend/app/api/v1/stripe_oauth.py`: Custom Stripe OAuth callback — extracts `stripe_user_id` from token response, stores in `IntegrationConnection.account_id`
- `backend/integrations/manifests/stripe.json`: Stripe manifest (13 capabilities, category: development)
- `backend/tests/test_stripe_integration.py`: 8 wiring tests for Stripe integration

**Batch 4 — PagerDuty (12 actions):**
- `backend/app/services/pagerduty/__init__.py`: PagerDuty service package
- `backend/app/services/pagerduty/pagerduty_client.py`: Async REST client for PagerDuty REST API v2 (offset pagination, 12 endpoints)
- `backend/app/services/connectors/pagerduty_connector.py`: PagerDuty BaseConnector wrapper (12 actions)
- `backend/app/api/v1/pagerduty_webhook.py`: PagerDuty webhook handler with HMAC-SHA256 signature verification (`X-PagerDuty-Signature` header, handles V3 array payloads)
- `backend/integrations/manifests/pagerduty.json`: PagerDuty manifest (12 capabilities, category: development)
- `backend/tests/test_pagerduty_integration.py`: 7 wiring tests for PagerDuty integration

**Batch 5 — Datadog (12 actions):**
- `backend/app/services/datadog/__init__.py`: Datadog service package
- `backend/app/services/datadog/datadog_client.py`: Async REST client for Datadog API (v1/v2, monitors/incidents/dashboards/metrics/events)
- `backend/app/services/connectors/datadog_connector.py`: Datadog BaseConnector wrapper (12 actions)
- `backend/app/api/v1/datadog_webhook.py`: Datadog webhook handler with HMAC-SHA256 (`X-Datadog-Signature` header)
- `backend/integrations/manifests/datadog.json`: Datadog manifest (12 capabilities, category: development)
- `backend/tests/test_datadog_integration.py`: 7 wiring tests for Datadog integration

**Batch 5 — Airtable (9 actions):**
- `backend/app/services/airtable/__init__.py`: Airtable service package
- `backend/app/services/airtable/airtable_client.py`: Async REST client for Airtable REST API (bases/tables/records CRUD, `filter_by_formula` support)
- `backend/app/services/connectors/airtable_connector.py`: Airtable BaseConnector wrapper (9 actions)
- `backend/app/api/v1/airtable_webhook.py`: Airtable webhook handler with HMAC-SHA256 (`X-Airtable-Content-MAC` header)
- `backend/integrations/manifests/airtable.json`: Airtable manifest (9 capabilities, category: productivity)
- `backend/tests/test_airtable_integration.py`: 7 wiring tests for Airtable integration

### Backend — Modified files (8)

- `backend/app/core/oauth.py`: Added Stripe (Connect OAuth), PagerDuty (standard), Datadog (standard), Airtable (standard) OAuthProviderConfig entries
- `backend/app/config.py`: Added 12 new settings: STRIPE_*, PAGERDUTY_*, DATADOG_*, AIRTABLE_* (client ID, client secret, webhook secret each)
- `backend/app/api/v1/integrations.py`: Added all 4 to AVAILABLE_INTEGRATIONS; added Stripe redirect override for custom OAuth callback
- `backend/app/api/v1/__init__.py`: Registered stripe_oauth, stripe_webhook, pagerduty_webhook, datadog_webhook, airtable_webhook routers
- `backend/app/services/integration_bridge.py`: Added 13 Stripe + 12 PagerDuty + 12 Datadog + 9 Airtable bridge capabilities; added token refresh blocks for all 4 using generic `_refresh_oauth_token()`
- `backend/app/services/connectors/__init__.py`: Registered all 4 new connectors (imports, __all__, CONNECTOR_TYPES)
- `backend/app/services/connectors/manager.py`: Registered all 4 new connectors in CONNECTOR_CLASSES
- `backend/tests/test_cross_integration_workflow.py`: Updated to test all 10 Batches 1-5 integrations

---

## TESTS RUN + RESULT

### Integration wiring tests (32 total)
```
tests/test_stripe_integration.py (8 tests) — ALL PASSED
tests/test_pagerduty_integration.py (7 tests) — ALL PASSED
tests/test_datadog_integration.py (7 tests) — ALL PASSED
tests/test_airtable_integration.py (7 tests) — ALL PASSED
tests/test_cross_integration_workflow.py (3 tests) — ALL PASSED

======================== 32 passed in 0.20s ========================
```

### Ruff lint
```
All checks passed!
```

### Code review
```
No issues found. Implementation correctly follows existing patterns.
```

---

## ISSUES FOUND + FIXED DURING SESSION

1. **Test route path assertions wrong** — Tests checked for `"/webhook"` but router prefix means actual paths are `"/stripe/webhook"`, `"/pagerduty/webhook"`. Fixed all 3 test assertions.

2. **Ruff SIM108 (pagerduty_webhook.py)** — `if/else` block replaced with ternary operator per linter.

3. **Ruff PERF403 (stripe_client.py)** — `for k, v in kwargs.items(): body[k] = v` replaced with `body.update(kwargs)`.

4. **Pre-commit ruff-format** — 5 files reformatted by pre-commit hooks on first commit. Required `git add -A && git commit` retry.

5. **celery-beat container naming conflict during Batch 4 deploy** — `docker compose up -d --force-recreate` hit "container name already in use" for celery-beat. Worked around by restarting only the backend container specifically.

6. **Pre-deploy health check transient failure** — During Batch 5 deploy, `curl` returned HTTP 000 despite container being healthy. Container was already running new image from the rebuild. Verified health manually.

---

## KEY DESIGN DECISIONS

1. **Stripe uses custom OAuth callback** (`stripe_oauth.py`) — Needed to extract `stripe_user_id` (e.g., `acct_1234abcd`) from token response. Simpler than Jira's callback (no site discovery). Stored in `IntegrationConnection.account_id`.

2. **PagerDuty uses standard OAuth callback** — No custom callback needed. Same pattern as Figma. Saves ~1 file.

3. **Datadog uses standard OAuth callback** — Same as PagerDuty/Figma. API uses v1 for most endpoints, v2 for incidents/users.

4. **Airtable uses standard OAuth callback** — PKCE recommended by Airtable but not enforced server-side. Standard `grant_type=authorization_code` works.

5. **All 4 use generic `_refresh_oauth_token()`** — The same helper that handles Jira/Confluence/Figma works for all new integrations. No custom refresh logic needed.

6. **Stripe form-encoded POST bodies** — Stripe requires `application/x-www-form-urlencoded` for POST/PUT, not JSON. The `StripeClient._flatten_params()` helper handles nested dict→bracket notation conversion.

7. **Airtable rate limits are strict** (5 req/s per base) — Connector uses conservative `RateLimitConfig` with 5 req/s.

---

## STATUS

```
$ git log --oneline -3
f67ba29 feat(integrations): add Datadog + Airtable integrations (Batch 5)
d1713fe feat(integrations): add Stripe + PagerDuty integrations (Batch 4)
docs: update exit audit with swagger fix + deploy status
```

---

## NEXT SESSION HANDOFF

> **Batches 4+5 (Stripe, PagerDuty, Datadog, Airtable) are fully implemented, tested, committed, pushed, and deployed.** Backend is healthy at `http://127.0.0.1:8000/api/health` (200). The next agent should:
>
> 1. **Set up OAuth apps** — Glenn needs to create OAuth apps for all 4 services and add env vars to `/opt/flowmanner/.env`:
>    - Stripe: Platform client_id (`ca_...`) + secret key (`sk_...`) + webhook secret (`whsec_...`) at https://dashboard.stripe.com/connect/apps
>    - PagerDuty: OAuth client at https://developer.pagerduty.com/
>    - Datadog: OAuth app at https://app.datadoghq.com/account/settings#integrations
>    - Airtable: OAuth integration at https://airtable.com/developers/web
>
> 2. **Deploy frontend** — Add `SiStripe`, `SiPagerduty`, `SiDatadog`, `SiAirtable` to ICON_MAP in frontend files (same pattern as Batch 3). Then `bash /opt/flowmanner/deploy-frontend.sh`.
>
> 3. **Consider Batch 6 candidates** — GitHub expansion (Actions, Releases), Slack expansion (Block Kit, Modals), or new integrations (Intercom, ClickUp, Asana).
>
> **Gotchas:**
> - Stripe's `client_id` is the platform's Connect client_id (starts with `ca_`), NOT the API key. The `client_secret` is the platform's secret key (`sk_...`).
> - The `celery-beat` container naming conflict during deploy is a recurring Docker issue. If `deploy-backend.sh` fails on this, restart only the backend: `cd /opt/flowmanner && docker compose up -d --no-deps --force-recreate backend`.
> - Airtable has very strict rate limits (5 req/s per base). The connector is configured conservatively.

---

## INTEGRATION STATUS MATRIX

| Batch | Integration | Backend | Tests | Frontend Icon | Committed | Deployed |
|-------|-------------|---------|-------|---------------|-----------|----------|
| 1 | Linear | ✅ | ✅ | ✅ | ✅ | ✅ |
| 1 | Sentry | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2 | Vercel | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2 | Jira | ✅ | ✅ | ✅ | ✅ | ✅ |
| 3 | Confluence | ✅ | ✅ | ✅ | ✅ | ✅ |
| 3 | Figma | ✅ | ✅ | ✅ | ✅ | ✅ |
| 4 | Stripe | ✅ | ✅ (8 new) | ❌ needed | ✅ `d1713fe` | ✅ |
| 4 | PagerDuty | ✅ | ✅ (7 new) | ❌ needed | ✅ `d1713fe` | ✅ |
| 5 | Datadog | ✅ | ✅ (7 new) | ❌ needed | ✅ `f67ba29` | ✅ |
| 5 | Airtable | ✅ | ✅ (7 new) | ❌ needed | ✅ `f67ba29` | ✅ |

---

## COMMITS THIS SESSION

| Hash | Message | Files |
|------|---------|-------|
| `d1713fe` | `feat(integrations): add Stripe + PagerDuty integrations (Batch 4)` | 21 files, +1793 |
| `f67ba29` | `feat(integrations): add Datadog + Airtable integrations (Batch 5)` | 20 files, +1456 |

---

## ENV VARS NEEDED (add to `/opt/flowmanner/.env`)

```bash
# Stripe (Batch 4)
STRIPE_OAUTH_CLIENT_ID=          # Platform client_id (ca_...)
STRIPE_OAUTH_CLIENT_SECRET=      # Platform secret key (sk_...)
STRIPE_WEBHOOK_SECRET=           # Webhook endpoint signing secret (whsec_...)

# PagerDuty (Batch 4)
PAGERDUTY_OAUTH_CLIENT_ID=
PAGERDUTY_OAUTH_CLIENT_SECRET=
PAGERDUTY_WEBHOOK_SECRET=

# Datadog (Batch 5)
DATADOG_OAUTH_CLIENT_ID=
DATADOG_OAUTH_CLIENT_SECRET=
DATADOG_WEBHOOK_SECRET=

# Airtable (Batch 5)
AIRTABLE_OAUTH_CLIENT_ID=
AIRTABLE_OAUTH_CLIENT_SECRET=
AIRTABLE_WEBHOOK_SECRET=
```
