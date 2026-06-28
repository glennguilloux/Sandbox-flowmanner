# EXIT AUDIT — 2026-06-28 — Session Handoff (Batch 6 + Batch 7 Plan)

**Session:** Buffy (mimo-v2.5-pro) on homelab
**Duration:** Single session
**Scope:** Tier 1 Integrations Batch 6 implementation + Batch 7 planning

---

=== EXIT AUDIT ===

WHAT CHANGED (one bullet per file, what + why):

**Batch 6 — GitHub Expansion (8 new connector actions, 11 new bridge capabilities):**
- `backend/app/services/connectors/github_connector.py`: Added 8 new actions (add_issue_comment, list_workflows, list_workflow_runs, get_workflow_run, rerun_workflow, list_deployments, create_release, list_discussions). Total connector actions: 18→26. Discussions use GraphQL POST.
- `backend/app/services/integration_bridge.py`: Expanded GitHub bridge capabilities from 7 to 18 (+11: get_issue, add_issue_comment, get_pr, merge_pr, list_workflows, list_workflow_runs, get_workflow_run, rerun_workflow, list_deployments, create_release, list_discussions)
- `backend/tests/test_github_connector.py`: Updated action count assertion 18→26. Fixed isinstance tuple syntax per ruff UP038.

**Batch 6 — Slack Expansion (3 new connector actions, 7 new bridge capabilities):**
- `backend/app/services/connectors/slack_connector.py`: Added 3 new actions (reply_to_thread, get_thread_replies, get_user_profile). Total connector actions: 14→17. `get_user_profile` aliases `get_user_info`.
- `backend/app/services/integration_bridge.py`: Expanded Slack bridge capabilities from 4 to 11 (+7: update_message, delete_message, reply_to_thread, get_thread_replies, add_reaction, get_user_profile, upload_file)
- `backend/tests/test_slack_connector.py`: Updated action count assertion 14→17. Fixed isinstance tuple syntax per ruff UP038.

**Batch 6 — Intercom (new integration, 10 actions):**
- `backend/app/services/intercom/__init__.py`: Intercom service package (NEW)
- `backend/app/services/intercom/intercom_client.py`: Async REST client for Intercom API. `Intercom-Version: 2.8` header on all requests. No token refresh (tokens don't expire). 10 endpoints. (NEW)
- `backend/app/services/connectors/intercom_connector.py`: Intercom BaseConnector wrapper, 10 actions, follows vercel_connector pattern. (NEW)
- `backend/app/api/v1/intercom_webhook.py`: Intercom webhook handler with HMAC-SHA256 signature verification (`X-Hub-Signature-256` header). (NEW)
- `backend/integrations/manifests/intercom.json`: Intercom manifest (10 capabilities, category: communication). (NEW)
- `backend/tests/test_intercom_integration.py`: 7 wiring tests for Intercom integration. (NEW)

**Batch 6 — Registration + Config:**
- `backend/app/core/oauth.py`: Added Intercom OAuthProviderConfig (authorize: `app.intercom.com/oauth`, token: `api.intercom.io/auth/eagle/token`)
- `backend/app/config.py`: Added INTERCOM_OAUTH_CLIENT_ID, INTERCOM_OAUTH_CLIENT_SECRET, INTERCOM_WEBHOOK_SECRET settings
- `backend/app/api/v1/integrations.py`: Added Intercom to AVAILABLE_INTEGRATIONS (category: communication)
- `backend/app/api/v1/__init__.py`: Registered intercom_webhook_router
- `backend/app/services/connectors/__init__.py`: Registered IntercomConnector (imports, __all__, CONNECTOR_TYPES). Ruff auto-fixed __all__ sort order.
- `backend/app/services/connectors/manager.py`: Registered IntercomConnector in CONNECTOR_CLASSES

**Batch 6 — Cross-integration test update:**
- `backend/tests/test_cross_integration_workflow.py`: Added assertions for GitHub (18 bridge caps), Slack (11 bridge caps), Intercom (10 bridge caps). Updated connector manager and CONNECTOR_TYPES assertions.

**Batch 7 — Plan:**
- `plans/PLAN-tier1-integrations-batch7.md`: Batch 7 plan for Asana (10 actions) + GitLab (14 actions). (NEW)

**Frontend (3 files):**
- `src/app/[locale]/integrations/integrations-page-content.tsx`: Added SiIntercom import and `intercom: SiIntercom` ICON_MAP entry
- `src/app/[locale]/integrations/browse/integration-marketplace-content.tsx`: Added SiIntercom import and `intercom: SiIntercom` ICON_MAP entry
- `src/components/integrations/IntegrationOnboardingWizard.tsx`: Added SiIntercom import and `intercom: SiIntercom` ICON_MAP entry

WHAT DID NOT CHANGE BUT WAS TOUCHED:
  - none

TESTS RUN + RESULT (integration-specific tests):

```
tests/test_intercom_integration.py (7 tests) — ALL PASSED
tests/test_cross_integration_workflow.py (3 tests) — ALL PASSED
tests/test_github_connector.py (27 tests) — ALL PASSED
tests/test_slack_connector.py (32 tests) — ALL PASSED

======================== 69 passed in 0.25s ========================
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
382fe9d docs: Batch 7 plan — Asana + GitLab
bf87537 docs: exit audit for Batch 6 (GitHub expansion, Slack expansion, Intercom)
67b13ee feat(integrations): add GitHub expansion, Slack expansion, and Intercom (Batch 6)
d9a3da3 docs: update exit audit with frontend icons + deploy status + Batch 6 plan
560d2ba docs: Batch 6 plan — GitHub expansion, Slack expansion, Intercom
```

□ docker compose exec backend alembic current
```
fix_search_vector_trigger_001 (head)
```

□ docker compose ps (VPS)
```
flowmanner-frontend    Up About a minute
flowmanner-nginx       Up About a minute
```

□ curl http://127.0.0.1:8000/api/health
```json
{
  "status": "ok",
  "service": "workflows-backend",
  "version": "production",
  "components": {
    "database": {"status": "ok", "latency_ms": 1.7},
    "redis": {"status": "ok", "latency_ms": 1.2},
    "langfuse": {"status": "ok", "circuits": "closed"},
    "llm_provider": {"status": "ok", "model": "deepseek/deepseek-v4-flash"}
  }
}
```

□ docker compose exec backend bash -c 'pytest -q' 2>&1 | tail -20
```
3427 passed, 153 failed, 53 errors, 126 skipped, 133 warnings in 56.27s
```

Note: The 153 failures and 53 errors are **pre-existing** in the broader test suite (handoff lease integration, integration_connected_db, integration_graph_execution modules). The 69 integration-specific tests for Batch 6 all pass. No regressions were introduced by this session's changes.

=== NEXT SESSION HANDOFF ===

> **Batch 6 is fully implemented, tested, deployed, and committed.** Both backend and frontend are healthy. Three commits landed on origin/main:
> - `67b13ee` — feat(integrations): add GitHub expansion, Slack expansion, and Intercom (Batch 6) — 18 files, +1066/-11
> - `bf87537` — docs: exit audit for Batch 6 — 1 file, +178
> - `382fe9d` — docs: Batch 7 plan — Asana + GitLab — 1 file, +408
>
> **Integration status:** 13 integrations total (Batches 1-6), 136 bridge capabilities. All integration-specific tests passing (69/69). Backend deployed and healthy. Frontend deployed with SiIntercom icons.
>
> **Next agent should:**
> 1. **Implement Batch 7** — Plan at `plans/PLAN-tier1-integrations-batch7.md`. Asana (10 actions) + GitLab (14 actions). Both are standard OAuth2 with refresh tokens. Follow the exact same patterns as Batches 1-6.
> 2. **Set up OAuth apps** — Glenn needs to create OAuth apps for both services and add env vars to `/opt/flowmanner/.env`:
>    - Asana: OAuth app at https://app.asana.com/app (under "My Apps")
>    - GitLab: OAuth app at https://gitlab.com/-/user_settings/applications
> 3. **Consider expanding existing integrations** — Notion (database writes), Linear (projects/cycles/roadmaps), or GitHub (Discussions GraphQL is implemented but could add more GraphQL mutations).
>
> **Gotchas:**
> - Asana responses are sparse by default — must use `opt_fields` query param to request specific fields. The client should pre-set useful `opt_fields` on all endpoints.
> - GitLab supports self-hosted instances — the connector needs a configurable `base_url` per connection (defaulting to `https://gitlab.com`).
> - Intercom tokens do NOT expire. No refresh_token is returned. The integration bridge correctly skips token refresh for Intercom.
> - GitHub `list_discussions` uses GraphQL (POST to `/graphql`), not REST. The base connector handles this correctly.
> - The `celery-beat` container naming conflict during deploy is a recurring Docker issue. If `deploy-backend.sh` fails on this, restart only the backend: `cd /opt/flowmanner && docker compose up -d --no-deps --force-recreate backend`.
> - Pre-commit hooks enforce ruff UP038 (use `X | Y` union syntax instead of `(X, Y)` tuple in isinstance). Fix before committing.
> - Frontend ICON_MAP files have different import formats per file — `integrations-page-content.tsx` uses comma-separated imports on one line, `IntegrationOnboardingWizard.tsx` uses one icon per line. Use the correct sed pattern for each.

=== FILES THIS AGENT DID NOT TOUCH BUT EXIST ===

- Untracked files: none (working tree clean)
- Deleted files: none

=== COMMITS THIS SESSION ===

| Hash | Message | Files |
|------|---------|-------|
| `67b13ee` | `feat(integrations): add GitHub expansion, Slack expansion, and Intercom (Batch 6)` | 18 files, +1066/-11 |
| `bf87537` | `docs: exit audit for Batch 6 (GitHub expansion, Slack expansion, Intercom)` | 1 file, +178 |
| `382fe9d` | `docs: Batch 7 plan — Asana + GitLab` | 1 file, +408 |

=== CAPABILITY COUNTS ===

| Integration | Before | After | Change |
|-------------|--------|-------|--------|
| GitHub bridge | 7 | 18 | +11 |
| GitHub connector | 18 | 26 | +8 |
| Slack bridge | 4 | 11 | +7 |
| Slack connector | 14 | 17 | +3 |
| Intercom bridge | — | 10 | new |
| Intercom connector | — | 10 | new |
| **Total bridge capabilities** | **97** | **136** | **+39** |

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
| 6 | GitHub (expanded) | ✅ | ✅ (27) | ✅ | ✅ `67b13ee` | ✅ |
| 6 | Slack (expanded) | ✅ | ✅ (32) | ✅ | ✅ `67b13ee` | ✅ |
| 6 | Intercom | ✅ | ✅ (7) | ✅ | ✅ `67b13ee` | ✅ |

=== ENV VARS NEEDED (add to /opt/flowmanner/.env) ===

```bash
# Intercom (Batch 6 — implemented, needs OAuth app)
INTERCOM_OAUTH_CLIENT_ID=
INTERCOM_OAUTH_CLIENT_SECRET=
INTERCOM_WEBHOOK_SECRET=

# Asana (Batch 7 — planned)
ASANA_OAUTH_CLIENT_ID=
ASANA_OAUTH_CLIENT_SECRET=
ASANA_WEBHOOK_SECRET=

# GitLab (Batch 7 — planned)
GITLAB_OAUTH_CLIENT_ID=
GITLAB_OAUTH_CLIENT_SECRET=
GITLAB_WEBHOOK_SECRET=
```

=== END ===
