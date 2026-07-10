# Task: Build 4 Frontend Pages for Backend-Ready Features

**Date:** 2026-07-01
**Estimated effort:** 6–10 hours
**Priority:** HIGH — backend APIs exist, frontend has nothing. Users who hit these pages see hardcoded stubs or 404s.

---

## 0. ⚠️ REPO PATH WARNING

Frontend lives at `/home/glenn/FlowmannerV2-frontend/`. Verify with `pwd`.
**DO NOT** touch the backend (`/opt/flowmanner/backend/`). All APIs listed here already exist and work.

## 1. Context — what's ACTUALLY a stub

After deep investigation, most "stub" pages are actually thin wrappers around real, wired components (analytics=200 lines, templates=235 lines, triggers=156 lines, etc.). The actual gaps are:

| # | Feature | Current state | Backend API | What's missing |
|---|---------|--------------|-------------|----------------|
| 1 | **Billing** | 31-line page, hardcoded `useState("free")` | `subscription.py` (8 routes) — tiers, upgrade, billing dashboard | Page needs to call `billing-api.ts` (already exists!) |
| 2 | **Data Export** | No page exists. SDK service exists at `src/lib/sdk/services/DataExportService.ts` | `data_export.py` (2 routes) — export + delete | Needs a settings sub-page with export/delete buttons |
| 3 | **Circuit Breaker** | NO frontend at all | `circuit_breaker.py` (3 routes) — mission limits, destructive action policy | Needs a new page + component |
| 4 | **Agent Capabilities** | Agent detail page (96 lines) shows name/description only | `agent_capabilities.py` (6 routes) — CRUD for agent capabilities | Detail page needs a "Capabilities" section |

### What is NOT a stub (already built, don't touch)

- Cost Attribution — 336-line dashboard + 3 sub-components + API client + store + hook
- Analytics — 200-line dashboard, wired to `usage-api.ts`
- Templates — 235-line gallery, wired to `/api/templates`
- Triggers — 156-line management, wired to `/api/triggers`
- RAG — 57-line page + 528 lines of real components (DocumentUploader, DocumentList, SearchBar)
- Memory Inspector — 20-line wrapper around 1066-line component
- External Events — 36-line wrapper around 673-line component
- Critiques — 19-line wrapper around 814-line component
- Agents list — 217-line page, fetches personalities + orchestration stats from API
- Chat — 8550 lines across 44 files
- Mission Builder — 7682 lines across 28 files

## 2. Files to create/modify

### Feature 1: Billing Page (MODIFY existing)

| File | Action |
|------|--------|
| `src/app/[locale]/(dashboard)/settings/billing/billing-page-content.tsx` | **Replace** — call `billing-api.ts` instead of hardcoded data |

The billing page currently (31 lines):
```tsx
const [plan] = useState("free");
// ... renders "You are on the free plan" with a non-functional button
```

Replace with:
- Call `fetchMySubscription()` to get current plan
- Call `fetchBillingTiers()` to show available tiers
- Call `fetchUsageSummary()` to show usage vs limits
- "Upgrade" button calls `upgradeSubscription()` → redirects to PayPal checkout URL
- Invoice/billing history section (if the `/api/subscription/billing` endpoint returns it)

**API client already exists:** `src/lib/billing-api.ts` (70 lines) with `fetchBillingTiers()`, `fetchMySubscription()`, `upgradeSubscription()`, `fetchUsageSummary()`, etc.
**Types already exist:** `src/lib/billing-types.ts` with `BillingTier`, `UserSubscription`, `CheckoutResponse`, etc.

### Feature 2: Data Export Settings Page (CREATE)

| File | Action |
|------|--------|
| `src/app/[locale]/(dashboard)/settings/export/page.tsx` | **Create** — server component with metadata |
| `src/components/settings/DataExportPanel.tsx` | **Create** — client component with export/delete UI |
| `src/app/[locale]/(dashboard)/settings/settings-page-content.tsx` | **Modify** — add "Data Export" link to settings grid |

The page should have:
- "Export All My Data" button → calls `DataExportService.exportUserDataApiDataExportMeExportPost()` → downloads ZIP
- "Delete All My Data" button → confirmation dialog → calls `DataExportService.deleteUserDataApiDataExportMeDelete()`
- GDPR compliance notice text
- Status feedback (loading, success, error)

**SDK service already exists:** `src/lib/sdk/services/DataExportService.ts` with `exportUserDataApiDataExportMeExportPost()` and `deleteUserDataApiDataExportMeDelete()`.

**Pattern to follow:** `src/app/[locale]/(dashboard)/settings/danger/danger-zone-page-content.tsx` (69 lines) — similar destructive-action pattern with confirmation.

### Feature 3: Circuit Breaker Page (CREATE)

| File | Action |
|------|--------|
| `src/app/[locale]/(dashboard)/circuit-breaker/page.tsx` | **Create** — server component |
| `src/app/[locale]/(dashboard)/circuit-breaker/page-client.tsx` | **Create** — client component |
| `src/components/settings/CircuitBreakerPanel.tsx` | **Create** — circuit breaker configuration UI |

First, read the backend API to understand the exact endpoints:
```bash
cat /opt/flowmanner/backend/app/api/v1/circuit_breaker.py
```

The page should show:
- Per-mission budget limits (set max cost per mission)
- Destructive action policy (allow/restrict destructive tool calls)
- Circuit breaker status (open/closed/half-open per mission)
- Override controls (manually open/close a circuit breaker)

**Pattern to follow:** `src/components/settings/api-keys-page-content.tsx` (344 lines) — form + table layout with CRUD.

### Feature 4: Agent Capabilities Section (MODIFY existing)

| File | Action |
|------|--------|
| `src/app/[locale]/agents/[...slug]/page-client.tsx` | **Modify** — add capabilities section |

First, read the backend API:
```bash
cat /opt/flowmanner/backend/app/api/v1/agent_capabilities.py
```

The agent detail page (96 lines) currently shows: name, description, domain, "Start Agent" button, "Configure" button. Add:
- "Capabilities" section below the existing details
- List of capabilities (tools the agent can use, supported actions)
- Each capability shows: name, description, type, enabled/disabled toggle
- "Add Capability" button (if the API supports it)

**Important:** The agent detail page currently receives props from a server component. The capabilities need to be fetched client-side (the page is `"use client"`). Use `apiClient` to call the capabilities endpoint directly in the component.

## 3. Constraints (HARD)

1. **Do NOT modify any backend files.** All APIs already exist.
2. **Use `apiClient` from `@/lib/api-client`** for all new API calls. Do NOT use raw `fetch()`.
3. **Use existing `billing-api.ts` and `billing-types.ts`** for the billing page. Do NOT create new API clients for subscription.
4. **Use existing `DataExportService`** for the data export page. Do NOT create new API clients.
5. **Follow existing component patterns:** `glass-card`, `btn-clay`, Tailwind classes, `animate-pulse` skeletons.
6. **Use `next-intl`** for all user-visible strings. Add keys to `messages/en.json`.
7. **Handle loading + error states** in every API-connected component.
8. **Run `npx tsc --noEmit` after each feature.**
9. **Read the backend API file before building each feature** to understand exact endpoint shapes, parameters, and response types.

## 4. Verification

### After each feature:

```bash
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit 2>&1 | tail -10
```

### After all features:

```bash
cd /home/glenn/FlowmannerV2-frontend

# TypeScript
npx tsc --noEmit 2>&1 | tail -20

# Build
pnpm build 2>&1 | tail -20

# Tests
NODE_ENV=test pnpm test -- --run 2>&1 | tail -20

# Verify billing is no longer hardcoded
grep -c "useState.*free" src/app/\[locale\]/\(dashboard\)/settings/billing/billing-page-content.tsx
# Should return 0

# Verify new pages exist
ls src/app/\[locale\]/\(dashboard\)/settings/export/page.tsx
ls src/app/\[locale\]/\(dashboard\)/circuit-breaker/page.tsx
ls src/components/settings/DataExportPanel.tsx
ls src/components/settings/CircuitBreakerPanel.tsx

# Verify settings page has export link
grep -c "export" src/app/\[locale\]/\(dashboard\)/settings/settings-page-content.tsx
# Should return >= 1

# Verify agent detail has capabilities
grep -c "capabilities\|Capabilities" src/app/\[locale\]/agents/\[...slug\]/page-client.tsx
# Should return >= 1
```

## 5. Handoff format

Write to `.sisyphus/handoffs/exit-audit-2026-07-01-frontend-feature-buildout.md`:

1. **What changed** — file-by-file, what it does, which API it calls.
2. **API endpoint mapping** — table: frontend component → backend endpoint → HTTP method.
3. **Verification output** — paste raw output from §4.
4. **What is NOT done** — tools catalog (111 tools without UI), playground, workspace features, episodic memory.
5. **Follow-up items** — what to build next.

## 6. Stop-the-line rules

- **If a backend API returns unexpected shape**, `curl` the endpoint and paste the response. Do NOT mock.
- **If `pnpm build` fails**, fix before moving on.
- **If the billing API uses PayPal (not Stripe)**, that's correct — the backend uses PayPal. Don't add Stripe integration.
- **If DataExportService returns a ZIP**, handle the download via blob/URL.createObjectURL pattern.

## 7. What "done" means

- Billing page calls real API (no more hardcoded "free plan")
- Data Export page exists in settings with export + delete buttons
- Circuit Breaker page shows mission limits and breaker status
- Agent detail page shows capabilities section
- `npx tsc --noEmit` exits 0
- `pnpm build` exits 0
- Tests pass
- Handoff written
- **You do NOT commit.** Per session ritual: Glenn reviews, Hermes commits.
