# EXIT AUDIT — 2026-06-28 — Batch 7 (Asana + GitLab)

**Session:** Buffy (mimo-v2.5-pro) on homelab
**Duration:** Single session
**Scope:** Tier 1 Integrations Batch 7 implementation — Asana (10 actions) + GitLab (14 actions)

---

=== EXIT AUDIT ===

WHAT CHANGED (one bullet per file, what + why):

**Batch 7 — Asana (new integration, 10 actions):**
- `backend/app/services/asana/__init__.py`: Asana service package. (NEW)
- `backend/app/services/asana/asana_client.py`: Async REST client for Asana API. All endpoints use `opt_fields` to avoid sparse responses. 10 endpoints. (NEW)
- `backend/app/services/connectors/asana_connector.py`: Asana BaseConnector wrapper, 10 actions, follows vercel_connector pattern. (NEW)
- `backend/app/api/v1/asana_webhook.py`: Asana webhook handler with HMAC-SHA256 signature verification (`X-Hook-Signature` header). Includes challenge handshake support. (NEW)
- `backend/integrations/manifests/asana.json`: Asana manifest (10 capabilities, category: productivity). (NEW)
- `backend/tests/test_asana_integration.py`: 7 wiring tests for Asana integration. (NEW)

**Batch 7 — GitLab (new integration, 14 actions):**
- `backend/app/services/gitlab/__init__.py`: GitLab service package. (NEW)
- `backend/app/services/gitlab/gitlab_client.py`: Async REST client for GitLab API v4. Supports self-hosted instances via configurable `base_url`. 19 client methods (14 exposed as connector actions). (NEW)
- `backend/app/services/connectors/gitlab_connector.py`: GitLab BaseConnector wrapper, 14 actions, follows vercel_connector pattern. Configurable `base_url` for self-hosted instances. (NEW)
- `backend/app/api/v1/gitlab_webhook.py`: GitLab webhook handler with `X-Gitlab-Token` shared secret verification. (NEW)
- `backend/integrations/manifests/gitlab.json`: GitLab manifest (14 capabilities, category: development). (NEW)
- `backend/tests/test_gitlab_integration.py`: 7 wiring tests for GitLab integration. (NEW)

**Batch 7 — Registration + Config:**
- `backend/app/core/oauth.py`: Added Asana OAuthProviderConfig (authorize: `app.asana.com/-/oauth_authorize`, token: `app.asana.com/-/oauth_token`) + GitLab OAuthProviderConfig (authorize: `gitlab.com/oauth/authorize`, token: `gitlab.com/oauth/token`, scopes: `["api"]`)
- `backend/app/config.py`: Added ASANA_OAUTH_CLIENT_ID, ASANA_OAUTH_CLIENT_SECRET, ASANA_WEBHOOK_SECRET, GITLAB_OAUTH_CLIENT_ID, GITLAB_OAUTH_CLIENT_SECRET, GITLAB_WEBHOOK_SECRET settings
- `backend/app/api/v1/integrations.py`: Added Asana (category: productivity) + GitLab (category: development) to AVAILABLE_INTEGRATIONS
- `backend/app/api/v1/__init__.py`: Registered asana_webhook_router + gitlab_webhook_router
- `backend/app/services/connectors/__init__.py`: Registered AsanaConnector + GitLabConnector (imports, __all__, CONNECTOR_TYPES)
- `backend/app/services/connectors/manager.py`: Registered AsanaConnector + GitLabConnector in CONNECTOR_CLASSES
- `backend/app/services/integration_bridge.py`: Added 10 Asana + 14 GitLab bridge capabilities + token refresh blocks using generic `_refresh_oauth_token()`

**Batch 7 — Cross-integration test update:**
- `backend/tests/test_cross_integration_workflow.py`: Added assertions for Asana (10 bridge caps), GitLab (14 bridge caps). Updated connector manager and CONNECTOR_TYPES assertions.

WHAT DID NOT CHANGE BUT WAS TOUCHED:
  - none

TESTS RUN + RESULT (integration-specific tests):

```
tests/test_asana_integration.py (7 tests) — ALL PASSED
tests/test_gitlab_integration.py (7 tests) — ALL PASSED
tests/test_cross_integration_workflow.py (3 tests) — ALL PASSED
tests/test_intercom_integration.py (7 tests) — ALL PASSED
tests/test_github_connector.py (27 tests) — ALL PASSED
tests/test_slack_connector.py (32 tests) — ALL PASSED

======================== 83 passed in 0.47s ========================
```

Ruff lint:
```
All checks passed!
```

=== STATUS (run these and paste the output, do not paraphrase) ===

□ git status
```
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean
```

□ git fetch origin && git log --oneline origin/main..main
```
(empty — local is up to date with origin/main)
```

□ git log --oneline -5
```
986877c feat(integrations): add Asana + GitLab integrations (Batch 7)
9c856ea docs: session exit audit handoff — Batch 6 complete, Batch 7 planned
382fe9d docs: Batch 7 plan — Asana + GitLab
bf87537 docs: exit audit for Batch 6 (GitHub expansion, Slack expansion, Intercom)
67b13ee feat(integrations): add GitHub expansion, Slack expansion, and Intercom (Batch 6)
```

□ docker compose exec backend alembic current
```
fix_search_vector_trigger_001 (head)
```

□ curl http://127.0.0.1:8000/api/health
```json
{
  "status": "ok",
  "service": "workflows-backend",
  "version": "production",
  "components": {
    "database": {"status": "ok", "latency_ms": 1.4},
    "redis": {"status": "ok", "latency_ms": 1.0},
    "langfuse": {"status": "ok", "circuits": "closed"},
    "llm_provider": {"status": "ok", "model": "deepseek/deepseek-v4-flash"}
  }
}
```

=== NEXT SESSION HANDOFF ===

> **Batch 7 is fully implemented, tested, deployed, and committed.** The backend is healthy and running the latest image with all 15 integrations (160 bridge capabilities). One commit landed on origin/main:
> - `986877c` — feat(integrations): add Asana + GitLab integrations (Batch 7) — 20 files, +1640
>
> **Integration status:** 15 integrations total (Batches 1-7), 160 bridge capabilities. All integration-specific tests passing (83/83). Backend deployed and healthy.
>
> **Next agent should:**
> 1. **Wait for Glenn to create OAuth apps** — Asana at https://app.asana.com/app and GitLab at https://gitlab.com/-/user_settings/applications. Redirect URIs: `https://flowmanner.com/api/integrations/{asana,gitlab}/oauth/callback`. Add env vars to `/opt/flowmanner/.env`, then restart backend.
> 2. **Consider expanding existing integrations** — Notion (database writes), Linear (projects/cycles/roadmaps), or GitHub (more GraphQL mutations).
> 3. **Future Batch 8+ candidates** — ClickUp, AWS, Cloudflare, Twilio, HubSpot. See `plans/PLAN-tier1-integrations-batch7.md` for the full list.
>
> **Gotchas:**
> - Asana responses are sparse by default — the client pre-sets `opt_fields` on all endpoints. Don't add new Asana endpoints without `opt_fields`.
> - GitLab supports self-hosted instances — the connector accepts configurable `base_url` per connection (defaulting to `https://gitlab.com/api/v4`).
> - Both Asana and GitLab tokens expire (1h and 2h respectively) and support refresh tokens. The generic `_refresh_oauth_token()` helper handles both.
> - The `celery-beat` container naming conflict during deploy is a recurring Docker issue. If `deploy-backend.sh` fails on this, restart only the backend: `cd /opt/flowmanner && docker compose up -d --no-deps --force-recreate backend`.
> - Pre-commit hooks enforce ruff UP038 (use `X | Y` union syntax instead of `(X, Y)` tuple in isinstance). Fix before committing.
> - ruff-format auto-reformatted `integration_bridge.py` on commit — the pre-commit hook staged the fix automatically on retry.

=== FILES THIS AGENT DID NOT TOUCH BUT EXIST ===

- Untracked files: none (working tree clean)
- Deleted files: none

=== COMMITS THIS SESSION ===

| Hash | Message | Files |
|------|---------|-------|
| `986877c` | `feat(integrations): add Asana + GitLab integrations (Batch 7)` | 20 files, +1640 |

=== CAPABILITY COUNTS ===

| Integration | Before | After | Change |
|-------------|--------|-------|--------|
| Asana bridge | — | 10 | new |
| Asana connector | — | 10 | new |
| GitLab bridge | — | 14 | new |
| GitLab connector | — | 14 | new |
| **Total bridge capabilities** | **136** | **160** | **+24** |

=== INTEGRATION STATUS MATRIX ===

| Batch | Integration | Backend | Tests | Frontend Icon | Committed | Deployed |
|-------|-------------|---------|-------|---------------|-----------|----------|
| 1 | Linear | ✅ | ✅ | ✅ | ✅ | ✅ |
| 1 | Sentry | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2 | Vercel | ✅ | ✅ | ✅ | ✅ | ✅ |
| 2 | Jira | ✅ | ✅ | ✅ | ✅ | ✅ |
| 3 | Confluence | ✅ | ✅ | ✅ | ✅ | ✅ |
| 3 | Figma | ✅ | ✅ | ✅ | ✅ | ✅ |
| 4 | Stripe | ✅ | ✅ (8) | ✅ | ✅ | ✅ |
| 4 | PagerDuty | ✅ | ✅ (7) | ✅ | ✅ | ✅ |
| 5 | Datadog | ✅ | ✅ (7) | ✅ | ✅ | ✅ |
| 5 | Airtable | ✅ | ✅ (7) | ✅ | ✅ | ✅ |
| 6 | GitHub (expanded) | ✅ | ✅ (27) | ✅ | ✅ | ✅ |
| 6 | Slack (expanded) | ✅ | ✅ (32) | ✅ | ✅ | ✅ |
| 6 | Intercom | ✅ | ✅ (7) | ✅ | ✅ | ✅ |
| 7 | Asana | ✅ | ✅ (7) | ⏳ | ✅ `986877c` | ✅ |
| 7 | GitLab | ✅ | ✅ (7) | ⏳ | ✅ `986877c` | ✅ |

Note: Frontend icons for Asana (SiAsana) and GitLab (SiGitlab) not yet added — requires frontend changes + deploy.

=== ENV VARS NEEDED (add to /opt/flowmanner/.env) ===

```bash
# Asana (Batch 7 — implemented, needs OAuth app)
ASANA_OAUTH_CLIENT_ID=
ASANA_OAUTH_CLIENT_SECRET=
ASANA_WEBHOOK_SECRET=

# GitLab (Batch 7 — implemented, needs OAuth app)
GITLAB_OAUTH_CLIENT_ID=
GITLAB_OAUTH_CLIENT_SECRET=
GITLAB_WEBHOOK_SECRET=
```

=== END ===
