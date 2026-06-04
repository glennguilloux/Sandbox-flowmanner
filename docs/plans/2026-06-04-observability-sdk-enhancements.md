# FlowManner Observability & SDK Enhancements

**Status:** Draft
**Date:** June 4, 2026
**Based on:** Deep Research Report (DEEP-RESEARCH-REPORT.md) + codebase audit

**Goal:** Close the gaps between FlowManner's existing observability/cost/SDK infrastructure and what the report recommends as P0 differentiation features.

---

## Already Exists (DO NOT rebuild)

The deep research report recommended building three P0 features. **All three already exist** in substantial form. This plan covers the *gaps* that would make them competitive with LangSmith / Langfuse / Vercel.

| Feature | Status | Key Files |
|---------|--------|-----------|
| Mission trace viewer | **509-line component**, event timeline, filtering, LLM call details, circuit breaker/HITL/budget panels | `frontend/src/components/observatory/mission-observatory.tsx` |
| Cost dashboard | **200-line component**, total tokens/cost, timeseries table, model breakdown, period selector | `frontend/src/components/analytics/AnalyticsDashboard.tsx` |
| Python SDK | **1452 auto-generated files**, AuthenticatedClient, mission CRUD, tasks, logs, agents, browser | `sdk-python/flowmanner-api-client/` |
| LLM call records | Full model: model_id, provider, tokens, cost_usd, latency_ms, agent_id, workspace_id | `backend/app/models/llm_call_record.py` |
| Cost attribution engine | Aggregation by agent, mission, user, workspace, period | `backend/app/observability/cost_engine.py` |
| Langfuse integration | LiteLLM success/failure callbacks, gauge metrics | `backend/app/services/langfuse_service.py` |
| Cost analytics API | `GET /api/v2/dashboard/costs` — total_cost, by_agent, by_model | `backend/app/api/v2/dashboard.py` |
| Usage analytics API | `GET /api/v1/usage/summary|timeseries|breakdown` | `backend/app/api/v1/analytics.py` |
| Substrate events API | `GET /api/v1/missions/{id}/events` + replay-state | `backend/app/api/v1/`, `frontend/src/lib/api/substrate.ts` |
| Workspace billing | `GET /api/v3/workspaces/{id}/billing` — tier, limits, subscription | `backend/app/api/v3/workspace_billing.py` |

---

## Architecture Overview

```
Phase 1 ─── Trace Viewer Waterfall View ─── LangSmith-parity visualization
Phase 2 ─── Cost Dashboard Charts ───────── Vercel-parity cost UX
Phase 3 ─── Python SDK Polish & Publish ─── pip install flowmanner
     │
     └── Independent phases, can run in parallel
```

---

## Phase 1: Trace Viewer — Waterfall & Cost Aggregation

> **Why first:** The observatory timeline exists but is a flat list. LangSmith/Langfuse differentiate with hierarchical waterfall views and per-span cost attribution. This is the highest-impact gap to close.

**Severity:** Medium-High (competitive parity)

### Task 1.1: Add cost/time aggregation summary to observatory header

**Objective:** Show total cost, total tokens, and total duration prominently in the observatory header (currently only shows status, events, completed, tokens).

**Files:**
- Modify: `frontend/src/components/observatory/mission-observatory.tsx` (line ~384-414, SummaryCard grid)

**What to add:**
- Add "Total Cost" card using `replayState.state?.total_cost_usd` (already available, just not displayed)
- Add "Duration" card computed from `replayState.state?.started_at` to `last_event_at`
- Add cost-per-task average stat

**Acceptance criteria:**
- [ ] Observatory header shows 6 cards: Status, Events, Completed, Tokens, Cost, Duration
- [ ] Cost card formats as `$X.XXXX` (4 decimal places)
- [ ] Duration card auto-formats (ms/s/m)

### Task 1.2: Add waterfall/Gantt view toggle

**Objective:** Add a toggle between the current "Timeline" (flat list) and a new "Waterfall" view that shows LLM calls as horizontal bars on a time axis, revealing parallelism and bottlenecks.

**Files:**
- Create: `frontend/src/components/observatory/waterfall-view.tsx` (~150 lines)
- Modify: `frontend/src/components/observatory/mission-observatory.tsx` (add toggle)

**What to add:**
- Toggle button: "Timeline | Waterfall" (next to the existing Filters button)
- Waterfall view: each event = one row, bar width = duration, x-axis = time
- Color-code by event type (reuse existing EVENT_COLORS)
- Hover tooltip: event label, duration, cost, tokens
- Only show events with duration info (LLM calls, tool calls, tasks)

**Implementation note:**
- Use pure CSS/divs for bars (no charting library needed). Each bar is `position: absolute` with `left: offset%` and `width: duration%` relative to the mission's total duration.
- The substrate events already have `timestamp` — compute duration from the gap to the next event of the same type, or use the `payload.latency_ms` for LLM calls.

**Acceptance criteria:**
- [ ] Toggle switches between Timeline and Waterfall
- [ ] Waterfall renders LLM calls as colored bars on time axis
- [ ] Hover shows: model, tokens, cost, latency
- [ ] Filter chips apply to waterfall view too

### Task 1.3: Add per-event cost breakdown in expanded view

**Objective:** When expanding an LLM call event, show input/output token cost breakdown (currently shows raw tokens but not the cost calculation).

**Files:**
- Modify: `frontend/src/components/observatory/mission-observatory.tsx` (line ~237-266, LLM call expanded section)

**What to add:**
- Show "Input: X tokens × $Y/1K = $Z" and "Output: A tokens × $B/1K = $C"
- Show "Total: $D" (already exists, keep it)
- The cost data is already in `payload.cost_usd` — just needs the per-token breakdown

**Note:** Token pricing data is NOT in the payload. For Phase 1, just show total cost + tokens. Per-token pricing breakdown is a Phase 2 enhancement that requires backend pricing tables.

**Acceptance criteria:**
- [ ] Expanded LLM call shows prompt tokens, completion tokens, and total cost
- [ ] Values are properly formatted (locale-aware numbers, 4-decimal cost)

### Task 1.4: Add Langfuse trace link

**Objective:** Each mission in the observatory should link to its Langfuse trace page if Langfuse is configured.

**Files:**
- Modify: `frontend/src/components/observatory/mission-observatory.tsx` (header area)
- Backend: Add `langfuse_trace_url` to replay-state response (optional, can construct client-side if LANGFUSE_HOST is known)

**What to add:**
- External link button in observatory header: "View in Langfuse →"
- Link opens `LANGFUSE_HOST/projects/{project}/traces/{mission_id}`
- Hide button if Langfuse is not configured (check env var or add a `langfuse_enabled` flag to the API response)

**Acceptance criteria:**
- [ ] "View in Langfuse" button appears when Langfuse is configured
- [ ] Button opens Langfuse trace page in new tab
- [ ] Button hidden when Langfuse is not configured

---

## Phase 2: Cost Dashboard — Charts & Per-Workspace

> **Why:** Current dashboard has tables and progress bars but no actual charts. Adding visual charts (line for trend, donut for model breakdown) brings it to Vercel/Linear parity. Per-workspace view is needed for multi-tenant B2B.

**Severity:** Medium

### Task 2.1: Replace timeseries table with a line chart

**Objective:** Replace the "Usage Over Time" table with an actual SVG line chart showing tokens and cost over time.

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsDashboard.tsx` (line ~140-170, timeseries section)
- Create: `frontend/src/components/analytics/usage-chart.tsx` (~80 lines)

**What to add:**
- Pure SVG line chart (no charting library — keep dependencies minimal)
- Dual-axis: tokens (left, blue) and cost (right, green)
- X-axis: dates from `timeseries[].timestamp`
- Hover crosshair showing exact values
- Responsive width (use `viewBox`)

**Acceptance criteria:**
- [ ] Line chart renders for both tokens and cost
- [ ] Hover shows date, tokens, and cost
- [ ] Chart is responsive (mobile-friendly)
- [ ] Falls back to table if < 2 data points

### Task 2.2: Replace model breakdown progress bars with a donut chart

**Objective:** Replace the horizontal progress bars with a donut chart showing cost distribution by model.

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsDashboard.tsx` (line ~172-200, breakdown section)
- Create: `frontend/src/components/analytics/cost-donut.tsx` (~60 lines)

**What to add:**
- SVG donut chart with color-coded segments per model
- Center label: total cost
- Legend on the right showing model name + cost + percentage
- Click segment to highlight

**Acceptance criteria:**
- [ ] Donut chart renders with correct proportions
- [ ] Center shows total cost
- [ ] Legend lists each model with cost and percentage
- [ ] Works with 1 to N models

### Task 2.3: Add per-workspace cost breakdown

**Objective:** If the user has multiple workspaces, show a workspace selector and cost breakdown per workspace.

**Files:**
- Modify: `backend/app/api/v2/dashboard.py` — add `workspace_id` query param to `/costs` endpoint
- Modify: `frontend/src/components/analytics/AnalyticsDashboard.tsx` — add workspace selector

**Backend change:**
```python
@router.get("/costs")
async def get_cost_analytics(
    period: str = Query("month"),
    workspace_id: str | None = Query(None),  # NEW
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # If workspace_id provided, filter LLMCallRecord by workspace_id
    # (LLMCallRecord already has workspace_id column)
```

**Frontend change:**
- Fetch workspaces list (existing API)
- Add dropdown: "All Workspaces" | "Workspace A" | "Workspace B"
- Re-fetch data when workspace changes

**Acceptance criteria:**
- [ ] Backend `/costs?workspace_id=X` returns costs scoped to that workspace
- [ ] Frontend workspace selector appears when user has >1 workspace
- [ ] Switching workspace re-fetches and updates all dashboard sections

### Task 2.4: Add cost trend indicator (up/down vs last period)

**Objective:** Show whether costs are trending up or down compared to the previous period.

**Files:**
- Modify: `backend/app/api/v2/dashboard.py` — extend `CostAnalyticsResponse` with `previous_period_cost` and `trend_percentage`
- Modify: `frontend/src/components/analytics/AnalyticsDashboard.tsx`

**Backend change:**
- Compute previous period cost (same duration, shifted back)
- Return `previous_period_cost` and `trend_pct` in response

**Frontend change:**
- Show ↑/↓ arrow with percentage next to "Total Cost" stat card
- Green for down, red for up

**Acceptance criteria:**
- [ ] Trend arrow appears next to total cost
- [ ] Percentage is correct (e.g., "+15.2%" or "-8.3%")
- [ ] Color-coded (green/red)

---

## Phase 3: Python SDK — Polish & Publish

> **Why:** SDK already exists (1452 auto-generated files) but is unpublishable: no high-level wrapper, no docs, not on PyPI. Publishing it signals "API-first" and unlocks CI/CD integration.

**Severity:** Medium

### Task 3.1: Add high-level convenience wrapper

**Objective:** Add a `FlowmannerClient` class that wraps the auto-generated low-level API with a clean, Pythonic interface.

**Files:**
- Create: `sdk-python/flowmanner_api_client/high_level.py` (~150 lines)

**What to add:**
```python
class FlowmannerClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        self._client = AuthenticatedClient(
            base_url=base_url,
            token=api_key or os.environ.get("FLOWMANNER_API_KEY", ""),
        )

    # Missions
    def create_mission(self, title: str, template: str | None = None, ...) -> Mission: ...
    def get_mission(self, mission_id: str) -> Mission: ...
    def execute_mission(self, mission_id: str, input: str | None = None) -> str: ...
    def get_mission_status(self, mission_id: str) -> str: ...
    def list_missions(self, limit: int = 20) -> list[Mission]: ...

    # Analytics
    def get_cost_analytics(self, period: str = "month") -> CostAnalytics: ...
    def get_mission_events(self, mission_id: str) -> list[Event]: ...

    # Context manager support
    def __enter__(self): return self
    def __exit__(self, *args): self._client.__exit__(*args)
```

**Acceptance criteria:**
- [ ] `FlowmannerClient` works with API key from env var or constructor
- [ ] Mission CRUD + execute works end-to-end against live API
- [ ] Context manager support (`with FlowmannerClient(...) as fm:`)

### Task 3.2: Add example scripts and quickstart docs

**Objective:** Add working example scripts that new users can copy-paste.

**Files:**
- Create: `sdk-python/examples/quickstart.py`
- Create: `sdk-python/examples/create_and_run_mission.py`
- Create: `sdk-python/examples/cost_analytics.py`
- Rewrite: `sdk-python/README.md` (currently generic auto-generated boilerplate)

**What the README should contain:**
```markdown
# FlowManner Python SDK

pip install flowmanner-api-client

## Quick Start
[10-line example: connect, create mission, execute, check status]

## Creating a Mission
[Full example with all options]

## Monitoring Costs
[Cost analytics example]

## API Reference
[Link to auto-generated docs]
```

**Acceptance criteria:**
- [ ] README has a 10-line quickstart that works
- [ ] 3 example scripts covering: basic CRUD, execution, analytics
- [ ] Examples run against the live API (or mock server)

### Task 3.3: Add `flowmanner` console entry point

**Objective:** Add a minimal CLI so users can check their setup and costs from terminal.

**Files:**
- Create: `sdk-python/flowmanner_api_client/cli.py` (~80 lines)
- Modify: `sdk-python/pyproject.toml` — add `[tool.poetry.scripts]` entry

**What to add:**
```bash
flowmanner status          # Check API connectivity + auth
flowmanner costs           # Show this month's costs
flowmanner missions list   # List recent missions
```

**Acceptance criteria:**
- [ ] `pip install flowmanner-api-client` installs `flowmanner` command
- [ ] `flowmanner status` works and shows connection info
- [ ] `flowmanner costs` shows total cost for current month

### Task 3.4: Publish to TestPyPI (dry run)

**Objective:** Verify the package builds and installs cleanly before publishing to real PyPI.

**Files:**
- Modify: `sdk-python/pyproject.toml` — add proper metadata (authors, license, homepage)

**Steps:**
1. `cd sdk-python && poetry build`
2. `poetry publish -r testpypi` (TestPyPI)
3. `pip install -i https://test.pypi.org/simple/ flowmanner-api-client`
4. Verify import works: `python -c "from flowmanner_api_client import AuthenticatedClient"`

**Acceptance criteria:**
- [ ] `poetry build` produces wheel + sdist without errors
- [ ] Package installs from TestPyPI
- [ ] Import works in a clean virtualenv

---

## Dependency Graph

```
Phase 1: Trace Viewer (no dependencies, can start immediately)
  ├── 1.1 Cost/time in header → independent
  ├── 1.2 Waterfall view → independent
  ├── 1.3 Per-event cost breakdown → independent
  └── 1.4 Langfuse link → independent

Phase 2: Cost Dashboard (no dependencies, can run parallel to Phase 1)
  ├── 2.1 Line chart → independent
  ├── 2.2 Donut chart → independent
  ├── 2.3 Per-workspace → needs backend change first
  └── 2.4 Trend indicator → needs backend change first

Phase 3: Python SDK (no dependencies, can run parallel to Phases 1-2)
  ├── 3.1 High-level wrapper → independent
  ├── 3.2 Examples + docs → depends on 3.1
  ├── 3.3 CLI entry point → depends on 3.1
  └── 3.4 TestPyPI publish → depends on 3.1 + 3.2
```

---

## Effort Estimate

| Phase | Tasks | Estimated time | Complexity |
|-------|-------|---------------|------------|
| Phase 1: Trace Viewer | 4 tasks | 3-4 days | Medium |
| Phase 2: Cost Dashboard | 4 tasks | 2-3 days | Low-Medium |
| Phase 3: Python SDK | 4 tasks | 2-3 days | Low |
| **Total** | **12 tasks** | **7-10 days** | |

---

## Quick Wins (< 1 hour each)

1. **Task 1.1** — Add cost/duration to observatory header. ~20 lines of JSX, data already available.
2. **Task 1.3** — Token/cost formatting in expanded LLM view. ~10 lines change.
3. **Task 2.4** — Trend indicator (backend returns previous_period_cost, frontend adds arrow).

---

## What This Plan Does NOT Cover (Deferred)

From the deep research report, these items are intentionally deferred:

- **HITL approval gates** — already partially designed (PAUSED status exists), needs backend state machine work
- **Eval harness** — requires golden datasets + quality metrics infrastructure
- **Template marketplace** — needs 20+ templates first
- **Multi-agent debate/consensus** — research-phase, not ready for implementation
- **Temporal migration** — Celery is fine at current scale

---

## Execution Strategy

These three phases are independent and can be assigned to different agents or worked sequentially. Recommended order:

1. **Phase 1 first** (highest competitive impact — trace viewer is the #1 differentiator)
2. **Phase 3 second** (SDK publish is low effort, high signal value)
3. **Phase 2 last** (dashboard polish is nice-to-have but less urgent)

Each task within a phase can be delegated to a subagent or worker independently.
