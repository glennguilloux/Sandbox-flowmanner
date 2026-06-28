# PLAN — Tier 1 Integrations: Batch 8 (ClickUp + HubSpot + Twilio)

**Date:** June 28, 2026
**Status:** Draft — ready for review
**Scope:** Add new ClickUp integration (12 actions) + new HubSpot integration (12 actions) + new Twilio integration (10 actions).
**Machine:** homelab (172.16.1.1)
**Prerequisite:** Batches 1-7 deployed and stable (15 integrations total, 160 bridge capabilities).
**Estimated effort:** ClickUp ~3 days, HubSpot ~4 days, Twilio ~3 days. Total ~1.5 weeks.

---

## TL;DR

Batch 8 adds three new integrations:

- **ClickUp** — Project management (alternative to Asana). The killer workflow: *Sentry error → agent creates ClickUp task with stack trace + priority*. Standard OAuth2. Tokens do NOT expire (like Intercom). No scopes — user authorizes per-workspace.
- **HubSpot** — CRM platform. The killer workflow: *Intercom conversation → agent creates/updates HubSpot contact + logs deal activity*. Standard OAuth2 with 30-min token expiry + refresh. High business value.
- **Twilio** — SMS/Voice communication. The killer workflow: *PagerDuty incident → agent sends SMS alert to on-call engineer*. API Key auth (not OAuth2). Webhook HMAC-SHA1 signature verification.

**Key insight:** ClickUp tokens don't expire (no refresh needed). HubSpot tokens expire in 30 minutes (refresh is critical — token may rotate). Twilio uses API Key auth, not OAuth2 (skips the OAuth flow entirely, like Linear/Discord).

---

## ⚠️ KEY FINDINGS FROM RESEARCH

### ClickUp — Project Management

| Aspect | What ClickUp does |
|--------|-------------------|
| Authorize URL | `https://app.clickup.com/api` (query params: `client_id`, `redirect_uri`) |
| Token URL | `https://api.clickup.com/api/v2/oauth/token` |
| Token exchange format | Standard JSON: `access_token` |
| Refresh endpoint | N/A — tokens do NOT expire |
| Auth header | `Authorization: Bearer {access_token}` |
| API base URL | `https://api.clickup.com/api/v2` |
| **Quirk** | No scopes — user authorizes access to specific Workspaces. Tokens don't expire. |
| Rate limits | 100 requests/minute per token |
| Webhook | HMAC-SHA256 signature in `X-Signature` header |
| Token expiry | **Never** (no refresh token provided) |

**Important quirk:** ClickUp access tokens do not expire and no refresh token is returned. This is the same pattern as Intercom — the integration bridge correctly skips token refresh for non-expiring tokens.

### HubSpot — CRM Platform

| Aspect | What HubSpot does |
|--------|-------------------|
| Authorize URL | `https://app.hubspot.com/oauth/authorize` |
| Token URL | `https://api.hubapi.com/oauth/v1/token` |
| Token exchange format | Standard JSON: `access_token`, `refresh_token`, `expires_in` |
| Refresh endpoint | Same token URL with `grant_type=refresh_token` |
| Auth header | `Authorization: Bearer {access_token}` |
| API base URL | `https://api.hubapi.com` |
| **Quirk** | Refresh token may rotate on each refresh — must store the new refresh token. 30-min token expiry. |
| Rate limits | 100 requests per 10 seconds (standard tier) |
| Webhook | HMAC-SHA256 via `X-HubSpot-Signature-v3` header (concatenates secret + method + URI + body) |
| Token expiry | 30 minutes (refresh token long-lived, may rotate) |

**Important quirk:** HubSpot refresh tokens may rotate on each refresh. The integration bridge must update the stored refresh token after every refresh. Also, HubSpot webhook verification concatenates the HTTP method + URI + body (not just the body).

### Twilio — SMS/Voice Communication

| Aspect | What Twilio does |
|--------|------------------|
| Auth method | **API Key** (not OAuth2 for per-user flows) |
| Auth header | HTTP Basic Auth: `username={API Key SID}`, `password={API Key Secret}` |
| API base URL | `https://api.twilio.com/2010-04-01` |
| **Quirk** | REST API uses date-versioned URLs. Account SID is part of the path. |
| Rate limits | Varies by endpoint (generally 100-1000/min) |
| Webhook | HMAC-SHA1 signature in `X-Twilio-Signature` header |
| Token expiry | N/A — API keys don't expire |

**Important quirk:** Twilio doesn't use OAuth2 for per-user integrations. It uses API Key + Secret (HTTP Basic Auth). This is the same pattern as Linear (API key) and Discord (bot token) — added to `_NON_OAUTH_CONFIGS` in the integration bridge, skipped from OAuth flow.

---

## PART A: ClickUp Integration (~3 days)

### Auth Model

Standard OAuth 2.0 Authorization Code flow. **No refresh token** — tokens do not expire. Same pattern as Intercom.

### Step A1: Add ClickUp OAuth provider

**File:** `backend/app/core/oauth.py`

```python
"clickup": OAuthProviderConfig(
    slug="clickup",
    name="ClickUp",
    authorize_url="https://app.clickup.com/api",
    token_url="https://api.clickup.com/api/v2/oauth/token",
    client_id_env="CLICKUP_OAUTH_CLIENT_ID",
    client_secret_env="CLICKUP_OAUTH_CLIENT_SECRET",
    scopes=[],  # ClickUp has no scopes — user authorizes per-workspace
),
```

### Step A2: Add ClickUp settings

**File:** `backend/app/config.py`

```python
# ClickUp integration
CLICKUP_OAUTH_CLIENT_ID: str = ""
CLICKUP_OAUTH_CLIENT_SECRET: str = ""
CLICKUP_WEBHOOK_SECRET: str = ""
```

### Step A3: Create ClickUpClient service

**File (NEW):** `backend/app/services/clickup/clickup_client.py`

Async REST client for ClickUp API v2. Auth via `Authorization: Bearer {access_token}`. No scopes, no token expiry.

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| get_user | GET | `/user` | Credential validation |
| list_workspaces | GET | `/team` | User's workspaces (teams) |
| list_spaces | GET | `/team/{team_id}/space` | Spaces in a workspace |
| list_folders | GET | `/space/{space_id}/folder` | Folders in a space |
| list_lists | GET | `/folder/{folder_id}/list` | Lists in a folder |
| list_tasks | GET | `/list/{list_id}/task` | Tasks in a list |
| get_task | GET | `/task/{task_id}` | Task details |
| create_task | POST | `/list/{list_id}/task` | Create task |
| update_task | PUT | `/task/{task_id}` | Update task |
| get_comments | GET | `/task/{task_id}/comment` | Task comments |
| add_comment | POST | `/task/{task_id}/comment` | Add comment |
| list_time_entries | GET | `/team/{team_id}/time_entries` | Time tracking |

### Step A4: Create ClickUpConnector

**File (NEW):** `backend/app/services/connectors/clickup_connector.py`

12 actions. Follow vercel_connector pattern.

### Step A5: Create ClickUp webhook handler

**File (NEW):** `backend/app/api/v1/clickup_webhook.py`

Webhook signature: ClickUp uses HMAC-SHA256. Signature in `X-Signature` header. Verify by computing HMAC of raw body using webhook secret.

Events: `taskCreated`, `taskUpdated`, `taskDeleted`, `taskCommentPosted`.

### Step A6: Register ClickUp bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"clickup": [
    {"id": "get_user", "name": "Get ClickUp User", ...},
    {"id": "list_workspaces", "name": "List ClickUp Workspaces", ...},
    {"id": "list_spaces", "name": "List ClickUp Spaces", ...},
    {"id": "list_folders", "name": "List ClickUp Folders", ...},
    {"id": "list_lists", "name": "List ClickUp Lists", ...},
    {"id": "list_tasks", "name": "List ClickUp Tasks", ...},
    {"id": "get_task", "name": "Get ClickUp Task", ...},
    {"id": "create_task", "name": "Create ClickUp Task", ...},
    {"id": "update_task", "name": "Update ClickUp Task", ...},
    {"id": "get_comments", "name": "Get ClickUp Task Comments", ...},
    {"id": "add_comment", "name": "Add ClickUp Task Comment", ...},
    {"id": "list_time_entries", "name": "List ClickUp Time Entries", ...},
],
```

### Step A7: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/clickup.json`
- **Static list:** Add `Integration(slug="clickup", ...)`
- **Frontend icon:** `SiClickup` from `@icons-pack/react-simple-icons`
- **Connect handler:** Standard OAuth2 flow

### Step A8: Register connector + router

- Register `ClickUpConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `clickup_webhook_router` in `api/v1/__init__.py`

### Step A9: Token refresh

**No token refresh needed.** ClickUp tokens do not expire. No refresh block in `integration_bridge.py`.

### Step A10: Tests

**File (NEW):** `backend/tests/test_clickup_integration.py`

- `test_clickup_in_v1_oauth_providers`
- `test_clickup_in_available_integrations`
- `test_clickup_manifest_exists`
- `test_clickup_bridge_capabilities`
- `test_clickup_webhook_router_exists`
- `test_clickup_connector_importable`
- `test_clickup_settings_exist`

---

## PART B: HubSpot Integration (~4 days)

### Auth Model

Standard OAuth 2.0 Authorization Code flow with refresh tokens. **Critical:** tokens expire in 30 minutes. Refresh tokens may rotate on each refresh — must store the new refresh token.

### Step B1: Add HubSpot OAuth provider

**File:** `backend/app/core/oauth.py`

```python
"hubspot": OAuthProviderConfig(
    slug="hubspot",
    name="HubSpot",
    authorize_url="https://app.hubspot.com/oauth/authorize",
    token_url="https://api.hubapi.com/oauth/v1/token",
    client_id_env="HUBSPOT_OAUTH_CLIENT_ID",
    client_secret_env="HUBSPOT_OAUTH_CLIENT_SECRET",
    scopes=[
        "crm.objects.contacts.read",
        "crm.objects.contacts.write",
        "crm.objects.companies.read",
        "crm.objects.companies.write",
        "crm.objects.deals.read",
        "crm.objects.deals.write",
        "crm.objects.owners.read",
        "tickets",
    ],
),
```

### Step B2: Add HubSpot settings

**File:** `backend/app/config.py`

```python
# HubSpot integration
HUBSPOT_OAUTH_CLIENT_ID: str = ""
HUBSPOT_OAUTH_CLIENT_SECRET: str = ""
HUBSPOT_WEBHOOK_SECRET: str = ""
```

### Step B3: Create HubSpotClient service

**File (NEW):** `backend/app/services/hubspot/hubspot_client.py`

Async REST client for HubSpot CRM API v3. Auth via `Authorization: Bearer {access_token}`. Cursor-based pagination with `after` param.

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| get_owner | GET | `/crm/v3/owners` | Credential validation (first page) |
| list_contacts | GET | `/crm/v3/objects/contacts` | Paginated with `after` cursor |
| get_contact | GET | `/crm/v3/objects/contacts/{id}` | Contact details |
| create_contact | POST | `/crm/v3/objects/contacts` | Create contact |
| update_contact | PATCH | `/crm/v3/objects/contacts/{id}` | Update contact |
| list_companies | GET | `/crm/v3/objects/companies` | Paginated |
| get_company | GET | `/crm/v3/objects/companies/{id}` | Company details |
| list_deals | GET | `/crm/v3/objects/deals` | Paginated |
| get_deal | GET | `/crm/v3/objects/deals/{id}` | Deal details |
| create_deal | POST | `/crm/v3/objects/deals` | Create deal |
| search_contacts | POST | `/crm/v3/objects/contacts/search` | Search by filter |
| list_tickets | GET | `/crm/v3/objects/tickets` | Support tickets |

### Step B4: Create HubSpotConnector

**File (NEW):** `backend/app/services/connectors/hubspot_connector.py`

12 actions. Follow vercel_connector pattern.

### Step B5: Create HubSpot webhook handler

**File (NEW):** `backend/app/api/v1/hubspot_webhook.py`

Webhook signature: HubSpot uses HMAC-SHA256 (v3). Concatenates `client_secret + HTTP_METHOD + URI + body`, then HMAC-SHA256. Signature in `X-HubSpot-Signature-v3` header.

Events: `contact.creation`, `contact.propertyChange`, `deal.creation`, `deal.propertyChange`.

### Step B6: Register HubSpot bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"hubspot": [
    {"id": "get_owner", "name": "Get HubSpot Owner", ...},
    {"id": "list_contacts", "name": "List HubSpot Contacts", ...},
    {"id": "get_contact", "name": "Get HubSpot Contact", ...},
    {"id": "create_contact", "name": "Create HubSpot Contact", ...},
    {"id": "update_contact", "name": "Update HubSpot Contact", ...},
    {"id": "list_companies", "name": "List HubSpot Companies", ...},
    {"id": "get_company", "name": "Get HubSpot Company", ...},
    {"id": "list_deals", "name": "List HubSpot Deals", ...},
    {"id": "get_deal", "name": "Get HubSpot Deal", ...},
    {"id": "create_deal", "name": "Create HubSpot Deal", ...},
    {"id": "search_contacts", "name": "Search HubSpot Contacts", ...},
    {"id": "list_tickets", "name": "List HubSpot Tickets", ...},
],
```

### Step B7: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/hubspot.json`
- **Static list:** Add `Integration(slug="hubspot", ...)`
- **Frontend icon:** `SiHubspot` from `@icons-pack/react-simple-icons`
- **Connect handler:** Standard OAuth2 flow

### Step B8: Register connector + router

- Register `HubSpotConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `hubspot_webhook_router` in `api/v1/__init__.py`

### Step B9: Token refresh

Add HubSpot token refresh block in `integration_bridge.py` using generic `_refresh_oauth_token()`. **Critical:** must update stored refresh token after each refresh (HubSpot may rotate it).

### Step B10: Tests

**File (NEW):** `backend/tests/test_hubspot_integration.py`

- `test_hubspot_in_v1_oauth_providers`
- `test_hubspot_in_available_integrations`
- `test_hubspot_manifest_exists`
- `test_hubspot_bridge_capabilities`
- `test_hubspot_webhook_router_exists`
- `test_hubspot_connector_importable`
- `test_hubspot_settings_exist`

---

## PART C: Twilio Integration (~3 days)

### Auth Model

**API Key auth** (not OAuth2). Same pattern as Linear and Discord — added to `_NON_OAUTH_CONFIGS` in the integration bridge. The user provides their Twilio Account SID + API Key SID + API Key Secret. HTTP Basic Auth.

### Step C1: Add Twilio to non-OAuth configs

**File:** `backend/app/services/integration_bridge.py`

```python
_NON_OAUTH_CONFIGS = {
    ...,
    "twilio": {
        "name": "twilio-instance",
        "auth_type": "api_key",
        "label": "Twilio API Key SID + Secret",
    },
}
```

### Step C2: Add Twilio settings

**File:** `backend/app/config.py`

```python
# Twilio integration
TWILIO_ACCOUNT_SID: str = ""
TWILIO_API_KEY_SID: str = ""
TWILIO_API_KEY_SECRET: str = ""
TWILIO_WEBHOOK_SECRET: str = ""  # Auth Token for webhook signature verification
```

### Step C3: Create TwilioClient service

**File (NEW):** `backend/app/services/twilio/twilio_client.py`

Async REST client for Twilio REST API. Auth via HTTP Basic Auth (`username=API_KEY_SID`, `password=API_KEY_SECRET`). API base URL includes account SID in path.

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| get_account | GET | `/Accounts/{AccountSid}` | Credential validation |
| list_messages | GET | `/Accounts/{AccountSid}/Messages` | SMS/MMS logs |
| send_message | POST | `/Accounts/{AccountSid}/Messages` | Send SMS/MMS |
| list_calls | GET | `/Accounts/{AccountSid}/Calls` | Call logs |
| get_call | GET | `/Accounts/{AccountSid}/Calls/{Sid}` | Call details |
| make_call | POST | `/Accounts/{AccountSid}/Calls` | Initiate outbound call |
| list_phone_numbers | GET | `/Accounts/{AccountSid}/IncomingPhoneNumbers` | Purchased numbers |
| get_recording | GET | `/Accounts/{AccountSid}/Recordings/{Sid}` | Call recording |
| list_recordings | GET | `/Accounts/{AccountSid}/Recordings` | All recordings |
| get_usage | GET | `/Accounts/{AccountSid}/Usage/Records` | Usage/billing |

### Step C4: Create TwilioConnector

**File (NEW):** `backend/app/services/connectors/twilio_connector.py`

10 actions. Follow vercel_connector pattern.

### Step C5: Create Twilio webhook handler

**File (NEW):** `backend/app/api/v1/twilio_webhook.py`

Webhook signature: Twilio uses HMAC-SHA1. Signature in `X-Twilio-Signature` header. Verify by computing HMAC of the full URL + sorted params using Auth Token.

Events: `message-status`, `call-status`, `recording-completed`.

### Step C6: Register Twilio bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"twilio": [
    {"id": "get_account", "name": "Get Twilio Account", ...},
    {"id": "list_messages", "name": "List Twilio Messages", ...},
    {"id": "send_message", "name": "Send Twilio SMS", ...},
    {"id": "list_calls", "name": "List Twilio Calls", ...},
    {"id": "get_call", "name": "Get Twilio Call", ...},
    {"id": "make_call", "name": "Make Twilio Call", ...},
    {"id": "list_phone_numbers", "name": "List Twilio Phone Numbers", ...},
    {"id": "get_recording", "name": "Get Twilio Recording", ...},
    {"id": "list_recordings", "name": "List Twilio Recordings", ...},
    {"id": "get_usage", "name": "Get Twilio Usage", ...},
],
```

### Step C7: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/twilio.json`
- **Static list:** Add `Integration(slug="twilio", ..., auth_type="api_key")`
- **Frontend icon:** `SiTwilio` from `@icons-pack/react-simple-icons`
- **Connect handler:** API key input (like Linear/Sentry)

### Step C8: Register connector + router

- Register `TwilioConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `twilio_webhook_router` in `api/v1/__init__.py`

### Step C9: Token refresh

**No token refresh needed.** API keys don't expire.

### Step C10: Tests

**File (NEW):** `backend/tests/test_twilio_integration.py`

- `test_twilio_in_available_integrations`
- `test_twilio_manifest_exists`
- `test_twilio_bridge_capabilities`
- `test_twilio_webhook_router_exists`
- `test_twilio_connector_importable`
- `test_twilio_settings_exist`
- `test_twilio_in_non_oauth_configs`

---

## PART D: Cross-Integration Workflow Test Update

Update `test_cross_integration_workflow.py`:
- ClickUp: assert 12 capabilities (new)
- HubSpot: assert 12 capabilities (new)
- Twilio: assert 10 capabilities (new)
- Update connector manager/init assertions

---

## Files Summary

### New files (12)

| File | Purpose |
|------|---------|
| `backend/app/services/clickup/__init__.py` | ClickUp service package |
| `backend/app/services/clickup/clickup_client.py` | ClickUp REST API client |
| `backend/app/services/connectors/clickup_connector.py` | ClickUp BaseConnector wrapper |
| `backend/app/api/v1/clickup_webhook.py` | ClickUp webhook handler |
| `backend/app/services/hubspot/__init__.py` | HubSpot service package |
| `backend/app/services/hubspot/hubspot_client.py` | HubSpot CRM API client |
| `backend/app/services/connectors/hubspot_connector.py` | HubSpot BaseConnector wrapper |
| `backend/app/api/v1/hubspot_webhook.py` | HubSpot webhook handler |
| `backend/app/services/twilio/__init__.py` | Twilio service package |
| `backend/app/services/twilio/twilio_client.py` | Twilio REST API client |
| `backend/app/services/connectors/twilio_connector.py` | Twilio BaseConnector wrapper |
| `backend/app/api/v1/twilio_webhook.py` | Twilio webhook handler |
| `backend/integrations/manifests/clickup.json` | ClickUp manifest |
| `backend/integrations/manifests/hubspot.json` | HubSpot manifest |
| `backend/integrations/manifests/twilio.json` | Twilio manifest |
| `backend/tests/test_clickup_integration.py` | ClickUp wiring tests |
| `backend/tests/test_hubspot_integration.py` | HubSpot wiring tests |
| `backend/tests/test_twilio_integration.py` | Twilio wiring tests |

### Modified files (8)

| File | Change |
|------|--------|
| `backend/app/core/oauth.py` | Add ClickUp + HubSpot OAuthProviderConfig |
| `backend/app/config.py` | Add CLICKUP_* + HUBSPOT_* + TWILIO_* settings |
| `backend/app/api/v1/integrations.py` | Add ClickUp + HubSpot + Twilio to AVAILABLE_INTEGRATIONS |
| `backend/app/api/v1/__init__.py` | Register clickup_webhook + hubspot_webhook + twilio_webhook routers |
| `backend/app/services/integration_bridge.py` | Add 12 ClickUp + 12 HubSpot + 10 Twilio bridge capabilities + HubSpot token refresh + Twilio non-OAuth config |
| `backend/app/services/connectors/__init__.py` | Register ClickUpConnector + HubSpotConnector + TwilioConnector |
| `backend/app/services/connectors/manager.py` | Register ClickUpConnector + HubSpotConnector + TwilioConnector in CONNECTOR_CLASSES |
| `backend/tests/test_cross_integration_workflow.py` | Update assertions for new capabilities |

---

## Done Criteria

### ClickUp
- [ ] 12 ClickUp actions working (workspaces, spaces, folders, lists, tasks, comments, time entries)
- [ ] ClickUp bridge capabilities: 12 total
- [ ] ClickUp connector: 12 actions
- [ ] No token refresh (tokens don't expire)
- [ ] ClickUp webhook signature verification (HMAC-SHA256, `X-Signature`)
- [ ] All 7 tests pass

### HubSpot
- [ ] 12 HubSpot actions working (contacts, companies, deals, tickets, search)
- [ ] HubSpot bridge capabilities: 12 total
- [ ] HubSpot connector: 12 actions
- [ ] Token refresh via generic `_refresh_oauth_token()` with refresh token rotation handling
- [ ] HubSpot webhook signature verification (HMAC-SHA256 v3, `X-HubSpot-Signature-v3`)
- [ ] All 7 tests pass

### Twilio
- [ ] 10 Twilio actions working (messages, calls, phone numbers, recordings, usage)
- [ ] Twilio bridge capabilities: 10 total
- [ ] Twilio connector: 10 actions
- [ ] API Key auth (non-OAuth, in `_NON_OAUTH_CONFIGS`)
- [ ] Twilio webhook signature verification (HMAC-SHA1, `X-Twilio-Signature`)
- [ ] All 7 tests pass

### Shared
- [ ] ruff check passes
- [ ] All existing tests still pass (83 from Batches 1-7)
- [ ] Commit pushed to origin/main
- [ ] Backend deployed and healthy

---

## Future Batches (Batch 9+ candidates)

| Integration | Complexity | Value | Auth | Notes |
|-------------|-----------|-------|------|-------|
| **Notion (expand)** | Low | Medium | Already done | Add database write operations |
| **Linear (expand)** | Low | Medium | Already done | Add projects, cycles, roadmaps |
| **AWS** | High | High | IAM/OAuth | Cloud infrastructure management |
| **Shopify** | Medium | High | OAuth2 | E-commerce platform |
| **Zendesk** | Medium | Medium | OAuth2 | Customer support ticketing |
| **Monday.com** | Medium | Medium | OAuth2 | Project management |
| **Gmail (expand)** | Low | Medium | Already done | Add email read/search capabilities |
| **Teams** | Medium | Medium | OAuth2 | Microsoft Teams messaging |

---

## CAPABILITY COUNTS (projected)

| Integration | Bridge Caps | Connector Actions |
|-------------|-------------|-------------------|
| ClickUp (new) | 12 | 12 |
| HubSpot (new) | 12 | 12 |
| Twilio (new) | 10 | 10 |
| **Batch 8 total** | **+34** | **+34** |
| **Grand total (Batches 1-8)** | **194** | — |
