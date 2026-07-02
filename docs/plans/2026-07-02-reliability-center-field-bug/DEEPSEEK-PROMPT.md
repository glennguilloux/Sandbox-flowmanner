# DeepSeek Prompt — Reliability Center Field-Name Bug Fix

You are a senior engineer fixing a small bug in an existing, working frontend
component. **Do not redesign. Do not refactor. Do not touch the backend.** Your
deliverable is the **fix in 2 files + test mocks**, verified by running the
project's verification gates.

## Project context

- **Project root:** `/home/glenn/FlowmannerV2-frontend`
- **Stack:** Next.js 16 (App Router) + React 19 + Tailwind v4 + lucide-react +
  next-intl. Frontend for the FlowManner backend.
- **Backend for this feature:** FastAPI at `http://127.0.0.1:8000`, router at
  `backend/app/api/v1/reliability.py`, services at
  `backend/app/services/reliability_assertions.py` and `chaos_langfuse.py`.

The Reliability Center feature was **already built and shipped** in commit
`96e498f` (and several before it). Pages, tests, i18n, SDK, nav entry, admin
guard — all done. The only remaining issue is a **field-name mismatch** between
the React component and the actual backend response shape. When real LLM
traffic hits the backend, every metric card shows garbage values.

## The bug (ground-truth verified 2026-07-02)

Live backend response shape (from `reliability_assertions.py:90-103`):

```json
{
  "llm_success_rate": 98.5,            // 0-100, NOT 0-1
  "llm_latency_violations": 3,
  "circuit_transitions": 7,            // NOT "circuit_breaker_transitions"
  "chaos_stats": {
    "enabled": true,
    "total_calls": 50,                  // NOT "total_injections"
    "failures_injected": 35,            // NOT "successful_failures"
    "delays_injected": 10,
    "timeouts_injected": 5
  },
  ...
}
```

Component (`page-client.tsx`) currently reads:
- `llm_success_rate * 100` → produces `9850%` instead of `98.5%`
- `latency_violations` (undefined) → always shows `0`
- `circuit_breaker_transitions` (undefined) → always shows `0`
- `chaos_stats.total_injections` (undefined) → always shows `0`

When the backend returns `status: "no_data"` (no LLM traffic yet), every value
is null/0 so the bug is invisible — until the first real LLM call hits.

## Existing infrastructure (DO NOT rebuild)

| File | Status |
|---|---|
| `src/app/[locale]/(dashboard)/reliability/page.tsx` | 15 lines, server component, generateMetadata |
| `src/app/[locale]/(dashboard)/reliability/page-client.tsx` | 277 lines, fully implemented, just reads wrong field names |
| `src/app/[locale]/(dashboard)/reliability/__tests__/ReliabilityPageClient.test.tsx` | 329 lines, 22 tests, mocks use the same wrong field names |
| `src/lib/sdk/services/ReliabilityService.ts` | Generated, has `getReliabilityReportApiReliabilityGet` + `toggleChaosModeApiReliabilityChaosPost` |
| `src/i18n/locales/{de,en,es,fr,ja}.json` | 23 reliability keys per locale, all complete |
| `src/components/layout/nav-config.ts:288` | Nav entry `{ labelKey: "nav.reliability", href: "/reliability" }` |
| `src/components/layout/floating-nav.tsx:73` | `ADMIN_ONLY_NAV_KEYS` includes `"nav.reliability"` |

## What to fix

### File 1: `src/app/[locale]/(dashboard)/reliability/page-client.tsx`

**Replace the `ReliabilityReport` interface (lines 30-37)** with the shape
below. Keep the `[key: string]: unknown` index signature for forward-compat
with future backend fields:

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
  status?: string;
  llm_total_calls?: number;
  llm_successful?: number;
  llm_success_rate?: number | null;
  llm_latency_violations?: number;
  langfuse_caused_failures?: number;
  langfuse_total_failures?: number;
  circuit_transitions?: number;
  circuit_transition_log?: Array<{ timestamp: string; from: string; to: string }>;
  assertion?: "PASS" | "FAIL";
  target_llm_success_rate?: string;
  actual_llm_success_rate?: string;
  chaos_stats?: ChaosStats | { error: string };
  langfuse_trace_stats?: LangfuseTraceStats | { error: string };
  [key: string]: unknown;
}
```

**Fix 4 read sites in the same file:**

1. **Line 91-93** — remove `* 100` (backend returns 0-100 already):

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

2. **Line 165** — `latency_violations` → `llm_latency_violations`:

```tsx
<p className="text-3xl font-bold text-charcoal">
  {report?.llm_latency_violations ?? 0}
</p>
```

3. **Line 178** — `circuit_breaker_transitions` → `circuit_transitions`:

```tsx
<p className="text-3xl font-bold text-charcoal">
  {report?.circuit_transitions ?? 0}
</p>
```

4. **Lines 95-98** — `chaos_stats.total_injections` → `chaos_stats.total_calls`:

```typescript
const chaosInjections =
  report?.chaos_stats && !("error" in report.chaos_stats)
    ? report.chaos_stats.total_calls ?? 0
    : 0;
```

### File 2: `src/app/[locale]/(dashboard)/reliability/__tests__/ReliabilityPageClient.test.tsx`

**Replace mockReport (lines 64-74)** with one that uses real backend field
names. This is critical — otherwise the tests pass with the buggy code:

```typescript
const mockReport = {
  status: "ok",
  llm_total_calls: 200,
  llm_successful: 197,
  llm_success_rate: 98.5,            // 0-100, not 0-1
  llm_latency_violations: 3,
  langfuse_caused_failures: 0,
  langfuse_total_failures: 5,
  circuit_transitions: 2,            // was circuit_breaker_transitions
  assertion: "PASS",
  chaos_stats: {
    enabled: false,
    total_calls: 42,                 // was total_injections
    failures_injected: 0,            // was successful_failures
    delays_injected: 5,
    timeouts_injected: 1,
  },
  langfuse_trace_stats: {
    sent: 200, failed: 5, circuit_state: "CLOSED",
    last_failure: null, worker_id: 1,
  },
};
```

**Replace mockReportChaosEnabled (lines 76-83)** with:

```typescript
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

Leave mockReportChaosError (lines 85-88) alone — it's an `{ error: string }`
shape that exercises the wrong-shape branch.

The assertion `expect(screen.getByText("99%")).toBeInTheDocument();` (line 126)
still matches the new mock (`98.5` rounds to `99`).

## Verification gates (run all, paste output)

```bash
cd /home/glenn/FlowmannerV2-frontend

# 1. Reliability tests pass
NODE_ENV=test pnpm test -- src/app/\[locale\]/\(dashboard\)/reliability/__tests__/ReliabilityPageClient.test.tsx

# 2. Full test suite (854 tests per baseline; should not regress)
NODE_ENV=test pnpm test --

# 3. TypeScript clean
npx tsc --noEmit

# 4. Production build
pnpm build
```

**Expected for all:** exit code 0, no new errors, reliability test count
stays at 22.

## Hard constraints

- Do NOT modify the backend (`/opt/flowmanner/backend/`) — the backend is
  correct
- Do NOT modify the SDK (`src/lib/sdk/`) — generated from backend OpenAPI
- Do NOT modify the i18n locales — keys are already correct
- Do NOT modify the nav entry, admin guard, or page.tsx server wrapper
- Do NOT add new dependencies
- Do NOT refactor the component beyond the 4 read sites listed above
- Do NOT commit. Glenn commits. Write a brief report at the end.

## When done

Report to Glenn (in your final response):
- One-sentence summary of what changed
- Output of all 4 verification gates (paste the tail of each)
- Any blocker or "I need to ask Glenn" items

## Stop rules

- If a test fails that didn't fail before this session, STOP and report.
  Do not chase test breakage — surface it.
- If `pnpm build` adds new lint or type errors, STOP and report.
- If you discover the backend response shape is different from what's
  documented above, STOP and report. The doc was verified live on 2026-07-02;
  if reality has changed, that's a separate investigation.

Do NOT push to origin. Glenn reviews, then Hermes verifies and commits.
