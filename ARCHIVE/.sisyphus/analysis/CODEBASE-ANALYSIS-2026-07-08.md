# Flowmanner Codebase Analysis — Backend & Frontend

**Date:** 2026-07-08
**Author:** Sisyphus (orchestration agent, homelab)
**Scope:** Full deep-dive of `/opt/flowmanner/backend/` (FastAPI) and `/home/glenn/FlowmannerV2-frontend/` (Next.js)
**Method:** Direct inspection (no delegation), guided by the codebase's own `AGENTS.md` contracts.

---

## 1. Executive Summary

Flowmanner is a large, multi-machine AI-workflow automation platform: a FastAPI backend on the homelab (postgres/redis/qdrant/rabbitmq/celery/llama.cpp) fronted by a Next.js App-Router app on the VPS, with a WireGuard tunnel between them.

- **Backend:** ~222k LOC Python across 65 ORM models, 42 service subpackages, and three API tiers (v1 legacy, v2 current default, v3 workspace/auth specialty). A recent major effort collapsed 7 legacy executors into a single **`UnifiedExecutor` substrate (H5.1, GA)**.
- **Frontend:** ~117k LOC TypeScript across a fully i18n'd App Router with ~200 routes, a generated SDK, a shared `ApiClient`, and Zustand stores.
- **Maturity:** Disciplined in places (feature-flag gating, CQRS split, envelope contracts, append-only event log, structured logging) but carries real debt: a bare `AppError`, duplicate auth systems (NextAuth JWT + `fm_tokens`), stub v3 OIDC/webhooks, legacy executors still wired behind a flag, and an uncommitted WIP diff on the backend.
- **Test ratio:** ~9.5% backend (21k test LOC / 222k prod), 81 frontend test files over 117k LOC — present but thin per-module; several subsystems (e.g. `improvement/`, `langgraph/`, `runtime/`) have large surface area with concentrated coverage.

**Top risks to flag:** (1) the documented Mission-system silent-mock failure mode may still exist in the legacy `mission_executor.py` path; (2) `core/exceptions.py` is a 2-line stub, so most errors collapse to a generic 500; (3) `git status` shows 7 uncommitted backend edits that must be committed per the end-of-session ritual.

---

## 2. Scale & Metrics

| Metric | Backend | Frontend |
|---|---|---|
| Total LOC (`app/`, `src/`) | **221,702** | **117,136** (ts/tsx) |
| Test LOC / files | 21,013 / 69 files (`app/tests/`) | 81 test files (`*.test.*`/`*.spec.*`) |
| Entry points | `app/main_fastapi.py` | `app/layout.tsx`, `app/[locale]/...` |
| ORM models | 65 | — |
| Service subpackages | 42 | — |
| API routers | v1: 75 files · v2: 24 · v3: 12 | ~200 routes under `app/[locale]` |
| Components | — | 30+ top-level component groups |
| State mgmt | — | Zustand (store + auth-store) + React Query |

Test-to-code ratio is roughly **1:10** on the backend — acceptable as a floor but uneven: substrate, mission, and auth have dedicated suites, while large clusters (`improvement/`, `langgraph/`, `runtime/`, `nexus/`) are covered by far fewer tests relative to their size (the `improvement/` subsystem alone is ~10.5k LOC per its own doc).

---

## 3. Backend Deep-Dive

### 3.1 Entry Point & Middleware (`app/main_fastapi.py`)
FastAPI 0.115 app with a carefully ordered middleware stack (ordering is load-bearing — `AGENTS.md` documents a silent-failure mode where a middleware class defined *below* its `add_middleware` call causes health-check failure with no traceback):

`AuthCookieMiddleware` → `ScopeValidationMiddleware` → `CORSMiddleware` → `SecurityHeadersMiddleware` → `AuditMiddleware` → `MetricsMiddleware` → `GlobalRateLimitMiddleware` → `GraphQLDeprecationMiddleware` → v2 `RateLimitHeadersMiddleware` → v2 `IdempotencyFinalizationMiddleware`.

Notable engineering:
- **Resilient OpenAPI generation** (`_resilient_openapi`): catches spec crashes and rebuilds route-by-route, skipping broken routes (capped at 20 skips) instead of taking the whole docs down. Good defensive pattern.
- **`general_error_handler`** fires a fire-and-forget `ntfy` 5xx alert via `asyncio.create_task` (won't block the 500). Good.
- **GraphQL** (strawberry) is optional — imported lazily and disabled if `strawberry` isn't installed.
- **Custom dark-themed Swagger/Redoc** injected via CSS string replacement (works around FastAPI 0.115 lacking `custom_css`).

### 3.2 API Tiers (`app/api/`)
Authoritative contracts exist in `app/api/AGENTS.md`, `app/api/v3/AGENTS.md`, `app/services/AGENTS.md`.

| Tier | Status | Envelope | Auth | Notes |
|---|---|---|---|---|
| **v1** (`api/v1/`, 75 files) | Legacy, stable | **None** (raw FastAPI) | `get_current_user` (JWT) | 60+ domains; must stay backward-compatible forever. No envelope, no GraphQL. |
| **v2** (`api/v2/`, 24 files) | **Current default** (`CURRENT_VERSION`) | `ok`/`paginated`/`err` | `get_current_user` (JWT) | "Genuine redesign." Includes Blueprint/Run + Phase-0 regression. |
| **v3** (`api/v3/`, 12 files) | Active, specialty | v2 envelope **+ `trace_id`** | `get_current_session` (httpOnly cookie + Bearer) | Workspace + auth surface only. |
| **CQRS** (`_mission_cqrs/`, `_blueprint_cqrs/`) | Internal | — | — | Command/Query split; routes are thin DI shells over handler classes. |

**Observations:**
- The versioning policy is coherent: *v1 = legacy stable, v2 = default new features, v3 = workspace/auth only*. Strong.
- v3 (per its `AGENTS.md`) is **partially stubbed**: `auth_oidc.py` returns hardcoded `https://example.com/...` placeholders and has no provider allowlist; `auth_webhooks.py` takes `workspace_id`/`url`/`events` as **query params instead of a body** and does not actually deliver webhooks (no HMAC, no retry). These are explicitly marked ⚠️ WIP and should not be shipped without refactor.
- v3 errors carry `trace_id` for log correlation — good operational hygiene.

### 3.3 Config & Secrets (`app/config.py`)
Single `Settings(BaseSettings)` pydantic model, 350+ lines, `extra="ignore"`, `.env`-backed.
- Per-environment safety: `assert_production_ready()` fails fast on placeholder/short `SECRET_KEY`/`JWT_SECRET_KEY`/`AES_ENCRYPTION_KEY`, insecure cookie flag, and missing `SENTRY_WEBHOOK_SECRET`. `validate_secrets()` returns warnings. Good.
- **Default-secret risk:** `SECRET_KEY`/`JWT_SECRET_KEY`/`AES_ENCRYPTION_KEY` default to `"change-me-in-production"`. Safe only because `assert_production_ready()` blocks startup in prod env — but a misconfigured `APP_ENV` (not "development") with the placeholder would be caught. Verified OK.
- Feature-flag-style bools are sprinkled throughout (`STRATEGY_EXPERIMENTAL`, `BUDGET_AWARE_PLAN_SELECTION`, `FLOWMANNER_CROSS_MISSION_MEMORY`, etc.). Useful, but many interact (experimental strategies failed validation per a comment — keep them off).
- 30+ integration OAuth secret pairs — all empty defaults; populated via env. Fine.

### 3.4 Data Models (`app/models/`, 65 models)
Sample inspected: `User` (well-structured, `Mapped`/`mapped_column` modern SQLAlchemy 2.0 typing, `TimestampMixin`, TOTP fields, relationships with `cascade="all, delete-orphan"`).
- Modern typing throughout (`Mapped[int]`, `String(255)`). Clean.
- **Universal soft-delete**: `deleted_at` IS NULL filter is a stated contract across CQRS queries. Good.
- **Concern:** 140+ Alembic migrations, many single-purpose (e.g. `20260630_add_mission_plan_candidates.py`). Migration churn is high but each is small and targeted — manageable, though the `reconcile_schema_001` incident (a `DELETE` that destroyed analytics rows) shows the risk. The 2026-06-25 convention (use sentinel `UPDATE`, never `DELETE`) is now documented and should be enforced.

### 3.5 Services (`app/services/`, 42 subpackages)
This is the business-logic seam. `app/services/AGENTS.md` is an excellent map (22 clusters). Highlights:

- **Mission execution cluster:** `mission_executor.py` was decomposed (ADR 001) from a 1,362-line god-class into `mission_planner`, `task_executor`, `llm_executor`, `browser_task_runner`, `cost_tracker` + helper modules. Constructor injection with **callables for late-bound deps** (`lambda: get_app_state().model_router`) and **callbacks** to break circular imports. This is a textbook refactor — strong.
- **LLM routing cluster:** `llm_router.py` (async, preferred) + `model_router.py` (legacy sync). BYOK precedence is `kwargs → stored user key → platform key`; llama.cpp ignores keys. There is a **known bug history** (`test_h1_1_model_router_silent_failure.py`) — the root cause documented in `CLAUDE.md` (Issue 3): `ModelRouter._is_model_available` calls `get_model()` without `user_id`/`db_session`, breaking external-key lookup, and the legacy `mission_executor` *swallows* `success=False` and returns `{"success": True}` with empty output. **This silent-mock path is the single most important correctness risk** and should be re-verified against the current code, since `mission_executor` is still wired behind `FLOWMANNER_UNIFIED_EXECUTOR`.
- **Execution substrate (H5.1, GA):** `services/substrate/` is the canonical path now. `UnifiedExecutor` (982 LOC) is the single entry point with **4 guarantees** (durable event log, type-checked I/O, capability-bounded tool calls, budget-enforced LLM). 7 strategies (solo/dag/graph/swarm/pipeline/meta/langgraph), append-only `substrate_events`, replay engine for crash recovery, and a regression loop (`BaselineExtractor` + `ReplayAssertionEngine`). The `substrate/AGENTS.md` is exemplary. **Old executors still coexist behind the flag** — cleanup (delete them) is pending parity confirmation.

### 3.6 Auth & Security
- **v3** (`auth_v3_service`): httpOnly `Secure`+`SameSite=Strict` refresh cookie (path-scoped to `/api/v3/auth`), explicit session list/revoke, scoped API keys **AES-256 encrypted at rest**, SHA-256 hash + prefix only stored, full key returned once. 2FA via TOTP (`totp_service`), backup codes, IP-based rate limiting (`auth_rate_limiter`). Password change revokes all sessions. Solid design.
- **Feature-flag gating:** every v3 endpoint calls `_require_*_enabled(db)` first → returns **404** (never 403) when disabled, so disabled features don't leak existence. Good security practice.
- **Weakness:** `core/exceptions.py` is a 2-line stub (`class AppError(Exception): pass`). Domain-specific exceptions are minimal; most failures collapse to the generic 500 handler. Consider a typed error hierarchy for cleaner client errors and observability.

### 3.7 Integrations (`app/integrations/`, `app/services/*`)
30+ integration OAuth pairs configured; connectors for github/notion/discord/email/google/linear/slack/webhook; plus dedicated `linear/`, `mcp/`, `webhook_handler/` (retry + signature verification). The `sandboxd` HTTP client lives in `app/integrations/sandboxd_client.py`. Breadth is high; most are env-gated and off by default.

### 3.8 Observability
structlog (JSON in prod) with request-id binding; OpenTelemetry → Jaeger (opt-in via `OTLP_ENDPOINT`); Prometheus metrics middleware; `ntfy` 5xx alerts; circuit breaker (`core/circuit_breaker.py`) per-provider; `runtime/` self-healing + predictive scaling. Mature.

### 3.9 Tests
69 files / 21k LOC. Substrate, mission, auth, and chat have dedicated suites; chaos suite (8 contract tests) for the substrate. Per-cluster `pytest` invocation documented. Coverage is uneven relative to total LOC but the critical execution/auth paths are well-covered.

---

## 4. Frontend Deep-Dive

### 4.1 Framework & Routing
Next.js **App Router** with full i18n via `app/[locale]/...` and a parallel `(dashboard)` / `(auth)` route groups. ~200 route files. Marketing/legal/blog pages coexist with the authenticated dashboard. Routes are split into `page.tsx` (server) + `page-client.tsx` (client) pairs — a consistent, clean pattern that keeps server/client boundaries explicit.

### 4.2 `lib/` — API & SDK
- **`lib/api-client.ts`** (238 LOC): fetch-based, same-origin relative paths, no `NEXT_PUBLIC_API_URL`. Key behaviors:
  - Token from NextAuth session; `PUBLIC_PATHS` skip auth. **Caveat (documented in-file):** matching uses `startsWith()`, so any sub-path of a public entry also skips auth — e.g. `/api/roadmap` would also match `POST /api/roadmap/comments` (which requires auth). This is a real, documented risk; needs verification that all sub-paths are truly public.
  - **401 handling:** single-retry after token-cache invalidation, then a **guarded `signOut`** (the `_signOutInProgress` flag prevents the A.3 redirect-loop symptom where one expired session triggered 5–10 signOut calls). Well-documented fix.
  - Auto-unwraps the v2 envelope (`{data, meta, error:null}`).
- **`lib/sdk/`**: generated OpenAPI client (`core/`, `models/`, `services/`) — 100+ model files. Auto-generated; treat as read-only.
- **`lib/auth.ts`, `get-auth-token.ts`**: NextAuth JWT wiring.
- ~50 domain API modules (`chat-types`, `mission-types`, `orchestration-api`, `workspace-api`, `sandbox-api`, etc.) — thorough.

### 4.3 State (`store/`, `providers/`)
- **`store/onboarding-store.ts`**: Zustand. All async actions **silently swallow errors** ("onboarding is non-critical"). Acceptable for onboarding, but the pattern (empty `catch {}`) should not leak into critical stores.
- **`providers/auth-provider.tsx`**: thin wrapper that initializes a Zustand `auth-store` on mount and exposes `useAuth()`. Note the **dual auth system**: NextAuth JWT cookie **and** Zustand `fm_tokens` localStorage key must agree (per `AGENTS.homelab.md`). Two sources of truth for session state is a recurring footgun — worth consolidating long-term.
- Other providers: `query-provider` (React Query), `websocket-provider`, `command-palette-provider`, `pwa-provider`.

### 4.4 Components
30+ top-level component groups (`chat/`, `mission-builder/`, `mission-gallery/`, `analytics/`, `marketplace/`, `settings/`, `ui/`, `layout/`, `sandbox/`, `observatory/`, `runs/`, `swarm/`, `templates/`, `triggers/`, `integrations/`, `memory-inspector/`, `critiques/`, `costs/`, `notifications/`, `onboarding/`, `workspace/`, `rag/`, `evaluation/`, `external-events/`, `inbox/`, `landing/`, `blog/`, `auth/`, `charts/`, `approvals/`, `shared/`, `dev/`, `seo/`). Several have `__tests__/` subdirs (vitest). `mission-builder/nodes/` suggests a node-graph editor (mirrors the backend substrate DAG/graph strategies). Component organization is feature-oriented and consistent.

### 4.5 Hooks & i18n
- `hooks/` (33 files) + `hooks/mission-builder/`. Some have tests.
- `i18n/locales/` with `__tests__`. Localization supported across locales.

### 4.6 Tests
81 test files; **vitest + playwright** configured (`vitest.config.ts`, `playwright.config.ts`). Coverage is concentrated in components/chat, analytics, critiques, marketplace, settings, mission-builder, reliability. E2E (`e2e/`) runs against localhost:3000. Relative to 117k LOC this is a thin-but-present floor; the high-risk chat/mission flows have some coverage.

---

## 5. Cross-Cutting Concerns & Risks

| # | Risk / Observation | Severity | Evidence |
|---|---|---|---|
| 1 | **Mission silent-mock (VERIFIED 2026-07-08)** — Root Cause 1 **FIXED** (`ModelRouter` now threads `user_id`/`db_session` into BYOK lookup, no more `ValueError("No models available")`). Root Cause 2 **RELOCATED**: `BudgetEnforcer.call` (`budget_enforcer.py:304-347`) silently falls back to local llamacpp on *any* `route_request` exception, returning `success: True` with local-model output. A failed cloud/BYOK model becomes a silent "success" on the wrong model. | **Medium-High** | `budget_enforcer.py:283-347`; `llm_router.py:93-95,350-362`; `node_executor.py:528,542` |
| 2 | **`core/exceptions.py` is a 2-line stub** — no typed error hierarchy; most failures → generic 500. | Medium | `app/core/exceptions.py` |
| 3 | **`PUBLIC_PATHS` `startsWith()` over-match** — sub-paths of public endpoints skip auth unintentionally. | Medium | `lib/api-client.ts:79-98` (self-documented) |
| 4 | **Dual auth state** (NextAuth JWT + `fm_tokens` localStorage) — two sources of truth; desync footgun. | Medium | `AGENTS.homelab.md`; `providers/auth-provider.tsx` |
| 5 | **v3 OIDC & webhooks are stubs** — hardcoded callback, query-param body, no HMAC/delivery. | Medium | `app/api/v3/AGENTS.md` |
| 6 | **Legacy executors still in tree** behind `FLOWMANNER_UNIFIED_EXECUTOR` — deletion pending parity confirmation. | Low/Medium | `app/services/substrate/AGENTS.md` |
| 7 | **Uncommitted backend WIP** — 7 modified files (chat v1/v2, sse_buffer + test, tools/*). Must commit per end-of-session ritual. | Process | `git status` |
| 8 | **Thin per-module test coverage** on large subsystems (`improvement/`, `langgraph/`, `runtime/`, `nexus/`). | Medium | LOC vs test counts |
| 9 | **High migration churn** (140+ Alembic files). `reconcile_schema_001` already destroyed data once via `DELETE`. | Low (mitigated) | `backend/AGENTS.md` migration convention |

---

## 6. Strengths (worth preserving)

- Coherent 3-tier API versioning with explicit backward-compat guarantees.
- CQRS split keeps routes thin; business logic in handler classes.
- `UnifiedExecutor` substrate with durable append-only event log, replay-based crash recovery, and a regression/baseline loop — genuinely sophisticated execution architecture.
- Feature-flag gating that returns 404 (no existence leak) for disabled features.
- Resilient OpenAPI generation that degrades gracefully.
- Structured logging + request-id + trace_id correlation + ntfy alerts.
- Mission-executor decomposition (ADR 001) with callable/late-bound DI and callback patterns — clean.
- Frontend `ApiClient` 401 guard preventing redirect loops; envelope auto-unwrap.
- Excellent in-repo `AGENTS.md` contracts at multiple levels (backend, api, v3, services, substrate) — rare and valuable.

---

## 7. Recommendations (prioritized)

1. **Close the relocated Risk #1 (VERIFIED)** — `mission_executor.py` is deleted and `node_executor._handle_llm` now checks `success`/empty content, so the *empty* silent-mock is gone. **But** `BudgetEnforcer.call` (`budget_enforcer.py:283-347`) still masks any `ModelRouter` failure with a local-llamacpp fallback that returns `success: True`. Fix: (a) only apply the llamacpp fallback when the *intended* model is itself local, or when an explicit `allow_fallback` flag is set; (b) when the fallback fires for a non-local intended model, surface a non-fatal warning to the client and tag the event log so the provider mismatch is visible. Add a test asserting a failed cloud/BYOK model does NOT become a silent `success` on the local model without a warning.
2. **Type the error hierarchy** — expand `core/exceptions.py` into domain exceptions mapped to v2/v3 `err()` codes so clients get actionable errors instead of generic 500s.
3. **Tighten `PUBLIC_PATHS`** — switch from `startsWith` to exact-path (or explicit allowlist with verified sub-paths) to remove the auth-skip footgun.
4. **Consolidate auth state** — pick one source of truth (NextAuth session or `fm_tokens`) and derive the other, eliminating the dual-system desync class of bugs.
5. **Finish or hide v3 OIDC/webhooks** — either implement provider allowlist + HMAC delivery, or keep them 404-gated until ready (don't ship the stubs).
6. **Delete legacy executors** once substrate parity is confirmed ≥2 weeks in prod (per substrate `AGENTS.md` checklist).
7. **Commit the WIP backend diff** and run the end-of-session ritual (exit audit + push) — currently 7 files are uncommitted.
8. **Raise test floors** on `improvement/`, `langgraph/`, `runtime/`, `nexus/` before further expansion.

---

## 8. File Index (key entry points)

**Backend**
- `app/main_fastapi.py` — app + middleware + OpenAPI
- `app/config.py` — settings & secret validation
- `app/core/exceptions.py` — error base (stub)
- `app/api/{v1,v2,v3}/` — API tiers; `app/api/{_mission_cqrs,_blueprint_cqrs}/` — CQRS
- `app/services/substrate/executor.py` — `UnifiedExecutor` (canonical execution)
- `app/services/mission_executor.py` — legacy orchestrator (decomposed)
- `app/services/llm_router.py` — async model router + BYOK
- `app/api/v3/auth.py` — v3 auth (sessions, API keys, 2FA)
- `app/models/user.py` — representative ORM model

**Frontend**
- `src/lib/api-client.ts` — shared fetch client
- `src/providers/auth-provider.tsx` — auth init
- `src/store/onboarding-store.ts` — Zustand store (example)
- `src/app/[locale]/(dashboard)/` — authenticated app shell + feature routes
- `src/lib/sdk/` — generated API client (read-only)
- `vitest.config.ts` / `playwright.config.ts` — test harness

---

---

## 9. Verification Addendum — Risk #1 (2026-07-08)

**Question:** Does the documented Mission silent-mock bug (`CLAUDE.md` Issue 3) still exist on the shipping path?

**Method:** Read the actual code on the current execution chain: `llm_router.py::ModelRouter.route_request` → `budget_enforcer.py::BudgetEnforcer.call` → `substrate/node_executor.py::_handle_llm` → `substrate/executor.py::call_llm`.

**Findings:**
1. `app/services/mission_executor.py` **no longer exists** — the H5.1 substrate cleanup deleted the legacy orchestrator. The "swallow success=False → return `{"success": True}` empty" code is gone.
2. **Root Cause 1 FIXED.** `route_request` (llm_router.py:67-69, 93-95) and `_is_model_available` (llm_router.py:350-362) now pass `user_id`/`db_session` into the BYOK key lookup. The old `ValueError("No models available")` path is gone; missing keys return `success=False` with a clear error (llm_router.py:114-130).
3. **Root Cause 2 RELOCATED (not fixed).** `BudgetEnforcer.call` (budget_enforcer.py:283-347) calls `ModelRouter.route_request(...)` inside a `try`, and on *any* exception silently falls back to a direct `httpx` POST to `LLM_BASE_URL` (default `http://localhost:11434`, the local llamacpp), returning `{"success": True, "provider": "llamacpp", ...}`. Net effect: a failed cloud/BYOK model becomes a silent "success" on the *local* model. `node_executor._handle_llm` checks `success` (line 528) and empty content (line 542), so a genuine `success:False` is correctly surfaced — but the fallback never lets `success:False` escape, so the downgrade is invisible to the user (only `provider: "llamacpp"` in the event log hints at it).
4. `executor.py::call_llm` (lines 608-695) delegates to `BudgetEnforcer.call`, so the fallback applies to every substrate LLM node.

**Verdict:** The *empty-output* silent-mock is resolved. A *wrong-model* silent-mock remains via `BudgetEnforcer`'s fallback and is the current shipping behavior. Severity downgraded High → Medium-High because (a) it only triggers when the intended cloud/BYOK model errors, and (b) the event log records the true provider. Recommended fix: gate the fallback on `allow_fallback` / local-only intent and emit a client-visible warning when it fires for a non-local model. See updated Risk #1 and Recommendation 1.

---

*Generated by Sisyphus (homelab agent). Analysis is static-read only; no files were modified except this report. Backend diff remains uncommitted — see Recommendation 7.*
