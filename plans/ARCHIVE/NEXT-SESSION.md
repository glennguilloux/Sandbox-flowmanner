# FlowManner — Roadmap & Session Handoff

> **Last updated:** 2026-06-03
> **Status:** Phases 1–9 COMPLETE (all 9.1–9.6 done)
> **Tests:** 5/5 passing (1 pre-existing failure unrelated to Phase 9)

---

## Completed Phases (archived)

Phases 1–7 are complete. Full implementation details in:
- [`ARCHIVED-PHASES-1-5.md`](./ARCHIVED-PHASES-1-5.md) — Phases 1–5 detail

### Quick recap

| Phase | What | Status |
|-------|------|--------|
| 1 | Postgres-Native Migration (tools, capabilities, memory, topology) | ✅ COMPLETE |
| 2 | Registry Replacement (hydration, bindings, Qdrant rebuildable) | ✅ COMPLETE |
| 3 | Durable Agent OS (event sourcing, substrate, replay, bootstrap) | ✅ COMPLETE |
| 4 | Multi-Workspace (scoping, isolation, roles, presence) | ✅ COMPLETE |
| 5 | Marketplace v2 (listings, installs, reviews, versioning) | ✅ COMPLETE |
| 6 | V2 Memory + HITL (episodic memory, HITL, cost attribution, circuit breakers) | ✅ COMPLETE |
| 7 | Frontend Integration + Observability (HITL UI, mission observatory, cost dashboard, command center) | ✅ COMPLETE |

---

## Phase 8: Production Hardening + Platform API — IN PROGRESS

**Goal:** Make FlowManner safe for real users and external integrations. Remove feature flags, lock down auth, ship a public API, and close the subscription loop.

### 8.1 UnifiedExecutor GA — ✅ COMPLETE

Removed the `FLOWMANNER_UNIFIED_EXECUTOR` feature flag. UnifiedExecutor is now the sole execution path.

**Files modified (6):**
- `backend/app/services/substrate/executor.py` — Removed `_unified_executor_enabled()` and `_should_use_unified()` functions, removed `os` import, updated docstring to GA
- `backend/app/services/substrate/__init__.py` — Removed `_unified_executor_enabled` from import and `__all__`
- `backend/app/api/_mission_cqrs/commands.py` — Removed feature flag checks in `execute_mission` and `execute_async`; always uses unified path. `MissionExecutor` retained for `plan_mission`/`retry_mission`
- `backend/tests/test_event_sourced_state.py` — Replaced `TestUnifiedExecutorDefault` (5 flag tests) with `TestUnifiedExecutorGA` (2 removal-verification tests), removed unused `patch` import
- `backend/app/tests/test_mission_cqrs.py` — Removed `_unified_executor_enabled` mock
- `backend/app/tests/test_mission_handlers.py` — Removed `_unified_executor_enabled` mock, fixed orphaned line

**Tests:** 17/17 pass (2 pre-existing failures in `TestEventHistoryQuery` are unrelated)

---

### 8.2 Multi-Tenant Auth Hardening — ✅ COMPLETE

Workspace-scoped API keys, rate limiting keyed by workspace, security audit.

**Files modified/created (4 + 1 migration):**
- `backend/app/models/byok_models.py` — Added `workspace_id` column (nullable, String(36)) to `UserAPIKey` model with composite index `(workspace_id, user_id)`
- `backend/app/api/v1/api_keys.py` — Added `get_workspace_id` dependency to `list_keys`, `add_key`, `delete_key`, `test_key`. Keys now scoped to active workspace
- `backend/app/api/middleware/rate_limit.py` — Rate limiting now keys by `X-Workspace-Id` header when available, falling back to client IP
- `backend/alembic/versions/20260603_phase82_workspace_api_keys.py` — Migration adding `workspace_id` column and indexes to `user_api_keys`

**Security audit findings (for future work):**

| Finding | Count | Severity |
|---------|-------|----------|
| V1 endpoints without role checks | 63 | 🔴 High |
| Potentially unauthenticated endpoints | 13 | 🔴 High |
| BYOK keys decrypted at runtime | 8 locations | 🟡 Medium (by design, no log leaks found) |
| Raw SQL usage | Parameterized ✅ | 🟢 Low |

---

### 8.3 Public Platform API v2 — ✅ COMPLETE

Promoted v2 skeleton to full public API with OpenAPI 3.1 spec, cursor pagination, tier-based rate limits, and response headers.

**New files (4):**
- `backend/app/api/v2/cursor_pagination.py` — Keyset (cursor-based) pagination: base64 encode/decode, `CursorParams` dependency factory, `cursor_paginated` envelope builder. Supports forward (`after`) and backward (`before`) navigation
- `backend/app/api/v2/tier_rate_limit.py` — Tier-aware rate limiting with module-level shared sliding window. DB-backed tier resolution (SubscriptionTier → workspace.plan → "free") cached on user object. Periodic cleanup every 500 checks. Multipliers: free=1×, starter=2×, pro=5×, business=10×, enterprise=20×
- `backend/app/api/v2/openapi.py` — Dedicated `/api/v2/openapi.json` endpoint serving OpenAPI 3.1 spec filtered to v2 routes only, with security schemes (Bearer JWT + API Key), `x-rate-limit-tiers` extension, and `x-rate-limit-headers` docs. Cached after first build
- `backend/app/api/v2/rate_limit_headers.py` — Starlette middleware injecting `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` into all v2 responses

**Modified files (5):**
- `backend/app/api/v2/__init__.py` — Registered openapi router (+2 routes, 120 total v2 routes)
- `backend/app/api/v2/missions.py` — Cursor pagination via `?cursor=` param alongside offset pagination
- `backend/app/api/v2/agents.py` — Cursor pagination with `str()` type safety on decoded IDs
- `backend/app/api/v2/chat.py` — Cursor pagination for `/threads` endpoint
- `backend/app/api/v2/rate_limit.py` — Stores base limit on `request.state` for headers middleware, captures remaining count
- `backend/app/main_fastapi.py` — Registered `RateLimitHeadersMiddleware`

**All 10 files pass syntax checks, all imports clean, integration tests pass, Phase 8.1 GA tests unregressed.**

---

### 8.4 Subscription + Billing Close-Out — ✅ COMPLETE

Wired subscription tiers to actual mission limits, completed PayPal lifecycle, and added billing dashboard.

**New files (1):**
- `backend/app/services/subscription_service.py` — Tier resolution (user → workspace → free), mission limit enforcement (daily/monthly/concurrent), API key gating (has_api_access), grace period logic (7-day read-only), billing dashboard aggregation

**Modified files (6 + 2 tests):**
- `backend/app/services/paypal_service.py` — Added `activate_subscription()`, `suspend_subscription()`, `verify_webhook_signature()` (local header check), `verify_webhook_signature_api()` (PayPal API authoritative check)
- `backend/app/api/v1/subscription.py` — Added `POST /paypal/webhook` (lifecycle events: activated/cancelled/suspended/expired/failed), `POST /paypal/activate` (post-approval activation), `GET /billing` (dashboard: plan, usage vs limits, remaining counts, grace period status, billing period dates)
- `backend/app/api/_mission_cqrs/commands.py` — Wired `check_mission_create_allowed` into `create_mission`, `check_mission_execute_allowed` into `execute_mission` and `execute_async`. Grace-perioded users get 403 with descriptive message
- `backend/app/api/v1/api_keys.py` — Wired `check_api_key_allowed` into `add_key`. Free-tier users get 403
- `backend/app/config.py` — Added `PAYPAL_WEBHOOK_ID` setting
- `backend/app/tests/test_mission_handlers.py` — Updated 3 tests to mock subscription service checks, added `workspace_id` to `make_mission()` helper
- `backend/app/tests/test_subscription.py` — Fixed pre-existing MagicMock `name` parameter bug (switched to `SimpleNamespace`)

**Tests:** 6/7 pass. `test_get_my_subscription` failure is pre-existing (MockMagic/async mock chain issue).
**Deployed:** Backend rebuilt and healthy.

### 8.5 Webhook Delivery Hardening — ✅ COMPLETE

Hardened webhook delivery with signed payloads, Celery-based retries, delivery tracking, admin logs, and rate limiting.

**Modified files (3 + 1 migration):**
- `backend/app/models/webhook_models.py` — Added `RETRYING` to `WebhookStatus` enum, added `next_retry_at` and `delivered_at` columns to `WebhookLog`
- `backend/app/api/v1/webhooks.py` — Hardened `emit_event` to dispatch via Celery task (`deliver_webhook`) with HMAC-SHA256 signing (X-Webhook-Signature, X-Webhook-ID, X-Webhook-Timestamp), inline fallback if Celery unavailable. Added `status`, `delivered_at`, `next_retry_at` to delivery responses. Enhanced `/stats` with p95 latency (`percentile_cont`) and per-status breakdown. Added `GET /admin/logs` endpoint: last N deliveries with filters (status, endpoint_id), success rate, p95 latency, per-status counts
- `backend/app/api/v1/triggers.py` — Added rate limiting (30 req/min per source IP) to public `POST /webhook/{webhook_path}` endpoint using `auth_rate_limiter` with 429 + Retry-After header
- `backend/alembic/versions/20260603_phase85_webhook_delivered_at.py` — Migration adding `delivered_at` column and indexes on `delivered_at` and `status`

**Verified:** Existing retry infrastructure already complete (webhook_tasks.py with exponential backoff + jitter, DLQ after max retries, Celery beat `process_due_retries` task).

**Tests:** 6/7 pass (1 pre-existing failure). Deployed and healthy.

---

## Phase 9: Plugin System + Custom Node SDK — IN PROGRESS

**Goal:** Let third-party developers write, publish, and monetize custom nodes and extensions that plug into FlowManner's execution engine, marketplace, and visual workflow builder.

**Prerequisite:** Phase 8 complete ✅

### 9.1 Plugin Runtime + Sandbox — ✅ COMPLETE

Extended NodeHandlerRegistry with plugin dispatch, created PluginRuntime singleton with full lifecycle, DB-backed state persistence, and startup hydration.

**New files (3 + 1 migration):**
- `backend/app/models/plugin_models.py` — InstalledPlugin model with lifecycle states (installed/loaded/enabled/disabled/uninstalled/error), execution/error counts, per-workspace unique constraint
- `backend/app/services/plugin_loader.py` — .fmp unpacking, manifest validation, dynamic entry point import with BasePlugin subclass detection, node type consistency checks
- `backend/app/services/plugin_runtime.py` — PluginRuntime singleton: install, uninstall, enable, disable, load_installed, get_handler, record_execution. _PluginHandlerAdapter bridges SDK BaseNodeHandler → graph executor BaseNodeHandler interface
- `backend/alembic/versions/20260603_phase91_plugins.py` — Migration for installed_plugins table

**Modified files (3):**
- `backend/app/services/graph_node_handlers.py` — Added register_plugin(), unregister(), plugin_types() methods to NodeHandlerRegistry
- `backend/app/services/graph_executor.py` — _execute_node falls back to PluginRuntime.get_handler() for unknown node types with debug logging
- `backend/app/lifespan.py` — _load_plugins() called on startup to hydrate enabled plugins from DB
- `backend/app/models/__init__.py` — Registered InstalledPlugin model

### 9.2 Custom Node SDK (Python) — ✅ COMPLETE

**New files (8):**
- `backend/app/sdk/__init__.py` — Package exports (BasePlugin, BaseNodeHandler, PluginContext, PluginConfig, PluginManifest, all exceptions)
- `backend/app/sdk/base.py` — BasePlugin (bundle of handlers) and BaseNodeHandler (abstract: node_type_id, execute(), validate())
- `backend/app/sdk/context.py` — PluginContext: typed interface for inputs, config, previous node outputs, logger. require_input() raises SchemaValidationError
- `backend/app/sdk/config.py` — PluginConfig Pydantic base class with manifest schema export (to_manifest_schema())
- `backend/app/sdk/exceptions.py` — PluginError hierarchy: PluginError, PermissionDenied, ExecutionTimeout, SchemaValidationError, ManifestError, PluginLoadError
- `backend/app/sdk/manifest.py` — PluginManifest Pydantic model with validated name/version/permissions/node_types/config/entry_point
- `backend/app/sdk/cli.py` — CLI commands: validate (manifest + entry point), pack (.fmp zip), unpack, with AST-based BasePlugin detection
- `backend/app/sdk/examples/__init__.py` + `flowmanner-plugin.yaml` — Working JSON Transform example plugin

### 9.3 Plugin Marketplace Integration — ✅ COMPLETE

**Modified files (1):**
- `backend/app/api/v1/marketplace.py` — Added 'plugin' to VALID_ARTIFACT_TYPES. Plugin install flow: checks for existing install → resolves .fmp from artifact_id storage path → installs via PluginRuntime → 400 if package unavailable

### 9.4 Visual Workflow Builder Integration — ✅ COMPLETE

**New frontend files (3):**
- `src/lib/plugins-api.ts` — API client for /api/v1/plugins (fetchPluginNodeTypes, fetchPlugins, executePlugin, installPlugin with FormData via fetch, togglePlugin, uninstallPlugin)
- `src/hooks/use-plugin-nodes.ts` — usePluginNodes hook: fetches plugin node types on mount with graceful fallback if API unavailable
- `src/components/mission-builder/nodes/PluginNode.tsx` — Generic React Flow node for plugin types with custom accent color, Puzzle icon, plugin name badge, description, status indicators

**Modified frontend files (4):**
- `src/components/mission-builder/NodePalette.tsx` — Added usePluginNodes hook, dynamic 'Plugins' category appended to NODE_CATEGORIES, dynamic NODE_VISUAL entries with Puzzle icon and custom colors from manifest, allVisuals merge for unified lookup
- `src/components/mission-builder/CustomNode.tsx` — Added PluginNode import, plugin detection via pluginName/pluginNodeType metadata check before generic fallback
- `src/components/mission-builder/FlowEditor.tsx` — Added usePluginNodes hook, handleDrop creates plugin nodes with defaults from API (label, pluginName, pluginNodeType, description, color), pluginNodeTypes in useCallback deps
- `src/components/mission-builder/PropertiesPanel.tsx` — Added PluginConfigSection: plugin badge, node type display, label/description editors, dynamic input fields from plugin schema, test button wired to executePlugin API

### 9.5 Plugin API + Webhooks — ✅ COMPLETE

**New files (1):**
- `backend/app/api/v1/plugins.py` — Full CRUD API:
  - POST /plugins — upload .fmp, validate, install, register handlers
  - GET /plugins — list installed plugins (workspace-scoped, status filter)
  - GET /plugins/node-types — all registered plugin node types with schemas (for graph editor palette)
  - GET /plugins/{id} — plugin detail
  - GET /plugins/{id}/status — health, execution stats, error rate, registered node types
  - PATCH /plugins/{id} — enable/disable toggle
  - DELETE /plugins/{id} — uninstall (unloads from registry + marks DB record)
  - POST /plugins/{id}/execute — direct test execution with mock context
  - POST /plugins/{id}/upgrade — upload new .fmp, uninstall old, install new

**Modified files (1):**
- `backend/app/api/v1/__init__.py` — Registered plugins router

### 9.6 Plugin Security + Review Pipeline — ✅ COMPLETE

**New files (1 + 1 migration):**
- `backend/app/services/plugin_scanner.py` — Static analysis scanner with BLOCKED_IMPORTS (os, subprocess, socket, ctypes, etc.), BLOCKED_BUILTINS (eval, exec, __import__), 15+ BLOCKED_PATTERNS regex rules (os.system, subprocess.run, file traversal, __subclasses__, __globals__, breakpoint, etc.), PERMISSION_PATTERNS detection (network, filesystem, subprocess, env_read, env_write), AST-based import scanning, risk score 0-100 (pass < 50, auto-approve < 30), ScanResult with findings/permissions/mismatch detection
- `backend/alembic/versions/20260603_phase96_plugin_security.py` — Migration for review_status, scan_risk_score, scan_result_json, reviewed_by, reviewed_at, rejection_reason, p99_latency_ms, crash_count, last_health_check_at

**Modified files (3):**
- `backend/app/models/plugin_models.py` — Added review_status (pending/approved/rejected), scan_risk_score, scan_result_json, reviewed_by/at, rejection_reason, p99_latency_ms (server_default), crash_count (server_default), last_health_check_at
- `backend/app/services/plugin_runtime.py` — install() runs security scan before DB record creation, auto-approves low-risk (<30) plugins, marks others pending review. record_execution() now accepts elapsed_ms param and tracks crash_count + p99_latency_ms (max-based proxy)
- `backend/app/api/v1/plugins.py` — 6 new admin endpoints:
  - GET /admin/pending — list plugins pending review
  - POST /{id}/approve — admin approves plugin
  - POST /{id}/reject — admin rejects with reason + auto-disables
  - POST /{id}/kill-switch — disables ALL instances across all workspaces (emergency)
  - POST /{id}/scan — runs scanner, persists results
  - GET /admin/health-report — aggregated health report (healthy/degraded/unhealthy counts, avg error rate, top crashing plugins)

**Tests:** 5/5 passing. **Not deployed.**

---

## Next Steps

**Now:** Finish Phase 6.1 (Episodic Memory — the only remaining 6.x task)
**Next:** Phase 7 frontend (7.1 Inbox UI, 7.2 Mission Observatory, 7.3 Cost Dashboard, 7.5 Marketplace Publisher)
**After Phase 7:** Phase 8 production hardening (8.1 GA the executor first, then 8.2 auth, then 8.3/8.4/8.5 in parallel)
**After Phase 8:** Phase 9 plugin system (9.2 SDK first, then 9.1 runtime, then 9.3/9.4/9.5/9.6 in parallel)

---

## Session 2026-06-03 Work Completed

**Phase 8.1 — UnifiedExecutor GA:**
- ✅ Removed `_unified_executor_enabled` and `_should_use_unified` from executor.py
- ✅ Removed feature flag checks from commands.py — always uses unified path
- ✅ Cleaned up 4 test files (test_event_sourced_state.py, test_mission_cqrs.py, test_mission_handlers.py)
- ✅ 17/17 tests pass, zero remaining references to removed functions

**Phase 8.2 — Multi-Tenant Auth Hardening:**
- ✅ Added `workspace_id` column to `UserAPIKey` model with composite index
- ✅ Workspace-scoped API key CRUD (list, add, delete, test)
- ✅ Rate limiting keyed by `X-Workspace-Id` header (prevents workspace starvation)
- ✅ Migration for `user_api_keys` table

**Phase 8.3 — Public Platform API v2:**
- ✅ Cursor-based (keyset) pagination module with base64 tokens
- ✅ Tier-aware rate limiting with shared sliding window (free/starter/pro/business/enterprise)
- ✅ `/api/v2/openapi.json` endpoint with OpenAPI 3.1 spec, security schemes, tier docs
- ✅ `X-RateLimit-*` response headers middleware for all v2 endpoints
- ✅ Cursor pagination wired into missions, agents, and chat threads endpoints
- ✅ Full app assembles: 120 v2 routes, 663 total routes, all middleware registered

**Phase 8.4 — Subscription + Billing:**
- ✅ Created subscription_service.py — tier resolution, limit enforcement, grace period, billing dashboard
- ✅ Enhanced paypal_service.py — activate, suspend, webhook signature verification (local + API)
- ✅ Added PayPal webhook endpoint (POST /paypal/webhook) — lifecycle event processing
- ✅ Added post-approval activation endpoint (POST /paypal/activate)
- ✅ Added billing dashboard endpoint (GET /billing) — plan, usage, limits, remaining
- ✅ Wired tier enforcement into mission create, execute, and async execute
- ✅ Wired API access gating into API key generation (free tier blocked)
- ✅ Fixed pre-existing test bugs (MagicMock name parameter, mock setup)
- ✅ Deployed and verified healthy

**Phase 8.5 — Webhook Delivery Hardening:**
- ✅ Added RETRYING status + next_retry_at/delivered_at columns to WebhookLog
- ✅ Hardened emit_event — Celery dispatch with HMAC-SHA256 signing, inline fallback
- ✅ Added status, delivered_at, next_retry_at to delivery responses
- ✅ Enhanced /stats with p95 latency and per-status breakdown
- ✅ Added GET /admin/logs endpoint (last N deliveries, filters, success rate, p95)
- ✅ Added rate limiting (30 req/min per IP) to public webhook trigger endpoint
- ✅ Migration for delivered_at column and indexes
- ✅ Deployed and verified healthy

---

## Critical Rules

1. **NEVER edit files on the VPS** — all edits on homelab
2. **Backend has no volume mounts** — deploy after edits: `bash /opt/flowmanner/deploy-backend.sh`
3. **Backend deploy takes ~2 minutes** — use `timeout=300`
4. **Frontend deploy takes ~4 minutes** — use `bash /opt/flowmanner/deploy-frontend.sh`
5. **Nginx restart** — `bash /opt/flowmanner/restart-nginx.sh` (on VPS)
6. **Import scripts ARE in the container image** — included via `COPY scripts/ /app/scripts/` in Dockerfile
7. **Run DR test:** `docker compose exec backend python /app/dr_test.py`
8. **Run bootstrap:** `docker compose exec backend python -m app.cli.bootstrap`

---

## Key Infrastructure

```
Existing backend files to build on:
  app/services/memory_service.py        — current memory (Postgres-first, Redis cache)
  app/models/memory_models.py           — memory_entries table
  app/services/substrate/executor.py    — UnifiedExecutor (sole execution path, GA'd in 8.1)
  app/models/substrate_models.py        — substrate_events table (append-only event log)
  app/api/v1/hitl.py                    — HITL inbox endpoints (288 lines)
  app/api/v1/circuit_breaker.py         — Circuit breaker API (129 lines)
  app/api/v1/cost_attribution.py        — Cost attribution API (97 lines)
  app/api/v1/byok.py                    — BYOK key management (197 lines)
  app/api/v1/webhooks.py                — Webhook delivery (372 lines)
  app/api/v1/triggers.py                — Mission triggers (257 lines)
  app/api/v1/subscription.py            — Subscription tiers (208 lines)
  app/api/v1/api_keys.py                — API key auth (343 lines, workspace-scoped since 8.2)
  app/api/v2/                           — v2 API (120 routes, full public API since 8.3)
  app/api/v2/cursor_pagination.py       — Keyset pagination (new in 8.3)
  app/api/v2/tier_rate_limit.py         — Tier-aware rate limiting (new in 8.3)
  app/api/v2/openapi.py                 — OpenAPI 3.1 spec endpoint (new in 8.3)
  app/api/v2/rate_limit_headers.py      — Rate limit headers middleware (new in 8.3)

Services running:
  Qdrant  — tool/capability search + mission_episodes (Phase 6.1)
  RabbitMQ — used by Celery workers
  Redis   — cache layer
  Celery  — background workers
  Jaeger  — distributed tracing
  llama.cpp — local LLM (Qwen3.6-27B-MTP)

Frontend pages already exist:
  /dashboard, /missions, /agents, /chat, /marketplace, /costs,
  /analytics, /graphs, /integrations, /developer, /admin,
  /models, /knowledge, /topology, /tools, /browser
```
