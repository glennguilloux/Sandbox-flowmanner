# PLAN — Tier 1 Integrations: Batch 2 (Vercel + Jira)

**Date:** June 28, 2026
**Status:** Ready for execution
**Scope:** Build the Vercel integration (deployment monitoring + actions) and Jira integration (enterprise issue tracking). Both are clean builds — zero existing infrastructure.
**Machine:** homelab (172.16.1.1)
**Prerequisite:** Batch 1 (Linear + Sentry) deployed and stable. The wiring patterns proven in Batch 1 are reused here.
**Supersedes:** The design in `analysis/integration-research-2026-06-27.md` (this plan has actual API research + codebase ground truth).

---

## TL;DR

Batch 1 proved the integration wiring pattern. Batch 2 applies it to two clean-build integrations:

- **Vercel** — OAuth2, well-documented REST API, standard webhooks. Low complexity. The killer workflow: *deploy → agent monitors → rollback on failure*.
- **Jira** — Atlassian OAuth 2.0 (3LO) with non-standard `audience` param + mandatory site selection step. High complexity. ADF (Atlassian Document Format) required for issue descriptions. The killer workflow: *Sentry error → agent triages → Jira issue created → team notified*.

Together with Batch 1, this completes the **Sentry → Linear/Jira → Vercel** full-stack observability loop.

**Estimated effort:** Vercel ~1.5 weeks, Jira ~2.5 weeks. Total ~4 weeks.

---

## ⚠️ AUTH COMPLEXITY WARNING: Jira

Jira Cloud uses **Atlassian OAuth 2.0 (3LO)** which is non-standard in three ways:

1. **`audience` parameter** — Token exchange requires `audience=api.atlassian.com` (not standard OAuth2)
2. **Site selection** — After getting an access token, you MUST call `GET https://api.atlassian.com/oauth/token/accessible-resources` to discover the user's Jira sites. Each site has a `cloudId` that becomes part of the API base URL: `https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3/`
3. **ADF format** — Issue descriptions and comments must be in Atlassian Document Format (JSON tree), not plain text

This means the Jira OAuth callback needs an **extra step** between token exchange and storing the connection: site discovery + selection. The existing `oauth_callback` handler in `integrations.py` doesn't support this — we need a custom callback handler for Jira.

**Vercel is standard OAuth2** — no special handling needed. Build Vercel first to stay productive while designing the Jira callback.

---

## Integration Architecture (from Batch 1 — reused)

The 12-layer architecture proven in Batch 1 applies to both integrations:

```
 1. Settings (config.py)              — env vars for credentials
 2. OAuth provider (core/oauth.py)    — provider endpoints + credential env names (v1)
 3. Manifest (manifests/*.json)       — metadata, capabilities, health check
 4. Static registry fallback          — AVAILABLE_INTEGRATIONS in integrations.py
 5. API client service                — async HTTP client (app/services/<name>/)
 6. Adapter (integrations/adapters/)  — SKIP for Batch 2 (v2 actions API, optional)
 7. Action catalog                    — SKIP for Batch 2 (optional)
 8. Connector (services/connectors/)  — BaseConnector wrapper
 9. Bridge capabilities               — _INTEGRATION_CAPABILITIES in integration_bridge.py
10. Webhook handler (api/v1/)         — receives events from the provider
11. Frontend icon                     — ICON_MAP in integrations-page-content.tsx
12. Router registration               — webhook router mounted in api/v1/__init__.py
```

**Vercel:** All 12 layers (OAuth2 path).
**Jira:** All 12 layers + custom OAuth callback for site selection.

---

## PART A: Vercel Integration (1.5 weeks)

### Auth Model

Standard OAuth2. User connects their Vercel account via the integrations page. Token stored in `IntegrationConnection`. The connector uses the stored token for API calls.

**Vercel OAuth endpoints:**
- Authorize: `https://vercel.com/oauth/authorize`
- Token: `https://vercel.com/oauth/token`

**Scopes:** `user`, `projects`, `deployments`

### Step A1: Add Vercel OAuth provider (5 min)

**File:** `backend/app/core/oauth.py`

```python
    "vercel": OAuthProviderConfig(
        slug="vercel",
        name="Vercel",
        authorize_url="https://vercel.com/oauth/authorize",
        token_url="https://vercel.com/oauth/token",
        client_id_env="VERCEL_OAUTH_CLIENT_ID",
        client_secret_env="VERCEL_OAUTH_CLIENT_SECRET",
        scopes=["user", "projects", "deployments"],
    ),
```

---

### Step A2: Add Vercel settings (5 min)

**File:** `backend/app/config.py`

```python
    # Vercel integration
    VERCEL_OAUTH_CLIENT_ID: str = ""
    VERCEL_OAUTH_CLIENT_SECRET: str = ""
    VERCEL_WEBHOOK_SECRET: str = ""
```

---

### Step A3: Create VercelClient service (0.5 day)

**File (NEW):** `backend/app/services/vercel/vercel_client.py`

Async REST client for the Vercel API. Uses the user's stored OAuth token.

**Key endpoints:**

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| Get current user | GET | `/v2/user` | Credential validation |
| List projects | GET | `/v9/projects` | Paginated with `until` cursor |
| Get project | GET | `/v9/projects/{id}` | |
| List deployments | GET | `/v6/deployments` | Filter by project |
| Get deployment | GET | `/v13/deployments/{id}` | Status, URL, build logs |
| Cancel deployment | POST | `/v13/deployments/{id}/cancel` | |
| Redeploy | POST | `/v13/deployments` | Body: `{deploymentId, target, ...}` |
| Get deployment logs | GET | `/v2/deployments/{id}/events` | SSE stream of build events |
| List domains | GET | `/v9/projects/{id}/domains` | |

**Pagination quirk:** Vercel uses `until` (timestamp) cursor, not page numbers. The client must handle this.

---

### Step A4: Create VercelConnector (0.5 day)

**File (NEW):** `backend/app/services/connectors/vercel_connector.py`

Follow the `linear_connector.py` / `sentry_connector.py` pattern.

**Actions:**
- `get_me` — Get authenticated user info
- `list_projects` — List projects
- `get_project` — Get project details
- `list_deployments` — List deployments (optionally filtered by project)
- `get_deployment` — Get deployment details (status, URL, meta)
- `cancel_deployment` — Cancel a running deployment
- `redeploy` — Trigger a redeployment
- `get_deployment_logs` — Get build logs/events for a deployment
- `list_domains` — List domains for a project

**Rate limits:** Vercel uses `x-ratelimit-limit` and `x-ratelimit-remaining` headers.

---

### Step A5: Create Vercel webhook handler (0.5 day)

**File (NEW):** `backend/app/api/v1/vercel_webhook.py`

**Webhook URL:** `POST /api/vercel/webhook`

**Events:**
- `deployment.created` — New deployment started
- `deployment.succeeded` — Deployment went live
- `deployment.ready` — Alias for succeeded
- `deployment.failed` — Build or deployment failed
- `deployment.canceled` — Deployment was canceled

**Signature verification:** HMAC-SHA256 using `x-vercel-signature` header and `VERCEL_WEBHOOK_SECRET`.

```python
import hmac, hashlib

def _verify_vercel_signature(body: bytes, signature: str) -> bool:
    secret = settings.VERCEL_WEBHOOK_SECRET
    if not secret:
        return True  # Accept unsigned in dev
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

**Agent workflow trigger:** On `deployment.failed`, log the event for agent triage (same pattern as Sentry webhook).

---

### Step A6: Register Vercel bridge capabilities (15 min)

**File:** `backend/app/services/integration_bridge.py`

Add to `_INTEGRATION_CAPABILITIES`:

```python
    "vercel": [
        {"id": "get_me", "name": "Get Vercel User", ...},
        {"id": "list_projects", "name": "List Vercel Projects", ...},
        {"id": "get_project", "name": "Get Vercel Project", ...},
        {"id": "list_deployments", "name": "List Vercel Deployments", ...},
        {"id": "get_deployment", "name": "Get Vercel Deployment", ...},
        {"id": "cancel_deployment", "name": "Cancel Vercel Deployment", ...},
        {"id": "redeploy", "name": "Redeploy Vercel Project", ...},
        {"id": "get_deployment_logs", "name": "Get Deployment Logs", ...},
        {"id": "list_domains", "name": "List Vercel Domains", ...},
    ],
```

Vercel uses OAuth2 (not API key), so it does NOT need a `_NON_OAUTH_CONFIGS` entry. The OAuth token from `IntegrationConnection` is used directly.

---

### Step A7: Manifest + static registry + icon (30 min)

- **Manifest:** `backend/integrations/manifests/vercel.json` (auth_type: `oauth2`)
- **Static list:** Add `Integration(slug="vercel", ...)` to `AVAILABLE_INTEGRATIONS`
- **Frontend icon:** `SiVercel` from `@icons-pack/react-simple-icons` — add to `ICON_MAP`
- **Connect handler:** No special handling needed — standard OAuth2 flow works

---

### Step A8: Register connector + router (15 min)

- Register `VercelConnector` in `connectors/__init__.py` (CONNECTOR_TYPES + __all__)
- Register `VercelConnector` in `connectors/manager.py` (CONNECTOR_CLASSES)
- Register `vercel_webhook_router` in `api/v1/__init__.py`

---

### Step A9: Tests (30 min)

**File (NEW):** `backend/tests/test_vercel_integration.py`

Same pattern as `test_linear_integration.py` and `test_sentry_integration.py`:
- `test_vercel_in_v1_oauth_providers`
- `test_vercel_in_available_integrations`
- `test_vercel_manifest_exists`
- `test_vercel_bridge_capabilities`
- `test_vercel_webhook_router_exists`
- `test_vercel_connector_importable`
- `test_vercel_settings_exist`

---

### Step A10: Vercel OAuth setup (manual, for Glenn)

1. Go to https://vercel.com/dashboard/settings/integrations
2. Create new OAuth application
3. Set redirect URL: `https://flowmanner.com/api/integrations/vercel/oauth/callback`
4. Copy Client ID and Client Secret
5. Set in `.env`: `VERCEL_OAUTH_CLIENT_ID`, `VERCEL_OAUTH_CLIENT_SECRET`

---

## PART B: Jira Integration (2.5 weeks)

### Auth Model

Atlassian OAuth 2.0 (3LO) — **non-standard flow**. Requires:

1. Standard authorization redirect (with `audience=api.atlassian.com`)
2. Standard token exchange
3. **Site discovery:** `GET https://api.atlassian.com/oauth/token/accessible-resources` to get the user's Jira sites
4. **Site selection:** User picks which Jira site to connect (or auto-select if only one)
5. Store `cloudId` + access token in `IntegrationConnection`

The existing `oauth_callback` handler in `integrations.py` only handles steps 1-2. We need a **custom callback handler** for Jira that adds steps 3-5.

### Jira API Base URL

All Jira API calls go through:
```
https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3/...
```

The `cloudId` is obtained during the OAuth callback site discovery step.

### ADF (Atlassian Document Format)

Issue descriptions and comments must be in ADF format. Plain text is rejected by API v3.

**ADF structure for simple text:**
```json
{
  "version": 1,
  "type": "doc",
  "content": [
    {
      "type": "paragraph",
      "content": [{"type": "text", "text": "Issue description here"}]
    }
  ]
}
```

We need a helper function `text_to_adf(text: str) -> dict` that converts plain text to ADF, handling:
- Paragraphs (split on `\n\n`)
- Line breaks within paragraphs
- Basic formatting (bold, code) is nice-to-have but not required for Batch 2

---

### Step B1: Add Jira OAuth provider (5 min)

**File:** `backend/app/core/oauth.py`

```python
    "jira": OAuthProviderConfig(
        slug="jira",
        name="Jira",
        authorize_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        client_id_env="JIRA_OAUTH_CLIENT_ID",
        client_secret_env="JIRA_OAUTH_CLIENT_SECRET",
        scopes=["read:jira-work", "write:jira-work", "read:jira-user"],
        extra_auth_params={"audience": "api.atlassian.com", "prompt": "consent"},
    ),
```

**Note:** `extra_auth_params` adds `audience=api.atlassian.com` to the authorize URL. The `oauth_authorize` handler in `integrations.py` already supports `extra_auth_params` (line ~276: `if provider.extra_auth_params: params.update(provider.extra_auth_params)`).

---

### Step B2: Add Jira settings (5 min)

**File:** `backend/app/config.py`

```python
    # Jira integration
    JIRA_OAUTH_CLIENT_ID: str = ""
    JIRA_OAUTH_CLIENT_SECRET: str = ""
    JIRA_WEBHOOK_SECRET: str = ""
```

---

### Step B3: Custom Jira OAuth callback (1 day) — CRITICAL

The standard `oauth_callback` handler in `integrations.py` can't handle Jira's site discovery step. We need a **custom callback endpoint** for Jira.

**File:** `backend/app/api/v1/jira_oauth.py`

```python
router = APIRouter(prefix="/jira", tags=["jira"])

@router.get("/oauth/callback")
async def jira_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Custom OAuth callback for Jira with site discovery."""
    # 1. Validate state (from Redis)
    stored = _pop_state(state)
    if not stored:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    # 2. Exchange code for token (standard OAuth2)
    provider = OAUTH_PROVIDERS.get("jira")
    token_data = {
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "code": code,
        "redirect_uri": stored["redirect_uri"],
        "grant_type": "authorization_code",
        "audience": "api.atlassian.com",  # REQUIRED for Atlassian
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(provider.token_url, json=token_data)
    # ... validate response, extract access_token, refresh_token

    # 3. Site discovery (Jira-specific)
    async with httpx.AsyncClient() as client:
        sites_resp = await client.get(
            "https://api.atlassian.com/oauth/token/accessible-resources",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    sites = sites_resp.json()
    # sites = [{"id": "cloud-id-xxx", "url": "https://mysite.atlassian.net", "name": "My Site", ...}]

    # 4. Auto-select if only one site, otherwise store for later selection
    if len(sites) == 1:
        cloud_id = sites[0]["id"]
        account_name = sites[0]["name"]
    else:
        # Store sites in Redis, redirect to site selection UI
        # For Batch 2 MVP: use first site
        cloud_id = sites[0]["id"]
        account_name = sites[0]["name"]

    # 5. Store connection with cloudId in account_id field
    conn = IntegrationConnection(
        id=str(uuid4()),
        user_id=stored["user_id"],
        integration_slug="jira",
        encrypted_access_token=encrypt_token(access_token),
        encrypted_refresh_token=encrypt_token(refresh_token) if refresh_token else None,
        account_name=account_name,
        account_id=cloud_id,  # Store cloudId for API calls
        is_active=True,
    )
    # ... save to DB, register capabilities, redirect
```

**Why a separate file:** The Jira callback is complex enough to warrant its own router. It still uses the same `_pop_state` / `encrypt_token` / `IntegrationConnection` infrastructure as the generic callback.

**Redirect URL for Jira OAuth app:** `https://flowmanner.com/api/jira/oauth/callback` (NOT `/api/integrations/jira/oauth/callback`).

---

### Step B4: Create JiraClient service (1 day)

**File (NEW):** `backend/app/services/jira/jira_client.py`

Async REST client for Jira Cloud API v3. The `cloudId` is passed at construction time.

**Key endpoints:**

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| Get myself | GET | `/rest/api/3/myself` | Credential validation |
| List projects | GET | `/rest/api/3/project` | |
| Get project | GET | `/rest/api/3/project/{projectIdOrKey}` | |
| Search issues | POST | `/rest/api/3/search` | JQL body: `{jql, fields, maxResults}` |
| Get issue | GET | `/rest/api/3/issue/{issueIdOrKey}` | |
| Create issue | POST | `/rest/api/3/issue` | Body uses ADF for description |
| Update issue | PUT | `/rest/api/3/issue/{issueIdOrKey}` | |
| Add comment | POST | `/rest/api/3/issue/{issueIdOrKey}/comment` | Body uses ADF |
| List transitions | GET | `/rest/api/3/issue/{issueIdOrKey}/transitions` | For status changes |
| Transition issue | POST | `/rest/api/3/issue/{issueIdOrKey}/transitions` | Change status |
| List boards | GET | `/agile/1.0/board` | Scrum/Kanban boards |
| List sprints | GET | `/agile/1.0/board/{boardId}/sprint` | Sprint data |

**All requests go to:** `https://api.atlassian.com/ex/jira/{cloudId}/rest/api/3/...`

**ADF helper:**

```python
def text_to_adf(text: str) -> dict:
    """Convert plain text to Atlassian Document Format."""
    paragraphs = text.split("\n\n")
    content = []
    for para in paragraphs:
        if not para.strip():
            continue
        content.append({
            "type": "paragraph",
            "content": [{"type": "text", "text": para}],
        })
    return {"version": 1, "type": "doc", "content": content or [{"type": "paragraph"}]}
```

**Token refresh:** Atlassian supports refresh tokens. The client should handle 401 → refresh → retry. The `IntegrationBridge._get_connector` already has Google token refresh logic — we'll add Jira refresh alongside it.

---

### Step B5: Create JiraConnector (0.5 day)

**File (NEW):** `backend/app/services/connectors/jira_connector.py`

**Actions:**
- `list_projects` — List Jira projects
- `get_project` — Get project details
- `search_issues` — Search issues with JQL
- `get_issue` — Get issue details
- `create_issue` — Create issue (with ADF description)
- `update_issue` — Update issue fields
- `add_comment` — Add comment (with ADF body)
- `transition_issue` — Change issue status
- `list_boards` — List Scrum/Kanban boards
- `list_sprints` — List sprints for a board

**Constructor quirk:** The `cloudId` is needed for all API calls. It's stored in `IntegrationConnection.account_id`. The connector factory must extract it and pass it to the client.

**Update `_get_connector` in integration_bridge.py:**

```python
if slug == "jira":
    # Extract cloudId from connection's account_id
    cloud_id = conn.account_id
    config.auth_config["cloud_id"] = cloud_id
```

---

### Step B6: Create Jira webhook handler (0.5 day)

**File (NEW):** `backend/app/api/v1/jira_webhook.py`

**Webhook URL:** `POST /api/jira/webhook`

**Events:**
- `jira:issue_created` — New issue created
- `jira:issue_updated` — Issue updated (status, assignee, etc.)
- `jira:issue_deleted` — Issue deleted

**Signature verification:** Jira webhooks use a shared secret (not HMAC). The secret is passed as a query parameter or custom header. For Batch 2, we'll use a simple shared secret comparison.

**Note:** Jira webhooks are configured per-site via the REST API (`POST /rest/api/3/webhook`), not via a global setting. Users will need to manually configure webhooks in their Jira project settings pointing to `https://flowmanner.com/api/jira/webhook`.

---

### Step B7: Register Jira bridge capabilities (15 min)

**File:** `backend/app/services/integration_bridge.py`

Add to `_INTEGRATION_CAPABILITIES`:

```python
    "jira": [
        {"id": "list_projects", "name": "List Jira Projects", ...},
        {"id": "get_project", "name": "Get Jira Project", ...},
        {"id": "search_issues", "name": "Search Jira Issues", ...},
        {"id": "get_issue", "name": "Get Jira Issue", ...},
        {"id": "create_issue", "name": "Create Jira Issue", ...},
        {"id": "update_issue", "name": "Update Jira Issue", ...},
        {"id": "add_comment", "name": "Add Jira Comment", ...},
        {"id": "transition_issue", "name": "Transition Jira Issue", ...},
        {"id": "list_boards", "name": "List Jira Boards", ...},
        {"id": "list_sprints", "name": "List Jira Sprints", ...},
    ],
```

Jira uses OAuth2 (not API key), so no `_NON_OAUTH_CONFIGS` entry needed.

---

### Step B8: Add Jira token refresh to IntegrationBridge (0.5 day)

**File:** `backend/app/services/integration_bridge.py`

Atlassian tokens expire (typically 1 hour). Add Jira refresh alongside the existing Google refresh logic in `_get_connector`:

```python
if slug == "jira" and conn.encrypted_refresh_token:
    try:
        new_token = await self._refresh_jira_token(decrypt_token(conn.encrypted_refresh_token))
        if new_token:
            conn.encrypted_access_token = encrypt_token(new_token["access_token"])
            # ... same pattern as Google refresh
    except Exception as e:
        logger.warning("Failed to refresh Jira token for user %s: %s", user_id, e)
```

```python
@staticmethod
async def _refresh_jira_token(refresh_token: str) -> dict[str, Any] | None:
    """Exchange a Jira refresh token for a fresh access token."""
    provider = OAUTH_PROVIDERS.get("jira")
    data = {
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(provider.token_url, data=data)
    if resp.status_code != 200:
        return None
    return resp.json()
```

---

### Step B9: Custom Jira OAuth callback router registration (5 min)

**File:** `backend/app/api/v1/__init__.py`

```python
jira_oauth_router = _import_router("jira_oauth")
# ... in the router registration:
("jira-oauth", jira_oauth_router),
```

Also register the webhook router:
```python
jira_webhook_router = _import_router("jira_webhook")
("jira", jira_webhook_router),
```

---

### Step B10: Manifest + static registry + icon (30 min)

- **Manifest:** `backend/integrations/manifests/jira.json` (auth_type: `oauth2`)
- **Static list:** Add `Integration(slug="jira", ...)` to `AVAILABLE_INTEGRATIONS`
- **Frontend icon:** Check `@icons-pack/react-simple-icons` for `SiJira`. If available, add to `ICON_MAP`. If not, create custom SVG (Atlassian logo).
- **Connect handler:** The standard OAuth2 flow in `integrations.py` redirects to `/integrations/jira/oauth/authorize`. But our custom callback is at `/api/jira/oauth/callback`. We need to make sure the `redirect_uri` in the authorize step points to the custom callback.

**Override for Jira authorize redirect:** In `oauth_authorize`, the redirect URI is built from `request.url_for("oauth_callback", slug=slug)`. For Jira, we need to redirect to the custom callback URL instead. Add a special case:

```python
# In oauth_authorize, after building redirect_uri:
if slug == "jira":
    redirect_uri = redirect_uri.replace(
        f"/api/integrations/jira/oauth/callback",
        "/api/jira/oauth/callback",
    )
```

---

### Step B11: JiraConnector cloudId extraction (15 min)

**File:** `backend/app/services/integration_bridge.py`

Update `_get_connector` to extract `cloudId` from `conn.account_id` for Jira:

```python
# In _get_connector, after decrypting the token:
if slug == "jira":
    cloud_id = conn.account_id
    if not cloud_id:
        logger.warning("No cloudId for user %s Jira connection", user_id)
        return None
    config = ConnectorConfig(
        name=f"jira-user-{user_id}",
        connector_type="jira",
        auth_type=AuthType.OAUTH2,
        auth_config={"access_token": access_token, "cloud_id": cloud_id},
    )
```

---

### Step B12: Tests (30 min)

**File (NEW):** `backend/tests/test_jira_integration.py`

Same pattern as other integration tests:
- `test_jira_in_v1_oauth_providers`
- `test_jira_in_available_integrations`
- `test_jira_manifest_exists`
- `test_jira_bridge_capabilities`
- `test_jira_webhook_router_exists`
- `test_jira_connector_importable`
- `test_jira_settings_exist`
- `test_jira_text_to_adf` — Verify ADF conversion
- `test_jira_oauth_callback_router_exists`

---

### Step B13: Jira OAuth setup (manual, for Glenn)

1. Go to https://developer.atlassian.com/console/myapps/
2. Create new OAuth 2.0 (3LO) app
3. Set redirect URL: `https://flowmanner.com/api/jira/oauth/callback`
4. Add permissions: `read:jira-work`, `write:jira-work`, `read:jira-user`
5. Copy Client ID and Client Secret
6. Set in `.env`: `JIRA_OAUTH_CLIENT_ID`, `JIRA_OAUTH_CLIENT_SECRET`

---

## PART C: Cross-Integration Workflow (bonus, 0.5 day)

### The Killer Workflow: Sentry Error → Linear/Jira Issue

Now that we have Sentry, Linear, and Jira all wired, we can document the intended agent workflow. No code changes needed — the agent tools are already available via the bridge capabilities. But we should add a test that verifies the tools are all discoverable.

**File (NEW):** `backend/tests/test_cross_integration_workflow.py`

```python
def test_sentry_linear_jira_tools_all_discoverable():
    """All three integrations have bridge capabilities registered."""
    from app.services.integration_bridge import _INTEGRATION_CAPABILITIES

    sentry_caps = _INTEGRATION_CAPABILITIES.get("sentry", [])
    linear_caps = _INTEGRATION_CAPABILITIES.get("linear", [])
    jira_caps = _INTEGRATION_CAPABILITIES.get("jira", [])

    assert len(sentry_caps) >= 8
    assert len(linear_caps) >= 7
    assert len(jira_caps) >= 10

    # The full triage workflow tools exist
    sentry_ids = {c["id"] for c in sentry_caps}
    assert "get_latest_event" in sentry_ids  # Get stack trace
    assert "list_issues" in sentry_ids       # Poll for new errors

    linear_ids = {c["id"] for c in linear_caps}
    assert "create_issue" in linear_ids      # Create Linear issue

    jira_ids = {c["id"] for c in jira_caps}
    assert "create_issue" in jira_ids        # Create Jira issue
    assert "search_issues" in jira_ids       # Check for duplicates
```

---

## PART D: Verification + Deploy

### Step D1: Full test run

```bash
cd /opt/flowmanner/backend
python -m pytest tests/test_vercel_integration.py tests/test_jira_integration.py tests/test_cross_integration_workflow.py -v

# Also run existing integration tests to make sure nothing broke
python -m pytest tests/ -k "linear or sentry" -v
```

### Step D2: Lint + Format

```bash
cd /opt/flowmanner/backend
ruff check app/services/vercel/ app/services/jira/ app/services/connectors/vercel_connector.py app/services/connectors/jira_connector.py app/api/v1/vercel_webhook.py app/api/v1/jira_webhook.py app/api/v1/jira_oauth.py app/core/oauth.py app/config.py app/api/v1/integrations.py app/api/v1/__init__.py app/services/integration_bridge.py tests/test_vercel_integration.py tests/test_jira_integration.py tests/test_cross_integration_workflow.py
```

### Step D3: Commit

```bash
cd /opt/flowmanner
git add backend/
git commit -m "feat(integrations): add Vercel + Jira integrations (Batch 2)

Vercel:
- New VercelClient REST service
- New VercelConnector (9 actions)
- New webhook handler (deployment events)
- OAuth2 integration with standard flow
- Register 9 bridge capabilities

Jira:
- New JiraClient REST service (Atlassian API v3)
- New JiraConnector (10 actions)
- Custom OAuth callback with site discovery
- ADF (Atlassian Document Format) conversion
- Token refresh support
- Webhook handler (issue events)
- Register 10 bridge capabilities

Cross-integration:
- Test verifying Sentry+Linear+Jira tool discoverability
- Enables Sentry error → Linear/Jira issue workflow"
git push origin main
```

### Step D4: Deploy (Glenn does this)

```bash
bash /opt/flowmanner/deploy-backend.sh
```

---

## Done Criteria

### Vercel
- [ ] `GET /api/integrations` includes Vercel
- [ ] Vercel OAuth provider registered in v1
- [ ] Vercel manifest at `integrations/manifests/vercel.json`
- [ ] VercelConnector importable with 9 actions
- [ ] `POST /api/vercel/webhook` endpoint exists
- [ ] 9 bridge capabilities registered
- [ ] Vercel icon renders on `/integrations` page
- [ ] All 7 test functions pass

### Jira
- [ ] `GET /api/integrations` includes Jira
- [ ] Jira OAuth provider registered with `audience` param
- [ ] Custom OAuth callback at `/api/jira/oauth/callback` handles site discovery
- [ ] Jira manifest at `integrations/manifests/jira.json`
- [ ] JiraConnector importable with 10 actions
- [ ] `text_to_adf` helper works correctly
- [ ] Token refresh implemented in IntegrationBridge
- [ ] `POST /api/jira/webhook` endpoint exists
- [ ] 10 bridge capabilities registered
- [ ] Jira icon renders on `/integrations` page
- [ ] All 9 test functions pass

### Shared
- [ ] `ruff check` passes on all new/modified files
- [ ] All 15+ new tests pass
- [ ] Commit pushed to `origin/main`
- [ ] Backend deployed and healthy

---

## Files Summary

### New files (10)

| File | Purpose |
|------|---------|
| `backend/app/services/vercel/__init__.py` | Vercel service package |
| `backend/app/services/vercel/vercel_client.py` | Vercel REST API client |
| `backend/app/services/jira/__init__.py` | Jira service package |
| `backend/app/services/jira/jira_client.py` | Jira REST API client + ADF helper |
| `backend/app/services/connectors/vercel_connector.py` | Vercel BaseConnector wrapper |
| `backend/app/services/connectors/jira_connector.py` | Jira BaseConnector wrapper |
| `backend/app/api/v1/vercel_webhook.py` | Vercel webhook handler |
| `backend/app/api/v1/jira_webhook.py` | Jira webhook handler |
| `backend/app/api/v1/jira_oauth.py` | Custom Jira OAuth callback with site discovery |
| `backend/integrations/manifests/vercel.json` | Vercel manifest |
| `backend/integrations/manifests/jira.json` | Jira manifest |
| `backend/tests/test_vercel_integration.py` | Vercel wiring tests |
| `backend/tests/test_jira_integration.py` | Jira wiring tests |
| `backend/tests/test_cross_integration_workflow.py` | Cross-integration discoverability test |

### Modified files (7)

| File | Change |
|------|--------|
| `backend/app/core/oauth.py` | Add Vercel + Jira OAuthProviderConfig |
| `backend/app/config.py` | Add VERCEL_*, JIRA_* settings |
| `backend/app/api/v1/integrations.py` | Add Vercel + Jira to AVAILABLE_INTEGRATIONS |
| `backend/app/api/v1/__init__.py` | Register vercel_webhook, jira_oauth, jira_webhook routers |
| `backend/app/services/integration_bridge.py` | Add Vercel + Jira capabilities + Jira token refresh |
| `backend/app/services/connectors/__init__.py` | Register VercelConnector + JiraConnector |
| `backend/app/services/connectors/manager.py` | Register VercelConnector + JiraConnector in CONNECTOR_CLASSES |

---

## Deferred to Batch 3 / Future

| Item | Why deferred |
|------|-------------|
| **Vercel v2 adapter + action catalog** | Optional v2 actions API path. v1 bridge is sufficient for agent tools. |
| **Jira v2 adapter + action catalog** | Same as Vercel. |
| **Jira site selection UI** | For Batch 2, auto-select first site. Multi-site selection UI deferred. |
| **Jira webhook auto-registration** | Manual webhook setup in Jira. Auto-registration via Connect app deferred. |
| **Confluence integration** | Natural pair with Jira (same Atlassian OAuth). Separate integration. |
| **Vercel + Jira cross-workflow** (deploy → Jira status update) | Requires event routing design. Deferred. |

---

## Context for Implementation

- You are on the **homelab** (172.16.1.1 / 10.99.0.3).
- Backend source: `/opt/flowmanner/backend/`
- Frontend source: `/home/glenn/FlowmannerV2-frontend/`
- **TWO OAuth systems exist.** The integration page uses v1 (`app/core/oauth.py`). Do NOT edit `app/integrations/oauth.py`.
- Batch 1 (Linear + Sentry) is deployed. Don't modify those files.
- The `oauth_authorize` handler already supports `extra_auth_params` — Jira's `audience` param works without modification.
- The `oauth_callback` handler in `integrations.py` handles standard OAuth2. Jira needs a **custom callback** because of the site discovery step.
- After all changes, follow `SESSION-RITUAL.md`. Commit and push.
- **DO NOT deploy.** Glenn deploys himself after review.
