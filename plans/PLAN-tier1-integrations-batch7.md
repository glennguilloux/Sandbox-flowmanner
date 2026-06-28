# PLAN — Tier 1 Integrations: Batch 7 (Asana + GitLab)

**Date:** June 28, 2026
**Status:** Draft — ready for review
**Scope:** Add new Asana integration (10 actions) + new GitLab integration (14 actions).
**Machine:** homelab (172.16.1.1)
**Prerequisite:** Batches 1-6 deployed and stable (13 integrations total, 136 bridge capabilities).
**Estimated effort:** Asana ~3 days, GitLab ~4 days. Total ~1.5 weeks.

---

## TL;DR

Batch 7 adds two new integrations:

- **Asana** — Project management. The killer workflow: *Sentry error → agent creates Asana task with stack trace + assignee*. Standard OAuth2 with `opt_fields` quirk for sparse responses. Refresh tokens supported (1-hour expiry).
- **GitLab** — Full DevOps platform (alternative to GitHub). The killer workflow: *Asana task → agent creates GitLab MR + monitors pipeline*. Standard OAuth2 with self-hosted instance support. Refresh tokens supported.

**Key insight:** Both are standard OAuth2 with refresh tokens. Both use the generic `_refresh_oauth_token()` helper already in the integration bridge. No custom OAuth callbacks needed.

---

## ⚠️ KEY FINDINGS FROM RESEARCH

### Asana — Project Management

| Aspect | What Asana does |
|--------|----------------|
| Authorize URL | `https://app.asana.com/-/oauth_authorize` |
| Token URL | `https://app.asana.com/-/oauth_token` |
| Token exchange format | Standard JSON: `access_token`, `refresh_token`, `expires_in` |
| Refresh endpoint | Same token URL with `grant_type=refresh_token` |
| Auth header | `Authorization: Bearer {access_token}` |
| API base URL | `https://app.asana.com/api/1.0` |
| **Quirk** | Responses are sparse by default — must use `opt_fields` query param to request specific fields |
| Rate limits | ~100-150 req/min per user (varies by tier) |
| Webhook | HMAC-SHA256 signature in `X-Hook-Signature` header |
| Token expiry | 1 hour (refresh token provided) |

**Important quirk:** Asana returns minimal data by default. Every list/get endpoint needs `opt_fields=name,completed,due_on,...` to get useful data. The client handles this.

### GitLab — Full DevOps Platform

| Aspect | What GitLab does |
|--------|----------------|
| Authorize URL | `https://gitlab.com/oauth/authorize` (or self-hosted) |
| Token URL | `https://gitlab.com/oauth/token` (or self-hosted) |
| Token exchange format | Standard JSON: `access_token`, `refresh_token`, `expires_in` |
| Refresh endpoint | Same token URL with `grant_type=refresh_token` |
| Auth header | `Authorization: Bearer {access_token}` |
| API base URL | `https://gitlab.com/api/v4` (or self-hosted) |
| **Quirk** | Supports self-hosted instances — API base URL is configurable per connection |
| Rate limits | 2,000 req/min per IP (GitLab.com) |
| Webhook | `X-Gitlab-Token` header (shared secret, not HMAC) |
| Token expiry | 2 hours (refresh token supported) |

**Important quirk:** GitLab supports self-hosted instances. The connector must accept a configurable `base_url` (defaulting to `https://gitlab.com`). The OAuth flow uses the instance URL for authorize/token endpoints.

---

## PART A: Asana Integration (~3 days)

### Auth Model

Standard OAuth 2.0 Authorization Code flow with refresh tokens. **No custom callback needed.** Tokens expire in 1 hour — the generic `_refresh_oauth_token()` helper handles refresh.

### Step A1: Add Asana OAuth provider

**File:** `backend/app/core/oauth.py`

```python
"asana": OAuthProviderConfig(
    slug="asana",
    name="Asana",
    authorize_url="https://app.asana.com/-/oauth_authorize",
    token_url="https://app.asana.com/-/oauth_token",
    client_id_env="ASANA_OAUTH_CLIENT_ID",
    client_secret_env="ASANA_OAUTH_CLIENT_SECRET",
    scopes=[],  # Asana uses "default" scope — no specific scopes needed
),
```

### Step A2: Add Asana settings

**File:** `backend/app/config.py`

```python
# Asana integration
ASANA_OAUTH_CLIENT_ID: str = ""
ASANA_OAUTH_CLIENT_SECRET: str = ""
ASANA_WEBHOOK_SECRET: str = ""
```

### Step A3: Create AsanaClient service

**File (NEW):** `backend/app/services/asana/asana_client.py`

Async REST client for Asana REST API. Auth via `Authorization: Bearer {access_token}`. All list endpoints use `opt_fields` to request useful data. Offset-based pagination with `offset` param.

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| get_me | GET | `/users/me` | Credential validation |
| list_workspaces | GET | `/workspaces` | User's workspaces |
| list_projects | GET | `/projects` | Filter by workspace |
| get_project | GET | `/projects/{gid}` | With opt_fields |
| list_tasks | GET | `/tasks` | Filter by project/assignee/workspace |
| get_task | GET | `/tasks/{gid}` | With opt_fields |
| create_task | POST | `/tasks` | Name, notes, project, assignee |
| update_task | PUT | `/tasks/{gid}` | Update fields |
| complete_task | POST | `/tasks/{gid}` | Set completed: true |
| list_sections | GET | `/projects/{gid}/sections` | Project sections |

### Step A4: Create AsanaConnector

**File (NEW):** `backend/app/services/connectors/asana_connector.py`

10 actions. Follow vercel_connector pattern.

### Step A5: Create Asana webhook handler

**File (NEW):** `backend/app/api/v1/asana_webhook.py`

Webhook signature: Asana uses HMAC-SHA256. Signature in `X-Hook-Signature` header. Verify by computing HMAC of raw body using webhook secret.

Events: `task.created`, `task.changed`, `task.completed`, `story.created`.

### Step A6: Register Asana bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"asana": [
    {"id": "get_me", "name": "Get Asana User", ...},
    {"id": "list_workspaces", "name": "List Asana Workspaces", ...},
    {"id": "list_projects", "name": "List Asana Projects", ...},
    {"id": "get_project", "name": "Get Asana Project", ...},
    {"id": "list_tasks", "name": "List Asana Tasks", ...},
    {"id": "get_task", "name": "Get Asana Task", ...},
    {"id": "create_task", "name": "Create Asana Task", ...},
    {"id": "update_task", "name": "Update Asana Task", ...},
    {"id": "complete_task", "name": "Complete Asana Task", ...},
    {"id": "list_sections", "name": "List Asana Sections", ...},
],
```

### Step A7: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/asana.json`
- **Static list:** Add `Integration(slug="asana", ...)`
- **Frontend icon:** `SiAsana` from `@icons-pack/react-simple-icons`
- **Connect handler:** Standard OAuth2 flow

### Step A8: Register connector + router

- Register `AsanaConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `asana_webhook_router` in `api/v1/__init__.py`

### Step A9: Token refresh

Add Asana token refresh block in `integration_bridge.py` using generic `_refresh_oauth_token()`:

```python
if slug == "asana" and conn.encrypted_refresh_token:
    # Same pattern as Figma/Stripe/PagerDuty/etc.
```

### Step A10: Tests

**File (NEW):** `backend/tests/test_asana_integration.py`

- `test_asana_in_v1_oauth_providers`
- `test_asana_in_available_integrations`
- `test_asana_manifest_exists`
- `test_asana_bridge_capabilities`
- `test_asana_webhook_router_exists`
- `test_asana_connector_importable`
- `test_asana_settings_exist`

---

## PART B: GitLab Integration (~4 days)

### Auth Model

Standard OAuth 2.0 Authorization Code flow with refresh tokens. **No custom callback needed.** Tokens expire in 2 hours — the generic `_refresh_oauth_token()` helper handles refresh.

**Self-hosted support:** The connector accepts a configurable `base_url` per connection. OAuth URLs are relative to the GitLab instance. For the default (gitlab.com), the full URLs are hardcoded in the OAuth provider config.

### Step B1: Add GitLab OAuth provider

**File:** `backend/app/core/oauth.py`

```python
"gitlab": OAuthProviderConfig(
    slug="gitlab",
    name="GitLab",
    authorize_url="https://gitlab.com/oauth/authorize",
    token_url="https://gitlab.com/oauth/token",
    client_id_env="GITLAB_OAUTH_CLIENT_ID",
    client_secret_env="GITLAB_OAUTH_CLIENT_SECRET",
    scopes=["api"],
),
```

### Step B2: Add GitLab settings

**File:** `backend/app/config.py`

```python
# GitLab integration
GITLAB_OAUTH_CLIENT_ID: str = ""
GITLAB_OAUTH_CLIENT_SECRET: str = ""
GITLAB_WEBHOOK_SECRET: str = ""
```

### Step B3: Create GitLabClient service

**File (NEW):** `backend/app/services/gitlab/gitlab_client.py`

Async REST client for GitLab REST API v4. Auth via `Authorization: Bearer {access_token}`. Supports configurable `base_url` for self-hosted instances. Keyset-based pagination with `page` param.

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| get_me | GET | `/user` | Credential validation |
| list_projects | GET | `/projects` | Filter by membership |
| get_project | GET | `/projects/:id` | Project details |
| list_merge_requests | GET | `/projects/:id/merge_requests` | Filter by state |
| get_merge_request | GET | `/projects/:id/merge_requests/:mr_iid` | MR details |
| create_merge_request | POST | `/projects/:id/merge_requests` | Title, source, target |
| merge_merge_request | PUT | `/projects/:id/merge_requests/:mr_iid/merge` | Merge MR |
| approve_merge_request | POST | `/projects/:id/merge_requests/:mr_iid/approve` | Approve MR |
| list_issues | GET | `/projects/:id/issues` | Filter by state |
| get_issue | GET | `/projects/:id/issues/:issue_iid` | Issue details |
| create_issue | POST | `/projects/:id/issues` | Title, description |
| add_issue_note | POST | `/projects/:id/issues/:issue_iid/notes` | Add comment |
| list_pipelines | GET | `/projects/:id/pipelines` | Filter by status |
| get_pipeline | GET | `/projects/:id/pipelines/:pipeline_id` | Pipeline details |
| retry_pipeline | POST | `/projects/:id/pipelines/:pipeline_id/retry` | Retry failed pipeline |
| cancel_pipeline | POST | `/projects/:id/pipelines/:pipeline_id/cancel` | Cancel running pipeline |
| list_deployments | GET | `/projects/:id/deployments` | Deployment history |
| list_releases | GET | `/projects/:id/releases` | Release history |
| create_release | POST | `/projects/:id/releases` | Create release |

### Step B4: Create GitLabConnector

**File (NEW):** `backend/app/services/connectors/gitlab_connector.py`

14 actions. Follow vercel_connector pattern. Configurable `base_url` for self-hosted instances.

### Step B5: Create GitLab webhook handler

**File (NEW):** `backend/app/api/v1/gitlab_webhook.py`

Webhook verification: GitLab uses `X-Gitlab-Token` header (shared secret comparison, not HMAC). Simple string equality check against configured secret.

Events: `merge_request`, `pipeline`, `deployment`, `note` (comments).

### Step B6: Register GitLab bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"gitlab": [
    {"id": "get_me", "name": "Get GitLab User", ...},
    {"id": "list_projects", "name": "List GitLab Projects", ...},
    {"id": "get_project", "name": "Get GitLab Project", ...},
    {"id": "list_merge_requests", "name": "List GitLab Merge Requests", ...},
    {"id": "get_merge_request", "name": "Get GitLab Merge Request", ...},
    {"id": "create_merge_request", "name": "Create GitLab Merge Request", ...},
    {"id": "merge_merge_request", "name": "Merge GitLab Merge Request", ...},
    {"id": "approve_merge_request", "name": "Approve GitLab Merge Request", ...},
    {"id": "list_issues", "name": "List GitLab Issues", ...},
    {"id": "get_issue", "name": "Get GitLab Issue", ...},
    {"id": "create_issue", "name": "Create GitLab Issue", ...},
    {"id": "add_issue_note", "name": "Add GitLab Issue Comment", ...},
    {"id": "list_pipelines", "name": "List GitLab Pipelines", ...},
    {"id": "retry_pipeline", "name": "Retry GitLab Pipeline", ...},
],
```

### Step B7: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/gitlab.json`
- **Static list:** Add `Integration(slug="gitlab", ...)`
- **Frontend icon:** `SiGitlab` from `@icons-pack/react-simple-icons`
- **Connect handler:** Standard OAuth2 flow

### Step B8: Register connector + router

- Register `GitLabConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `gitlab_webhook_router` in `api/v1/__init__.py`

### Step B9: Token refresh

Add GitLab token refresh block in `integration_bridge.py` using generic `_refresh_oauth_token()`:

```python
if slug == "gitlab" and conn.encrypted_refresh_token:
    # Same pattern as Figma/Stripe/PagerDuty/etc.
```

### Step B10: Tests

**File (NEW):** `backend/tests/test_gitlab_integration.py`

- `test_gitlab_in_v1_oauth_providers`
- `test_gitlab_in_available_integrations`
- `test_gitlab_manifest_exists`
- `test_gitlab_bridge_capabilities`
- `test_gitlab_webhook_router_exists`
- `test_gitlab_connector_importable`
- `test_gitlab_settings_exist`

---

## PART C: Cross-Integration Workflow Test Update

Update `test_cross_integration_workflow.py`:
- Asana: assert 10 capabilities (new)
- GitLab: assert 14 capabilities (new)
- Update connector manager/init assertions

---

## Files Summary

### New files (8)

| File | Purpose |
|------|---------|
| `backend/app/services/asana/__init__.py` | Asana service package |
| `backend/app/services/asana/asana_client.py` | Asana REST API client |
| `backend/app/services/connectors/asana_connector.py` | Asana BaseConnector wrapper |
| `backend/app/api/v1/asana_webhook.py` | Asana webhook handler |
| `backend/app/services/gitlab/__init__.py` | GitLab service package |
| `backend/app/services/gitlab/gitlab_client.py` | GitLab REST API client |
| `backend/app/services/connectors/gitlab_connector.py` | GitLab BaseConnector wrapper |
| `backend/app/api/v1/gitlab_webhook.py` | GitLab webhook handler |
| `backend/integrations/manifests/asana.json` | Asana manifest |
| `backend/integrations/manifests/gitlab.json` | GitLab manifest |
| `backend/tests/test_asana_integration.py` | Asana wiring tests |
| `backend/tests/test_gitlab_integration.py` | GitLab wiring tests |

### Modified files (8)

| File | Change |
|------|--------|
| `backend/app/core/oauth.py` | Add Asana + GitLab OAuthProviderConfig |
| `backend/app/config.py` | Add ASANA_* + GITLAB_* settings |
| `backend/app/api/v1/integrations.py` | Add Asana + GitLab to AVAILABLE_INTEGRATIONS |
| `backend/app/api/v1/__init__.py` | Register asana_webhook + gitlab_webhook routers |
| `backend/app/services/integration_bridge.py` | Add 10 Asana + 14 GitLab bridge capabilities + token refresh blocks |
| `backend/app/services/connectors/__init__.py` | Register AsanaConnector + GitLabConnector |
| `backend/app/services/connectors/manager.py` | Register AsanaConnector + GitLabConnector in CONNECTOR_CLASSES |
| `backend/tests/test_cross_integration_workflow.py` | Update assertions for new capabilities |

---

## Done Criteria

### Asana
- [ ] 10 Asana actions working (projects, tasks, sections, users)
- [ ] Asana bridge capabilities: 10 total
- [ ] Asana connector: 10 actions
- [ ] `opt_fields` used on all list/get endpoints
- [ ] Token refresh via generic `_refresh_oauth_token()`
- [ ] Asana webhook signature verification (HMAC-SHA256, `X-Hook-Signature`)
- [ ] All 7 tests pass

### GitLab
- [ ] 14 GitLab actions working (projects, MRs, issues, pipelines, deployments, releases)
- [ ] GitLab bridge capabilities: 14 total
- [ ] GitLab connector: 14 actions
- [ ] Configurable `base_url` for self-hosted instances
- [ ] Token refresh via generic `_refresh_oauth_token()`
- [ ] GitLab webhook verification (`X-Gitlab-Token` shared secret)
- [ ] All 7 tests pass

### Shared
- [ ] ruff check passes
- [ ] All existing tests still pass (69 from Batches 1-6)
- [ ] Commit pushed to origin/main
- [ ] Backend deployed and healthy

---

## Future Batches (Batch 8+ candidates)

| Integration | Complexity | Value | Auth | Notes |
|-------------|-----------|-------|------|-------|
| **ClickUp** | Medium | Medium | OAuth2 | Project management. More complex API than Asana. |
| **Notion (expand)** | Low | Medium | Already done | Add database write operations |
| **Linear (expand)** | Low | Medium | Already done | Add projects, cycles, roadmaps |
| **AWS** | High | High | IAM/OAuth | Cloud infrastructure management. |
| **Cloudflare** | Medium | Medium | OAuth2 | DNS, CDN, Workers management. |
| **Twilio** | Medium | Medium | API key | SMS/Voice communication. |
| **HubSpot** | Medium | High | OAuth2 | CRM, marketing, sales. |

---

## CAPABILITY COUNTS (projected)

| Integration | Bridge Caps | Connector Actions |
|-------------|-------------|-------------------|
| Asana (new) | 10 | 10 |
| GitLab (new) | 14 | 14 |
| **Batch 7 total** | **+24** | **+24** |
| **Grand total (Batches 1-7)** | **160** | — |
