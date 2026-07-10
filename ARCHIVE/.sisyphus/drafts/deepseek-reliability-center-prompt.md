# DeepSeek Build Prompt — Reliability Center

You are a senior frontend engineer building a new page for **FlowManner**, an
agentic AI workflow platform. Your task is to build the **Reliability Center**
page — a new admin-facing dashboard that surfaces chaos testing health metrics
and provides a chaos mode toggle.

## Machine context

- You are on the **homelab** (172.16.1.1 / 10.99.0.3).
- **Frontend source** (edit here): `/home/glenn/FlowmannerV2-frontend/`
- **Backend source** (read-only reference): `/opt/flowmanner/backend/`
- Do NOT deploy. Do NOT run `deploy-frontend.sh`. Just build and verify locally.

## Backend API (already complete — do not modify)

Read `/opt/flowmanner/backend/app/api/v1/reliability.py` to see the exact
endpoint contracts. Two endpoints:

### GET /api/reliability
Returns a reliability report. Key fields (based on the backend code):
- LLM success rate during chaos testing (target: ~100%)
- Latency violations
- Circuit breaker transitions
- Chaos injection statistics

### POST /api/reliability/chaos
Body: `{ "enabled": true/false }`
Toggles chaos mode at runtime. When enabled, randomly injects failures into
Langfuse SDK calls to verify LLM responses remain unaffected.

## Related existing code to study

Before writing any code, READ these files to match existing patterns:

1. **`src/components/settings/CircuitBreakerPanel.tsx`** — existing reliability-
   adjacent component. Shows the glass-card layout style, mission selector,
   progress bars, toggle switches, toast usage, loading states.

2. **`src/lib/api-client.ts`** — the API client. Use `apiClient.get()` and
   `apiClient.post()`. Auth JWT is injected automatically. Do NOT handle tokens
   manually.

3. **`src/app/[locale]/(dashboard)/admin/features/admin-features-page-content.tsx`**
   — example of a full admin page with table layout, create modal, toggle
   actions, toast feedback. Match this structure.

4. **`src/app/[locale]/(dashboard)/circuit-breaker/page.tsx`** — example of
   the server `page.tsx` + client content split with `generateMetadata()`.

## What to build

### 1. Page route (2 files)

**`src/app/[locale]/(dashboard)/reliability/page.tsx`** (server component):
```tsx
import { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import ReliabilityPageClient from "./page-client";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("reliability");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

export default function Page() {
  return <ReliabilityPageClient />;
}
```

**`src/app/[locale]/(dashboard)/reliability/page-client.tsx`** (`"use client"`):
The main component. It should:

- Fetch `GET /api/reliability` on mount
- Display health metrics in a grid of stat cards (glass-card style):
  - LLM success rate (with progress bar)
  - Latency violations count
  - Circuit breaker transitions count
  - Chaos injection statistics
- Show a chaos mode toggle switch with confirmation dialog before toggling
  (POST `/api/reliability/chaos` with `{ enabled: boolean }`)
- Show toast on success/failure of toggle
- Loading state: `<Loader2 className="h-6 w-6 text-clay animate-spin" />`
- Refresh button to re-fetch the report

### 2. i18n keys

Add a `reliability` namespace to ALL 5 locale files:
`src/i18n/locales/{en,de,es,fr,ja}.json`

Minimum keys needed (translate properly for each language):
```json
{
  "reliability": {
    "metaTitle": "Reliability Center — FlowManner",
    "metaDescription": "Monitor LLM health during chaos testing",
    "title": "Reliability Center",
    "subtitle": "LLM health metrics and chaos testing controls",
    "llmSuccessRate": "LLM Success Rate",
    "latencyViolations": "Latency Violations",
    "circuitBreakerTransitions": "Circuit Breaker Transitions",
    "chaosInjections": "Chaos Injections",
    "chaosMode": "Chaos Mode",
    "chaosModeDescription": "When enabled, randomly injects failures into Langfuse SDK calls to verify LLM responses remain unaffected.",
    "enableChaos": "Enable Chaos Mode",
    "disableChaos": "Disable Chaos Mode",
    "chaosEnabled": "Chaos mode is ON",
    "chaosDisabled": "Chaos mode is OFF",
    "confirmEnable": "Are you sure you want to enable chaos mode? This will inject failures into Langfuse SDK calls.",
    "confirmDisable": "Are you sure you want to disable chaos mode?",
    "toggleSuccess": "Chaos mode updated successfully",
    "toggleError": "Failed to toggle chaos mode",
    "loadError": "Failed to load reliability report",
    "refresh": "Refresh",
    "refreshing": "Refreshing..."
  }
}
```

### 3. Navigation (optional — flag in completion notes)

Check `src/config/nav-config.ts` (or wherever the sidebar nav is configured).
If there's an admin section, add a "Reliability" entry pointing to
`/reliability`. If you can't find the nav config, note it in your completion
comment — don't guess.

## Must do

- Match the existing codebase style exactly (glass-card, btn-clay, lucide-react
  icons, sonner toasts, next-intl translations).
- Use TypeScript interfaces for the API response shape (define them inline in
  the client component — infer from `reliability.py`).
- Handle loading and error gracefully.
- `npx tsc --noEmit` must pass after your changes.
- `npx vitest run` must pass (no test regressions).
- Commit message: `feat(frontend): add reliability center page with chaos toggle`

## Must NOT do

- Do NOT modify any backend files.
- Do NOT run `deploy-frontend.sh` or any deploy commands.
- Do NOT create test files — this is a UI page, not a test task.
- Do NOT add new npm dependencies — use what's already installed.
- Do NOT touch `.env` or credential files.
- Do NOT use `as any` type assertions.
- Do NOT create separate API client files — use `apiClient` from `@/lib/api-client`
  directly in the component.

## Acceptance criteria

- [ ] `src/app/[locale]/(dashboard)/reliability/page.tsx` exists
- [ ] `src/app/[locale]/(dashboard)/reliability/page-client.tsx` exists
- [ ] `npx tsc --noEmit` passes
- [ ] `npx vitest run` passes
- [ ] `reliability` i18n namespace added to all 5 locale files
- [ ] Component fetches `GET /api/reliability` on mount
- [ ] Chaos toggle calls `POST /api/reliability/chaos`
- [ ] Loading/error states handled

## When done

Report:
- Files created/modified (list)
- `npx tsc --noEmit` output (pass/fail)
- `npx vitest run` output (pass/fail)
- Any blockers or notes (especially the nav-config question)

Do NOT push to origin. Glenn reviews, then Hermes verifies and commits.
