# DeepSeek Build Prompt — Tool Routing Inspector

You are a senior frontend engineer building a new page for **FlowManner**, an
agentic AI workflow platform. Your task is to build the **Tool Routing
Inspector** page — a new admin/dev-facing dashboard that surfaces tool routing
audit trails and provides an interactive routing playground.

This is the **second of three features** in a frontend wiring roadmap. The
first (Reliability Center) is already built and committed. Match its style
exactly.

## Machine context

- You are on the **homelab** (172.16.1.1 / 10.99.0.3).
- **Frontend source** (edit here): `/home/glenn/FlowmannerV2-frontend/`
- **Backend source** (read-only reference): `/opt/flowmanner/backend/`
- Do NOT deploy. Do NOT run `deploy-frontend.sh`. Just build and verify locally.

## Backend API (already complete — do not modify)

Read `/opt/flowmanner/backend/app/api/v1/tool_routing.py` to see the exact
endpoint contracts. Also read the response models in
`/opt/flowmanner/backend/app/models/tool_routing_models.py`.

Two endpoints, both mounted under `/api/tool-routing/`:

### GET /api/missions/{mission_id}/tool-routing-events

Returns an audit trail of routing decisions for a mission. This is the
**primary feature** of this page.

**Path param:** `mission_id` (string — the mission's UUID)

**Response shape** (`MissionRoutingEventsResponse`):
```typescript
{
  events: ToolRoutingEvent[];
  count: number;
}
```

Each `ToolRoutingEvent` has:
```typescript
{
  id: string | null;        // event UUID
  sequence: number | null;  // ordering within the mission
  type: string | null;      // always "tool_route_decided" for this endpoint
  payload: Record<string, unknown> | null;  // see below
  actor: string | null;     // who/what triggered the route
  timestamp: string | null; // ISO datetime
}
```

The `payload` dict contains the routing decision details (based on
`ToolRouteDecidedEvent` in the backend models):
```typescript
{
  mode: "sparse" | "fallback-full-registry";
  top_score: number;          // 0.0–1.0
  candidates_considered: number;
  candidates_returned: number;
  selected_tool_ids: string[];
  task_text_hash: string;     // SHA-256 hex — never the raw task text
  workspace_id: string;
  user_id: number;
  mission_id: string | null;
}
```

### POST /api/tool-routing/route

Scores and selects top-k tool candidates for a task description. This is the
**secondary feature** — a "try it" playground.

**Request body** (`RouteRequest`):
```typescript
{
  task_text: string;      // 1–5000 chars, natural language task description
  workspace_id: string;   // UUID string — DERIVE FROM SESSION, see below
  user_id: number;        // integer — DERIVE FROM SESSION, see below
  k?: number;             // optional, 1–50, default 8
}
```

**Response shape** (`ToolRouteResult`):
```typescript
{
  tools: Record<string, unknown>[];     // selected ToolDefinition dicts
  mode: "sparse" | "fallback-full-registry";
  top_score: number;                     // 0.0–1.0
  reasons: Record<string, string>;       // per-tool_id → reason string
  candidates_considered: number;
  candidates_returned: number;
  task_text_hash: string;                // SHA-256 hex
  scores: ToolScore[];                   // per-tool score breakdowns
}
```

Each `ToolScore`:
```typescript
{
  tool_id: string;
  score: number;            // 0.0–1.0
  components: Record<string, number>;  // text_similarity, category_match, etc.
  reasons: string[];
}
```

## ⚠️ Critical risk: workspace_id and user_id

The POST endpoint requires `workspace_id` (UUID string) and `user_id` (int).
**You must derive these from the auth session and workspace store — NEVER ask
the user to type them.**

### How to get user_id

From the NextAuth session:

```typescript
import { useSession } from "next-auth/react";

const { data: session } = useSession();
const userId = session?.user?.id;  // string — parse to int for the API call
```

`session.user.id` is a **string**. The API expects an **int**. Parse it:
```typescript
const userIdInt = userId ? parseInt(userId, 10) : NaN;
if (isNaN(userIdInt)) {
  toast.error(t("sessionError"));
  return;
}
```

### How to get workspace_id

From the Zustand workspace store:

```typescript
import { useWorkspaceStore } from "@/stores/workspace-store";

const activeWorkspace = useWorkspaceStore((s) => s.activeWorkspace);
const workspaceId = activeWorkspace?.id;  // string UUID
```

If `activeWorkspace` is null, the store hasn't loaded yet. Call
`loadWorkspaces()` on mount if needed. If still null after load, show an error
state — do not submit the POST.

**Read these files to understand the patterns:**
- `/home/glenn/FlowmannerV2-frontend/src/auth.ts` (lines 406–414) — session callback
- `/home/glenn/FlowmannerV2-frontend/src/stores/workspace-store.ts` — workspace store

## Related existing code to study

Before writing any code, READ these files to match existing patterns:

1. **`src/app/[locale]/(dashboard)/reliability/page-client.tsx`** — the feature
   you are matching. It was just built by another agent. Copy its layout style,
   header pattern, glass-card grid, loading/error states, refresh button.

2. **`src/components/settings/CircuitBreakerPanel.tsx`** — the **mission
   selector pattern** you need for the audit trail view. It fetches
   `/api/missions`, populates a `<select>` dropdown, and loads data when a
   mission is selected. Study lines 50–109 closely.

3. **`src/lib/api-client.ts`** — the API client. Use `apiClient.get()` and
   `apiClient.post()`. Auth JWT is injected automatically. Do NOT handle tokens
   manually.

4. **`src/hooks/use-missions.ts`** — alternative mission fetching hook (uses
   react-query). You can use either the hook or direct `apiClient.get()` —
   match whichever the CircuitBreakerPanel uses (it uses direct apiClient).

5. **`src/stores/workspace-store.ts`** — Zustand store for active workspace.

6. **`src/app/[locale]/(dashboard)/reliability/page.tsx`** — example of the
   server `page.tsx` + client content split with `generateMetadata()`.

## What to build

### 1. Page route (2 files)

**`src/app/[locale]/(dashboard)/tool-routing/page.tsx`** (server component):
```tsx
import { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import ToolRoutingPageClient from "./page-client";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("toolRouting");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
  };
}

export default function Page() {
  return <ToolRoutingPageClient />;
}
```

**`src/app/[locale]/(dashboard)/tool-routing/page-client.tsx`** (`"use client"`):
The main component. It has **two sections**:

#### Section A: Audit Trail (primary)

- Mission selector dropdown (fetch `/api/missions`, same pattern as
  CircuitBreakerPanel)
- When a mission is selected, fetch
  `GET /api/missions/{mission_id}/tool-routing-events`
- Render the events as a **timeline or table**:
  - Each row shows: timestamp, mode badge (`sparse` = green,
    `fallback-full-registry` = amber), top_score, candidates_considered vs
    candidates_returned, selected_tool_ids (as chips/tags)
  - Expandable payload detail (click to expand → show full payload JSON)
- Empty state: "No routing events found for this mission"
- Loading state while fetching events
- Refresh button

#### Section B: Routing Playground (secondary)

- A `<textarea>` for task text input (placeholder: "Describe a task to route…")
- Optional `<select>` or `<input type="number">` for `k` (top-k, default 8)
- Submit button → POST `/api/tool-routing/route`
- **Before submitting:** validate that `session.user.id` and
  `activeWorkspace.id` are available. If not, show toast error and abort.
- Render results as a **ranked list of scored tools**:
  - Each tool: tool_id, score (with progress bar), reasons array, component
    breakdown
  - Show mode badge and summary stats (candidates_considered,
    candidates_returned, top_score)
- Loading state during POST
- Error toast on failure
- Clear/reset button

### 2. i18n keys

Add a `toolRouting` namespace to ALL 5 locale files:
`src/i18n/locales/{en,de,es,fr,ja}.json`

Minimum keys needed (translate properly for each language):
```json
{
  "toolRouting": {
    "metaTitle": "Tool Routing Inspector — FlowManner",
    "metaDescription": "Audit trail and playground for AI tool routing decisions",
    "title": "Tool Routing Inspector",
    "subtitle": "Inspect routing decisions and test tool selection",
    "auditTrail": "Audit Trail",
    "auditTrailDescription": "Routing decisions for each mission",
    "selectMission": "Select a mission",
    "noMissionSelected": "Select a mission to view routing events",
    "noEvents": "No routing events found for this mission",
    "loadEventsError": "Failed to load routing events",
    "loadMissionsError": "Failed to load missions",
    "playground": "Routing Playground",
    "playgroundDescription": "Test tool routing for a task description",
    "taskPlaceholder": "Describe a task to route…",
    "topK": "Top K",
    "route": "Route",
    "routing": "Routing…",
    "clear": "Clear",
    "sessionError": "Session or workspace not available — please reload",
    "routeError": "Failed to route tools",
    "taskRequired": "Please enter a task description",
    "mode": "Mode",
    "sparse": "Sparse",
    "fallback": "Full Registry Fallback",
    "topScore": "Top Score",
    "candidatesConsidered": "Candidates Considered",
    "candidatesReturned": "Candidates Returned",
    "selectedTools": "Selected Tools",
    "scoreBreakdown": "Score Breakdown",
    "components": "Components",
    "reasons": "Reasons",
    "noResults": "Submit a task to see routing results",
    "timestamp": "Timestamp",
    "actor": "Actor",
    "refresh": "Refresh"
  }
}
```

### 3. Navigation

Add a nav entry to `src/components/layout/nav-config.ts`. The `tools` group in
`topTier` already has "Tools", "Tools Hub", and "Memory Inspector". Add a
"Tool Routing" entry there:

```typescript
{
  id: "tools",
  labelKey: "nav.tools",
  items: [
    { labelKey: "nav.tools", href: "/tools" },
    { labelKey: "nav.toolsHub", href: "/tools/catalog" },
    { labelKey: "nav.memoryInspector", href: "/memory-inspector" },
    { labelKey: "nav.toolRouting", href: "/tool-routing" },  // ADD THIS
  ],
},
```

Also add the `nav.toolRouting` translation key to all 5 locale files under the
existing `nav` namespace (e.g. `"toolRouting": "Tool Routing"` for en).

## Must do

- Match the existing codebase style exactly (glass-card, btn-clay, lucide-react
  icons, sonner toasts, next-intl translations).
- Use TypeScript interfaces for both API response shapes (define them inline in
  the client component — infer from `tool_routing.py` and
  `tool_routing_models.py`).
- Handle loading and error gracefully for BOTH sections independently.
- The mission selector and playground should NOT block each other — they are
  independent sections on the same page.
- `npx tsc --noEmit` must pass after your changes.
- `npx vitest run` must pass (no test regressions).
- Commit message: `feat(frontend): add tool routing inspector with audit trail and playground`

## Must NOT do

- Do NOT modify any backend files.
- Do NOT run `deploy-frontend.sh` or any deploy commands.
- Do NOT create test files — this is a UI page, not a test task.
- Do NOT add new npm dependencies — use what's already installed.
- Do NOT touch `.env` or credential files.
- Do NOT use `as any` type assertions.
- Do NOT create separate API client files — use `apiClient` from `@/lib/api-client`
  directly in the component.
- Do NOT ask the user to type `workspace_id` or `user_id` — derive from session
  and workspace store.
- Do NOT use `React.FC` — use plain function components (`export default function X()`).

## Acceptance criteria

- [ ] `src/app/[locale]/(dashboard)/tool-routing/page.tsx` exists
- [ ] `src/app/[locale]/(dashboard)/tool-routing/page-client.tsx` exists
- [ ] Audit trail section fetches `GET /api/missions/{mission_id}/tool-routing-events`
- [ ] Audit trail has mission selector dropdown (populated from `/api/missions`)
- [ ] Playground section calls `POST /api/tool-routing/route` with session-derived `workspace_id` + `user_id`
- [ ] Playground validates session/workspace before submit (shows toast if missing)
- [ ] `toolRouting` i18n namespace added to all 5 locale files
- [ ] `nav.toolRouting` key added to `nav` namespace in all 5 locale files
- [ ] Nav entry added to `tools` group in `nav-config.ts`
- [ ] `npx tsc --noEmit` passes
- [ ] `npx vitest run` passes
- [ ] Loading/error states handled for both sections independently

## When done

Report:
- Files created/modified (list)
- `npx tsc --noEmit` output (pass/fail)
- `npx vitest run` output (pass/fail)
- Any blockers or notes

Do NOT push to origin. Glenn reviews, then Hermes verifies and commits.
