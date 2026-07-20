# Flowmanner Frontend — Architecture & Route→API Map

> Read-only analysis for knowledge-graph ingestion. All claims anchored to `file:line` in the
> `/home/glenn/FlowmannerV2-frontend` repo (branch `agent/20260720-kg/frontend`).
> Product name is **Flowmanner** (NOT "Flowmapper"). Repo root in this task: `FlowmapperV2-frontend`
> symlink target = `FlowmannerV2-frontend`.

---

## APP STRUCTURE

Next.js **16.2.6** App Router, standalone output, TypeScript **5 strict**. Generated with `create-next-app`,
i18n via `next-intl` (single `en` locale, all routes under `[locale]`).

### Tech stack (from `package.json`)
- **Framework**: `next@16.2.6`, `react@19.2.4`, `react-dom@19.2.4` (`package.json:59-64`)
- **Styling**: `tailwindcss@3.4.19`, `tailwindcss-animate`, `@tailwindcss/typography`; Radix UI primitives (`@radix-ui/*`), `class-variance-authority`, `clsx`, `tailwind-merge`
- **State**: `zustand@5.0.13` (client stores only — see below), `@tanstack/react-query@5` (provider present, used sparingly)
- **Data fetching**: hand-rolled `fetch` wrapper `apiClient` (`src/lib/api-client.ts:175`), NOT Axios. `src/lib/sdk/` is a generated OpenAPI client (`@/lib/sdk/services/*`) that coexists with feature API modules.
- **Auth**: `next-auth@5.0.0-beta.31` (Auth.js v5), `@auth/core@0.41.2` (`package.json:18,60`)
- **Graph editor**: `@xyflow/react@12.10.2` (React Flow) (`package.json:47`)
- **Real-time**: `socket.io-client@4.8.3` (`package.json:76`)
- **Forms/i18n/misc**: `react-hook-form`, `zod@4`, `next-intl@4`, `motion`, `recharts`, `kbar` (cmd palette), `sonner` (toasts), `lucide-react`

### Directory tree (top-level under `src/`)
```
src/
├── app/
│   ├── api/                      # Next.js API routes (auth bridge + onboarding + config)
│   │   ├── auth/                 # [...nextauth], login, me, password, settings, avatar, preview-cookie
│   │   ├── onboarding/           # complete/skip/status/step/steps/sample-data
│   │   ├── config/milestones/route.ts
│   │   └── og/route.ts
│   ├── [locale]/
│   │   ├── (auth)/              # signin, signup  (route group, no URL segment)
│   │   ├── (dashboard)/         # chat, missions, marketplace, blueprints, runs, team, settings, admin, analytics, rag, plugins, evaluations, reliability, swarm, templates, triggers, files...
│   │   ├── dashboard/           # alternate dashboard page (settings/integrations/programs/evaluation/swarm)
│   │   ├── agents/              # agent marketplace + detail ([...slug])
│   │   ├── tools/               # browser, terminal, topology, catalog
│   │   ├── integrations/        # integrations browse + detail
│   │   ├── blog/ case-studies/ guides/ docs/ developers/  # content/marketing pages
│   │   ├── pricing/ about/ security/ privacy/ terms/ dpa/ careers/ contact/ status/ roadmap/  # public/legal pages
│   │   ├── inbox/ notifications/ profile/ invite/[token]/  # user surfaces
│   │   ├── layout.tsx page.tsx page-client.tsx  # root [locale] shell
│   │   ├── layout.tsx providers.tsx  # wraps everything in providers
│   │   └── ...
│   ├── layout.tsx globals.css error.tsx loading.tsx  # app root
├── components/
│   ├── ui/            # shadcn-derived + app components (see AGENTS.md CUSTOMIZATIONS.md)
│   ├── chat/          # ChatLayout, SSEChat, ThreadSidebar, tiles/*, CommandQueuePanel...
│   ├── mission-builder/ # FlowEditor + nodes/* (React Flow nodes)
│   ├── dashboard/     # widgets (MissionsWidget, UsageStatsWidget, RunHistoryWidget...)
│   ├── marketplace/   # listing-card, featured-carousel, listing-detail...
│   ├── analytics/     # MissionDashboard, charts
│   ├── layout/ auth/ settings/ templates/ triggers/ rag/ swarm/ onboarding/ notifications/ blog/ seo/ approvals/
├── lib/
│   ├── api-client.ts        # THE central fetch wrapper (auth, retry, envelope unwrap)
│   ├── get-auth-token.ts    # token resolution (server auth() / client sessionStorage+getSession)
│   ├── auth.ts              # NextAuth config (providers, jwt/session callbacks, refresh)
│   ├── auth/                # lib/auth helpers (authApi, register, etc.)
│   ├── workspace-api.ts     # team/workspace/membership/invitation/messages
│   ├── marketplace-api.ts   # listings, reviews, install
│   ├── rag-api.ts usage-api.ts cost-api.ts billing-api.ts notification-api*.ts mission-stream-types.ts
│   ├── api/                 # feature API modules: runs.ts, programs.ts, substrate.ts, critique.ts, personal-memory.ts, io.ts, onboarding.ts, tts-api.ts
│   ├── sdk/                 # GENERATED OpenAPI client (services/ + models/)
│   ├── websocket.ts         # socket.io singleton
│   └── ...
├── stores/                  # Zustand stores (note: plural `stores`, not `store`)
│   ├── auth-store.ts chat-store.ts workspace-store.ts program-store.ts inbox-store.ts notification-store.ts cost-store.ts
├── providers/               # Providers, QueryProvider, WebSocketProvider, PWAProvider, CommandPaletteProvider, auth-provider
├── hooks/                   # custom React hooks (use-programs, use-chat-keyboard, ...)
├── types/                   # shared TS types (auth, workspace, marketplace, mission-types, chat-types...)
└── test/ i18n/ data/
```

### State management summary
- **Global client state**: Zustand, 7 stores in `src/stores/` (`auth-store.ts:72` `create<AuthState>`, `chat-store.ts`, `workspace-store.ts`, `program-store.ts`, `inbox-store.ts`, `notification-store.ts`, `cost-store.ts`). **No Redux.**
- **Server-state / fetching**: `QueryClientProvider` is mounted (`providers.tsx:14`, `query-provider.tsx:6`) but the dominant pattern is **imperative `apiClient` calls inside `useEffect`** (e.g. `chat/page-client.tsx:27`, `FlowEditor.tsx:1048`), not `useQuery` hooks. `SWR` is **not present** (0 matches).
- **Auth state**: NextAuth `SessionProvider` (`providers.tsx:12`) + a Zustand `useAuthStore` convenience wrapper (`stores/auth-store.ts`).

---

## ROUTE→API MAP

Pattern: most pages render a thin `page.tsx` server shell that delegates to a `*-page-content.tsx` / `page-client.tsx` client component, which calls the backend via `apiClient`. Backend base is **relative** (`apiClient` base URL = `""`, `api-client.ts:35`) — same-origin; Nginx proxies `/api/*` → backend `10.99.0.3:8000`.

| Route (under `/[locale]`) | Main component file | Backend endpoints consumed |
|---|---|---|
| `(auth)/signin`, `(auth)/signup` | `signin/page.tsx`, `signup/sign-up-page-content.tsx` | `POST /api/auth/login` (via NextAuth `authorize`), `POST /api/auth/register` (via `authApi.register`) — `auth.ts:248`, `auth-store.ts:94` |
| `(dashboard)/chat` | `chat/page-client.tsx` → `components/chat/ChatLayout`, `SSEChat.tsx` | `GET/POST/DELETE/PATCH /api/v2/chat/threads`, `/api/v2/chat/folders`, `/api/v2/chat/messages/{id}/react`, `POST /api/v2/chat/threads/{id}/title` — `ThreadSidebar.tsx:77-189`, `SSEChat.tsx:421-497` |
| `(dashboard)/missions/builder` | `missions/builder/page-client.tsx` → `components/mission-builder/FlowEditor.tsx` | `GET /api/v2/blueprints/{id}` (`runs.ts:166`), `POST /api/v2/blueprints/` (`FlowEditor.tsx:1050`), `PATCH /api/v2/blueprints/{id}` (`FlowEditor.tsx:1048`), `POST /api/graphs/{id}/resume/{execId}` (`FlowEditor.tsx:1401`), `GET /api/graphs/compare/{a}/{b}` (`FlowEditor.tsx:1031`) |
| `(dashboard)/missions`, `missions/[id]/observatory`, `missions/[id]/replay` | `missions/page-client.tsx`, `replay/page-client.tsx` | `/api/v2/missions/*` via `apiClient` (mission list/status) — `MissionStatusTile.tsx:65 GET /api/v2/missions/{id}/status` |
| `(dashboard)/blueprints`, `blueprints/[id]`, `blueprints/[id]/executions` | `blueprints/page-client.tsx`, `blueprints/[id]/page-client.tsx` | `GET /api/v2/blueprints{?qs}` (`runs.ts:179`), `GET /api/v2/blueprints/{id}/versions` (`runs.ts:201`), `POST /api/v2/blueprints/{id}/run` (`runs.ts:133`) |
| `(dashboard)/runs`, `runs/[id]` | `runs/page-client.tsx`, `runs/[id]/run-detail-client.tsx` | `GET /api/v2/runs{?qs}` (`runs.ts:93`), `GET /api/v2/runs/{id}` (`runs.ts:97`), `/events`, `/replay`, `/assertions`, `/diff/{other}`, `/abort`, `/retry` (`runs.ts:104-126`) |
| `(dashboard)/marketplace` | `marketplace/marketplace-page-content.tsx` | `GET /api/v2/marketplace/listings{?qs}`, `/featured`, `/categories`, `POST/DELETE /api/v2/marketplace/listings/{slug}`, `/install` — `marketplace-api.ts:112-267` |
| `(dashboard)/marketplace/listing-detail`, `create-listing`, `my-listings`, `my-installed` | `marketplace/listing-detail/listing-detail-content.tsx`, `create-listing/create-listing-content.tsx` | `/api/v2/marketplace/listings/{slug}` (`marketplace-api.ts:127`), `/{slug}/reviews` (`marketplace-api.ts:211`) |
| `(dashboard)/team` | `team/team-management-page-content.tsx` | `GET /api/workspaces/my`, `/api/teams/*`, `/api/teams/{id}/members`, `/api/invitations/*`, `/api/workspaces/{id}/messages` via `workspace-api.ts:51+`; `GET /api/v2/notifications/unread-count` (`notification-api.ts`) |
| `(dashboard)/settings/*` (api-keys, billing, notifications, danger, export, integrations, tools) | `settings/settings-page-content.tsx`, `api-keys-page-content.tsx`, etc. | `/api/v1/usage/summary|timeseries|breakdown` (`usage-api.ts:35-43`), `/api/v2/integrations/oauth` (`oauth-api.ts:5`), `/api/v2/notifications/*` (`notification-api-v2.ts`) |
| `(dashboard)/analytics`, `(dashboard)/dashboard` | `dashboard/page.tsx` → `dashboard/*Widget`, `analytics/page-client.tsx` | `GET /api/v2/dashboard/{path}` (`components/analytics/MissionDashboard.tsx:68`), `GET /api/v2/dashboard/costs` (`cost-api.ts:107`) |
| `(dashboard)/rag` | `rag/page-client.tsx` | `POST /api/v1/rag/context/search` (`rag-api.ts:35`) |
| `(dashboard)/reliability`, `(dashboard)/eval` | `reliability/page-client.tsx`, `eval/page-client.tsx` | `GET /api/v2/evals/runs?limit=50`, `/api/v2/evals/runs/{id}/cases` (`components/dashboard/ReliabilityTab.tsx:75,94`) |
| `(dashboard)/programs`, `programs/[id]`, `programs/new` | `dashboard/programs/page.tsx` | `GET/POST/DELETE/PATCH /api/v2/programs{?qs}` (`programs.ts:138-211`), `/fire`, `/runs`, `/consolidate`, `/learning` |
| `(dashboard)/critiques` | `critiques/page-client.tsx` | `GET /api/v2/critiques`, `/api/v2/critiques/{id}` (`api/critique.ts:98,110`) |
| `(dashboard)/memory-inspector` | `memory-inspector/page-client.tsx` | `GET /api/v2/personal_memory/inspector`, `PATCH/DELETE /api/v2/personal_memory/claims/{id}`, `POST /api/v2/personal_memory/forget` (`api/personal-memory.ts:146-186`) |
| `(dashboard)/admin/*` (users, system, audit, features, maintenance) | `admin/admin-dashboard-content.tsx`, `admin-*/page-content.tsx` | `/api/audit/logs` (`workspace-api.ts:193` comment → `app/api/v1/audit_log.py`), admin user/role endpoints via `lib/sdk` `AdminService`/`RolesService` |
| `agents`, `agents/[...slug]` | `agents/agents-page-content.tsx`, `agents/[...slug]/page-client.tsx` | `/api/domain/agents` (PUBLIC_PREFIX — `api-client.ts:152`), agent detail via `lib/sdk` `AgentRegistryService`/`AgentsService` |
| `tools/browser`, `tools/terminal`, `tools/topology`, `tools/catalog` | `tools/*/page-client.tsx` | `/api/v2/workspaces/{id}/tools/request` (`components/chat/ToolAccessCard.tsx:22`), tool catalog via `lib/sdk` `ToolsService` |
| `integrations`, `integrations/browse` | `integrations/integrations-page-content.tsx` | `/api/v2/integrations/oauth` (`oauth-api.ts:5`), integrations via `lib/sdk` `IntegrationsService` |
| `inbox`, `notifications` | `inbox/page.tsx`, `(dashboard)/notifications/page.tsx` | `GET /api/v2/notifications{?qs}`, `/unread-count`, `/{id}/read`, `/read-all` (`notification-api-v2.ts:104-124`) |
| `profile` | `profile/profile-page-content.tsx` | `GET /api/auth/me` (via `authApi.getCurrentUser`) |
| `invite/[token]` | `invite/[token]/invitation-page-content.tsx` | invitation acceptance via `lib/sdk` `InvitationsService` |
| `blog`, `blog/[slug]`, `case-studies`, `guides` | `blog/page.tsx`, `blog/[slug]/page.tsx` | `GET /api/blog` (PUBLIC_EXACT — `api-client.ts:144`), `GET /api/roadmap` (PUBLIC_EXACT — `api-client.ts:143`) |

> Note: API versioning is **mixed** — v1 (`/api/v1/usage/*`, `/api/v1/rag/*`), v2 (`/api/v2/missions`, `/blueprints`, `/chat`, `/marketplace`, `/programs`, `/evals`, `/critiques`, `/personal_memory`, `/notifications`, `/dashboard/*`, `/integrations/oauth`, `/regression`), and un-versioned (`/api/auth/*`, `/api/workspaces`, `/api/teams`, `/api/invitations`, `/api/domain/agents`, `/api/graphs/*`, `/api/orchestration/queue`). See KEY FINDINGS.

---

## AUTH FLOW

Single source of truth: **Auth.js v5 (NextAuth beta)** in `src/auth.ts`. Backend issues the JWT; NextAuth stores it in its **JWT session cookie** and auto-refreshes via the `jwt` callback.

1. **Login (credentials)** — `auth.ts:243` `authorize()` POSTs `{username_or_email, password}` to `BACKEND_URL/api/auth/login` (`auth.ts:248`). On success it receives `{access_token, refresh_token, user}` and (optionally) forwards the backend's `refresh_token` httpOnly cookie (`auth.ts:256-276`). Returns tokens to the `jwt` callback which persists them (`auth.ts:363-367`).
2. **Login (GitHub/Google)** — `signIn` callback (`auth.ts:307`) exchanges the OAuth provider token for a backend JWT at `POST /api/auth/social/token` (`auth.ts:311`), storing the resulting `access_token`/`refresh_token` on the user object.
3. **Token storage** — tokens live in the **NextAuth JWT** (server-side session, httpOnly cookie). The client obtains the current access token via `getAuthToken()` (`lib/get-auth-token.ts:138`), which uses a 3-layer cache: (1) in-memory `_cachedToken` (30s TTL), (2) **`sessionStorage` key `fm_auth_token`** (`get-auth-token.ts:31`), (3) last-resort `getSession()` network call. It is seeded by `PreviewCookieSync` via `seedTokenCache()`.
   - ⚠️ **AGENTS.md is STALE here**: it describes a Zustand `localStorage` key `fm_tokens` bridge. The real implementation uses `sessionStorage` (`fm_auth_token`) + NextAuth JWT, and `apiClient` reads tokens via `getAuthToken()`, NOT localStorage. (`api-client.ts:5-8` comment: "no localStorage".)
4. **Token refresh** — `jwt` callback (`auth.ts:353`) checks `expiresAt`; if expired calls `refreshAccessToken` (`auth.ts:190`). Tries **v3 cookie-based** `/api/v3/auth/sessions/refresh` first (`auth.ts:78`, reads refresh token from httpOnly cookie), and **falls back to v1** `/api/auth/refresh` (body-based) if v3 returns 404 (`auth.ts:204-207`). Refresh is deduplicated (`_refreshPromise`, `auth.ts:50,192`).
5. **Request attachment** — `apiClient.request()` (`api-client.ts:196`) calls `getAuthToken()` for any `/api/*` path not in the public allowlists (`api-client.ts:142-171`) and sets `Authorization: Bearer <token>` (`api-client.ts:232-234`).
6. **401 handling** — on 401 it invalidates the token cache and retries once (`api-client.ts:250-253`); on repeated 401 it fires a single guarded `signOut()` (`api-client.ts:256-261`, guard `_signOutInProgress` at `:16-29`) to avoid the historic redirect loop (A.3).
7. **Client auth state** — `useAuthStore` (`stores/auth-store.ts`) wraps NextAuth: `login()` calls `signIn("credentials", {redirect:false})` then `refreshUser()` (`auth-store.ts:77-91`); `initialize()` (`auth-store.ts:142`) waits for the token then loads the profile via `getCurrentUser()` (`/api/auth/me`). `AuthProvider` runs `initialize()` on mount (`auth-provider.tsx:29-31`).

---

## KEY SURFACES

### 1. Chat / Agent UI
- **Entry**: `(dashboard)/chat/page.tsx` → `chat/page-client.tsx` (`src/app/[locale]/(dashboard)/chat/page-client.tsx:12`).
- **Core components**: `components/chat/ChatLayout.tsx`, `SSEChat.tsx` (streaming), `ThreadSidebar.tsx` (folders/threads), `CommandQueuePanel.tsx`, `tiles/*` (incl. `MissionStatusTile.tsx` — the Builder↔Chat bridge).
- **State**: `stores/chat-store.ts` (Zustand) is the single source of truth for messages/threads.
- **Backend endpoints**: `/api/v2/chat/threads`, `/api/v2/chat/folders`, `/api/v2/chat/messages/{id}/react`, `POST /api/v2/chat/threads/{id}/title` (see ROUTE→API MAP). Real-time streaming rides the same `apiClient` fetch (SSE), not the socket.
- **Handoff seam**: `?missionId=<id>` in the URL triggers a pre-wired Mission Status tile (`chat/page-client.tsx:21-42`), enabling one-click Run→Chat handoff from the builder.

### 2. Builder / Blueprint Editor
- **Entry**: `(dashboard)/missions/builder/page.tsx` → `page-client.tsx` (`src/app/[locale]/(dashboard)/missions/builder/page-client.tsx`) → `components/mission-builder/FlowEditor.tsx`.
- **Core**: React Flow 12 (`@xyflow/react`). Node types in `components/mission-builder/nodes/` (Router, Transform, SubFlow, Loop, Approval, Webhook, Plugin, Parallel, Delay, LogEvent, Custom). `PropertiesPanel.tsx`, `VersionHistoryPanel.tsx`, `TemplatePicker.tsx`, `ExportImportDialog.tsx`.
- **Backend endpoints**: `GET /api/v2/blueprints/{id}`, `POST /api/v2/blueprints/`, `PATCH /api/v2/blueprints/{id}`, `POST /api/v2/blueprints/{id}/run`, `POST /api/graphs/{id}/resume/{execId}`, `GET /api/graphs/compare/{a}/{b}` (`FlowEditor.tsx:1031-1401`, `lib/api/runs.ts:133-201`).
- **Save flow**: `FlowEditor` builds a payload and POSTs/PATCHes blueprints (`FlowEditor.tsx:1048-1050`); blueprint→mission conversion via `blueprintToMissionFlow`.

### 3. Marketplace
- **Entry**: `(dashboard)/marketplace/page.tsx` → `marketplace-page-content.tsx` (`src/app/[locale]/(dashboard)/marketplace/marketplace-page-content.tsx:21`) + sub-pages `listing-detail`, `create-listing`, `my-listings`, `my-installed`.
- **Core**: `components/marketplace/listing-card.tsx`, `featured-carousel.tsx`, `listing-detail-content.tsx`, `create-listing-content.tsx`.
- **Backend endpoints**: `GET /api/v2/marketplace/listings{?qs}`, `/featured`, `/categories`, `POST/DELETE /api/v2/marketplace/listings/{slug}`, `/{slug}/install`, `/{slug}/reviews` (`lib/marketplace-api.ts:112-267`). All calls go through `apiClient` (no React Query).

### 4. Dashboard
- **Entry**: `dashboard/page.tsx` (RSC) → `DashboardServerContent` (`src/app/[locale]/dashboard/page.tsx:19`) composing widgets: `MissionsWidget`, `UsageStatsWidget`, `RunHistoryWidget`, `GettingStartedChecklist`, `QuickActions`, `RecentActivity` (`dashboard/page.tsx:22-29`).
- **Core**: `components/dashboard/*Widget.tsx`, `analytics/page-client.tsx` + `components/analytics/MissionDashboard.tsx`.
- **Backend endpoints**: `GET /api/v2/dashboard/{path}` (`MissionDashboard.tsx:68`), `GET /api/v2/dashboard/costs` (`cost-api.ts:107`), `GET /api/v1/usage/summary|timeseries|breakdown` (`usage-api.ts:35-43`).

### 5. Workspace / Team Management
- **Entry**: `(dashboard)/team/page.tsx` → `team/team-management-page-content.tsx` (2145-line client component, `src/app/[locale]/(dashboard)/team/team-management-page-content.tsx:1`).
- **Core**: team CRUD, member management, invitations, RBAC, plus a comms hub (DM, activity feed, @mentions). Uses `useWorkspaceStore` (`stores/workspace-store.ts:18`) and the **WebSocket** context for live messages (`team-management-page-content.tsx:28`).
- **Backend endpoints**: `GET /api/workspaces/my`, `/api/teams/*`, `/api/teams/{id}/members`, `/api/invitations/*`, `/api/workspaces/{id}/messages` (all via `lib/workspace-api.ts`). Workspace scoping is enforced by sending the `X-Workspace-Id` header (`workspace-api.ts:30-33`); backend silently falls back to primary workspace if omitted — a documented security axis.
- **Real-time**: `lib/websocket.ts` (`getWebSocket()`) opens a socket.io connection to `NEXT_PUBLIC_WS_URL` with `auth:{token}` (`websocket.ts:18-27`), `path:/ws/socket.io`.

---

## KEY FINDINGS

1. **Auth storage model diverges from AGENTS.md.** Real implementation stores backend JWT in the **NextAuth JWT (httpOnly cookie)** + a `sessionStorage` key `fm_auth_token` (`get-auth-token.ts:31`), read via `getAuthToken()` — NOT the `localStorage` `fm_tokens` Zustand bridge AGENTS.md describes. `api-client.ts:5-8` explicitly states "no localStorage". *Update AGENTS.md.*
2. **Centralized fetch layer exists but is bypassed by React Query.** `apiClient` (`api-client.ts:175`) is the single network primitive (auth injection, 401-retry, v2 envelope auto-unwrap at `:276-279`, `ApiError` w/ `trace_id` at `:50-68`). However `QueryClientProvider` is mounted (`providers.tsx:14`) yet the codebase overwhelmingly calls `apiClient` inside `useEffect` rather than `useQuery` — so the configured cache/retry (30s staleTime, 3 retries) mostly sits unused. No SWR (0 matches).
3. **Mixed API versioning across the backend surface.** v1 (`/api/v1/usage/*`, `/api/v1/rag/*`), v2 (`/api/v2/missions`, `/blueprints`, `/chat`, `/marketplace`, `/programs`, `/evals`, `/critiques`, `/personal_memory`, `/notifications`, `/dashboard/*`, `/regression`, `/integrations/oauth`), and **un-versioned** (`/api/auth/*`, `/api/workspaces`, `/api/teams`, `/api/invitations`, `/api/domain/agents`, `/api/graphs/*`, `/api/orchestration/queue`). Two API styles coexist: hand-written `lib/*-api.ts` modules and a generated `lib/sdk/` OpenAPI client (`lib/sdk/services/*`).
4. **Public-path auth allowlist has explicit security semantics.** `api-client.ts:142-171` splits public routes into `PUBLIC_EXACT_PATHS` (e.g. `/api/roadmap`, `/api/blog` — exact only, children require auth) vs `PUBLIC_PREFIX_PATHS` (whole trees, e.g. `/api/auth/login`, `/api/domain/agents`). This was a deliberate fix for CVE-like over-broad prefix matching (see comment §CODEBASE-ANALYSIS-FOLLOWUP-PLAN-2026-07-08 §C).
5. **Token refresh is resilient-by-design.** `auth.ts` implements v3 cookie-based refresh (`/api/v3/auth/sessions/refresh`, `auth.ts:78`) with transparent v1 fallback (`/api/auth/refresh`, `auth.ts:138`) and deduplication (`auth.ts:50,192`) — specifically to survive WireGuard tunnel body corruption. Refresh failures clear `refreshToken` to force re-auth (`auth.ts:394-396`).
6. **Sign-out loop guard is load-bearing.** `_signOutInProgress` (`api-client.ts:16-29`) prevents the A.3 redirect loop where every concurrent 401 fired its own `signOut()`. Also reset on `pageshow` (`:31-33`).
7. **Builder↔Chat handoff is a first-class seam.** `FlowEditor` navigates to `/chat?missionId=<id>`; `chat/page-client.tsx:21-42` de-dupes a `mission_status` canvas tile. The tile itself reads `GET /api/v2/missions/{id}/status` (`MissionStatusTile.tsx:65`). This closes the Run→Chat loop (Phase B/C).
8. **Stale-token cache poisoning risk is mitigated.** `apiClient` invalidates the token cache on 401 and retries once (`api-client.ts:250-253`); `invalidateTokenCache()` (`get-auth-token.ts:125`) clears in-memory + `sessionStorage` layers. But `auth-store.refreshUser()` 401 only clears local Zustand state without re-syncing from `/api/auth/session` — the AGENTS.md "stale-token trap" fix is **partially** applied (compare `auth-store.ts:108-118` vs AGENTS.md guidance).
9. **Routing uses Next.js route groups.** `(auth)` and `(dashboard)` are URL-less route groups; all user-facing routes sit under `[locale]` (i18n). Page architecture is consistently `page.tsx` (RSC shell) → `*-page-content.tsx` / `page-client.tsx` (client). Public/legal pages (`pricing`, `about`, `privacy`, `terms`, `security`, `dpa`, `careers`, `contact`, `status`, `roadmap`, `blog`, `case-studies`, `guides`) are mostly static/marketing.
10. **Real-time uses socket.io, not the chat SSE path.** Live team DMs/activity ride `lib/websocket.ts` (`getWebSocket()`), while chat message streaming uses `apiClient` SSE (`SSEChat.tsx`). Two distinct real-time transports in the app.
11. **Build/tooling**: scripts in `package.json:5-15` — `dev` (next dev), `build` (next build, standalone), `lint` (eslint src), `test` (vitest run), `test:watch`, `test:e2e` (playwright), `storybook`. ESLint uses flat config `eslint.config.mjs` (`eslint-config-next` core-web-vitals + typescript). TS `strict:true`, path alias `@/*`→`src/*` (`tsconfig.json:11,25-28`). Vitest 4 + Playwright 1.60 for tests; Storybook 10 present. React Compiler (`babel-plugin-react-compiler`) and `react-scan` are in devDeps (perf tooling).

---

*Analysis generated read-only. No files committed, pushed, or edited in source. Output written to `/opt/flowmanner/.kg-analysis/frontend-architecture.md`.*
