# FlowManner Observability & Moat Roadmap

**Status:** Draft
**Date:** June 4, 2026
**Sources:** Deep Research Report + GPT-5.6 strategic analysis + codebase audit

**Goal:** Ship the features that turn FlowManner from "workflow tool" into "operating system for autonomous work." The key insight: FlowManner already has the hardest infrastructure (append-only event log, replay engine, CQRS). The competitive moat comes from features that leverage this infrastructure in ways competitors can't copy quickly.

---

## Strategic Hierarchy

```
PHASE 0 ── Replay Assertions + Intervention Distance
│           THE MOAT. Unique to FlowManner. 3-5 days.
│           "Record expected behavior → detect regressions → measure autonomy"
│
PHASE 1 ── Trace Viewer Polish ─── Competitive parity (LangSmith/Langfuse)
PHASE 2 ── Cost Dashboard Charts ─ Competitive parity (Vercel/Linear)
PHASE 3 ── Python SDK Publish ──── Distribution + CI/CD integration signal
│
│           Phases 1-3 are independent and can run parallel to Phase 0.
```

**Why Phase 0 first:** The trace viewer and cost dashboard bring you to parity. Replay assertions create a category nobody else competes in. Parity features can ship after the moat.

---

## Already Exists (DO NOT rebuild)

| Feature | Status | Key Files |
|---------|--------|-----------|
| Mission trace viewer | **509-line component**, event timeline, filtering, LLM call details, circuit breaker/HITL/budget panels | `frontend/src/components/observatory/mission-observatory.tsx` |
| Cost dashboard | **200-line component**, total tokens/cost, timeseries table, model breakdown, period selector | `frontend/src/components/analytics/AnalyticsDashboard.tsx` |
| Python SDK | **1452 auto-generated files**, AuthenticatedClient, mission CRUD, tasks, logs, agents, browser | `sdk-python/flowmanner-api-client/` |
| LLM call records | Full model: model_id, provider, tokens, cost_usd, latency_ms, agent_id, workspace_id | `backend/app/models/llm_call_record.py` |
| Cost attribution engine | Aggregation by agent, mission, user, workspace, period | `backend/app/observability/cost_engine.py` |
| Substrate event log | **Append-only** (PG trigger enforced), event types: mission/node lifecycle, LLM calls, tool calls, HITL, circuit breaker, budget | `backend/app/models/substrate_models.py` |
| Replay engine | Rebuild state from events, time-travel debugging (any sequence), determinism verification | `backend/app/services/substrate/replay_engine.py` |
| SubstrateRunState | In-memory projection: status, task_states, completed/failed, total_tokens, total_cost_usd | `backend/app/models/substrate_models.py` |
| Mission templates | JSONB default_plan, default_tasks, default_constraints | `backend/app/models/mission_advanced_models.py` |
| Mission versions | Immutable snapshots with plan, tasks_snapshot, constraints | `backend/app/models/mission_advanced_models.py` |
| Cost analytics API | `GET /api/v2/dashboard/costs` — total_cost, by_agent, by_model | `backend/app/api/v2/dashboard.py` |
| Usage analytics API | `GET /api/v1/usage/summary|timeseries|breakdown` | `backend/app/api/v1/analytics.py` |
| Substrate events API | `GET /api/v1/missions/{id}/events` + replay-state | `backend/app/api/v1/`, `frontend/src/lib/api/substrate.ts` |
| Langfuse integration | LiteLLM success/failure callbacks, gauge metrics | `backend/app/services/langfuse_service.py` |

---

## Phase 0: Replay Assertions + Intervention Distance

> **Why first:** This is the moat. FlowManner's event-sourced substrate + replay engine is the hardest piece to build, and it's already done. The features below turn that infrastructure into a product surface that no competitor offers. Everything in Phases 1-3 can be copied in a sprint. This cannot.

**Severity:** Critical (strategic differentiator)

### Task 0.1: Define ExpectedBehavior schema and store in mission templates

**Objective:** Add an `expected_behaviors` JSONB field to MissionTemplate that defines assertions a successful mission run should satisfy. These are recorded once (manually or auto-extracted from a successful run) and then validated on every subsequent run.

**Files:**
- Create: `backend/app/models/expected_behavior.py` (~60 lines)
- Modify: `backend/app/models/mission_advanced_models.py` — add field to MissionTemplate
- Create: `backend/app/alembic/versions/xxx_add_expected_behaviors.py`

**Schema:**

```python
class ExpectedBehavior:
    """Stored in MissionTemplate.expected_behaviors (JSONB array)."""
    
    # Each item is one assertion. Types:
    
    # 1. Tool sequence assertion
    {
        "type": "tool_sequence",
        "expected_tools": ["search_docs", "extract_content", "summarize"],
        "order": "exact" | "subset" | "any",
        "max_calls_per_tool": {"search_docs": 3}  # optional
    }
    
    # 2. Cost ceiling assertion
    {
        "type": "cost_ceiling",
        "max_cost_usd": 0.50,
        "warn_at_pct": 80  # warn at 80% of ceiling
    }
    
    # 3. Latency assertion
    {
        "type": "latency",
        "max_duration_seconds": 120,
        "warn_at_pct": 80
    }
    
    # 4. Task completion assertion
    {
        "type": "task_completion",
        "min_tasks_completed": 3,
        "max_tasks_failed": 0
    }
    
    # 5. No-error assertion
    {
        "type": "no_circuit_breaker",
        "description": "Circuit breaker should not trip"
    }
```

**Migration:**
```sql
ALTER TABLE mission_templates 
ADD COLUMN expected_behaviors JSONB DEFAULT '[]'::jsonb;
```

**Acceptance criteria:**
- [ ] Migration adds column without data loss
- [ ] MissionTemplate model exposes `expected_behaviors` as `Mapped[list | None]`
- [ ] API endpoint to GET/SET expected behaviors on a template
- [ ] Default to empty list (backward compatible)

### Task 0.2: Build ReplayAssertionEngine — validate replay state against expected behaviors

**Objective:** A service that takes a completed run's replay state + event log and checks each expected behavior assertion. Returns a structured report of passes/failures/warnings.

**Files:**
- Create: `backend/app/services/substrate/assertion_engine.py` (~200 lines)
- Create: `backend/app/tests/test_assertion_engine.py` (~150 lines)

**Core logic:**

```python
class AssertionResult:
    assertion_type: str
    passed: bool
    severity: "failure" | "warning" | "info"
    actual: dict       # what actually happened
    expected: dict     # what was expected
    message: str       # human-readable

class ReplayAssertionEngine:
    async def evaluate(
        self,
        db: AsyncSession,
        run_id: str,
        expected_behaviors: list[dict],
    ) -> list[AssertionResult]:
        """Replay events, check each assertion, return results."""
        
        # 1. Replay events for the run
        state = await replay_engine.rebuild_state(db, run_id)
        events = await event_log.get_events(db, run_id)
        
        # 2. Evaluate each assertion
        results = []
        for assertion in expected_behaviors:
            match assertion["type"]:
                case "tool_sequence":
                    results.append(self._check_tool_sequence(events, assertion))
                case "cost_ceiling":
                    results.append(self._check_cost(state, assertion))
                case "latency":
                    results.append(self._check_latency(state, assertion))
                case "task_completion":
                    results.append(self._check_completion(state, assertion))
                case "no_circuit_breaker":
                    results.append(self._check_no_circuit_breaker(events, assertion))
        
        return results
```

**Tool sequence checking:**
- Extract all `tool.call` events, get tool names from payload
- Compare against expected list with order semantics
- Report extra/missing tools and call count violations

**Cost ceiling checking:**
- Compare `state.total_cost_usd` against `max_cost_usd`
- Return warning if above `warn_at_pct` threshold

**Acceptance criteria:**
- [ ] All 5 assertion types implemented and tested
- [ ] AssertionResult serializes to JSON for API responses
- [ ] Performance: evaluates in <500ms for runs with <1000 events
- [ ] Tests cover: passing run, failing run, warning case, empty assertions

### Task 0.3: Add "Freeze as Baseline" — auto-extract expected behaviors from a successful run

**Objective:** The fastest path to populating expected_behaviors is extracting them from a known-good run. Add a "Freeze as Baseline" action that analyzes a completed mission's event log and generates suggested assertions.

**Files:**
- Create: `backend/app/services/substrate/baseline_extractor.py` (~120 lines)
- Modify: `backend/app/api/v1/missions.py` — add `POST /api/v1/missions/{id}/freeze-baseline`

**Extraction logic:**

```python
class BaselineExtractor:
    async def extract_from_run(
        self, db: AsyncSession, run_id: str
    ) -> list[dict]:
        """Analyze a successful run and generate expected_behaviors."""
        
        state = await replay_engine.rebuild_state(db, run_id)
        events = await event_log.get_events(db, run_id)
        
        behaviors = []
        
        # 1. Extract tool sequence
        tool_calls = [e for e in events if e.type == "tool.call"]
        tool_names = [e.payload.get("tool_name") for e in tool_calls]
        call_counts = Counter(tool_names)
        
        behaviors.append({
            "type": "tool_sequence",
            "expected_tools": list(set(tool_names)),
            "order": "subset",  # allow reordering
            "max_calls_per_tool": {
                name: count + 1  # allow 1 extra call as headroom
                for name, count in call_counts.items()
            },
        })
        
        # 2. Cost ceiling (actual cost × 1.5 = headroom)
        behaviors.append({
            "type": "cost_ceiling",
            "max_cost_usd": round(state.total_cost_usd * 1.5, 4),
            "warn_at_pct": 80,
        })
        
        # 3. Latency (actual duration × 2 = headroom)
        duration = (state.last_event_at - state.started_at).total_seconds()
        behaviors.append({
            "type": "latency",
            "max_duration_seconds": int(duration * 2),
            "warn_at_pct": 80,
        })
        
        # 4. Task completion
        behaviors.append({
            "type": "task_completion",
            "min_tasks_completed": len(state.completed_tasks),
            "max_tasks_failed": 0,
        })
        
        # 5. No circuit breaker (always include)
        behaviors.append({
            "type": "no_circuit_breaker",
            "description": "Circuit breaker should not trip",
        })
        
        return behaviors
```

**API:**
```python
@router.post("/missions/{mission_id}/freeze-baseline")
async def freeze_baseline(mission_id: str, run_id: str, ...):
    """Extract expected behaviors from a successful run and save to template."""
    behaviors = await extractor.extract_from_run(db, run_id)
    template = await get_template_for_mission(db, mission_id)
    template.expected_behaviors = behaviors
    await db.commit()
    return {"extracted": behaviors}
```

**Acceptance criteria:**
- [ ] `POST /missions/{id}/freeze-baseline` returns extracted behaviors
- [ ] Extracted behaviors are saved to the mission's template
- [ ] Frontend button "Freeze as Baseline" in observatory header (completed missions only)
- [ ] Behaviors are editable before saving (user can adjust headroom multipliers)

### Task 0.4: Surface assertion results in the observatory UI

**Objective:** After a mission completes, show a "Behavior Check" panel in the observatory that displays pass/fail/warn for each assertion alongside the replay state.

**Files:**
- Create: `frontend/src/components/observatory/assertion-results.tsx` (~100 lines)
- Modify: `frontend/src/components/observatory/mission-observatory.tsx` — add panel
- Modify: `backend/app/api/_blueprint_cqrs/queries.py` — add assertion results to replay-state response

**Backend change:**
Extend the replay-state response to include assertion results when the mission's template has `expected_behaviors`:

```python
# In replay_state query:
if template and template.expected_behaviors:
    engine = ReplayAssertionEngine()
    assertion_results = await engine.evaluate(db, run_id, template.expected_behaviors)
    response["assertion_results"] = [r.to_dict() for r in assertion_results]
```

**Frontend:**

```
┌─────────────────────────────────────────┐
│  BEHAVIOR CHECK                    ✓ 4/5│
├─────────────────────────────────────────┤
│  ✓ Tool Sequence      3/3 tools called │
│  ✓ Cost Ceiling       $0.12 / $0.50    │
│  ⚠ Latency            145s / 120s      │
│  ✓ Task Completion    5/5, 0 failed    │
│  ✓ No Circuit Breaker                  │
└─────────────────────────────────────────┘
```

- Green checkmark = passed
- Yellow warning = warning threshold hit
- Red X = assertion violated
- Click to expand for details (actual vs expected)

**Acceptance criteria:**
- [ ] Panel appears in observatory when expected_behaviors exist
- [ ] Panel hidden when no behaviors defined (no clutter)
- [ ] Results update in real-time as mission progresses (for running missions)
- [ ] Each row expandable to show actual vs expected values

### Task 0.5: Intervention Distance metric

**Objective:** A new metric that measures how autonomous a mission (or workspace) actually is. Computed by counting autonomous actions between HITL interrupt events. This is category-creation: "We measure how autonomous your agents are."

**Files:**
- Create: `backend/app/observability/intervention_distance.py` (~80 lines)
- Modify: `backend/app/api/v2/dashboard.py` — add to analytics response
- Modify: `frontend/src/components/analytics/AnalyticsDashboard.tsx` — add stat card

**Computation:**

```python
def compute_intervention_distance(events: list[SubstrateEvent]) -> dict:
    """Measure autonomous actions between human interventions.
    
    Returns:
        {
            "total_actions": int,        # all non-HITL events
            "human_interventions": int,  # HITL resolved events
            "autonomous_actions": int,   # actions between interventions
            "intervention_distance": float,  # avg actions per intervention
            "autonomy_score": float,     # 0.0 to 1.0
        }
    """
    total_actions = 0
    human_interventions = 0
    actions_since_last_intervention = 0
    distances = []

    for event in events:
        if event.type == SubstrateEventType.HUMAN_INTERRUPT_RESOLVED:
            human_interventions += 1
            distances.append(actions_since_last_intervention)
            actions_since_last_intervention = 0
        else:
            total_actions += 1
            actions_since_last_intervention += 1

    # Add final segment (actions after last intervention)
    distances.append(actions_since_last_intervention)

    avg_distance = sum(distances) / len(distances) if distances else 0
    autonomy_score = 1.0 - (human_interventions / max(total_actions, 1))

    return {
        "total_actions": total_actions,
        "human_interventions": human_interventions,
        "autonomous_actions": total_actions,
        "intervention_distance": round(avg_distance, 1),
        "autonomy_score": round(autonomy_score, 3),
    }
```

**Frontend stat card:**

```
┌──────────────────────┐
│  INTERVENTION DIST.  │
│      47.2            │
│  avg actions between  │
│  human interventions  │
│  Autonomy: 94.2%     │
└──────────────────────┘
```

- Show in analytics dashboard at workspace level
- Show in observatory at mission level
- Trend: "Your autonomy score went from 82% → 94% this month"

**Acceptance criteria:**
- [ ] Metric computed correctly from event log
- [ ] Shows in analytics dashboard (workspace-level aggregate)
- [ ] Shows in observatory (per-mission)
- [ ] Handles edge case: zero interventions = 100% autonomous (distance = total actions)
- [ ] Handles edge case: zero actions = 0 distance

### Task 0.6: Regression report API

**Objective:** An API endpoint that compares a run against its template's expected behaviors and returns a structured regression report. This enables future CI/CD integration ("did model upgrade break anything?").

**Files:**
- Create: `backend/app/api/v2/regression.py` (~80 lines)
- Add route: `GET /api/v2/regression/{mission_id}/compare?run_id=...`

**Response:**
```json
{
  "mission_id": "...",
  "run_id": "...",
  "template_version": 3,
  "evaluated_at": "2026-06-04T...",
  "results": [
    {
      "type": "tool_sequence",
      "passed": false,
      "severity": "failure",
      "actual": {"tools_called": ["search_docs", "summarize"], "missing": ["extract_content"]},
      "expected": {"tools": ["search_docs", "extract_content", "summarize"]},
      "message": "Expected tool 'extract_content' was not called"
    },
    {
      "type": "cost_ceiling",
      "passed": true,
      "severity": "info",
      "actual": {"cost_usd": 0.12},
      "expected": {"max_cost_usd": 0.50},
      "message": "Cost within budget"
    }
  ],
  "summary": {
    "total": 5,
    "passed": 4,
    "failed": 1,
    "warnings": 0
  }
}
```

**Acceptance criteria:**
- [ ] `GET /api/v2/regression/{mission_id}/compare` returns structured report
- [ ] Handles missing expected_behaviors (returns "no baseline set" message, not error)
- [ ] Response time <500ms for typical run
- [ ] Auth-scoped to mission owner/workspace

---

## Phase 1: Trace Viewer — Waterfall & Cost Aggregation

> **Why:** LangSmith/Langfuse differentiate with hierarchical waterfall views. The observatory timeline is a flat list today. This is competitive parity, not a moat — but it's the surface where Phase 0 assertion results live.

**Severity:** Medium-High (competitive parity + Phase 0 UI surface)

### Task 1.1: Add cost/time aggregation summary to observatory header

**Files:**
- Modify: `frontend/src/components/observatory/mission-observatory.tsx` (SummaryCard grid ~line 384)

**What to add:**
- "Total Cost" card using `replayState.state?.total_cost_usd` (already available, not displayed)
- "Duration" card computed from `started_at` to `last_event_at`
- Cost-per-task average

**Acceptance criteria:**
- [ ] Header shows: Status, Events, Completed, Tokens, Cost, Duration
- [ ] Cost formats as `$X.XXXX`
- [ ] Duration auto-formats (ms/s/m)

### Task 1.2: Add waterfall/Gantt view toggle

**Files:**
- Create: `frontend/src/components/observatory/waterfall-view.tsx` (~150 lines)
- Modify: `frontend/src/components/observatory/mission-observatory.tsx`

**What to add:**
- Toggle: "Timeline | Waterfall" (next to Filters button)
- Waterfall: each event = row, bar = duration, x-axis = time
- Color-code by event type (reuse EVENT_COLORS)
- Hover tooltip: label, duration, cost, tokens
- Only events with duration info (LLM calls, tool calls, tasks)
- Pure CSS/divs — no charting library

**Acceptance criteria:**
- [ ] Toggle switches between Timeline and Waterfall
- [ ] Waterfall renders LLM/tool calls as colored bars
- [ ] Hover shows model, tokens, cost, latency
- [ ] Filter chips apply to waterfall view

### Task 1.3: Add Langfuse trace link

**Files:**
- Modify: `frontend/src/components/observatory/mission-observatory.tsx`
- Optional backend: `langfuse_trace_url` in replay-state response

**Acceptance criteria:**
- [ ] "View in Langfuse →" button appears when configured
- [ ] Opens Langfuse trace page in new tab
- [ ] Hidden when Langfuse not configured

---

## Phase 2: Cost Dashboard — Charts & Per-Workspace

> **Why:** Current dashboard has tables and progress bars but no charts. Adding visual charts brings it to Vercel/Linear parity. Per-workspace view needed for multi-tenant B2B.

**Severity:** Medium

### Task 2.1: Replace timeseries table with SVG line chart

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsDashboard.tsx`
- Create: `frontend/src/components/analytics/usage-chart.tsx` (~80 lines)

**Acceptance criteria:**
- [ ] Pure SVG line chart (no charting library)
- [ ] Dual-axis: tokens (left, blue) and cost (right, green)
- [ ] Hover crosshair with exact values
- [ ] Responsive (use viewBox)
- [ ] Falls back to table if <2 data points

### Task 2.2: Replace model breakdown progress bars with donut chart

**Files:**
- Modify: `frontend/src/components/analytics/AnalyticsDashboard.tsx`
- Create: `frontend/src/components/analytics/cost-donut.tsx` (~60 lines)

**Acceptance criteria:**
- [ ] SVG donut with color-coded segments per model
- [ ] Center label: total cost
- [ ] Legend: model name + cost + percentage
- [ ] Works with 1 to N models

### Task 2.3: Add per-workspace cost breakdown

**Files:**
- Modify: `backend/app/api/v2/dashboard.py` — add `workspace_id` query param
- Modify: `frontend/src/components/analytics/AnalyticsDashboard.tsx`

**Acceptance criteria:**
- [ ] `/costs?workspace_id=X` returns scoped costs
- [ ] Workspace selector appears when user has >1 workspace
- [ ] Switching workspace re-fetches all dashboard sections

### Task 2.4: Add cost trend indicator

**Acceptance criteria:**
- [ ] Trend arrow next to total cost (↑/↓ with percentage)
- [ ] Green for down, red for up
- [ ] Backend returns `previous_period_cost` + `trend_pct`

---

## Phase 3: Python SDK — Polish & Publish

> **Why:** 1452 auto-generated files exist but are unpublishable: no wrapper, no docs, not on PyPI. Publishing signals "API-first" and unlocks CI/CD integration.

**Severity:** Medium

### Task 3.1: Add FlowmannerClient high-level wrapper

**Files:**
- Create: `sdk-python/flowmanner_api_client/high_level.py` (~150 lines)

**Acceptance criteria:**
- [ ] `FlowmannerClient(base_url, api_key)` works with env var fallback
- [ ] Mission CRUD + execute + status
- [ ] Cost analytics + mission events
- [ ] Context manager support

### Task 3.2: Add example scripts and quickstart docs

**Files:**
- Create: `sdk-python/examples/quickstart.py`
- Create: `sdk-python/examples/create_and_run_mission.py`
- Create: `sdk-python/examples/cost_analytics.py`
- Rewrite: `sdk-python/README.md`

**Acceptance criteria:**
- [ ] README has a 10-line quickstart that works
- [ ] 3 example scripts covering CRUD, execution, analytics

### Task 3.3: Add `flowmanner` CLI entry point

**Acceptance criteria:**
- [ ] `flowmanner status` — check API connectivity + auth
- [ ] `flowmanner costs` — show monthly costs
- [ ] `flowmanner missions list` — list recent missions

### Task 3.4: Publish to TestPyPI

**Acceptance criteria:**
- [ ] `poetry build` produces wheel + sdist
- [ ] Installs from TestPyPI
- [ ] Import works in clean virtualenv

---

## Dependency Graph

```
Phase 0: Replay Assertions (THE MOAT)
  ├── 0.1 ExpectedBehavior schema + migration → independent, start first
  ├── 0.2 AssertionEngine → depends on 0.1
  ├── 0.3 Freeze as Baseline → depends on 0.1 + 0.2
  ├── 0.4 Observatory UI panel → depends on 0.2 (backend results)
  ├── 0.5 Intervention Distance → independent (just reads events)
  └── 0.6 Regression report API → depends on 0.2

Phase 1: Trace Viewer (independent of Phase 0)
  ├── 1.1 Cost/time header → independent
  ├── 1.2 Waterfall view → independent
  └── 1.3 Langfuse link → independent

Phase 2: Cost Dashboard (independent of Phases 0-1)
  ├── 2.1 Line chart → independent
  ├── 2.2 Donut chart → independent
  ├── 2.3 Per-workspace → needs backend change
  └── 2.4 Trend indicator → needs backend change

Phase 3: Python SDK (independent of Phases 0-2)
  ├── 3.1 High-level wrapper → independent
  ├── 3.2 Examples + docs → depends on 3.1
  ├── 3.3 CLI → depends on 3.1
  └── 3.4 TestPyPI → depends on 3.1 + 3.2
```

---

## Effort Estimate

| Phase | Tasks | Estimated time | Complexity | Impact |
|-------|-------|---------------|------------|--------|
| **Phase 0: Replay Assertions** | 6 tasks | **3-5 days** | Medium | **Critical (moat)** |
| Phase 1: Trace Viewer | 3 tasks | 2-3 days | Medium | High (parity) |
| Phase 2: Cost Dashboard | 4 tasks | 2-3 days | Low-Medium | Medium (parity) |
| Phase 3: Python SDK | 4 tasks | 2-3 days | Low | Medium (distribution) |
| **Total** | **17 tasks** | **9-14 days** | | |

---

## Execution Strategy

**Recommended order:**

1. **Phase 0 first** — Tasks 0.1 and 0.2 in sequence (schema → engine), then 0.3-0.6 in parallel. Ship the moat before the polish.
2. **Phase 1 second** — Trace viewer is where assertion results surface. 1.1 first (quick win), then 1.2.
3. **Phase 3 third** — SDK publish is low effort, high signal.
4. **Phase 2 last** — Dashboard polish is nice-to-have.

**Parallelization:** Once Phase 0 tasks 0.1+0.2 are done, Phases 1-3 can run in parallel with Phase 0 tasks 0.3-0.6.

---

## What This Plan Does NOT Cover (Deferred)

- **HITL approval gates** — PAUSED status exists, needs state machine work (post-moat)
- **Eval harness with golden datasets** — Phase 0 assertions are the lightweight version; full eval harness needs labeled data at scale
- **Template marketplace** — needs 20+ templates first
- **Multi-agent debate/consensus** — research-phase
- **Temporal migration** — Celery is fine at current scale
- **Behavioral fingerprinting (full)** — Phase 0 assertions are the MVP. Full fingerprints (output embeddings, tool sequence diffing, causal attribution) layer on top once Phase 0 is in production
- **Open-source replay engine** — strategically sound but multi-month maintenance burden. Park until Phase 0 proves the concept

---

## Quick Wins (< 1 hour each)

1. **Task 0.5** — Intervention Distance metric. ~80 lines backend + 20 lines frontend. Data already in event log.
2. **Task 1.1** — Cost/duration in observatory header. ~20 lines JSX, data already available.
3. **Task 2.4** — Cost trend indicator. Backend returns previous_period_cost, frontend adds arrow.
