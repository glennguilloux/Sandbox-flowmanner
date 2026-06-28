# PLAN — Tier 1 Integrations: Batch 9 (Shopify + Zendesk + Monday.com + Telegram)

**Date:** June 28, 2026
**Status:** Draft — ready for review
**Scope:** Add new Shopify integration (12 actions) + new Zendesk integration (12 actions) + new Monday.com integration (10 actions) + new Telegram integration (12 actions).
**Machine:** homelab (172.16.1.1)
**Prerequisite:** Batches 1-8 deployed and stable (23 integrations total, 234 bridge capabilities).
**Estimated effort:** Shopify ~4 days, Zendesk ~3 days, Monday.com ~3 days, Telegram ~2 days. Total ~2 weeks.

---

## TL;DR

Batch 9 adds three new integrations covering e-commerce, customer support, and project management:

- **Shopify** — E-commerce platform. The killer workflow: *Shopify order placed → agent creates HubSpot deal + sends Twilio SMS confirmation*. Standard OAuth2 with shop-specific URLs. HMAC-SHA256 webhook verification. Leaky-bucket rate limits (40 req/min baseline). **High business value.**
- **Zendesk** — Customer support ticketing. The killer workflow: *Zendesk ticket created → agent creates ClickUp/Linear task + searches Notion for relevant docs*. Standard OAuth2 with subdomain-specific URLs. HMAC webhook verification. **Fills the support ticketing gap beyond Intercom.**
- **Monday.com** — Work management platform. The killer workflow: *Sentry error → agent creates Monday item with severity + stack trace link*. Standard OAuth2. Complexity-based rate limits (not request-count). **Broadens the project management options beyond Asana/ClickUp/Jira.**
- **Telegram** — Messaging platform via Bot API. The killer workflow: *Mission complete → agent sends summary to Telegram group + pins it*. Bot token auth (no OAuth). **Unlocks conversational agent notifications and two-way chat via Telegram bots.**

**Key insight:** Shopify uses shop-specific URLs (`{shop}.myshopify.com`) — the OAuth flow must dynamically set the authorize and token URLs per shop. Zendesk similarly uses subdomain-specific URLs. Monday.com uses a GraphQL API (not REST) — a first for our integrations. Telegram uses bot tokens (like Twilio's API key pattern) — no OAuth needed.

---

## ⚠️ KEY FINDINGS FROM RESEARCH

### Shopify — E-Commerce Platform

| Aspect | What Shopify does |
|--------|-------------------|
| Authorize URL | `https://{shop}.myshopify.com/admin/oauth/authorize` (dynamic per shop) |
| Token URL | `https://{shop}.myshopify.com/admin/oauth/access_token` |
| Token exchange format | Standard JSON: `access_token` |
| Refresh endpoint | N/A — tokens do NOT expire (app-level tokens) |
| Auth header | `X-Shopify-Access-Token: {access_token}` |
| API base URL | `https://{shop}.myshopify.com/admin/api/2024-01` |
| **Quirk** | Shop-specific URLs — must capture `shop` param during OAuth and store it. Access tokens are long-lived and don't expire. |
| Rate limits | Leaky bucket: 40 req/min (REST), replenishes at 2/sec. Monitor `X-Shopify-Shop-Api-Call-Limit` header. |
| Webhook | HMAC-SHA256 in `X-Shopify-Hmac-SHA256` header (base64 digest of body using app secret) |
| Token expiry | **Never** (app-level access tokens) |

**Important quirk:** Shopify access tokens do not expire. The OAuth flow requires capturing the `shop` parameter from the initial request and using it to construct dynamic authorize/token URLs. We'll store the shop domain in `account_name` on the `IntegrationConnection`.

### Zendesk — Customer Support

| Aspect | What Zendesk does |
|--------|-------------------|
| Authorize URL | `https://{subdomain}.zendesk.com/oauth/authorizations/new` (dynamic per subdomain) |
| Token URL | `https://{subdomain}.zendesk.com/oauth/tokens` |
| Token exchange format | Standard JSON: `access_token`, `refresh_token`, `expires_in` |
| Refresh endpoint | Same token URL with `grant_type=refresh_token` |
| Auth header | `Authorization: Bearer {access_token}` |
| API base URL | `https://{subdomain}.zendesk.com/api/v2` |
| **Quirk** | Subdomain-specific URLs — must capture subdomain during OAuth. Tokens expire in ~12 hours. |
| Rate limits | Dynamic based on plan: 200-700 req/min. Monitor `X-Rate-Limit` header. |
| Webhook | Shared secret verification via `X-Zendesk-Webhook-Signature` header |
| Token expiry | ~12 hours (refresh token long-lived) |

**Important quirk:** Zendesk uses subdomain-specific URLs, similar to Shopify's shop-specific pattern. The subdomain must be captured during OAuth and stored in `account_name`. Tokens expire in ~12 hours (not the typical 30-min or 1-hour window).

### Monday.com — Work Management

| Aspect | What Monday.com does |
|--------|---------------------|
| Authorize URL | `https://auth.monday.com/oauth2/authorize` |
| Token URL | `https://auth.monday.com/oauth2/token` |
| Token exchange format | Standard JSON: `access_token`, `refresh_token`, `expires_in` |
| Refresh endpoint | Same token URL with `grant_type=refresh_token` |
| Auth header | `Authorization: Bearer {access_token}` |
| API base URL | `https://api.monday.com/v2` (GraphQL) |
| **Quirk** | **GraphQL API** (not REST) — all requests are POST to a single endpoint with a `query` field. First GraphQL integration. Rate limits based on query complexity (not request count). |
| Rate limits | Complexity-based: each query has a "cost" and you have a per-minute complexity budget. Monitor via response headers. |
| Webhook | No standard signature verification — security via tokens in URL or IP whitelisting |
| Token expiry | Long-lived (no expiry for personal tokens), OAuth tokens may vary |

**Important quirk:** Monday.com uses GraphQL, not REST. All requests are POST to `https://api.monday.com/v2` with a JSON body containing `{ "query": "..." }`. This is the first GraphQL integration — the client will need to send GraphQL queries rather than REST calls.

---

## PART A: Shopify Integration (~4 days)

### Auth Model

Standard OAuth 2.0 Authorization Code flow with **dynamic URLs**. The `shop` parameter must be captured from the connect request and used to construct the authorize and token URLs. Tokens do NOT expire.

### Step A1: Add Shopify OAuth provider

**File:** `backend/app/core/oauth.py`

Shopify requires dynamic URLs per shop. We'll use a placeholder URL and override it in the OAuth flow with the actual shop domain. The `extra_auth_params` will include `scope` as a comma-separated string (Shopify uses comma-separated scopes, not space-separated).

```python
"shopify": OAuthProviderConfig(
    slug="shopify",
    name="Shopify",
    authorize_url="https://{shop}.myshopify.com/admin/oauth/authorize",  # Dynamic — overridden at runtime
    token_url="https://{shop}.myshopify.com/admin/oauth/access_token",   # Dynamic — overridden at runtime
    client_id_env="SHOPIFY_OAUTH_CLIENT_ID",
    client_secret_env="SHOPIFY_OAUTH_CLIENT_SECRET",
    scopes=[
        "read_products",
        "write_products",
        "read_orders",
        "write_orders",
        "read_customers",
        "read_inventory",
    ],
),
```

### Step A2: Add Shopify settings

**File:** `backend/app/config.py`

```python
# Shopify integration
SHOPIFY_OAUTH_CLIENT_ID: str = ""
SHOPIFY_OAUTH_CLIENT_SECRET: str = ""
SHOPIFY_WEBHOOK_SECRET: str = ""
```

### Step A3: Create ShopifyClient service

**File (NEW):** `backend/app/services/shopify/shopify_client.py`

Async REST client for Shopify Admin API. Auth via `X-Shopify-Access-Token` header. Shop-specific base URL.

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| get_shop | GET | `/shop.json` | Credential validation |
| list_products | GET | `/products.json` | Products (paginated) |
| get_product | GET | `/products/{id}.json` | Product details |
| create_product | POST | `/products.json` | Create product |
| list_orders | GET | `/orders.json` | Orders (paginated) |
| get_order | GET | `/orders/{id}.json` | Order details |
| update_order | PUT | `/orders/{id}.json` | Update order |
| list_customers | GET | `/customers.json` | Customers (paginated) |
| get_customer | GET | `/customers/{id}.json` | Customer details |
| list_inventory_levels | GET | `/inventory_levels.json?inventory_item_ids={ids}` | Inventory |
| create_webhook | POST | `/webhooks.json` | Programmatically create webhooks |
| list_transactions | GET | `/orders/{id}/transactions.json` | Payment transactions |

### Step A4: Create ShopifyConnector

**File (NEW):** `backend/app/services/connectors/shopify_connector.py`

12 actions. Follow vercel_connector pattern.

### Step A5: Create Shopify webhook handler

**File (NEW):** `backend/app/api/v1/shopify_webhook.py`

Webhook signature: Shopify uses HMAC-SHA256. Signature in `X-Shopify-Hmac-SHA256` header as base64 digest. Verify by computing HMAC of raw body using the app's shared secret.

Events: `orders/create`, `orders/updated`, `products/create`, `products/update`, `customers/create`.

### Step A6: Register Shopify bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"shopify": [
    {"id": "get_shop", "name": "Get Shopify Shop", ...},
    {"id": "list_products", "name": "List Shopify Products", ...},
    {"id": "get_product", "name": "Get Shopify Product", ...},
    {"id": "create_product", "name": "Create Shopify Product", ...},
    {"id": "list_orders", "name": "List Shopify Orders", ...},
    {"id": "get_order", "name": "Get Shopify Order", ...},
    {"id": "update_order", "name": "Update Shopify Order", ...},
    {"id": "list_customers", "name": "List Shopify Customers", ...},
    {"id": "get_customer", "name": "Get Shopify Customer", ...},
    {"id": "list_inventory_levels", "name": "List Shopify Inventory Levels", ...},
    {"id": "create_webhook", "name": "Create Shopify Webhook", ...},
    {"id": "list_transactions", "name": "List Shopify Transactions", ...},
],
```

### Step A7: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/shopify.json`
- **Static list:** Add `Integration(slug="shopify", ...)`
- **Frontend icon:** `SiShopify` from `@icons-pack/react-simple-icons`
- **Connect handler:** Modified OAuth2 flow (requires `shop` parameter)

### Step A8: Register connector + router

- Register `ShopifyConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `shopify_webhook_router` in `api/v1/__init__.py`

### Step A9: Token refresh

**No token refresh needed.** Shopify app-level access tokens do not expire.

### Step A10: Tests

**File (NEW):** `backend/tests/test_shopify_integration.py`

- `test_shopify_in_v1_oauth_providers`
- `test_shopify_in_available_integrations`
- `test_shopify_manifest_exists`
- `test_shopify_bridge_capabilities`
- `test_shopify_webhook_router_exists`
- `test_shopify_connector_importable`
- `test_shopify_settings_exist`

---

## PART B: Zendesk Integration (~3 days)

### Auth Model

Standard OAuth 2.0 Authorization Code flow with **subdomain-specific URLs**. The subdomain must be captured from the connect request. Tokens expire in ~12 hours.

### Step B1: Add Zendesk OAuth provider

**File:** `backend/app/core/oauth.py`

```python
"zendesk": OAuthProviderConfig(
    slug="zendesk",
    name="Zendesk",
    authorize_url="https://{subdomain}.zendesk.com/oauth/authorizations/new",  # Dynamic
    token_url="https://{subdomain}.zendesk.com/oauth/tokens",  # Dynamic
    client_id_env="ZENDESK_OAUTH_CLIENT_ID",
    client_secret_env="ZENDESK_OAUTH_CLIENT_SECRET",
    scopes=[
        "read",
        "write",
    ],
),
```

### Step B2: Add Zendesk settings

**File:** `backend/app/config.py`

```python
# Zendesk integration
ZENDESK_OAUTH_CLIENT_ID: str = ""
ZENDESK_OAUTH_CLIENT_SECRET: str = ""
ZENDESK_WEBHOOK_SECRET: str = ""
```

### Step B3: Create ZendeskClient service

**File (NEW):** `backend/app/services/zendesk/zendesk_client.py`

Async REST client for Zendesk API v2. Auth via `Authorization: Bearer {access_token}`. Subdomain-specific base URL.

| Action | Method | Endpoint | Notes |
|--------|--------|----------|-------|
| get_me | GET | `/users/me.json` | Credential validation |
| list_tickets | GET | `/tickets.json` | Tickets (paginated with `page`) |
| get_ticket | GET | `/tickets/{id}.json` | Ticket details |
| create_ticket | POST | `/tickets.json` | Create ticket |
| update_ticket | PUT | `/tickets/{id}.json` | Update ticket (status, priority, assignee) |
| list_users | GET | `/users.json` | Users (paginated) |
| get_user | GET | `/users/{id}.json` | User details |
| search_tickets | GET | `/search.json?query=...` | Search with Zendesk query syntax |
| list_organizations | GET | `/organizations.json` | Organizations (paginated) |
| list_groups | GET | `/groups.json` | Agent groups |
| add_ticket_comment | PUT | `/tickets/{id}.json` | Add comment via update |
| list_ticket_metrics | GET | `/ticket_metrics.json` | Ticket satisfaction/SLA metrics |

### Step B4: Create ZendeskConnector

**File (NEW):** `backend/app/services/connectors/zendesk_connector.py`

12 actions. Follow vercel_connector pattern.

### Step B5: Create Zendesk webhook handler

**File (NEW):** `backend/app/api/v1/zendesk_webhook.py`

Webhook signature: Zendesk uses `X-Zendesk-Webhook-Signature` header for shared secret verification.

Events: `ticket.created`, `ticket.updated`, `ticket.solved`.

### Step B6: Register Zendesk bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"zendesk": [
    {"id": "get_me", "name": "Get Zendesk User", ...},
    {"id": "list_tickets", "name": "List Zendesk Tickets", ...},
    {"id": "get_ticket", "name": "Get Zendesk Ticket", ...},
    {"id": "create_ticket", "name": "Create Zendesk Ticket", ...},
    {"id": "update_ticket", "name": "Update Zendesk Ticket", ...},
    {"id": "list_users", "name": "List Zendesk Users", ...},
    {"id": "get_user", "name": "Get Zendesk User", ...},
    {"id": "search_tickets", "name": "Search Zendesk Tickets", ...},
    {"id": "list_organizations", "name": "List Zendesk Organizations", ...},
    {"id": "list_groups", "name": "List Zendesk Groups", ...},
    {"id": "add_ticket_comment", "name": "Add Zendesk Ticket Comment", ...},
    {"id": "list_ticket_metrics", "name": "List Zendesk Ticket Metrics", ...},
],
```

### Step B7: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/zendesk.json`
- **Static list:** Add `Integration(slug="zendesk", ...)`
- **Frontend icon:** `SiZendesk` from `@icons-pack/react-simple-icons`
- **Connect handler:** Modified OAuth2 flow (requires subdomain parameter)

### Step B8: Register connector + router

- Register `ZendeskConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `zendesk_webhook_router` in `api/v1/__init__.py`

### Step B9: Token refresh

Add Zendesk token refresh block in `integration_bridge.py` using generic `_refresh_oauth_token()`. Tokens expire in ~12 hours.

### Step B10: Tests

**File (NEW):** `backend/tests/test_zendesk_integration.py`

- `test_zendesk_in_v1_oauth_providers`
- `test_zendesk_in_available_integrations`
- `test_zendesk_manifest_exists`
- `test_zendesk_bridge_capabilities`
- `test_zendesk_webhook_router_exists`
- `test_zendesk_connector_importable`
- `test_zendesk_settings_exist`

---

## PART C: Monday.com Integration (~3 days)

### Auth Model

Standard OAuth 2.0 Authorization Code flow. **First GraphQL integration** — all API calls go to a single POST endpoint with a `query` body. Tokens expire in ~30 days for OAuth apps.

### Step C1: Add Monday.com OAuth provider

**File:** `backend/app/core/oauth.py`

```python
"monday": OAuthProviderConfig(
    slug="monday",
    name="Monday.com",
    authorize_url="https://auth.monday.com/oauth2/authorize",
    token_url="https://auth.monday.com/oauth2/token",
    client_id_env="MONDAY_OAUTH_CLIENT_ID",
    client_secret_env="MONDAY_OAUTH_CLIENT_SECRET",
    scopes=[
        "boards:read",
        "boards:write",
        "items:read",
        "items:write",
        "users:read",
    ],
),
```

### Step C2: Add Monday.com settings

**File:** `backend/app/config.py`

```python
# Monday.com integration
MONDAY_OAUTH_CLIENT_ID: str = ""
MONDAY_OAUTH_CLIENT_SECRET: str = ""
MONDAY_WEBHOOK_SECRET: str = ""
```

### Step C3: Create MondayClient service

**File (NEW):** `backend/app/services/monday/monday_client.py`

Async client for Monday.com GraphQL API. All requests are POST to `https://api.monday.com/v2` with a `{ "query": "..." }` body. Auth via `Authorization: Bearer {access_token}`.

| Action | GraphQL Query | Notes |
|--------|--------------|-------|
| get_me | `{ me { id name email } }` | Credential validation |
| list_boards | `{ boards(limit: 50) { id name state description } }` | Boards (paginated) |
| get_board | `{ boards(ids: [board_id]) { id name columns { id title type } groups { id title } } }` | Board details + schema |
| list_items | `{ boards(ids: [board_id]) { items_page(limit: 50) { items { id name column_values { id text value } } } } }` | Items in a board |
| get_item | `{ items(ids: [item_id]) { id name column_values { id text value } } }` | Item details |
| create_item | `mutation { create_item(board_id, group_id, item_name, column_values) { id } }` | Create item |
| update_item | `mutation { change_column_values(item_id, board_id, column_values) { id } }` | Update item columns |
| create_update | `mutation { create_update(item_id, body) { id } }` | Add comment/update |
| list_users | `{ users(limit: 50) { id name email } }` | Workspace users |
| list_workspaces | `{ workspaces { id name } }` | Workspaces |

### Step C4: Create MondayConnector

**File (NEW):** `backend/app/services/connectors/monday_connector.py`

10 actions. Follow vercel_connector pattern.

### Step C5: Create Monday.com webhook handler

**File (NEW):** `backend/app/api/v1/monday_webhook.py`

Monday.com webhooks do not use standard HMAC signature verification. Security is handled via tokens in the URL or IP whitelisting. The handler will validate the incoming payload structure.

Events: `change_column_value`, `create_item`, `create_update`.

### Step C6: Register Monday.com bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"monday": [
    {"id": "get_me", "name": "Get Monday User", ...},
    {"id": "list_boards", "name": "List Monday Boards", ...},
    {"id": "get_board", "name": "Get Monday Board", ...},
    {"id": "list_items", "name": "List Monday Items", ...},
    {"id": "get_item", "name": "Get Monday Item", ...},
    {"id": "create_item", "name": "Create Monday Item", ...},
    {"id": "update_item", "name": "Update Monday Item", ...},
    {"id": "create_update", "name": "Create Monday Update (Comment)", ...},
    {"id": "list_users", "name": "List Monday Users", ...},
    {"id": "list_workspaces", "name": "List Monday Workspaces", ...},
],
```

### Step C7: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/monday.json`
- **Static list:** Add `Integration(slug="monday", ...)`
- **Frontend icon:** `SiMondaydotcom` from `@icons-pack/react-simple-icons`
- **Connect handler:** Standard OAuth2 flow

### Step C8: Register connector + router

- Register `MondayConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `monday_webhook_router` in `api/v1/__init__.py`

### Step C9: Token refresh

Add Monday.com token refresh block in `integration_bridge.py` using generic `_refresh_oauth_token()`. OAuth tokens are long-lived (~30 days) but refresh is still supported.

### Step C10: Tests

**File (NEW):** `backend/tests/test_monday_integration.py`

- `test_monday_in_v1_oauth_providers`
- `test_monday_in_available_integrations`
- `test_monday_manifest_exists`
- `test_monday_bridge_capabilities`
- `test_monday_webhook_router_exists`
- `test_monday_connector_importable`
- `test_monday_settings_exist`

---

## PART D: Telegram Integration (~2 days)

### Auth Model

**Bot token auth** (no OAuth). Same pattern as Twilio — API key stored in settings. The bot token is obtained by messaging @BotFather on Telegram and creating a new bot. Token format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`.

### Key Findings — Telegram Bot API

| Aspect | What Telegram does |
|--------|-------------------|
| Auth | Bot token in URL: `https://api.telegram.org/bot<TOKEN>/method` |
| Token format | `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` (from @BotFather) |
| API base URL | `https://api.telegram.org/bot<TOKEN>` |
| **Quirk** | Token is embedded in the URL path, not a header. Each API call is `GET` or `POST` to `/bot<TOKEN>/<method>`. |
| Rate limits | ~30 messages/sec to different chats, ~1 msg/sec to same chat. ~20 messages/min to same group. |
| Webhook | HTTPS only. Set via `setWebhook` with a public URL. Telegram sends updates as JSON POST. Optional secret token in `X-Telegram-Bot-Api-Secret-Token` header. |
| Polling | Alternative to webhook: `getUpdates` long-polling. |
| Token expiry | **Never** (bot tokens don't expire unless revoked via @BotFather) |

**Important quirk:** Telegram bot tokens are embedded in the URL path, not sent as headers. The client must construct URLs like `https://api.telegram.org/bot123456789:ABC.../sendMessage`. This differs from every other integration we have.

### Step D1: Add Telegram settings

**File:** `backend/app/config.py`

```python
# Telegram integration
TELEGRAM_BOT_TOKEN: str = ""
TELEGRAM_WEBHOOK_SECRET: str = ""  # X-Telegram-Bot-Api-Secret-Token
```

No OAuth — just a bot token. Add to `_NON_OAUTH_CONFIGS` in `integrations.py`.

### Step D2: Create TelegramClient service

**File (NEW):** `backend/app/services/telegram/__init__.py` + `backend/app/services/telegram/telegram_client.py`

Async REST client for Telegram Bot API. Auth via bot token in URL path.

| Action | Method | Telegram API Method | Notes |
|--------|--------|---------------------|-------|
| get_me | GET | `getMe` | Credential validation — returns bot info |
| send_message | POST | `sendMessage` | Send text message to chat |
| send_photo | POST | `sendPhoto` | Send photo (URL or file_id) |
| send_document | POST | `sendDocument` | Send file/document |
| edit_message | POST | `editMessageText` | Edit a previously sent message |
| delete_message | POST | `deleteMessage` | Delete a message |
| forward_message | POST | `forwardMessage` | Forward message to another chat |
| get_chat | POST | `getChat` | Get chat info (title, type, etc.) |
| get_chat_member | POST | `getChatMember` | Get info about a chat member |
| pin_message | POST | `pinChatMessage` | Pin a message in a chat |
| set_webhook | POST | `setWebhook` | Configure webhook URL for bot updates |
| get_updates | GET | `getUpdates` | Poll for updates (alternative to webhook) |

### Step D3: Create TelegramConnector

**File (NEW):** `backend/app/services/connectors/telegram_connector.py`

12 actions. Follow twilio_connector pattern (API key auth, not OAuth).

### Step D4: Create Telegram webhook handler

**File (NEW):** `backend/app/api/v1/telegram_webhook.py`

Telegram sends updates as JSON POST to the webhook URL. Optional verification via `X-Telegram-Bot-Api-Secret-Token` header (compare against configured secret).

Events: `message`, `edited_message`, `channel_post`, `my_chat_member`.

### Step D5: Register Telegram bridge capabilities

**File:** `backend/app/services/integration_bridge.py`

```python
"telegram": [
    {"id": "get_me", "name": "Get Telegram Bot Info", ...},
    {"id": "send_message", "name": "Send Telegram Message", ...},
    {"id": "send_photo", "name": "Send Telegram Photo", ...},
    {"id": "send_document", "name": "Send Telegram Document", ...},
    {"id": "edit_message", "name": "Edit Telegram Message", ...},
    {"id": "delete_message", "name": "Delete Telegram Message", ...},
    {"id": "forward_message", "name": "Forward Telegram Message", ...},
    {"id": "get_chat", "name": "Get Telegram Chat Info", ...},
    {"id": "get_chat_member", "name": "Get Telegram Chat Member", ...},
    {"id": "pin_message", "name": "Pin Telegram Message", ...},
    {"id": "set_webhook", "name": "Set Telegram Webhook", ...},
    {"id": "get_updates", "name": "Get Telegram Updates", ...},
],
```

### Step D6: Manifest + static registry + icon

- **Manifest:** `backend/integrations/manifests/telegram.json`
- **Static list:** Add `Integration(slug="telegram", ...)` — in `_NON_OAUTH_CONFIGS` (not OAuth)
- **Frontend icon:** `SiTelegram` from `@icons-pack/react-simple-icons`
- **Connect handler:** API key (bot token) — same flow as Twilio

### Step D7: Register connector + router

- Register `TelegramConnector` in `connectors/__init__.py` and `connectors/manager.py`
- Register `telegram_webhook_router` in `api/v1/__init__.py`

### Step D8: Token refresh

**No token refresh needed.** Telegram bot tokens do not expire.

### Step D9: Tests

**File (NEW):** `backend/tests/test_telegram_integration.py`

- `test_telegram_in_available_integrations`
- `test_telegram_in_non_oauth_configs`
- `test_telegram_manifest_exists`
- `test_telegram_bridge_capabilities`
- `test_telegram_webhook_router_exists`
- `test_telegram_connector_importable`
- `test_telegram_settings_exist`

Note: No `test_telegram_in_v1_oauth_providers` — Telegram uses bot token auth, not OAuth (same as Twilio).

---

## PART E: Cross-Integration Workflow Test Update (was Part D)

Update `test_cross_integration_workflow.py`:
- Shopify: assert 12 capabilities (new)
- Zendesk: assert 12 capabilities (new)
- Monday.com: assert 10 capabilities (new)
- Telegram: assert 12 capabilities (new)
- Update connector manager/init assertions

---

## Files Summary

### New files (21)

| File | Purpose |
|------|---------|
| `backend/app/services/shopify/__init__.py` | Shopify service package |
| `backend/app/services/shopify/shopify_client.py` | Shopify Admin API client |
| `backend/app/services/connectors/shopify_connector.py` | Shopify BaseConnector wrapper |
| `backend/app/api/v1/shopify_webhook.py` | Shopify webhook handler |
| `backend/app/services/zendesk/__init__.py` | Zendesk service package |
| `backend/app/services/zendesk/zendesk_client.py` | Zendesk API v2 client |
| `backend/app/services/connectors/zendesk_connector.py` | Zendesk BaseConnector wrapper |
| `backend/app/api/v1/zendesk_webhook.py` | Zendesk webhook handler |
| `backend/app/services/monday/__init__.py` | Monday.com service package |
| `backend/app/services/monday/monday_client.py` | Monday.com GraphQL client |
| `backend/app/services/connectors/monday_connector.py` | Monday.com BaseConnector wrapper |
| `backend/app/api/v1/monday_webhook.py` | Monday.com webhook handler |
| `backend/app/services/telegram/__init__.py` | Telegram service package |
| `backend/app/services/telegram/telegram_client.py` | Telegram Bot API client |
| `backend/app/services/connectors/telegram_connector.py` | Telegram BaseConnector wrapper |
| `backend/app/api/v1/telegram_webhook.py` | Telegram webhook handler |
| `backend/integrations/manifests/shopify.json` | Shopify manifest |
| `backend/integrations/manifests/zendesk.json` | Zendesk manifest |
| `backend/integrations/manifests/monday.json` | Monday.com manifest |
| `backend/integrations/manifests/telegram.json` | Telegram manifest |
| `backend/tests/test_shopify_integration.py` | Shopify wiring tests |
| `backend/tests/test_zendesk_integration.py` | Zendesk wiring tests |
| `backend/tests/test_monday_integration.py` | Monday.com wiring tests |
| `backend/tests/test_telegram_integration.py` | Telegram wiring tests |

### Modified files (8)

| File | Change |
|------|--------|
| `backend/app/core/oauth.py` | Add Shopify + Zendesk + Monday OAuthProviderConfig |
| `backend/app/config.py` | Add SHOPIFY_* + ZENDESK_* + MONDAY_* + TELEGRAM_* settings |
| `backend/app/api/v1/integrations.py` | Add Shopify + Zendesk + Monday + Telegram to AVAILABLE_INTEGRATIONS; add Telegram to _NON_OAUTH_CONFIGS |
| `backend/app/api/v1/__init__.py` | Register shopify_webhook + zendesk_webhook + monday_webhook + telegram_webhook routers |
| `backend/app/services/integration_bridge.py` | Add 12 Shopify + 12 Zendesk + 10 Monday + 12 Telegram bridge capabilities + Zendesk/Monday token refresh |
| `backend/app/services/connectors/__init__.py` | Register ShopifyConnector + ZendeskConnector + MondayConnector + TelegramConnector |
| `backend/app/services/connectors/manager.py` | Register ShopifyConnector + ZendeskConnector + MondayConnector + TelegramConnector in CONNECTOR_CLASSES |
| `backend/tests/test_cross_integration_workflow.py` | Update assertions for new capabilities |

---

## Done Criteria

### Shopify
- [ ] 12 Shopify actions working (shop info, products, orders, customers, inventory, webhooks, transactions)
- [ ] Shopify bridge capabilities: 12 total
- [ ] Shopify connector: 12 actions
- [ ] No token refresh (tokens don't expire)
- [ ] Dynamic OAuth URLs (shop-specific)
- [ ] Shopify webhook signature verification (HMAC-SHA256, `X-Shopify-Hmac-SHA256`)
- [ ] All 7 tests pass

### Zendesk
- [ ] 12 Zendesk actions working (tickets, users, search, organizations, groups, comments, metrics)
- [ ] Zendesk bridge capabilities: 12 total
- [ ] Zendesk connector: 12 actions
- [ ] Token refresh via generic `_refresh_oauth_token()` (~12 hour expiry)
- [ ] Dynamic OAuth URLs (subdomain-specific)
- [ ] Zendesk webhook signature verification
- [ ] All 7 tests pass

### Monday.com
- [ ] 10 Monday.com actions working (boards, items, updates, users, workspaces)
- [ ] Monday.com bridge capabilities: 10 total
- [ ] Monday.com connector: 10 actions
- [ ] GraphQL client (first GraphQL integration)
- [ ] Token refresh via generic `_refresh_oauth_token()`
- [ ] All 7 tests pass

### Telegram
- [ ] 12 Telegram actions working (messages, photos, documents, chat info, webhooks)
- [ ] Telegram bridge capabilities: 12 total
- [ ] Telegram connector: 12 actions
- [ ] Bot token auth (no OAuth, same as Twilio)
- [ ] Telegram webhook handler with secret token verification
- [ ] All 7 tests pass

### Shared
- [ ] ruff check passes
- [ ] All existing tests still pass
- [ ] Commit pushed to origin/main
- [ ] Backend deployed and healthy

---

## CAPABILITY COUNTS (projected)

| Integration | Bridge Caps | Connector Actions |
|-------------|-------------|-------------------|
| Shopify (new) | 12 | 12 |
| Zendesk (new) | 12 | 12 |
| Monday.com (new) | 10 | 10 |
| Telegram (new) | 12 | 12 |
| **Batch 9 total** | **+46** | **+46** |
| **Grand total (Batches 1-9)** | **280** | — |

---

## Future Batches (Batch 10+ candidates)

| Integration | Complexity | Value | Auth | Notes |
|-------------|-----------|-------|------|-------|
| **AWS** | High | High | SigV4 | Cloud infrastructure — needs boto3 or manual SigV4 |
| **Gmail (expand)** | Low | Medium | Already done | Add email read/search capabilities |
| **Teams** | Medium | Medium | OAuth2 (Azure AD) | Microsoft Teams via Graph API |
| **Zendesk (expand)** | Low | Low | Already done | Add macros, automations, help center |
| **Shopify (expand)** | Low | Low | Already done | Add fulfillments, discounts, metafields |
| **Salesforce** | High | High | OAuth2 | Enterprise CRM — complex but high value |
| **Linear (expand)** | Low | Medium | Already done | Add initiatives, views, favorites |
| **Grafana** | Medium | Medium | API Key | Monitoring dashboards and alerts |
