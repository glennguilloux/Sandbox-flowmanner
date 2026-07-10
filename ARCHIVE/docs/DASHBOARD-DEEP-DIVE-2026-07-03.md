# FlowManner HIL Dashboard — Deep Dive & Improvement Roadmap

**Date:** July 3, 2026
**Project:** `flowmanner-dashboard-HIL` (`/home/glenn/flowmanner-dashboard-HIL/`)
**Status:** MC Port complete (11 phases, exit audit 2026-07-03). This document supersedes the DeepSeek plan and exit audit roadmap with a unified, prioritized improvement plan.

---

## 0. What the Dashboard Is

The HIL Dashboard is a **Human-in-the-Loop operational control surface** for FlowManner. It runs on the homelab at `http://localhost:3000` (WireGuard LAN only) and provides:

- **Tactic approval gates** — agents propose actions; high-risk ones pause for human review
- **PR management** — sync GitHub PRs as tactics, view CI status, approve/merge from the UI
- **Mission monitoring** — live SSE feed of FlowManner mission execution
- **Agent orchestration** — Hermes Agent management, heartbeats, skill assignment
- **System health** — PostgreSQL, LLM, WireGuard watchdog, model swap daemon
- **Goal/skill/strategy management** — Eisenhower matrix, kanban, brain dump triage
- **Executive briefing** — AI-generated daily summary (local LLM or OpenRouter)

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Framework | Next.js 16 (App Router), React 19 |
| Database | PostgreSQL 15, Drizzle ORM 0.45 (`hil_ops` schema, isolated) |
| Styling | Tailwind CSS v4, lucide-react icons |
| State | No global state library — per-component `useState` + polling |
| Data fetching | Server component `async/await` + client-side `apiFetch` + SSE `EventSource` |
| Package manager | pnpm |
| CI | GitHub Actions (typecheck + lint + build) |
| Auth | Bearer token (`HIL_AUTH_SECRET`) on API routes — no middleware |

### Scale

| Metric | Count |
|--------|-------|
| Source files (src/) | 189 |
| Lines of code (src/) | 14,371 |
| Pages | 20 |
| API routes | 56 |
| Components | 70 |
| Lib modules | 33 |
| DB tables | 14 |
| DB enums | 16 |
| Tests in src/ | **0** |
| Tests in mission-control/ | 5 files |

---

## 1. Architecture Assessment

### What Works Well

1. **Schema isolation is excellent.** The `hil_ops` Postgres schema is fully isolated from the FlowManner `public` schema. Drizzle config enforces `schemaFilter: ["hil_ops"]` — no accidental cross-schema writes.

2. **Tactic-as-unified-hub is a smart pattern.** PRs, inbox items, and agent proposals all map to `tactics` with a `source` field. The approval flow branches by source to execute the right side effect (gh CLI, DB update, etc.). This is clean and extensible.

3. **SectionErrorBoundary is the right granularity.** Every dashboard panel is wrapped in an error boundary — one failing component doesn't crash the page. This is defensive and correct for a dashboard with 15+ independent panels.

4. **Event journal is immutable.** `tactic_events` is an append-only audit trail. This is the right pattern for operational accountability.

5. **Gate logic is centralized.** `gate.ts` contains the single `needsGate()` function with clear thresholds (confidence < 70, risk = high, requiresHumanApproval). One place to change the rules.

6. **`gh` CLI integration is pragmatic.** Instead of importing Octokit and managing tokens, the dashboard shells out to `gh` which uses the user's existing keyring auth. Simple, no extra deps, works on the homelab.

7. **Model swap panel is well-designed.** State machine (idle → confirming → activating → polling), progress feedback, error handling. This is the most polished component in the codebase.

### What Needs Work

#### A1. Zero Test Coverage in src/

**The problem:** Not a single test file exists in `src/`. The 5 test files in `mission-control/` are for the ported sub-project, not the dashboard itself. 14,371 LOC of untested code.

**What to do:**
- Add unit tests for `gate.ts` (the approval gate logic — this is security-critical)
- Add unit tests for `github.ts` (PR parsing, risk calculation)
- Add unit tests for `review.ts` (LLM response parsing — JSON extraction is fragile)
- Add integration tests for key API routes: `POST /api/tactics`, `POST /api/tactics/[id]/approve`, `POST /api/prs/sync`
- Add a Playwright E2E smoke test: load dashboard → see panels → approve a tactic

**Effort:** M | **Impact:** High | **Risk if not done:** High (silent regressions)

#### A2. No Authentication Middleware

**The problem:** The dashboard has no Next.js middleware. API routes check a Bearer token (`HIL_AUTH_SECRET`), but pages are server-rendered with no auth check. Anyone on the WireGuard LAN can view the dashboard and all its data. The Bearer token is also optional in dev mode (`if (!secret) return null` — auth is silently disabled).

**What to do:**
- Add Next.js middleware that protects all routes except `/help` and `/api/health`
- Use a simple session cookie (JWT signed with `HIL_AUTH_SECRET`) set via a login page
- Or: since this is LAN-only, at minimum enforce that `HIL_AUTH_SECRET` is set in production and fail closed if not
- Add a basic login page (password → set cookie) — doesn't need full OAuth

**Effort:** S | **Impact:** High | **Risk if not done:** Medium (LAN-only mitigates, but WireGuard peers could access)

#### A3. Raw SQL in fm-inbox.ts

**The problem:** `src/lib/fm-inbox.ts` uses raw SQL strings to update `public.inbox_items` in the FlowManner database. This crosses the schema isolation boundary and uses string interpolation for SQL.

**What to do:**
- Use Drizzle's query builder or parameterized queries instead of raw string SQL
- Consider whether the dashboard should write to the `public` schema at all — maybe the FM backend should expose an API endpoint for inbox resolution instead
- If raw SQL is unavoidable, use parameterized queries (`db.execute(sql\`UPDATE ... WHERE id = ${id}\`)`)

**Effort:** S | **Impact:** Medium | **Risk if not done:** Medium (SQL injection if inputs aren't sanitized)

#### A4. No Input Validation on API Routes

**The problem:** Most API routes read `request.json()` and use the fields directly without validation. There's no Zod schema, no Pydantic equivalent, no runtime type checking. A malformed request body could cause runtime errors or database corruption.

**What to do:**
- Add Zod schemas for all mutation endpoints (POST/PATCH/DELETE)
- Validate request bodies before passing to DB operations
- Return 400 with field-level errors for invalid input
- Start with the highest-risk routes: `/api/tactics` (POST), `/api/tactics/[id]/approve` (POST), `/api/prs/sync` (POST)

**Effort:** M | **Impact:** Medium | **Risk if not done:** Medium (runtime errors, bad data)

#### A5. Data Fetching is Fragmented Across 4 Patterns

**The problem:**
1. Server components: `async` function + `getDashboardData()` (direct DB access)
2. Client polling: `usePolling()` hook + `apiFetch()` (30s interval)
3. SSE: `EventSource` for mission live feed
4. Direct `fetch()` in `useEffect` for one-off loads (e.g., `ExecutiveBriefing`, `ModelSwapPanel`)

No SWR, no React Query, no caching layer. Every page load hits the database. Every panel polls independently. No deduplication of requests.

**What to do:**
- Standardize on SWR for client-side data fetching (lightweight, built-in dedup + caching)
- Keep server component fetching for initial page load (SSR data)
- Keep SSE for real-time mission feed (SWR doesn't replace streaming)
- Migrate `usePolling` to use SWR's `refreshInterval` option
- Migrate direct `fetch()` in `useEffect` to SWR hooks

**Effort:** M | **Impact:** Medium | **Risk if not done:** Low (works, but inefficient and inconsistent)

#### A6. Large Component Files Need Splitting

**The problem:** Several components are 500+ LOC:
- `hermes-panel.tsx` (597 LOC)
- `hermes-agents-panel.tsx` (538 LOC)
- `model-swap-panel.tsx` (521 LOC)
- `wg-watchdog-panel.tsx` (516 LOC)
- `seed.ts` (685 LOC)

These are doing too much — likely mixing data fetching, state management, and rendering.

**What to do:**
- Extract sub-components (e.g., `HermesPanel` → `HermesHeader` + `HermesSessionList` + `HermesJobQueue`)
- Extract custom hooks (e.g., `useHermesData()`, `useModelSwap()`)
- Target: no component > 300 LOC

**Effort:** M | **Impact:** Low | **Risk if not done:** Low (maintainability degrades slowly)

#### A7. `mission-control/` Directory is Untracked

**The problem:** The `mission-control/` directory is a full Next.js sub-project (with its own `package.json`, `src/`, tests, daemon) that's untracked in git. It's excluded from `tsconfig.json`. It's unclear if this is:
- A reference implementation that was ported into `src/` (and should be deleted)
- A separate project that should be its own repo
- A work-in-progress that will be integrated later

**What to do:**
- If ported: delete `mission-control/` and commit the deletion
- If separate: move to its own repo and remove from this project
- If WIP: add it to `.gitignore` or commit it with a clear README

**Effort:** S | **Impact:** Low | **Risk if not done:** Low (confusion, bloated repo)

---

## 2. Security Assessment

### S1. Bearer Token Auth is Weak

**What exists:** API routes check `Authorization: Bearer <token>` against `HIL_AUTH_SECRET`. In dev mode, if the secret is unset, auth is silently bypassed.

**What's wrong:**
- No token rotation
- No expiry
- Single shared secret (no per-user auth)
- Silent bypass in dev mode could leak to production if misconfigured
- No rate limiting on any endpoint

**What to do:**
- Fail closed if `HIL_AUTH_SECRET` is unset in production (`NODE_ENV=production`)
- Add rate limiting (at minimum, prevent brute-force on the approval endpoint)
- Consider session-based auth with expiry for the UI

**Effort:** S | **Impact:** Medium | **Risk if not done:** Medium

### S2. GitHub CLI Shell Execution

**What exists:** `lib/github.ts` executes `gh pr list --json ...` via `child_process.execSync`. The `gh` CLI uses the user's keyring credentials.

**What's wrong:**
- Shell injection risk if any argument contains special characters (repo name, PR title)
- `execSync` blocks the event loop — synchronous I/O in an async framework
- No timeout on `gh` commands — a hung `gh` process blocks the dashboard

**What to do:**
- Use `execFile` (not `exec`) to avoid shell interpretation
- Use the async `promisify(execFile)` version instead of `execSync`
- Add timeouts (30s) to all `gh` commands
- Sanitize all arguments (repo name, PR numbers should be integers)
- Or: migrate to Octokit with a dedicated GitHub token (more standard, async, no shell)

**Effort:** S | **Impact:** Medium | **Risk if not done:** Medium (shell injection, event loop blocking)

### S3. No Security Headers

**What exists:** `next.config.ts` is empty — no `headers()`, no CSP, no `X-Frame-Options`.

**What to do:**
- Add basic security headers in `next.config.ts`:
  ```typescript
  headers: () => [{
    source: '/(.*)',
    headers: [
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    ],
  }],
  ```

**Effort:** S | **Impact:** Low | **Risk if not done:** Low (LAN-only mitigates)

### S4. No CORS Configuration

**What exists:** No CORS headers on API routes. The dashboard is same-origin (served by Next.js), so this is mostly fine. But if any external tool tries to hit the API, it'll fail silently.

**What to do:**
- Add explicit CORS headers for API routes (allow same origin, deny others)
- Or use Next.js middleware to add CORS headers for `/api/*`

**Effort:** S | **Impact:** Low | **Risk if not done:** Low

---

## 3. UX & Design Assessment

### U1. No Loading States Strategy

**The problem:** Server components fetch data with `async/await` — the page doesn't render until all data is loaded. With 15+ panels on the dashboard, a single slow query delays the entire page. Client components use `usePolling` but loading states are inconsistent (some show nothing, some show a spinner).

**What to do:**
- Add `loading.tsx` files for route segments (Next.js Suspense streaming)
- Or: convert the main dashboard to streaming with `Suspense` boundaries per panel
- Add skeleton components (a `SkeletonCard` already exists — use it everywhere)
- Show skeletons during initial load, show stale data during refresh (SWR does this automatically)

**Effort:** M | **Impact:** High | **Risk if not done:** Medium (perceived performance is poor)

### U2. No Keyboard Shortcuts

**The problem:** The dashboard is an operational tool used daily. Power users want keyboard shortcuts. None exist. A `KeyboardHelp` component exists but isn't wired.

**What to do:**
- Add a global keyboard shortcut handler (`useHotkeys` or simple `keydown` listener)
- Key shortcuts:
  - `/` — focus search
  - `g` then `d` — go to dashboard
  - `g` then `p` — go to PRs
  - `g` then `t` — go to tactics
  - `a` — approve focused tactic
  - `r` — reject focused tactic
  - `?` — show keyboard help
- Wire the existing `KeyboardHelp` component

**Effort:** S | **Impact:** Medium | **Risk if not done:** Low

### U3. Dark Mode Incomplete

**The problem:** A `ThemeToggle` component exists but dark mode support is inconsistent across components. Tailwind v4 has built-in dark mode support, but many components use hardcoded color classes (e.g., `bg-white` instead of `bg-white dark:bg-zinc-900`).

**What to do:**
- Audit all components for hardcoded color classes
- Replace with dark-mode-aware classes (`bg-white dark:bg-zinc-900`, `text-zinc-900 dark:text-zinc-100`)
- Test dark mode across all 20 pages
- Consider using CSS variables for theme colors instead of Tailwind dark: prefixes

**Effort:** M | **Impact:** Low | **Risk if not done:** Low (cosmetic)

### U4. No Empty States

**The problem:** When a panel has no data (no tactics, no PRs, no missions), it shows nothing or a blank card. No "No items yet" message, no call to action.

**What to do:**
- Add empty state illustrations/messages to every panel
- Include a call to action (e.g., "No PRs to review. Click 'Sync PRs' to fetch from GitHub.")
- Use a consistent `EmptyState` component

**Effort:** S | **Impact:** Medium | **Risk if not done:** Low

### U5. No Toast/Notification System

**The problem:** When an API call succeeds or fails, feedback is inconsistent. The approval gate shows inline status, but other actions (PR sync, model swap) have varying feedback mechanisms. No centralized toast system.

**What to do:**
- Add `sonner` (or `react-hot-toast`) as the toast library
- Wrap all API calls with success/error toasts
- Consistent patterns: green toast on success, red toast on error with retry action

**Effort:** S | **Impact:** Medium | **Risk if not done:** Low

### U6. Mobile Responsiveness is Minimal

**The problem:** The sidebar has a mobile drawer, but the dashboard's 12-column grid layout doesn't adapt well to small screens. Panels are cramped or overflow on mobile.

**What to do:**
- Test all 20 pages on mobile viewport (375px width)
- Adjust grid layouts: single column on mobile, 2 columns on tablet, 12 columns on desktop
- Hide non-essential panels on mobile (WG watchdog, usage charts, etc.)
- Consider a "mobile mode" that shows only the approval queue + PRs

**Effort:** M | **Impact:** Low | **Risk if not done:** Low (LAN-only, likely used on desktop)

---

## 4. Performance Assessment

### P1. No Caching — Everything is force-dynamic

**The problem:** Every page and API route uses `export const dynamic = "force-dynamic"`. This means every request hits the database. No caching at any layer.

**What to do:**
- Cache relatively static data (agents list, skills, strategies) with `unstable_cache` or SWR
- Cache GitHub PR data with a 60-second TTL (PRs don't change every second)
- Keep mission live feed and health checks as force-dynamic
- Add `Cache-Control` headers to API responses where appropriate

**Effort:** S | **Impact:** Medium | **Risk if not done:** Low (works, but unnecessary DB load)

### P2. Synchronous Shell Commands Block the Event Loop

**The problem:** `lib/github.ts` uses `execSync` for all `gh` commands. This blocks the Node.js event loop during every PR sync, PR approval, and PR merge. On the homelab, `gh` commands can take 2-5 seconds each.

**What to do:**
- Replace `execSync` with `promisify(execFile)` (async)
- Or migrate to `@octokit/rest` with a dedicated token

**Effort:** S | **Impact:** Medium | **Risk if not done:** Medium (UI freezes during gh calls)

### P3. No Database Connection Pooling Config

**The problem:** `src/db/index.ts` creates a Drizzle instance with a `pg.Pool`. The pool configuration (max connections, idle timeout) isn't visible in the summary. With 56 API routes and 15+ polling panels, connection exhaustion is possible.

**What to do:**
- Verify pool config: `max: 10`, `idleTimeoutMillis: 30000`
- Add connection health checks
- Monitor pool stats (active/idle/waiting connections)

**Effort:** S | **Impact:** Low | **Risk if not done:** Low

### P4. Polling Storms

**The problem:** Each panel with `usePolling` polls independently at 30s intervals. With 15+ panels, that's 15+ API calls every 30 seconds. No coordination, no dedup, no backoff.

**What to do:**
- Migrate to SWR with shared cache keys (panels requesting the same data share one request)
- Or: add a centralized polling coordinator that batches requests
- Add exponential backoff on errors (don't keep polling at 30s when the backend is down)

**Effort:** M | **Impact:** Medium | **Risk if not done:** Low (works, but wasteful)

---

## 5. Code Quality Assessment

### C1. No Prettier Configuration

**The exists:** ESLint is configured but no Prettier. Code formatting is inconsistent across files.

**What to do:**
- Add Prettier with `prettier-plugin-tailwindcss` for class sorting
- Add `format` script to package.json
- Run `prettier --write` on the codebase

**Effort:** S | **Impact:** Low | **Risk if not done:** Low

### C2. No Pre-commit Hooks

**The problem:** No husky, no lint-staged, no pre-commit hooks. CI catches issues but only after push.

**What to do:**
- Add husky + lint-staged: run `eslint --fix` and `prettier --write` on staged files
- Optional: run `tsc --noEmit` on staged files (slower but catches type errors early)

**Effort:** S | **Impact:** Low | **Risk if not done:** Low

### C3. TypeScript Strict Mode is Good but Unused Types Exist

**The problem:** `tsconfig.json` has `"strict": true` which is excellent. But the exit audit mentions "ongoing minor typecheck errors" — there are likely `any` types or unused imports.

**What to do:**
- Run `tsc --noEmit` and fix all remaining errors
- Add `noUnusedLocals` and `noUnusedParameters` to tsconfig
- Audit for `any` types and replace with proper types

**Effort:** S | **Impact:** Low | **Risk if not done:** Low

### C4. No Environment Variable Validation

**The problem:** `.env.example` lists env vars but there's no runtime validation. If a required env var is missing, the app fails with a cryptic error at runtime.

**What to do:**
- Add `@t3-oss/env-nextjs` or `zod` to validate env vars at startup
- Fail fast with a clear error message if required vars are missing
- Document which vars are required vs optional

**Effort:** S | **Impact:** Medium | **Risk if not done:** Low

---

## 6. Feature Roadmap (Building on Exit Audit Tiers)

The exit audit already defines a 5-tier roadmap. This section refines it with specific tasks and effort estimates.

### Tier 1: Real Data Integration (Highest Value)

| # | Task | Effort | Impact | Status |
|---|------|--------|--------|--------|
| T1.1 | **PR sync + CI rollup** — Wire `prs/sync` to run on a cron, show CI status badges on tactic cards, auto-create tactics from new PRs | M | High | Partially built (sync exists, CI rollup exists, no cron) |
| T1.2 | **Decisions → real GitHub actions** — When a decision is made in the UI, execute the real `gh` command (approve, merge, comment) | S | High | Partially built (approve route exists, needs wiring to decisions page) |
| T1.3 | **Inbox sync polling** — Auto-poll FM backend inbox every 60s, create tactics from new interrupts | S | High | Built (sync route exists, no auto-poll) |
| T1.4 | **Mission live feed real connection** — Connect SSE to real FM backend `/api/v1/missions/{id}/stream` | S | High | Built (EventSource exists, needs real URL) |

### Tier 2: Operational Maturity

| # | Task | Effort | Impact | Status |
|---|------|--------|--------|--------|
| T2.1 | **Add auth middleware** — Protect all routes, fail closed in production | S | High | Not started |
| T2.2 | **Add Zod input validation** on all mutation API routes | M | Medium | Not started |
| T2.3 | **Fix raw SQL in fm-inbox.ts** — Use parameterized queries | S | Medium | Not started |
| T2.4 | **Async GitHub commands** — Replace `execSync` with async `execFile` | S | Medium | Not started |
| T2.5 | **Typecheck cleanup** — Fix all remaining TS errors, add `noUnusedLocals` | S | Low | Not started |
| T2.6 | **Env var validation** — Validate at startup with zod | S | Medium | Not started |
| T2.7 | **Pre-commit hooks** — husky + lint-staged | S | Low | Not started |

### Tier 3: AI/LLM Features

| # | Task | Effort | Impact | Status |
|---|------|--------|--------|--------|
| T3.1 | **Background LLM reviewer** — Auto-score tactic risk/confidence on creation, re-score on CI status change | M | High | `review.ts` exists, no auto-trigger |
| T3.2 | **PR diff analysis** — LLM analyzes PR diff and posts review comment via `gh` | M | Medium | Not started |
| T3.3 | **Smart executive briefing** — LLM generates daily summary from tactic/PR/mission data (not just a prompt template) | M | Medium | `briefing.ts` exists, needs smarter prompt |
| T3.4 | **Batch review scoring** — Score all pending tactics in one LLM call | S | Medium | `review/score/batch` route exists, needs wiring |

### Tier 4: UX Polish

| # | Task | Effort | Impact | Status |
|---|------|--------|--------|--------|
| T4.1 | **Loading states** — `loading.tsx` + Suspense streaming + skeleton cards | M | High | Not started |
| T4.2 | **Toast notifications** — `sonner` for all API call feedback | S | Medium | Not started |
| T4.3 | **Empty states** — Consistent `EmptyState` component for all panels | S | Medium | Not started |
| T4.4 | **Keyboard shortcuts** — Global hotkeys + wire `KeyboardHelp` | S | Medium | Component exists, not wired |
| T4.5 | **Dark mode audit** — Fix hardcoded colors across all components | M | Low | `ThemeToggle` exists, inconsistent |
| T4.6 | **Mobile responsiveness** — Single-column layout on mobile | M | Low | Sidebar has drawer, rest is desktop-only |
| T4.7 | **SWR migration** — Replace `usePolling` + raw `fetch` with SWR | M | Medium | Not started |

### Tier 5: Testing & CI

| # | Task | Effort | Impact | Status |
|---|------|--------|--------|--------|
| T5.1 | **Unit tests for gate.ts** — Test all gate threshold combinations | S | High | Not started |
| T5.2 | **Unit tests for github.ts** — Test PR parsing, risk calculation | S | Medium | Not started |
| T5.3 | **Unit tests for review.ts** — Test LLM JSON parsing edge cases | S | Medium | Not started |
| T5.4 | **Integration tests for API routes** — Test tactic CRUD, approval flow, PR sync | M | High | Not started |
| T5.5 | **Playwright E2E smoke test** — Load dashboard, see panels, approve tactic | S | Medium | Not started |
| T5.6 | **Add tests to CI** — Run vitest + playwright in GitHub Actions | S | Medium | Not started |
| T5.7 | **Add test for approval idempotency** — Verify the 10s lock works | S | Medium | Not started |

### Tier 6: Cleanup & Hygiene

| # | Task | Effort | Impact | Status |
|---|------|--------|--------|--------|
| T6.1 | **Resolve mission-control/ directory** — Delete, move, or gitignore | S | Low | Untracked |
| T6.2 | **Split large components** — Break 500+ LOC files into sub-components + hooks | M | Low | Not started |
| T6.3 | **Add security headers** — Configure `next.config.ts` | S | Low | Not started |
| T6.4 | **Add Prettier** — Format the codebase consistently | S | Low | Not started |
| T6.5 | **Cache static data** — Agents, skills, strategies with 60s TTL | S | Medium | Not started |
| T6.6 | **Add rate limiting** — At minimum on auth + approval endpoints | S | Medium | Not started |

---

## 7. Prioritized Action Plan

Ordered by impact × urgency ÷ effort:

| Priority | Item | Tier | Effort | Impact |
|----------|------|------|--------|--------|
| **P0** | Add auth middleware (T2.1) | Security | S | High |
| **P0** | Fix raw SQL in fm-inbox.ts (T2.3) | Security | S | Medium |
| **P1** | Async GitHub commands (T2.4) | Performance | S | Medium |
| **P1** | Unit tests for gate.ts (T5.1) | Testing | S | High |
| **P1** | Wire PR sync cron + CI badges (T1.1) | Data | M | High |
| **P1** | Auto-poll inbox sync (T1.3) | Data | S | High |
| **P1** | Loading states + skeletons (T4.1) | UX | M | High |
| **P1** | Toast notifications (T4.2) | UX | S | Medium |
| **P2** | Zod input validation (T2.2) | Security | M | Medium |
| **P2** | Env var validation (T2.6) | Ops | S | Medium |
| **P2** | Background LLM reviewer (T3.1) | AI | M | High |
| **P2** | SWR migration (T4.7) | Performance | M | Medium |
| **P2** | Resolve mission-control/ (T6.1) | Hygiene | S | Low |
| **P2** | Typecheck cleanup (T2.5) | Quality | S | Low |
| **P2** | Empty states (T4.3) | UX | S | Medium |
| **P3** | Integration tests for API routes (T5.4) | Testing | M | High |
| **P3** | Keyboard shortcuts (T4.4) | UX | S | Medium |
| **P3** | Mission live feed real connection (T1.4) | Data | S | High |
| **P3** | Decisions → real GitHub actions (T1.2) | Data | S | High |
| **P3** | Cache static data (T6.5) | Performance | S | Medium |
| **P3** | Pre-commit hooks (T2.7) | Quality | S | Low |
| **P3** | Security headers (T6.3) | Security | S | Low |
| **P4** | Playwright E2E smoke test (T5.5) | Testing | S | Medium |
| **P4** | PR diff analysis (T3.2) | AI | M | Medium |
| **P4** | Smart executive briefing (T3.3) | AI | M | Medium |
| **P4** | Split large components (T6.2) | Quality | M | Low |
| **P4** | Prettier + format (T6.4) | Quality | S | Low |
| **P4** | Dark mode audit (T4.5) | UX | M | Low |
| **P4** | Rate limiting (T6.6) | Security | S | Medium |
| **P5** | Mobile responsiveness (T4.6) | UX | M | Low |
| **P5** | Batch review scoring (T3.4) | AI | S | Medium |
| **P5** | Add tests to CI (T5.6) | Testing | S | Medium |

---

## 8. What to Cut

| Item | Justification |
|------|---------------|
| `mission-control/` directory (if ported) | Already ported into `src/`. 500+ files of dead code. Delete or move to separate repo. |
| `Example/` directory | Template/scaffold + ZIP archives. Not referenced by the project. Delete. |
| `OpusDocs/competitor.txt` | API.market analysis — not actionable for the dashboard. Move to main FM docs if needed. |
| `.crush/` directory | Unknown tool artifacts. Verify if needed, otherwise gitignore. |
| `seed.ts` (685 LOC) | Demo data seeder. Keep until real data integration is complete, then remove. |
| `SeedBanner` component | Only relevant while using seed data. Remove once real data is the default. |
| `SimulateProposal` component | Demo-only — simulates an agent proposing a tactic. Remove once real agents propose. |

---

## 9. Open Questions for Glenn

1. **Should the dashboard have user authentication?** It's LAN-only (WireGuard), but multiple people could be on the LAN. Is a simple password login sufficient, or do you need multi-user with roles?
Not for the minute my LAN is secure (firewall closes port 3000!)
2. **Should `mission-control/` be committed or deleted?** It's untracked and excluded from tsconfig. Is it reference code, a future project, or leftover from the port?
deleted
3. **Is the `gh` CLI approach working well?** Or would you prefer migrating to Octokit with a dedicated GitHub token (async, no shell exec, more standard)?
YES https://github.com/octokit
4. **Should the dashboard write to the FM `public` schema?** The inbox resolution currently writes to `public.inbox_items` via raw SQL. Should this go through the FM backend API instead?
Yes of course
5. **How important is dark mode?** The toggle exists but coverage is inconsistent. Is this a priority or a nice-to-have?
I only want dark mode
6. **Should the executive briefing use the local LLM or OpenRouter?** The component supports both. Which is the preferred default?
OpenRouter or deepseek or local would be nice to have a choice!
7. **What's the target refresh rate for real-time data?** Currently 30s polling. Is that sufficient, or do you need SSE/WebSocket for everything?
No keep it simple only when I am on the page "refresh"
8. **Should the dashboard be deployable outside the homelab?** Currently it requires LAN access to Postgres, `gh` CLI, LLM, Hermes, and FM backend. Is it always homelab-only?
homelab-only
---

## 10. Architecture Vision: "Next Level"

### V1. Real-time Tactical Operations Center

Transform the dashboard from a polling-based collection of panels into a **real-time operations center**:

- **Single SSE/WebSocket connection** for all real-time data (tactic updates, PR status changes, mission events, agent heartbeats). One connection, multiplexed events, no polling.
- **Server-Sent Events from FM backend** — the FM backend already has SSE endpoints (`/api/v1/missions/{id}/stream`). Extend to a general event stream that the dashboard subscribes to.
- **Live tactic queue** — tactics appear in the approval queue the moment they're created, with a live indicator. No refresh needed.
- **CI status push** — GitHub webhook → FM backend → dashboard SSE → instant CI status update on the tactic card.

### V2. AI-Powered Risk Assessment

Make the LLM integration proactive, not reactive:

- **Auto-score on creation** — every new tactic (from PR sync, inbox, or agent) is automatically scored by the local LLM. No manual trigger needed.
- **Re-score on CI change** — when CI status flips from pending to pass/fail, re-score the tactic (CI failure increases risk).
- **Batch scoring** — score all pending tactics in one LLM call (efficient context packing).
- **PR diff summarization** — LLM reads the PR diff and generates a 2-sentence summary + risk assessment. Displayed on the tactic card.
- **Trend analysis** — track confidence/risk scores over time. Show a chart of "average tactic risk" per day. Spot degrading agent quality.

### V3. Operational Intelligence

Turn the dashboard from a passive monitor into an active advisor:

- **Anomaly detection** — "Agent X has 3 failed tactics in a row" → alert. "CI failure rate doubled this week" → alert.
- **Bottleneck analysis** — "Tactics waiting for approval average 4.2 hours" → suggest auto-approving low-risk tactics.
- **Agent performance ranking** — which agents produce the highest-quality tactics? Which need more guardrails?
- **Time-to-merge tracking** — PR → approval → merge cycle time. Spot delays.
- **Daily executive briefing** — AI-generated summary of what happened, what needs attention, and what to do next. Delivered as a page you read with coffee.

### V4. Workflow Automation

Let the dashboard do things, not just show things:

- **Auto-approve low-risk tactics** — if confidence > 90, risk = low, and CI passes → auto-approve with a logged decision. Human sees it in the timeline.
- **Auto-merge PRs** — if tactic is approved, CI passes, and mergeable → auto-merge with `gh pr merge --squash`.
- **Auto-create tactics from GitHub issues** — new issues with specific labels become tactics automatically.
- **Escalation rules** — if a tactic sits in "needs_review" for > 24h → escalate (highlight, notify, move to top of queue).
- **Kill switch** — one button to pause all agent activity (cancel pending tactics, stop agents, freeze the queue).

---
