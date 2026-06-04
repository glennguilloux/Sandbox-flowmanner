# FlowManner API v3→v4 Migration Roadmap

> **Generated: 2026-05-31** — Forward-looking study based on actual codebase analysis.
> **Author:** Buffy (DeepSeek V4 Pro), Senior API Platform Architect

---

## Executive Summary

FlowManner currently has two API versions:
- **v1** (`/api/v1/`): Legacy monolith with 60+ route files, ad-hoc response shapes, no envelope.
- **v2** (`/api/v2/`): Clean redesign with standardized `{ data, meta, error }` envelope, Strawberry GraphQL at `/api/v2/graphql`, and 6 REST services.

This roadmap proposes what **v3** and **v4** should be — a genuine evolution, not speculation. The analysis is grounded in the existing v1/v2 codebase (`/opt/flowmanner/backend/app/`), identifying real technical debt, missing features, and modern API design patterns to adopt.

### The 5 Services Under Migration Study

| # | Service | v2 Prefix | Key Entities | Lines |
|---|---------|-----------|-------------|-------|
| 1 | **Auth** | `/api/v2/auth` | Users, JWT, 2FA, refresh tokens, registration | ~290 |
| 2 | **Missions** | `/api/v2/missions` | Missions, Tasks, Logs, Execution, Analytics | ~280 |
| 3 | **Agents** | `/api/v2/agents` | Agents, AgentTemplates | ~160 |
| 4 | **Chat** | `/api/v2/chat` | Threads, Messages, Folders, Branches, Files, SSE | ~340 |
| 5 | **Workspaces** | `/api/v2/workspaces` | Workspaces, Members, Teams, Invitations | ~260 |

Search (`/api/v2/search`) is deliberately excluded — it is lightweight (2 endpoints), has no breaking-change story, and can be migrated as a fast-follower.

---

## 1. Auth Service (`/api/v2/auth`)

### 1.1 Breaking Changes Table

| Change | v2 (Current) | v3 (Proposed) | v4 (Proposed) | Impact |
|--------|--------------|---------------|---------------|--------|
| **Endpoint rename** | `POST /auth/login` (reads body via `request.json()` manually, no Pydantic model) | `POST /auth/sessions` — proper Pydantic `LoginRequest` | Same as v3 | **HIGH** — frontend URL change required |
| **Endpoint rename** | `POST /auth/refresh` | `POST /auth/sessions/refresh` | Same | **HIGH** |
| **Endpoint rename** | `POST /auth/logout` | `DELETE /auth/sessions/{session_id}` | Same | **HIGH** |
| **Endpoint rename** | `POST /auth/register` | `POST /auth/users` | Same | **MEDIUM** |
| **Endpoint rename** | `POST /auth/login/2fa` | `POST /auth/sessions/verify` | Same | **HIGH** |
| **Response shape** | `{ "data": TokenResponse, "meta": {...}, "error": null }` | Same envelope, but TokenResponse gains `session_id` + `expires_at` fields | `data` field renamed to `result` (JSON:API compliance) | **LOW** (v3) / **HIGH** (v4) |
| **Field deprecation** | `login_count` on `/auth/me` | Removed from me; moved to `GET /auth/users/{id}/stats` | Same | **LOW** |
| **Field deprecation** | `refresh_token` in TokenResponse | Replaced by httpOnly cookie by default; token still available with `?token_response=body` | Cookie-only in v4 | **HIGH** |
| **Pagination** | N/A (auth has no lists) | `GET /auth/sessions` returns paginated device list | Same | **NEW** |
| **Error format** | HTTPException → v2 `{ error: { code, message, details } }` | Adds `error.trace_id` for correlation | Adds `error.links.about` per RFC 7807 | **LOW** |
| **SDK drops** | N/A | Python SDK drops `login_with_email()` — use `create_session()` | TypeScript SDK adds session management | **MEDIUM** |

### 1.2 Authentication/Authz Differences

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Auth method** | JWT Bearer token (HS256) | JWT + refresh token in httpOnly cookie | OAuth2-style with PKCE for SPA clients |
| **Token storage** | Client-side (localStorage/sessionStorage) | httpOnly, Secure, SameSite=Strict cookie for refresh tokens; access token still Bearer | Both tokens in httpOnly cookies (access token short-lived, 5 min) |
| **Token rotation** | Manual — client sends refresh token, gets new pair | Automatic rotation on each use with replay detection (family_id) | Same, plus device fingerprinting |
| **Scope model** | Role-based only (`user`/`admin`) | Scopes: `missions:read`, `missions:write`, `agents:manage`, `workspace:admin` | Same, plus resource-level scopes (`workspace:{id}:admin`) |
| **2FA** | TOTP with backup codes, temp_token flow | TOTP + WebAuthn (passkeys) support | WebAuthn-first, TOTP fallback |
| **Password policy** | Server-side validation (`validate_password_strength`) | Same, plus HaveIBeenPwned API check on registration | Same |
| **Session management** | No session list endpoint | `GET /auth/sessions` — list all active sessions, revoke individually | `GET /auth/sessions` with device metadata (OS, browser, IP, location) |
| **OIDC** | Not in v2 (exists in v1) | `POST /auth/oidc/{provider}` — Google, GitHub, Microsoft | Same, plus custom OIDC provider config per workspace |
| **API keys** | Not in v2 (exists in v1) | `POST /auth/api-keys` — scoped, expirable keys | Same, plus key usage analytics |

### 1.3 Rate Limits

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Login** | 5 req/60s per IP (in-memory rate limiter) | 5 req/60s per IP, 10 req/5min per account (Redis-backed) | Same, plus anomaly detection (geo-velocity) |
| **Register** | 3 req/60s per IP | 3 req/60s per IP + email verification required | Same |
| **2FA verify** | 5 req/60s per IP | 3 req/60s per IP (stricter) | Same |
| **Token refresh** | No specific limit | 30 req/5min per session | Same |
| **Headers** | `Retry-After` only on 429 | Adds `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` on all responses | Adds `RateLimit-Policy` header per IETF draft |
| **Plan tiers** | Hardcoded limits | Free: 100 req/hr, Pro: 1000 req/hr, Enterprise: custom | Same |

### 1.4 Webhook Changes

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Events** | None | `user.registered`, `user.login`, `user.password_changed`, `session.revoked` | Same, plus `user.2fa_enabled`, `user.2fa_disabled` |
| **Signing** | None | HMAC-SHA256 with workspace webhook secret | Same |
| **Delivery** | None | At-least-once with exponential backoff (5 retries over 24h) | Same |
| **Payload** | None | Standard envelope: `{ event, timestamp, data }` | Same |

### 1.5 Data Format Migrations

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Response envelope** | `{ data, meta, error }` | Same | `{ result, meta, errors }` (namespaced errors) |
| **Date format** | ISO 8601 strings (manual `str(dt)`) | ISO 8601 with timezone offset (UTC default) | Same |
| **ID format** | `user.id` = integer (DB serial) | Integer (internal) + prefixed public ID: `user_<uuid>` for external APIs | UUIDv7 for all public IDs |
| **Enum values** | `user.role` = string | `user.role` = enum: `owner`, `admin`, `member`, `viewer` | Same |
| **OpenAPI** | Auto-generated from FastAPI | Hand-crafted OpenAPI 3.1 with examples, deprecation notices | Same, plus OpenAPI 3.1 webhooks section |

### 1.6 Migration Effort Estimate

| Factor | v2→v3 | v3→v4 |
|--------|-------|-------|
| **Overall effort** | **MEDIUM** | **LARGE** |
| **Route changes** | 4 renames, 3 new endpoints, cookie support | JSON:API compliance, UUIDv7 IDs |
| **Frontend churn** | ~8 files (auth forms, token handling, session UI) | ~15 files (ID format changes everywhere) |
| **Database changes** | Add `sessions` table for session management, add `api_keys` table | Add UUIDv7 columns, dual-write period |
| **Test coverage gap** | Session list/revoke, OIDC, API keys (currently no tests) | UUID migration, cookie-only token flow |
| **Blockers** | None — all additive or additive-first | UUID migration requires dual-write phase (4-6 weeks) |
| **Fallback** | v2 endpoints remain active behind `?version=2` query param for 90 days | v3 fallback for 90 days |

### 1.7 Compatibility Checklist

- [ ] Add httpOnly cookie support for refresh tokens (configurable, defaults off in v3, on in v4)
- [ ] Create `auth_sessions` table with device metadata
- [ ] Create `api_keys` table with scopes and expiration
- [ ] Create `auth_webhook_subscriptions` table
- [ ] Add OIDC provider configurations
- [ ] Add `SCOPES` enum and scope validation middleware
- [ ] Feature flag: `AUTH_V3_COOKIES`, `AUTH_V3_SESSIONS`, `AUTH_V3_API_KEYS`
- [ ] Canary: 5% of new users → 25% → 50% → 100%
- [ ] Monitoring: login success rate, refresh failure rate, 2FA failure rate
- [ ] Alert: `auth_login_failure_rate > 10%` for 5 minutes
- [ ] Backward compat: v2 endpoints respond for 90 days after v3 launch

---

## 2. Missions Service (`/api/v2/missions`)

### 2.1 Breaking Changes Table

| Change | v2 (Current) | v3 (Proposed) | v4 (Proposed) | Impact |
|--------|--------------|---------------|---------------|--------|
| **Endpoint rename** | `POST /missions/{id}/execute` (sync) + `POST /missions/{id}/execute-async` (async) | `POST /missions/{id}/executions` creates an execution; `?async=true` query param | `POST /missions/{id}/executions` | **MEDIUM** — unify two endpoints |
| **Endpoint rename** | `GET /missions/{id}/status` | `GET /missions/{id}/executions/{execution_id}` — supports multiple executions per mission | Same | **HIGH** |
| **Endpoint rename** | `GET /missions/{id}/stream` | `GET /missions/{id}/executions/{execution_id}/stream` | Same | **HIGH** |
| **New endpoint** | N/A | `POST /missions/{id}/executions/{execution_id}/cancel` | Same | **NEW** |
| **New endpoint** | N/A | `POST /missions/{id}/executions/{execution_id}/retry` | Same | **NEW** |
| **New endpoint** | N/A | `GET /missions/{id}/versions` — version history | Same | **NEW** |
| **Response shape** | MissionResponse has 15 fields | MissionResponse gains `tags: []string`, `parent_mission_id`, `version` | Same | **LOW** |
| **Field deprecation** | `estimated_cost` (always null in practice) | Removed | Removed | **LOW** |
| **Pagination change** | `page`/`per_page` query params | Cursor-based: `?cursor=<id>&limit=20` (better for real-time lists) | Same | **MEDIUM** |
| **Error format** | Same as auth | Adds `error.execution_id` for execution errors | Same | **LOW** |
| **SDK drops** | N/A | `executeMissionSync()` removed — use `createExecution()` + poll | `getMissionStatus()` removed — use execution-centric API | **MEDIUM** |

### 2.2 Authentication/Authz Differences

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Ownership** | Mission tied to `user_id` | Mission tied to `workspace_id` (mandatory) | Same |
| **Permissions** | Only owner can read/modify | Workspace roles: `owner`/`admin` full access, `member` can read/execute, `viewer` read-only | Same, with per-mission collaborator invites |
| **API keys** | N/A | API keys with `missions:write` scope can execute missions | Same |
| **Audit** | No audit for mission operations | All mutating operations logged to audit trail | Same |

### 2.3 Rate Limits

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Mission execute** | No specific limit | 10 concurrent executions per workspace (Free), 50 (Pro) | Same |
| **Mission create** | No limit | 100/hr per workspace | Same |
| **SSE stream** | No limit | 5 concurrent streams per user | Same |
| **Analytics** | No limit | 30 req/5min | Same |

### 2.4 Webhook Changes

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Events** | None (uses analytics events in-code) | `mission.created`, `mission.execution.started`, `mission.execution.completed`, `mission.execution.failed`, `mission.task.completed` | Same, plus `mission.execution.cancelled` |
| **Payload** | None | `{ event, mission_id, execution_id, status, timestamp, data }` | Same |
| **Delivery** | None | At-least-once, HMAC-SHA256 signed | Same |

### 2.5 Data Format Migrations

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **ID format** | UUID v4 (`uuid.UUID`) | UUID v7 (time-ordered, better for DB indexes) | Same |
| **Status enum** | String: `pending`, `queued`, `running`, `completed`, `failed`, `cancelled` | Same values but typed as enum in OpenAPI | Same |
| **Priority enum** | String: `low`, `medium`, `high`, `critical` | Same + `urgent` | Same |
| **Dates** | None (model timestamps server-managed) | `scheduled_at` field for delayed execution | Same |
| **Results** | `results` = JSON (unstructured) | `results` = typed union: `TextResult`, `FileResult`, `TableResult`, `ErrorResult` | Same |
| **Plan** | `plan` = JSON (unstructured) | `plan` = typed `ExecutionPlan` with `steps[]` array | Same |

### 2.6 Migration Effort Estimate

| Factor | v2→v3 | v3→v4 |
|--------|-------|-------|
| **Overall effort** | **LARGE** | **MEDIUM** |
| **Route changes** | Unify 2 execute endpoints, add 3 new endpoints, cursor pagination | UUIDv7 migration, typed results |
| **Frontend churn** | ~12 files (mission detail, execution panel, SSE handling) | ~5 files (ID format) |
| **Database changes** | Add `executions` table, add `workspace_id` to missions, add `mission_versions` table | UUIDv7 primary keys, dual-write |
| **Test coverage gap** | Execution retry, cancellation, cursor pagination, webhook delivery | UUID migration, typed results |
| **Blockers** | `workspace_id` migration requires all missions to belong to a workspace (backfill needed) | UUIDv7 dual-write |
| **Fallback** | v2 endpoints behind feature flag | v3 fallback |

### 2.7 Compatibility Checklist

- [ ] Create `executions` table (one mission → many executions)
- [ ] Create `mission_versions` table for version history
- [ ] Add `workspace_id` foreign key to `missions` table (nullable during migration)
- [ ] Backfill `workspace_id` for all existing missions (personal workspace per user)
- [ ] Implement cursor-paginated `GET /missions` with `?cursor=<id>&limit=20`
- [ ] Unify execute/execute-async into single endpoint with `?async=true`
- [ ] Add SSE cancellation via client disconnect detection
- [ ] Feature flags: `MISSIONS_V3_EXECUTIONS`, `MISSIONS_V3_CURSOR`
- [ ] Canary: 5% → 25% → 50% → 100%
- [ ] Monitoring: execution completion rate, execution latency p50/p95/p99, SSE connection drops
- [ ] Alert: `mission_execution_failure_rate > 25%` for 5 minutes
- [ ] Backward compat: v2 endpoints behind `?version=2` for 90 days

---

## 3. Agents Service (`/api/v2/agents`)

### 3.1 Breaking Changes Table

| Change | v2 (Current) | v3 (Proposed) | v4 (Proposed) | Impact |
|--------|--------------|---------------|---------------|--------|
| **Endpoint rename** | `GET /agents/templates/list` | `GET /agents/templates` (use paginated list) | Same | **LOW** |
| **New endpoint** | N/A | `POST /agents/{id}/test` — test agent with a prompt, return output | Same | **NEW** |
| **New endpoint** | N/A | `GET /agents/{id}/usage` — usage analytics per agent | Same | **NEW** |
| **New endpoint** | N/A | `POST /agents/{id}/clone` — duplicate an agent | Same | **NEW** |
| **Field deprecation** | `config: str` (JSON string) | `config: JSON` — typed as dict, not string | Same | **HIGH** |
| **Field addition** | N/A | `agent.tags: []string`, `agent.is_public: bool`, `agent.icon: string` | Same | **NEW** |
| **Model preference** | `model_preference: str` (free-form) | `model_preference: ModelPreference` (typed, validated against available models) | Same | **MEDIUM** |
| **Response shape** | Same as other services | AgentResponse gains `last_used_at`, `usage_count`, `average_rating` | Same | **LOW** |
| **Error codes** | Generic `NOT_FOUND` | Specific: `AGENT_NOT_FOUND`, `TEMPLATE_NOT_FOUND`, `AGENT_LIMIT_REACHED` | Same | **LOW** |
| **SDK drops** | N/A | `agent.config` changes from `string` to `object` — code change required | Same | **HIGH** |

### 3.2 Authentication/Authz Differences

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Ownership** | Agent tied to `owner_id` (user) | Agent tied to `workspace_id` (like missions) | Same |
| **Visibility** | Private only | Private + `is_public` flag (public agents visible to all workspaces) | Same, plus workspace-restricted sharing |
| **Marketplace** | Not in v2 (exists in v1) | Public agents are listed in marketplace | Same |
| **Permissions** | Only owner | Workspace roles + `agents:manage` scope | Same |

### 3.3 Rate Limits

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Agent create** | No limit | 50 per workspace (Free), unlimited (Pro) | Same |
| **Agent test** | N/A | 10 req/60s | Same |
| **Template list** | No limit | 30 req/5min | Same |

### 3.4 Webhook Changes

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Events** | None | `agent.created`, `agent.updated`, `agent.deleted`, `agent.published` | Same |

### 3.5 Data Format Migrations

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **config field** | `config: str` (JSON-encoded string — anti-pattern) | `config: dict` (native JSON in DB using JSONB) | Same |
| **ID format** | UUID v4 strings | UUID v7 | Same |
| **Template model_config** | `model_config: JSON` (already native) | Same | Same |
| **Enum values** | `agent_type` = free-form string | `agent_type` = enum: `assistant`, `coder`, `writer`, `analyst`, `custom` | Same |

### 3.6 Migration Effort Estimate

| Factor | v2→v3 | v3→v4 |
|--------|-------|-------|
| **Overall effort** | **MEDIUM** | **SMALL** |
| **Route changes** | 1 cleanup, 3 new endpoints | UUID change only |
| **Frontend churn** | ~5 files (agent config change from string to object, tags UI) | ~2 files |
| **Database changes** | Alter `config` column to JSONB, add `workspace_id`, `tags`, `is_public`, `icon` | UUIDv7 |
| **Test coverage gap** | Agent test endpoint, public agents, usage analytics | Minimal |
| **Blockers** | `config` column migration — parse existing JSON strings to JSONB (risk of malformed JSON) | None |
| **Fallback** | v2 endpoints behind feature flag | v3 fallback |

### 3.7 Compatibility Checklist

- [ ] Migrate `config` column from `VARCHAR`/`TEXT` to `JSONB` with validation
- [ ] Parse all existing `config` values; flag malformed JSON for manual repair
- [ ] Add `workspace_id` to agents table with backfill
- [ ] Add `tags`, `is_public`, `icon`, `last_used_at`, `usage_count`, `average_rating` columns
- [ ] Implement `POST /agents/{id}/test` with sandboxed LLM call
- [ ] Implement agent usage tracking
- [ ] Feature flags: `AGENTS_V3_CONFIG_JSONB`, `AGENTS_V3_PUBLIC`
- [ ] Monitoring: agent test latency, agent creation rate
- [ ] Backward compat: v2 `config` as string accepted for 60 days, auto-converted

---

## 4. Chat Service (`/api/v2/chat`)

### 4.1 Breaking Changes Table

| Change | v2 (Current) | v3 (Proposed) | v4 (Proposed) | Impact |
|--------|--------------|---------------|---------------|--------|
| **Endpoint rename** | `POST /chat/threads/{id}/chat` (non-streaming) + `POST /chat/threads/{id}/chat/stream` (SSE) | Unified `POST /chat/threads/{id}/messages` with `?stream=true` | Same | **MEDIUM** |
| **New endpoint** | N/A | `POST /chat/threads/{id}/messages/{msg_id}/reactions` | Same | **NEW** |
| **New endpoint** | N/A | `GET /chat/search` — full-text search across messages | Same | **NEW** |
| **New endpoint** | N/A | `POST /chat/threads/{id}/export` — export thread as JSON/Markdown | Same | **NEW** |
| **Field deprecation** | ChatMessageCreate has `system_prompt` (set on thread metadata, not message) | Removed from message; `system_prompt` moved to thread-level `PATCH /chat/threads/{id}` | Same | **LOW** |
| **Field change** | `content: str` | `content: str | ContentBlock[]` (multi-modal: text, image, file ref) | Same | **HIGH** |
| **Branching** | Branches = separate sub-threads with parent_message_id | Branches = first-class concept with `branch_id` on messages, easier UI traversal | Same | **MEDIUM** |
| **Attachments** | Payload-level `attachments: [...]` on create | Attachment upload endpoint: `POST /chat/threads/{id}/attachments` then reference by ID | Same | **MEDIUM** |
| **Model routing** | Header-based: `X-User-API-Key`, `X-User-Base-URL`, `model_id` in body | Thread-level `model_config: { provider, model, api_key_ref }` | Same | **HIGH** |
| **Error format** | Same pattern | Adds `error.retryable: bool` | Same | **LOW** |
| **SDK drops** | N/A | `chatWithLlm()` → `createMessage()`, `chatWithLlmStream()` → `createMessage({ stream: true })` | Same | **HIGH** |

### 4.2 Authentication/Authz Differences

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Thread ownership** | Thread tied to `user_id` | Thread tied to `workspace_id` | Same |
| **Thread sharing** | Not supported | Thread can be shared with workspace members via `thread.shared_with: []` | Same, plus public share links (read-only) |
| **BYOK** | `X-User-API-Key` header (user's own API key) | API key stored encrypted in DB, referenced by `api_key_id` on thread config | Same |

### 4.3 Rate Limits

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Chat messages** | No specific limit | 50 messages/min per user (Free), 200/min (Pro) | Same |
| **SSE streams** | No limit | 3 concurrent streams per user | Same |
| **Threads** | No limit | 100 threads per workspace (Free), unlimited (Pro) | Same |
| **File uploads** | No limit | 10 MB per file, 100 MB total per workspace | Same |

### 4.4 Webhook Changes

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Events** | None | `chat.thread.created`, `chat.message.created`, `chat.message.completed` (when LLM finishes) | Same |

### 4.5 Data Format Migrations

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Message content** | `content: str` | `content: str | ContentBlock[]` where ContentBlock = `{ type, text?, image_url?, file_id? }` | Same |
| **Thread model** | `model_preference: str` | `model_config: { provider, model, api_key_id, temperature, max_tokens }` | Same |
| **Folder ID** | Integer (DB serial) | UUID | Same |
| **Branch ID** | Integer | UUID | Same |
| **Message role** | `user`, `assistant`, `system` | `user`, `assistant`, `system`, `tool` | Same |
| **Timestamps** | Server-managed `created_at` | Adds `edited_at` for message edits | Same |

### 4.6 Migration Effort Estimate

| Factor | v2→v3 | v3→v4 |
|--------|-------|-------|
| **Overall effort** | **LARGE** | **MEDIUM** |
| **Route changes** | Unify 2 chat endpoints, 3 new endpoints, model config restructure | UUIDv7, content blocks |
| **Frontend churn** | ~20 files (chat UI, message rendering, model selector, attachment upload) | ~10 files |
| **Database changes** | Content blocks migration, model_config JSONB, add reactions, shared_with | UUIDv7 |
| **Test coverage gap** | Streaming unification, content blocks, reactions, export, search | UUID migration |
| **Blockers** | Content migration: parse existing `content: str` into `ContentBlock` format; multi-model config from headers to DB | UUID dual-write |
| **Fallback** | v2 endpoints behind feature flag | v3 fallback |

### 4.7 Compatibility Checklist

- [ ] Create `chat_reactions` table
- [ ] Create `chat_attachments` table (separate upload endpoint)
- [ ] Add `model_config` JSONB column to threads
- [ ] Add `workspace_id` to threads
- [ ] Migrate existing `content` to `ContentBlock[]` format (wrap in `{ type: "text", text: content }`)
- [ ] Add `edited_at` to messages
- [ ] Add full-text search index on message content
- [ ] Unify chat/chat-stream into single `POST /messages` with `?stream=true`
- [ ] Feature flags: `CHAT_V3_UNIFIED`, `CHAT_V3_CONTENT_BLOCKS`, `CHAT_V3_MODEL_CONFIG`
- [ ] Canary: 5% → 25% → 50% → 100%
- [ ] Monitoring: message latency (time-to-first-token, total), stream error rate, attachment upload success rate
- [ ] Alert: `chat_stream_error_rate > 5%` for 5 minutes
- [ ] Backward compat: v2 endpoints for 90 days

---

## 5. Workspaces Service (`/api/v2/workspaces`)

### 5.1 Breaking Changes Table

| Change | v2 (Current) | v3 (Proposed) | v4 (Proposed) | Impact |
|--------|--------------|---------------|---------------|--------|
| **New endpoint** | N/A | `POST /workspaces/{id}/invitations` — send invite emails | Same | **NEW** |
| **New endpoint** | N/A | `POST /workspaces/{id}/invitations/{invite_id}/accept` | Same | **NEW** |
| **New endpoint** | N/A | `GET /workspaces/{id}/audit-log` — workspace activity feed | Same | **NEW** |
| **New endpoint** | N/A | `GET /workspaces/{id}/billing` — subscription/usage for workspace | Same | **NEW** |
| **New endpoint** | N/A | `POST /workspaces/{id}/transfer-ownership` | Same | **NEW** |
| **Endpoint change** | `GET /workspaces/{id}/members` returns inline user data | `GET /workspaces/{id}/members` returns membership records (user data via `?include=user`) | Same | **MEDIUM** |
| **Response shape** | WorkspaceResponse has 9 fields | WorkspaceResponse gains `logo_url`, `settings: JSON`, `member_limit`, `storage_used` | Same | **LOW** |
| **Field deprecation** | `plan: str = "free"` | Moved to `GET /workspaces/{id}/billing` | Same | **LOW** |
| **Team management** | Teams are nested under workspaces | Teams become top-level: `GET /teams?workspace_id={id}` | Same | **MEDIUM** |
| **Error codes** | Generic `NOT_FOUND` | `WORKSPACE_NOT_FOUND`, `SLUG_CONFLICT`, `MEMBER_LIMIT_REACHED`, `INVITE_ALREADY_ACCEPTED` | Same | **LOW** |
| **SDK drops** | N/A | `member.user_email` no longer inline — require `?include=user` or second call | Same | **MEDIUM** |

### 5.2 Authentication/Authz Differences

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Roles** | `owner`, `admin`, `member` | `owner`, `admin`, `member`, `viewer` (read-only) | Same, plus custom roles |
| **Ownership transfer** | Not supported | `POST /workspaces/{id}/transfer-ownership` with 2FA confirmation | Same |
| **Invitations** | Table exists but no endpoint | Full invite flow: send → accept → auto-join | Same |
| **SSO** | Not supported | SAML/OIDC per workspace (Enterprise) | Same |

### 5.3 Rate Limits

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Invite send** | N/A | 50 invites/hr per workspace | Same |
| **Workspace create** | No limit | 5 per user (Free), 20 (Pro), unlimited (Enterprise) | Same |

### 5.4 Webhook Changes

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **Events** | None | `workspace.created`, `workspace.member.joined`, `workspace.member.removed`, `workspace.member.role_changed` | Same |

### 5.5 Data Format Migrations

| Aspect | v2 (Current) | v3 (Proposed) | v4 (Proposed) |
|--------|--------------|---------------|---------------|
| **ID format** | UUID v4 strings | UUID v7 | Same |
| **Invitations** | Table exists, no endpoints | Full CRUD with `email`, `role`, `expires_at`, `accepted_at` | Same |
| **Workspace settings** | Not supported | `settings: JSON` column for workspace-level config (default model, timezone, notifications) | Same |
| **Teams** | Nested under workspaces (`GET /workspaces/{id}/teams`) | Top-level `/api/v3/teams?workspace_id={id}` | Same |

### 5.6 Migration Effort Estimate

| Factor | v2→v3 | v3→v4 |
|--------|-------|-------|
| **Overall effort** | **MEDIUM** | **SMALL** |
| **Route changes** | 5 new endpoints, 2 response shape changes, teams restructure | UUIDv7 |
| **Frontend churn** | ~10 files (workspace settings, invitations, billing, member management) | ~3 files |
| **Database changes** | Add `settings` JSONB, `logo_url`, `member_limit`, `storage_used` to workspaces; add expiry to invitations | UUIDv7 |
| **Test coverage gap** | Invitations, billing, ownership transfer, audit log | Minimal |
| **Blockers** | Invitation SMTP integration, billing integration (PayPal/Stripe) | None |
| **Fallback** | v2 endpoints behind feature flag | v3 fallback |

### 5.7 Compatibility Checklist

- [ ] Add `settings` JSONB column to workspaces
- [ ] Add `logo_url`, `member_limit`, `storage_used` columns
- [ ] Add `expires_at` to workspace_invitations
- [ ] Implement SMTP email sending for invitations
- [ ] Implement invitation accept flow with token validation
- [ ] Create `GET /workspaces/{id}/audit-log` endpoint
- [ ] Create `GET /workspaces/{id}/billing` endpoint
- [ ] Implement ownership transfer with 2FA
- [ ] Extract teams to top-level routes in v3
- [ ] Feature flags: `WORKSPACES_V3_INVITES`, `WORKSPACES_V3_BILLING`
- [ ] Monitoring: invite acceptance rate, member growth
- [ ] Backward compat: v2 endpoints for 90 days

---

## Cross-Service Analysis

### Ranked Summary Table

| Rank | Service | v2→v3 Effort | v3→v4 Effort | Breaking Changes | Risk | Recommended Order |
|------|---------|-------------|-------------|-----------------|------|-------------------|
| 1 | **Auth** | MEDIUM | LARGE | 4 route renames, cookie migration | Session loss during cookie migration | **First** — foundation for all other services |
| 2 | **Workspaces** | MEDIUM | SMALL | 5 new endpoints, teams restructure | Invitation email delivery | **Second** — workspace-scoping required by Missions, Agents, Chat |
| 3 | **Agents** | MEDIUM | SMALL | config: string→JSONB, 3 new endpoints | Malformed JSON in existing configs | **Third** — depends on workspace-scoping |
| 4 | **Chat** | LARGE | MEDIUM | 6 endpoint changes, content blocks, model config | Content migration, streaming regression | **Fourth** — most complex, do after simpler services |
| 5 | **Missions** | LARGE | MEDIUM | 7 endpoint changes, executions model, cursor pagination | Execution state migration, backfill | **Fifth** — depends on workspace-scoping, most v1 parity needed |

### Recommended Migration Order & Rationale

1. **Auth v3** — Everything authenticates through auth. Cookies, sessions, scopes must land first so other services can adopt them.
2. **Workspaces v3** — Missions, Agents, and Chat all need workspace-scoping. Do this before touching those services.
3. **Agents v3** — Relatively self-contained. The `config: string→JSONB` migration is the main risk.
4. **Chat v3** — Most complex v3 migration. Do after gaining confidence from simpler services.
5. **Missions v3** — Largest surface area. The execution model change is the riskiest part of v3.

**v4 across all services** — After all v3 migrations are stable (90+ days), do v4 in one coordinated push: UUIDv7 everywhere, JSON:API compliance, cookie-only auth. This is primarily a data format and protocol migration, not behavioral.

### Common Migration Pitfalls Per Service

| Service | Pitfall |
|---------|---------|
| **Auth** | Cookie migration: users logged out when you flip from Bearer to httpOnly. Mitigation: dual-accept for 30 days. |
| **Auth** | 2FA temp_token flow is custom — users on 2FA will break if temp_token format changes mid-deploy. |
| **Missions** | Executions model: existing missions have no execution records. Backfill with a synthetic execution per mission. |
| **Missions** | SSE stream refactoring: clients reconnect aggressively; new stream URL must be backward-compat redirected. |
| **Agents** | `config` field contains arbitrary JSON strings — some may be malformed. Pre-migration validation script needed. |
| **Chat** | Content blocks migration: all existing `content` strings must be wrapped in `[{ type: "text", text: ... }]`. Must be atomic. |
| **Chat** | Model config migration: BYOK keys currently passed via headers; moving to DB requires key encryption at rest. |
| **Workspaces** | Invitation emails: SMTP reliability is critical. Set up Resend/SendGrid with bounce handling before launch. |

### Sample Curl Diffs for Most Dangerous Breaking Changes

#### Auth: Login endpoint rename
```diff
# v2
- POST /api/v2/auth/login
- Body: { "username_or_email": "...", "password": "..." }
+ POST /api/v2/auth/sessions
+ Body: { "login": "...", "password": "...", "provider": "credentials" }

# v2 response
- { "data": { "access_token": "...", "refresh_token": "..." }, "meta": {...}, "error": null }
+ // v3 — same envelope, new fields
+ { "data": { "access_token": "...", "refresh_token": "...", "session_id": "sess_...", "expires_at": "2026-06-01T..." }, "meta": {...}, "error": null }
```

#### Missions: Unified execution
```diff
# v2
- POST /api/v2/missions/{id}/execute
- POST /api/v2/missions/{id}/execute-async
+ POST /api/v3/missions/{id}/executions?async=true

# v2 response
- { "data": { "mission_id": "...", "status": "running", ... }, "meta": {...}, "error": null }
+ // v3 — execution-centric
+ { "data": { "execution_id": "exec_...", "mission_id": "...", "status": "running", "started_at": "..." }, "meta": {...}, "error": null }
```

#### Chat: Content blocks
```diff
# v2
- POST /api/v2/chat/threads/42/chat
- Body: { "role": "user", "content": "Hello Claude" }
+ POST /api/v3/chat/threads/42/messages?stream=true
+ Body: { "role": "user", "content": [{ "type": "text", "text": "Hello Claude" }] }

# v2 SSE stream
- data: {"token": "Hello"} \n\n
+ data: {"type": "token", "text": "Hello"} \n\n
```

---

## Global v4 Changes (All Services)

| Aspect | v3 | v4 |
|--------|----|----|
| **ID format** | Mixed: UUID v4, integer, prefixed strings | UUIDv7 everywhere (sortable, time-ordered) |
| **Response envelope** | `{ data, meta, error }` | `{ result, meta, errors }` (namespaced errors array) |
| **Error format** | Single error object | Errors array: `[{ code, title, detail, source, links }]` per JSON:API |
| **Pagination** | Mixed: page-based and cursor-based | Cursor-based everywhere with `Link` header (RFC 8288) |
| **Auth** | Access token Bearer, refresh cookie | Both tokens in httpOnly cookies |
| **API versioning** | URL prefix (`/api/v3/`) | URL prefix + `Accept: application/vnd.flowmanner.v4+json` header |
| **Rate limit headers** | `X-RateLimit-*` custom headers | `RateLimit-*` per IETF draft |
| **OpenAPI spec** | OpenAPI 3.1 per service | OpenAPI 3.1 unified spec with webhooks |

---

## Timeline Estimate

| Phase | Duration | Services | Key Milestone |
|-------|----------|----------|---------------|
| **Phase 1: Foundation** | 6 weeks | Auth v3, Workspaces v3 | Workspace-scoped auth, invite flow |
| **Phase 2: Core Services** | 6 weeks | Agents v3, Chat v3 | Content blocks, model config migration |
| **Phase 3: Missions** | 4 weeks | Missions v3 | Executions model, cursor pagination |
| **Phase 4: Stabilize** | 4 weeks | All v3 | Bug fixes, performance, monitoring |
| **Phase 5: v4** | 8 weeks | All services | UUIDv7, JSON:API, cookie-only auth |

**Total: ~28 weeks** for full v3+v4 migration across all 5 services.

---

## Appendix: Current Codebase References

| Service | v2 Route File | v1 Route File | Models | Schemas |
|---------|-------------|--------------|--------|---------|
| Auth | `api/v2/auth.py` | `api/v1/auth.py` | `models/auth_models.py`, `models/user.py` | `schemas/auth.py` |
| Missions | `api/v2/missions.py` | `api/v1/mission.py` | `models/mission_models.py` | `schemas/mission.py` |
| Agents | `api/v2/agents.py` | `api/v1/agent.py` | `models/agent.py` | `schemas/agent.py` |
| Chat | `api/v2/chat.py` | `api/v1/chat.py` | `models/chat.py` | `schemas/chat.py` |
| Workspaces | `api/v2/workspaces.py` | `api/v1/workspace.py` | `models/workspace_models.py` | (inline in routes) |
| Search | `api/v2/search.py` | `api/v1/search.py` | N/A | (inline) |
| GraphQL | `api/v2/schema.py` | N/A | (via REST models) | (via REST schemas) |

---

*Generated: 2026-05-31 by Buffy (DeepSeek V4 Pro)*
*Codebase analyzed: `/opt/flowmanner/backend/app/`*
