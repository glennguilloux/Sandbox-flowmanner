# DEEPSEEK TASK 15: Hermes Dashboard — Run Inspector with Live SSE Streaming

## Depends On
- TASK-14 (API Server Bridge) — the `/api/runs/*` proxy endpoints must exist first

## Context

Now that the bridge exists (TASK-14), this task adds a **Run Inspector** tab to the dashboard frontend — a live view of agent runs with progress streaming, tool call display, approval controls, and stop/kill actions.

## Files

The Hermes dashboard frontend is a **Vite/React** app (not Next.js). It lives under:

```
~/.hermes/hermes-agent/web/src/
├── App.tsx                  # Route registry: BUILTIN_ROUTES_CORE + BUILTIN_NAV_REST
├── pages/
│   ├── SessionsPage.tsx     # ← follow this pattern for the new RunsPage
│   ├── AnalyticsPage.tsx
│   ├── CronPage.tsx
│   ├── LogsPage.tsx
│   ├── SkillsPage.tsx
│   ├── ConfigPage.tsx       # (loaded lazily)
│   └── ...                  # 12+ page components
├── components/              # Shared UI components
└── hooks/                   # Custom React hooks
```

## Step 1: Register the tab in App.tsx

Add the new page to `BUILTIN_ROUTES_CORE` (line 108 of `web/src/App.tsx`):

```typescript
// ~/.hermes/hermes-agent/web/src/App.tsx
import RunsPage from "./pages/RunsPage";

const BUILTIN_ROUTES_CORE: Record<string, ComponentType> = {
  "/": RootRedirect,
  "/sessions": SessionsPage,
  "/runs": RunsPage,      // ← ADD THIS
  "/analytics": AnalyticsPage,
  // ...rest unchanged
};
```

Add the nav item to `BUILTIN_NAV_REST` (line 131):

```typescript
const BUILTIN_NAV_REST: NavItem[] = [
  // ...existing items...
  {
    path: "/runs",
    labelKey: "runs",
    label: "Runs",
    icon: Play,           // or Activity, Zap, Terminal
  },
  // ...rest unchanged...
];
```

Ensure `Play` (or whatever icon you choose) is in `ICON_MAP` at line 165.

The API server check goes in the main nav — if the API server is offline, show a yellow badge on the Runs nav icon.

## Step 2: Create the RunsPage component

Create `~/.hermes/hermes-agent/web/src/pages/RunsPage.tsx`. Follow the same pattern as `SessionsPage.tsx` — no special state management libs, just React hooks (`useState`, `useEffect`, `useCallback`).

The page has three areas:

```
┌──────────────────────────────────────────────────────────────┐
│ Run Inspector                                        [+ New] │
├──────────────────┬───────────────────────────────────────────┤
│ Active Runs       │ Run Detail (select one)                  │
│                  │                                           │
│ ● run-abc123     │ Status: Running (23s)                     │
│   "Search..."    │ ──────────────────────                     │
│   web tool       │ [14:32:01] Run submitted                   │
│                  │ [14:32:02] Loading skill: web-researcher   │
│ ○ run-def456     │ [14:32:05] 🛠 search("price of X")         │
│   "Summarize..." │ [14:32:07] Result: 3 pages...             │
│   skill=summarize│ [14:32:10] 💭 Thinking...                  │
│                  │ [14:32:12] "The price is..."               │
│                  │ ──────────────────────                     │
│                  │                    [Stop] [New Run]        │
├──────────────────┴───────────────────────────────────────────┤
│ Pending Approvals                                 (1)        │
│ ─────────────────────────────────────────────                  │
│ run-abc123 needs approval for:                                │
│   Command: rm -rf /tmp/build-cache/                           │
│   [Approve] [Deny] [View Context]                             │
└──────────────────────────────────────────────────────────────┘
```

### State structure

```typescript
interface Run {
  id: string;
  prompt: string;
  status: "running" | "completed" | "cancelled" | "error" | "pending_approval";
  created_at: string;
  skills: string[];
  model: string;
  max_turns: number;
}

interface RunEvent {
  type: "thinking" | "tool_call" | "tool_result" | "approval_request" | "error" | "complete";
  data: any;
  timestamp?: string;
  sequence?: number;
}

interface PendingApproval {
  runId: string;
  prompt: string;
  action: string;
  context: string;
}
```

### Step 3: SSE Event Stream

This is the core feature. Use the browser-native `EventSource` API:

```typescript
const [events, setEvents] = useState<RunEvent[]>([]);
const [eventSource, setEventSource] = useState<EventSource | null>(null);
const [connectionStatus, setConnectionStatus] = useState<"connected" | "disconnected" | "reconnecting">("disconnected");

function connectToRunEvents(runId: string) {
  // Close any existing connection first
  if (eventSource) {
    eventSource.close();
  }

  const es = new EventSource(`/api/runs/${runId}/events`);

  es.onopen = () => setConnectionStatus("connected");

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      setEvents(prev => [...prev, {
        type: data.type || "unknown",
        data: data,
        timestamp: data.timestamp || new Date().toISOString(),
        sequence: data.sequence,
      }]);
    } catch (e) {
      // Keep raw data for non-JSON SSE frames
      setEvents(prev => [...prev, {
        type: "raw" as any,
        data: event.data,
      }]);
    }
  };

  es.onerror = () => {
    setConnectionStatus("reconnecting");
    // EventSource auto-reconnects — just update UI
  };

  setEventSource(es);
}

// Cleanup on unmount
useEffect(() => {
  return () => {
    if (eventSource) {
      eventSource.close();
    }
  };
}, []);
```

**Event type rendering:**

| `data.type` | Display |
|-------------|---------|
| `thinking` | 💭 "Agent is thinking..." with animated dots |
| `tool_call` | `🛠 tool_name(param1=val1, ...)` collapsible card |
| `tool_result` | Collapsible card with truncated result + "Show more" |
| `approval_request` | Red-tinted card: "Needs approval: {action}" + [Approve] [Deny] buttons |
| `error` | ❌ Red card with error message |
| `complete` | ✅ Green checkmark + summary |
| `cancelled` | ⏹ Grey card "Run cancelled" |

### Step 4: Polling fallback

If the EventSource disconnects for >10 seconds without reconnecting, fall back to polling:

```typescript
const [pollInterval, setPollInterval] = useState<NodeJS.Timeout | null>(null);

function startPolling(runId: string) {
  const interval = setInterval(async () => {
    try {
      const resp = await fetch(`/api/runs/${runId}`);
      const data = await resp.json();
      if (data.status) {
        setEvents(prev => [...prev, {
          type: "status_poll",
          data: { status: data.status, ...data },
          timestamp: new Date().toISOString(),
        }]);
      }
    } catch (e) {
      // API server offline — show banner
    }
  }, 3000);
  setPollInterval(interval);
}

// Auto-switch to polling after SSE failure
useEffect(() => {
  if (connectionStatus === "reconnecting") {
    const timer = setTimeout(() => {
      if (connectionStatus === "reconnecting") {
        startPolling(selectedRunId);
      }
    }, 10000);
    return () => clearTimeout(timer);
  }
}, [connectionStatus]);
```

### Step 5: Run controls

```typescript
async function stopRun(runId: string) {
  await fetch(`/api/runs/${runId}`, { method: "DELETE" });
}

async function approveRun(runId: string, approved: boolean, reason?: string) {
  await fetch(`/api/runs/${runId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, reason: reason || "" }),
  });
}
```

### Step 6: New Run form

A minimal modal or inline form:

```typescript
async function createRun(prompt: string, skills?: string[], model?: string, maxTurns?: number) {
  const resp = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      skills: skills || [],
      model: model || undefined,
      max_turns: maxTurns || 30,
    }),
  });
  const data = await resp.json();
  // Add to active runs list, select it, open SSE stream
}
```

### Step 7: Capabilities-aware rendering

Check at mount whether the API server supports runs:

```typescript
const [runsEnabled, setRunsEnabled] = useState<boolean | null>(null);

useEffect(() => {
  fetch("/api/server/capabilities")
    .then(r => r.json())
    .then(caps => setRunsEnabled(caps?.run_submission === true))
    .catch(() => setRunsEnabled(false));
}, []);
```

If `runsEnabled === false`, show the offline banner.

### Step 8: Poll the active runs list

```typescript
const [runs, setRuns] = useState<Run[]>([]);

useEffect(() => {
  const interval = setInterval(async () => {
    try {
      const resp = await fetch("/api/runs");
      const data = await resp.json();
      if (Array.isArray(data)) {
        setRuns(data);
      }
    } catch (e) {
      // Silent fail — banner handles this
    }
  }, 5000); // Poll every 5s for active runs list

  return () => clearInterval(interval);
}, []);
```

A newly submitted run should also be added to the local state immediately (before the next poll).

## Verification

1. Open `http://127.0.0.1:9119/runs` in the browser
2. If API server is offline: see yellow "API Server Offline" banner
3. Submit a new run from the [+ New] form
4. Watch events stream live in the detail pane
5. Click [Stop] — run should show as cancelled
6. If an approval_request event arrives, [Approve] or [Deny] should work
7. Kill the API server mid-stream — see "Reconnecting..." indicator
8. Restart the API server — verify auto-reconnection

## Pitfalls

- **EventSource uses GET only.** The SSE endpoint at `/api/runs/{id}/events` must be a GET. Auth is via session cookie (the dashboard's existing auth model), not Authorization header. The browser's EventSource API doesn't support custom headers — so auth must come from the session cookie.
- **Cleanup on unmount** — Always close EventSource and clear poll intervals in useEffect cleanup. Opening multiple EventSources to different runs leaks connections.
- **CSS for event types** — Use color-coding (green for complete, red for error, blue for tool_call, yellow for approval) to make the event log scannable at a glance.
- **Event ordering** — SSE events can arrive out of order. Use `data.sequence` if available to sort.
- **Approval race conditions** — If two tabs open the same run, both show approval buttons. First click wins; second gets a 409. Show "Already handled" for stale buttons.
- **Long event logs** — Cap the in-memory event array at ~500 events and add a "Load older" button or scroll pagination.
- **Time formatting** — Show relative time ("23s ago", "2m ago") with a timer that updates every second for active runs.
