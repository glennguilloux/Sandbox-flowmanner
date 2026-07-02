# Reliability Center — Bug-Fix Plan (not a build plan)

**Status:** Ready
**Owner:** DeepSeek (or Hermes in-session)
**Priority:** Medium — bug only visible on dashboards that have actual LLM call data
**Estimated effort:** ~30 lines across 2 files + 2 mock data updates

> **Important:** This is **NOT** a from-scratch build. The Reliability Center
> frontend (page + page-client + i18n + tests + nav entry + admin guard) was
> **finished on 2026-07-01** in commit `96e498f` (i18n+stubs audit) and prior
> sessions. This plan fixes a **single class of bug**: the React component maps
> wrong field names against the actual backend response shape, so when real LLM
> calls exist, every metric card shows garbage (`undefined` → 0, or `9850%`
> instead of `98.5%`). See "Bug found" below.

---

## Context (what already exists — DO NOT rebuild)

| Resource | Location | Status |
|---|---|---|
| Backend router | `backend/app/api/v1/reliability.py` (63 lines) | ✅ Mounted at `/api/reliability` + `/api/reliability/chaos` (verified via `grep -n reliability app/api/v1/__init__.py`) |
| Backend service | `backend/app/services/reliability_assertions.py` (114 lines) | ✅ Singleton `get_reliability_monitor()`, `get_reliability_report()` |
| Chaos injection | `backend/app/services/chaos_langfuse.py` (120 lines) | ✅ Singleton `get_chaos()`, `toggle_chaos()`, `get_stats()` |
| Langfuse trace stats | `backend/app/services/langfuse_service.py:get_trace_stats()` | ✅ Live, returns `{sent, failed, circuit_state, last_failure, worker_id}` |
| Frontend page (server) | `frontend/src/app/[locale]/(dashboard)/reliability/page.tsx` | ✅ 15 lines, generates metadata |
| Frontend page (client) | `frontend/src/app/[locale]/(dashboard)/reliability/page-client.tsx` | ✅ 277 lines, fully implemented |
| Tests | `frontend/src/app/[locale]/(dashboard)/reliability/__tests__/ReliabilityPageClient.test.tsx` | ✅ 329 lines, 22 tests |
| SDK (generated) | `frontend/src/lib/sdk/services/ReliabilityService.ts` | ✅ `getReliabilityReportApiReliabilityGet()` + `toggleChaosModeApiReliabilityChaosPost()` |
| Nav entry | `frontend/src/components/layout/nav-config.ts:288` | ✅ `href: "/reliability"` |
| Admin guard | `frontend/src/components/layout/floating-nav.tsx:73` | ✅ `ADMIN_ONLY_NAV_KEYS` includes `"nav.reliability"` |
| i18n (5 locales) | `frontend/src/i18n/locales/{de,en,es,fr,ja}.json` | ✅ All 23 keys per locale |

---

## Bug found (ground-truth verified 2026-07-02)

Live response from `curl http://127.0.0.1:8000/api/reliability` (truncated):

```json
{
  "status": "no_data",
  "llm_success_rate": null,
  "chaos_stats": {
    "enabled": false,
    "total_calls": 0,
    "failures_injected": 0,
    "delays_injected": 0,
    "timeouts_injected": 0
  },
  "langfuse_trace_stats": {
    "sent": 0, "failed": 0, "circuit_state": "CLOSED",
    "last_failure": null, "worker_id": 1
  }
}
```

When real LLM traffic exists, the full shape (from `reliability_assertions.py:90-103`) is:

```json
{
  "llm_total_calls": 1234,
  "llm_successful": 1232,
  "llm_success_rate": 99.84,        // ← ALREADY 0-100, not 0-1
  "llm_latency_violations": 3,
  "langfuse_caused_failures": 0,
  "langfuse_total_failures": 5,
  "circuit_transitions": 7,         // ← backend uses "circuit_transitions", not "circuit_breaker_transitions"
  "circuit_transition_log": [...],
  "chaos_stats": null,              // ← overwritten by chaos module to:
  "chaos_stats": {                  //   {enabled, total_calls, failures_injected, delays_injected, timeouts_injected}
    "enabled": true,
    "total_calls": 50,              // ← not "total_injections"
    "failures_injected": 35,        // ← not "successful_failures"
    "delays_injected": 10,
    "timeouts_injected": 5
  },
  "langfuse_trace_stats": {...},
  "assertion": "PASS",
  "target_llm_success_rate": "~100%",
  "actual_llm_success_rate": "99.84%"
}
```

### Mismatches (component expects vs backend returns)

| Card | Component expects | Backend returns | Symptom |
|---|---|---|---|
| LLM Success Rate | `llm_success_rate * 100` then round | `llm_success_rate` already a 0–100 number | Shows `9850%` instead of `98.5%` |
| Latency Violations | `latency_violations` | `llm_latency_violations` | Shows `0` always |
| Circuit Breaker Transitions | `circuit_breaker_transitions` | `circuit_transitions` | Shows `0` always |
| Chaos Injections | `chaos_stats.total_injections` | `chaos_stats.total_calls` | Shows `0` always |
| (chaos detail panel) | `chaos_stats.successful_failures` | `chaos_stats.failures_injected` | Shows `0` always |

The component ALSO uses `llm_success_rate != null` guard to show `—`, so when the dashboard sees `null` it correctly shows the dash — but the moment real traffic starts, the multipliers kick in and `9850%` appears.

---

## Implementation steps

### Step 1: Fix the TypeScript interface in `page-client.tsx`

**File:** `frontend/src/app/[locale]/(dashboard)/reliability/page-client.tsx`

Replace `ReliabilityReport` interface (lines 30-37) with one that matches the
backend. Keep the `[key: string]: unknown` index signature for forward-compat.

```typescript
interface ChaosStats {
  enabled?: boolean;
  total_calls?: number;
  failures_injected?: number;
  delays_injected?: number;
  timeouts_injected?: number;
  [key: string]: unknown;
}

interface LangfuseTraceStats {
  sent?: number;
  failed?: number;
  circuit_state?: string;
  last_failure?: string | null;
  worker_id?: number;
  [key: string]: unknown;
}

interface ReliabilityReport {
  // Core report fields (from reliability_assertions.py:90-103)
  status?: string;                          // "no_data" when empty
  llm_total_calls?: number;
  llm_successful?: number;
  llm_success_rate?: number | null;         // 0-100, NOT 0-1
  llm_latency_violations?: number;
  langfuse_caused_failures?: number;
  langfuse_total_failures?: number;
  circuit_transitions?: number;             // NOT circuit_breaker_transitions
  circuit_transition_log?: Array<{
    timestamp: string;
    from: string;
    to: string;
  }>;
  assertion?: "PASS" | "FAIL";
  target_llm_success_rate?: string;
  actual_llm_success_rate?: string;
  // Enrichment fields (added by reliability.py router)
  chaos_stats?: ChaosStats | { error: string };
  langfuse_trace_stats?: LangfuseTraceStats | { error: string };
  [key: string]: unknown;
}
```

### Step 2: Fix the field reads in the same file

**Same file:** `page-client.tsx`

Four fixes, exact locations:

**Fix A** (line 91-93) — remove the `* 100` multiplier and the `Math.round` is no
longer needed (backend returns already-rounded values per
`reliability_assertions.py:93`):

```typescript
// Before
const successRatePercent = report?.llm_success_rate != null
  ? Math.round(report.llm_success_rate * 100)
  : null;

// After
const successRatePercent = report?.llm_success_rate != null
  ? Math.round(report.llm_success_rate)
  : null;
```

**Fix B** (line 165) — `latency_violations` → `llm_latency_violations`:

```tsx
<p className="text-3xl font-bold text-charcoal">
  {report?.llm_latency_violations ?? 0}
</p>
```

**Fix C** (line 178) — `circuit_breaker_transitions` → `circuit_transitions`:

```tsx
<p className="text-3xl font-bold text-charcoal">
  {report?.circuit_transitions ?? 0}
</p>
```

**Fix D** (lines 95-98) — `chaos_stats.total_injections` → `chaos_stats.total_calls`:

```typescript
// Before
const chaosInjections =
  report?.chaos_stats && !("error" in report.chaos_stats)
    ? report.chaos_stats.total_injections ?? 0
    : 0;

// After
const chaosInjections =
  report?.chaos_stats && !("error" in report.chaos_stats)
    ? report.chaos_stats.total_calls ?? 0
    : 0;
```

### Step 3: Update the test mocks

**File:** `frontend/src/app/[locale]/(dashboard)/reliability/__tests__/ReliabilityPageClient.test.tsx`

The mock at lines 64-83 uses the same wrong field names. Fix the mockReport and
its variants to use real backend field names so the tests actually verify the
bug-fix:

```typescript
// Lines 64-74 — REPLACE mockReport with:
const mockReport = {
  status: "ok",
  llm_total_calls: 200,
  llm_successful: 197,
  llm_success_rate: 98.5,                  // already 0-100
  llm_latency_violations: 3,
  langfuse_caused_failures: 0,
  langfuse_total_failures: 5,
  circuit_transitions: 2,                  // was circuit_breaker_transitions
  assertion: "PASS",
  chaos_stats: {
    enabled: false,
    total_calls: 42,                       // was total_injections
    failures_injected: 0,                  // was successful_failures
    delays_injected: 5,
    timeouts_injected: 1,
  },
  langfuse_trace_stats: {
    sent: 200, failed: 5, circuit_state: "CLOSED",
    last_failure: null, worker_id: 1,
  },
};

// Lines 76-83 — REPLACE mockReportChaosEnabled with:
const mockReportChaosEnabled = {
  ...mockReport,
  chaos_stats: {
    enabled: true,
    total_calls: 50,
    failures_injected: 2,
    delays_injected: 8,
    timeouts_injected: 2,
  },
};
```

Then update the test that asserts `expect(screen.getByText("99%")).toBeInTheDocument();`
(line 126): since the mock now has `llm_success_rate: 98.5`, the displayed text
should be `99%` (after rounding). That assertion already matches — leave it.

### Step 4: Verify

Run the test suite for this file:

```bash
cd /home/glenn/FlowmannerV2-frontend
NODE_ENV=test pnpm test -- src/app/\[locale\]/\(dashboard\)/reliability
```

**Expected:** 22 passed (unchanged total). The mocked data still matches the
component's expected shape, and the renamed fields align with the real backend.

Then run the full suite to confirm no regressions:

```bash
NODE_ENV=test pnpm test --
```

**Expected:** Same as before this session (854 tests total per
`.sisyphus/handoffs/exit-audit-2026-07-01-i18n-and-stubs.md`). Plus the full
TypeScript and build gates per AGENTS.md:

```bash
npx tsc --noEmit                       # EXIT 0
pnpm build                              # SUCCESS
```

### Step 5: Live-curl verification (post-deploy)

Once the user deploys the frontend, verify the live `/api/reliability` payload
matches what the component reads. Document the change in a short exit audit:

```bash
curl -s http://127.0.0.1:8000/api/reliability \
  -H "Authorization: Bearer <admin-token>" | python3 -m json.tool
```

Confirm:
- `llm_success_rate` is a number 0–100 (or `null` when `status: "no_data"`)
- `chaos_stats.total_calls` is the chaos injection counter
- `circuit_transitions` is the circuit breaker counter

---

## Files summary

| File | Change | ~LOC |
|---|---|---|
| `frontend/src/app/[locale]/(dashboard)/reliability/page-client.tsx` | Replace interface + 4 field reads | ~30 |
| `frontend/src/app/[locale]/(dashboard)/reliability/__tests__/ReliabilityPageClient.test.tsx` | Fix mockReport + variants | ~10 |

## No changes needed

- Backend (router + service) — already returns correct shape
- i18n — 23 keys per locale, all match what the component uses
- Nav entry, admin guard — wired correctly
- SDK — generated, will continue to match

---

## Acceptance criteria

- [ ] `page-client.tsx` interface declares the 5 wrong field names corrected
- [ ] Component shows `0`–`100%` (not `0`–`10000%`) for `llm_success_rate`
- [ ] Component shows non-zero values for `llm_latency_violations`,
      `circuit_transitions`, and `chaos_stats.total_calls` when backend reports them
- [ ] Test mock data uses real backend field names
- [ ] All 22 reliability tests pass
- [ ] Full frontend suite still passes (854 tests)
- [ ] `npx tsc --noEmit` clean
- [ ] `pnpm build` succeeds
- [ ] Live `curl /api/reliability` matches the component's read path
