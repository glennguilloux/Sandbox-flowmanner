# PLAN — Tier 1 Integrations: Batch 6 (GitHub Expansion + Slack Expansion + Intercom)

**Date:** June 28, 2026
**Status:** Draft — ready for review
**Scope:** Expand GitHub (7→18 actions), expand Slack (4→11 actions), add new Intercom integration (10 actions).
**Machine:** homelab (172.16.1.1)
**Prerequisite:** Batches 1-5 deployed and stable (10 integrations total).
**Estimated effort:** GitHub expansion ~3 days, Slack expansion ~2 days, Intercom ~4 days. Total ~1.5 weeks.

---

## TL;DR

Batch 6 expands two existing integrations and adds one new one:

- **GitHub expansion** — Adds Actions (workflow runs, rerun), Deployments, Releases, Discussions (GraphQL), and richer Issue/PR management. 7→18 actions. Uses existing OAuth + connector. No new OAuth, no new webhook.
- **Slack expansion** — Adds threads, reactions, file uploads, message update/delete. 4→11 actions. Uses existing OAuth + connector. No new OAuth, no new webhook.
- **Intercom** — Customer messaging platform. The killer workflow: *Sentry error → agent checks if affected customer has open Intercom conversation → posts update*. Standard OAuth2 with `Intercom-Version` header quirk.

**Key insight:** GitHub and Slack expansions only add new actions to existing clients/connectors. No new OAuth providers, no new webhook handlers, no new router registrations. This makes them significantly cheaper than new integrations.

---

## ⚠️ KEY FINDINGS FROM RESEARCH

### GitHub Expansion — Actions, Releases, Discussions

**Current capabilities (7):** create_issue, list_issues, create_pr, list_prs, search_code, get_repo, list_repos

**Missing capabilities (11):** get_issue, add_issue_comment, get_pr, merge_pr, list_workflows, list_workflow_runs, get_workflow_run, rerun_workflow, list_deployments, create_release, list_discussions

**Key details:**
- All GitHub REST endpoints use `Authorization: Bearer {token}` — same as existing
- Actions API: `GET/POST /repos/{owner}/{repo}/actions/runs`, `GET /repos/{owner}/{repo}/actions/workflows`
- Deployments API: `GET /repos/{owner}/{repo}/deployments`
- Releases API: `GET/POST /repos/{owner}/{repo}/releases`
- **Discussions require GraphQL:** `POST https://api.github.com/graphql` with `createDiscussion`, `addDiscussionComment` mutations
- Rate limit: 5,000 req/hour per user (shared pool)
- No new OAuth callback needed — uses existing GitHub OAuth
- No new webhook handler needed — GitHub webhook already exists in the project

**GitHub client changes:** Add ~11 new methods to `backend/app/services/github/github_client.py` (or create if it doesn't exist — need to check).

### Slack Expansion — Threads, Reactions, Files

**Current capabilities (4):** send_message, list_channels, list_users, get_channel_history

**Missing capabilities (7):** update_message, delete_message, reply_to_thread, get_thread_replies, add_reaction, upload_file, get_user_profile

**Key details:**
- All Slack Web API endpoints use `Authorization: Bearer {token}` — same as existing
- Threads: `chat.postMessage` with `thread_ts` parameter
- Reactions: `POST /reactions.add` with `channel`, `timestamp`, `name`
- Files: `POST /files.upload` with multipart form data
- Update/delete: `chat.update`, `chat.delete`
- Rate limit: Tier-based (most tiers: ~1 req/sec for posting)
- No new OAuth callback needed
- No new webhook handler needed

**Slack client changes:** Add ~7 new methods to the existing Slack client.

### Intercom — New Integration

| Aspect | What Intercom does |
|--------|-------------------|
| Authorize URL | `https://app.intercom.com/oauth` |
| Token URL | `https://api.intercom.io/auth/eagle/token` |
| Token exchange format | Standard JSON: `access_token`, `token_type` |
| Refresh endpoint | Intercom tokens do NOT expire (no refresh_token) |
| Auth header | `Authorization: Bearer {access_token}` |
| API base URL | `https://api.intercom.io` |
| **Quirk** | Requires `Intercom-Version` header (e.g., `2.8`) on all requests |
| Rate limits | 10,000 req/min per app, 25,000 req/min per workspace |
| Webhook | Hub signature (HMAC-SHA256 with shared secret) |

**No custom OAuth callback needed.** Standard token exchange, no refresh token (tokens don't expire).

**Important quirk:** Every API request must include `Intercom-Version: 2.8` header. The client handles this.

---

## PART A: GitHub Expansion (~3 days)

### Current state
- OAuth provider: ✅ registered
- Connector: ✅ `GitHubConnector` exists
- Bridge capabilities: 7 registered
- Client: Need to check if `github_client.py` exists or if actions go through connector directly

### New actions to add (11)

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| get_issue | GET | `/repos/{owner}/{repo}/issues/{issue_number}` | |
| add_issue_comment | POST | `/repos/{owner}/{repo}/issues/{issue_number}/comments` | |
| get_pr | GET | `/repos/{owner}/{repo}/pulls/{pull_number}` | |
| merge_pr | PUT | `/repos/{owner}/{repo}/pulls/{pull_number}/merge` | |
| list_workflows | GET | `/repos/{owner}/{repo}/actions/workflows` | |
| list_workflow_runs | GET | `/repos/{owner}/{repo}/actions/runs` | |
| get_workflow_run | GET | `/repos/{owner}/{repo}/actions/runs/{run_id}` | |
| rerun_workflow | POST | `/repos/{owner}/{repo}/actions/runs/{run_id}/rerun` | |
| list_deployments | GET | `/repos/{owner}/{repo}/deployments` | |
| create_release | POST | `/repos/{owner}/{repo}/releases` | |
| list_discussions | POST | `/graphql` | GraphQL query |

### Files to modify

| File | Change |
|------|--------|
| `backend/app/services/github/github_client.py` | Add 11 new methods (check if file exists first) |
| `backend/app/services/connectors/github_connector.py` | Add 11 new action handlers |
| `backend/app/services/integration_bridge.py` | Add 11 new capabilities to `github` list |

### No changes needed
- OAuth provider (already registered)
- Config settings (already set)
- Router registration (already done)
- Manifest (update capabilities count only)
- Available integrations (already listed)

---

## PART B: Slack Expansion (~2 days)

### Current state
- OAuth provider: ✅ registered
- Connector: ✅ `SlackConnector` exists
- Bridge capabilities: 4 registered
- Client: Need to check existing Slack client

### New actions to add (7)

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| update_message | POST | `chat.update` | Requires `channel`, `ts`, `text` |
| delete_message | POST | `chat.delete` | Requires `channel`, `ts` |
| reply_to_thread | POST | `chat.postMessage` | With `thread_ts` parameter |
| get_thread_replies | GET | `conversations.replies` | Requires `channel`, `ts` |
| add_reaction | POST | `reactions.add` | Requires `channel`, `timestamp`, `name` |
| upload_file | POST | `files.upload` | Multipart form data |
| get_user_profile | GET | `users.info` | Requires `user` |

### Files to modify

| File | Change |
|------|--------|
| Backend Slack client | Add 7 new methods |
| `backend/app/services/connectors/slack_connector.py` | Add 7 new action handlers |
| `backend/app/services/integration_bridge.py` | Add 7 new capabilities to `slack` list |

### No changes needed
- OAuth provider, config, router, manifest (update capabilities only)

---

## PART C: Intercom Integration (~4 days)

### Auth Model

Standard OAuth 2.0 Authorization Code flow. **No custom callback needed.** Tokens don't expire (no refresh_token).

**Quirk:** All API requests require `Intercom-Version: 2.8` header.

**Scopes:** Granular — `Read and list users`, `Write conversations`, `Read admins`, etc.

### Step C1: Add Intercom OAuth provider

**File:** `backend/app/core/oauth.py`

```python
"intercom": OAuthProviderConfig(
    slug="intercom",
    name="Intercom",
    authorize_url="https://app.intercom.com/oauth",
    token_url="https://api.intercom.io/auth/eagle/token",
    client_id_env="INTERCOM_OAUTH_CLIENT_ID",
    client_secret_env="INTERCOM_OAUTH_CLIENT_SECRET",
    scopes=["Read and list users", "Write conversations", "Read conversations", "Read admins"],
),
```

### Step C2: Add Intercom settings

**File:** `backend/app/config.py`

```python
# Intercom integration
INTERCOM_OAUTH_CLIENT_ID: str = ""
INTERCOM_OAUTH_CLIENT_SECRET: str = ""
INTERCOM_WEBHOOK_SECRET: str = ""
```

### Step C3: OAuth callback — NO custom callback needed

Standard `oauth_callback` handler works. Intercom returns standard `access_token` with no `refresh_token` (tokens don't expire).

### Step C4: Create IntercomClient service

**File (NEW):** `backend/app/services/intercom/intercom_client.py`

Async REST client for Intercom REST API. Auth via `Authorization: Bearer {access_token}`. All requests include `Intercom-Version: 2.8` header.

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| get_admin | GET | `/admins/me` | Credential validation |
| list_conversations | GET | `/conversations` | Paginated with `starting_after` |
| get_conversation | GET | `/conversations/{id}` | |
| reply_to_conversation | POST | `/conversations/{id}/reply` | Message type, body |
| list_contacts | GET | `/contacts` | Paginated |
| get_contact | GET | `/contacts/{id}` | |
| list_companies | GET | `/companies` | Paginated |
| list_teams | GET | `/teams` | |
| list_tags | GET | `/tags` | |
| search_contacts | POST | `/contacts/search` | Query-based search |

### Step C5: Create IntercomConnector

**File (NEW):** `backend/app/services/connectors/intercom_connector.py`

10 actions. Follow vercel_connector pattern.

### Step C6: Create Intercom webhook handler

**File (NEW):** `backend/app/api/v1/intercom_webhook.py`

Webhook signature: Intercom uses hub signature (HMAC-SHA256 with shared secret). Similar to Slack's webhook verification.

Events: `conversation.user.created`, `conversation.user.replied`, `conversation.admin.replied`, `contact.created`, `contact.updated`.

### Step C7: Register Intercom bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"intercom": [
    {"id": "get_admin", "name": "Get Intercom Admin", ...},
    {"id": "list_conversations", "name": "List Intercom Conversations", ...},
    {"id": "get_conversation", "name": "Get Intercom Conversation", ...},
    {"id": "reply_to_conversation", "name": "Reply to Intercom Conversation", ...},
    {"id": "list_contacts", "name": "List Intercom Contacts", ...},
    {"id": "get_contact", "name": "Get Intercom Contact", ...},
    {"id": "list_companies", "name": "List Intercom Companies", ...},
    {"id": "list_teams", "name": "List Intercom Teams", ...},
    {"id": "list_tags", "name": "List Intercom Tags", ...},
    {"id": "search_contacts", "name": "Search Intercom Contacts", ...},
],
```

**No token refresh needed** — Intercom tokens don't expire.

### Step C8: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/intercom.json`
- **Static list:** Add `Integration(slug="intercom", ...)`
- **Frontend icon:** `SiIntercom` from `@icons-pack/react-simple-icons`
- **Connect handler:** Standard OAuth2 flow

### Step C9: Register connector + router

- Register `IntercomConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `intercom_webhook_router` in `api/v1/__init__.py`

### Step C10: Tests

**File (NEW):** `backend/tests/test_intercom_integration.py`

- `test_intercom_in_v1_oauth_providers`
- `test_intercom_in_available_integrations`
- `test_intercom_manifest_exists`
- `test_intercom_bridge_capabilities`
- `test_intercom_webhook_router_exists`
- `test_intercom_connector_importable`
- `test_intercom_settings_exist`

---

## PART D: Cross-Integration Workflow Test Update

Update `test_cross_integration_workflow.py`:
- GitHub: assert 18 capabilities (was 7)
- Slack: assert 11 capabilities (was 4)
- Intercom: assert 10 capabilities (new)
- Update connector manager/init assertions

---

## Files Summary

### New files (6)

| File | Purpose |
|------|---------|
| `backend/app/services/intercom/__init__.py` | Intercom service package |
| `backend/app/services/intercom/intercom_client.py` | Intercom REST API client |
| `backend/app/services/connectors/intercom_connector.py` | Intercom BaseConnector wrapper |
| `backend/app/api/v1/intercom_webhook.py` | Intercom webhook handler |
| `backend/integrations/manifests/intercom.json` | Intercom manifest |
| `backend/tests/test_intercom_integration.py` | Intercom wiring tests |

### Modified files (9)

| File | Change |
|------|--------|
| `backend/app/core/oauth.py` | Add Intercom OAuthProviderConfig |
| `backend/app/config.py` | Add INTERCOM_* settings |
| `backend/app/api/v1/integrations.py` | Add Intercom to AVAILABLE_INTEGRATIONS |
| `backend/app/api/v1/__init__.py` | Register intercom webhook router |
| `backend/app/services/integration_bridge.py` | Add 11 GitHub + 7 Slack + 10 Intercom capabilities |
| `backend/app/services/connectors/__init__.py` | Register IntercomConnector |
| `backend/app/services/connectors/manager.py` | Register IntercomConnector in CONNECTOR_CLASSES |
| `backend/app/services/github/github_client.py` | Add 11 new methods (GitHub Actions, Releases, Discussions) |
| `backend/app/services/connectors/github_connector.py` | Add 11 new action handlers |
| `backend/tests/test_cross_integration_workflow.py` | Update assertions for expanded capabilities |

**Note:** Slack client and connector files also need 7 new methods/handlers — exact file paths TBD (need to check if `slack_client.py` exists).

---

## Done Criteria

### GitHub Expansion
- [ ] 11 new GitHub actions working (Actions, Deployments, Releases, Discussions)
- [ ] GitHub bridge capabilities: 18 total
- [ ] GitHub connector: 18 actions
- [ ] All new GitHub tests pass

### Slack Expansion
- [ ] 7 new Slack actions working (threads, reactions, files, update/delete)
- [ ] Slack bridge capabilities: 11 total
- [ ] Slack connector: 11 actions
- [ ] All new Slack tests pass

### Intercom
- [ ] Intercom OAuth provider registered
- [ ] Standard v1 OAuth callback used (no custom `intercom_oauth.py`)
- [ ] IntercomConnector importable with 10 actions
- [ ] `Intercom-Version` header included in all requests
- [ ] Intercom webhook signature verification
- [ ] 10 bridge capabilities registered
- [ ] Manifest + AVAILABLE_INTEGRATIONS entry
- [ ] All 7 tests pass

### Shared
- [ ] ruff check passes
- [ ] All existing tests still pass (32 from Batches 1-5)
- [ ] Commit pushed to origin/main
- [ ] Backend deployed and healthy

---

## Future Batches (Batch 7+ candidates)

| Integration | Complexity | Value | Auth | Notes |
|-------------|-----------|-------|------|-------|
| **Asana** | Low | Medium | OAuth2 | Project management. Clean API. |
| **ClickUp** | Medium | Medium | OAuth2 | Project management. More complex API. |
| **Notion (expand)** | Low | Medium | Already done | Add database write operations |
| **GitLab** | Medium | High | OAuth2 | Alternative to GitHub. Full DevOps platform. |
| **AWS** | High | High | IAM/OAuth | Cloud infrastructure management. |
| **Cloudflare** | Medium | Medium | OAuth2 | DNS, CDN, Workers management. |
| **Linear (expand)** | Low | Medium | Already done | Add projects, cycles, roadmaps |

**Recommended Batch 7:** Asana (low complexity, pairs with project management) + GitLab (high value, full DevOps).
