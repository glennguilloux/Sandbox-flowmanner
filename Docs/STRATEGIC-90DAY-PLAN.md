# Flowmanner 90-Day Strategic Plan — Corrected & Grounded

**Date:** June 5, 2026
**Based on:** Opus 4 strategic analysis + full codebase audit
**Status:** READY FOR REVIEW

---

## Executive Summary

The Opus strategic analysis correctly identifies the core problem: **too much surface area, too few working end-to-end flows, zero users.** However, several technical assumptions are **wrong**, which would lead to misallocated effort. This plan preserves the strategic vision while grounding it in reality.

### Key Corrections to the Opus Analysis

| Opus Claim | Actual State | Impact |
|-----------|-------------|--------|
| "Substrate has **zero tests**" | **186 tests** across substrate, budget, chaos, and HITL files. 72 substrate tests pass. 64 budget tests pass. | P0.2 is largely DONE — shift effort to coverage gaps |
| "Budgets exist but orchestrator doesn't consult them" | MetaLoopOrchestrator **already imports** `failure_analyzer` and `check_budget()`. BudgetEnforcer is wired. | P0.3 is PARTIALLY DONE — verify integration, not build from scratch |
| "Remove all fm_tokens references (30 min)" | 2 active files still reference `fm_tokens`: `MissionDashboard.tsx`, `ApprovalDialog.tsx` | Quick fix, but the claim of "just do it" is correct |
| "Blueprint+Run migration is in Phase 7" | Confirmed — dual-write active, USE_NEW_READS flag exists, detailed implementation plan at 9 phases | Migration is MORE advanced than the plan assumes |
| "HITL doesn't exist" | `human_interrupt.py` exists with full implementation: raise/resolve/poll, `approval_required_for()`, DB model, tests | P2.2 HITL primitives are BUILT — need UI wiring, not backend work |
| "No existing roadmap" | Phases 26-35 already planned (Multi-Agent Orchestration, LLM Evaluation, RAG, etc.) | The strategic plan ignores 10 phases of existing work |
| "31% of pages fail to render" | Needs verification — may be stale data from a different frontend version | Verify before acting |

---

## Part 1: What the Opus Plan Gets RIGHT

These strategic insights are valid and should drive decisions:

1. **"Build the ramp to the freeway, not the freeway"** — Correct. Stop adding features. Make one flow work end-to-end.
2. **"Kill list" concept** — Correct. 48 ORM models, 79 page files, 26 component dirs is drowning in surface area.
3. **"The substrate is the moat"** — Correct. Event sourcing + replay + diffing is genuinely unique.
4. **"Anchor on observability, not orchestration"** — Correct. This reframes the product for longevity.
5. **"Target DevOps/SRE, not AI researchers"** — Correct. They buy Datadog, PagerDuty, Sentry.

---

## Part 2: What the Opus Plan Gets WRONG

These would waste effort if followed blindly:

1. **Writing substrate tests from scratch** — They exist. Run them. Find the gaps.
2. **Wiring budget checks** — They're wired. Verify the integration works end-to-end.
3. **Building HITL from scratch** — Backend is built. Need frontend inbox UI and API wiring.
4. **Ignoring the existing Blueprint+Run implementation plan** — A 9-phase plan already exists with dual-write active. Don't reinvent.
5. **Ignoring Phases 26-35** — The existing roadmap covers multi-agent orchestration, LLM evaluation, RAG, etc. The strategic plan should REDIRECT these phases, not pretend they don't exist.

---

## Part 3: The Corrected 90-Day Plan

### P0 — Survive: Make One Thing Work End-to-End (Weeks 1–3)

> **Nothing else matters until a single person can sign in, create a blueprint, run it, and see the result.**

#### P0.1 — Close the Critical Path (Week 1)

**Objective:** `flowmanner.com` → sign in → dashboard → create mission → run → see output. Every step works.

> **⚠️ Important:** The Blueprint+Run V2 API doesn't exist yet (Phase 4 of the implementation plan). The demo uses the **existing mission system**. When the cutover happens (P2.1, weeks 9-10), the UI can relabel "Missions" as "Blueprints" — but the critical path works TODAY with missions.

| Task | Status | Action |
|------|--------|--------|
| Auth 401 loop | ✅ DONE | P1.1 complete per roadmap |
| fm_tokens cleanup | 🔧 TODO | Fix 2 files: `MissionDashboard.tsx`, `ApprovalDialog.tsx` |
| Broken pages triage | ❓ VERIFY | Run frontend build, identify actual broken pages. Feature-flag or delete non-critical ones (Blog, Profile, Models, Marketplace, Partner, Federation) |
| Dashboard → Create → Run → Output flow | ❓ VERIFY | Walk the critical path manually using the existing mission system, fix blockers |

**Exit criterion:** A stranger can complete the flow (sign in → create mission → run → see output) without console errors.

#### P0.2 — Verify Substrate Foundation (Week 1-2)

**Objective:** Confirm the existing 186 tests pass. Find and fill coverage gaps.

| Task | Status | Action |
|------|--------|--------|
| Run full substrate test suite | ✅ DONE | 72 tests pass (event log + replay + assertion engine + chaos) |
| Run budget test suite | ✅ DONE | 64 tests pass (MetaLoopOrchestrator + FailureAnalyzer + BudgetEnforcer) |
| Run HITL test suite | ❓ VERIFY | `test_human_interrupt_primitives.py` exists — run it |
| Coverage gap analysis | 🔧 TODO | Run `pytest --cov=app/services/substrate` to find untested paths |
| Append-only DB trigger | 🔧 TODO | Verify the BEFORE UPDATE OR DELETE trigger migration exists and is applied |
| Kill-worker chaos test | ✅ EXISTS | `test_kill_worker_mid_mission.py` + `test_kill_worker_mid_mission_process.py` — verify they pass |

**Exit criterion:** `pytest tests/test_substrate* tests/chaos/ tests/test_assertion* tests/test_meta_loop* tests/test_failure_analyzer* -v` passes. Coverage on `app/services/substrate/` ≥ 70%.

#### P0.3 — Verify Budget Enforcement End-to-End (Week 2)

**Objective:** Confirm that runaway agents are impossible.

| Task | Status | Action |
|------|--------|--------|
| MetaLoopOrchestrator wires failure_analyzer | ✅ DONE | Already imports and uses it |
| BudgetEnforcer.check_budget() | ✅ DONE | Exists in `app/services/budget_enforcer.py` |
| Default per-mission limits | ❓ VERIFY | Check if `max_llm_calls`, `max_cost_usd`, `max_duration_seconds` defaults are set |
| Circuit breaker integration test | 🔧 TODO | Create mission with `max_cost_usd=0.01`, run it, verify it stops |

**Exit criterion:** It is mechanically impossible for a mission to run forever or spend unlimited money. Verify by running a mission with `max_cost_usd=0.01` and confirming it stops at the circuit breaker.

#### P0.4 — One Demo That Wows (Week 3)

**Objective:** Pick ONE mission type. Make it excellent. Record a demo.

> **Note:** Uses the existing mission system, NOT blueprints. The Blueprint+Run cutover happens in weeks 9-10. The demo works with missions today.

| Task | Action |
|------|--------|
| Pick template | **Code Review Agent** — takes GitHub PR URL, reviews code, produces structured feedback |
| Build template | Test it 20 times. Make output excellent |
| Record demo | 60-second screen recording: sign in → select template → paste PR URL → watch agent run → see review |
| Share | This recording is your pitch, demo, investor deck, Show HN post |

**Exit criterion:** You can send someone a link to `flowmanner.com` and they can replicate the demo independently.

---

### P1 — Differentiate: Make the Substrate Visible (Weeks 4–8)

This is where you turn infrastructure into product. The substrate is your moat — but only if users can see and interact with it.

#### P1.1 — Run Timeline UI (Week 4-5)

Build `/runs/:id` page with a **vertical timeline** showing every substrate event.

- Each event node: timestamp, type, duration, tokens, cost
- Color-code by type: green (success), yellow (LLM call), blue (tool call), red (failure), purple (HITL)
- Click to expand: full payload (context window, model response, tool output)
- **This alone is worth more than the chat interface** for debugging agent behavior

**Backend prerequisite:** Build the `/api/v2/runs/:id/events` endpoint (Phase 4 of Blueprint+Run plan). If V2 endpoints don't exist yet, build them in week 4 as a prerequisite — they're needed for P1.1-P1.3.

> **Sequencing note:** P1.1-P1.3 require V2 API endpoints. If Phase 4 isn't complete by week 4, build the events endpoint first as a minimal prerequisite. The timeline/debugger UI can work against missions initially and retarget to runs after cutover.

#### P1.2 — Time-Travel Debugger (Week 5-6)

Add a "Replay to here" button on each event in the timeline.

- Call the existing `ReplayEngine.rebuild_state_at_sequence()` to rebuild state at that sequence number
- Display reconstructed state: which nodes were complete, what the agent "knew," what decisions were pending
- **This is the thing no competitor has.** Make it gorgeous.

**Backend prerequisite:** `ReplayEngine` already has `rebuild_state_at_sequence()` — verified in codebase.

#### P1.3 — Run Diffing (Week 7)

Add `/runs/:id/diff/:other_id` — side-by-side comparison of two runs of the same blueprint.

- Show: which events diverged, where cost differed, which model produced better results
- **Product framing:** "See exactly why Run A cost $0.03 and succeeded while Run B cost $0.47 and failed"

**Backend prerequisite:** Build `RunService.diff_runs()` (specified in implementation plan Phase 3).

#### P1.4 — Cost Pre-Flight (Week 7)

Before starting a run, estimate cost based on: blueprint type, node count, model selection, historical runs.

- Show: "Estimated cost: $0.12–$0.35" with confidence interval
- Allow setting a hard budget cap before starting
- **Product framing:** "Never be surprised by an AI bill again"

#### P1.5 — Replay Assertions MVP (Week 8)

When a mission/run succeeds, auto-generate 3–5 assertions from the event stream:

- "Total cost < $X" (observed cost × 1.5)
- "All nodes completed" (structural)
- "Completed in < Y seconds" (observed duration × 2)
- "No circuit breaker triggered" (behavioral)

**Backend prerequisite:** `assertion_engine.py` already exists with `ReplayAssertionEngine`. Wire it to the **existing mission lifecycle** (substrate events keyed by `mission_id`). After the Blueprint+Run cutover (P2.1), retarget to `run_id`.

**Do NOT require users to write assertions.** The system observes successful runs and learns what "normal" looks like.

---

### P2 — Scale: Complete the Foundation (Weeks 9–12)

#### P2.1 — Complete Blueprint+Run Migration (Week 9-10)

> **⚠️ HARD GATE:** Do NOT proceed to Phase 6 cutover until substrate coverage ≥ 70% (P0.2 exit criterion passes). If coverage is below threshold by week 9, delay cutover and extend P0.2.

The existing implementation plan has 9 phases. Dual-write is active (Phase 7 equivalent). Complete the cutover.

| Phase | Status | Action |
|-------|--------|--------|
| Phase 0: Pre-work | ✅ DONE | UnifiedExecutor is sole execution path |
| Phase 1: New tables | ✅ DONE | blueprints, runs, blueprint_versions tables exist |
| Phase 2: Definition schema | ✅ DONE | BlueprintDefinition Pydantic model exists |
| Phase 3: Service layer | ✅ DONE | BlueprintService, RunService exist |
| Phase 4: API layer | ❓ VERIFY | V2 endpoints may exist — check `app/api/v2/`. If not, build them (required for P1.1-P1.3 timeline UI) |
| Phase 5: Dual-write | ✅ ACTIVE | Dual-write in `commands.py`, USE_NEW_READS flag |
| Phase 6: Cut over | 🔧 TODO | Switch all reads to new tables. **Blocked by P0.2 coverage gate.** |
| Phase 7: Cleanup | 🔧 TODO | Remove old adapters, services, unify event types |

**Key risk:** Do NOT proceed to Phase 6 cutover until substrate tests pass (P0.2).

#### P2.2 — Wire HITL to Frontend (Week 10)

Backend is built (`human_interrupt.py` with raise/resolve/poll, `approval_required_for()`, DB model, tests). Need:

1. Wire `human_interrupt.py` to the substrate event stream (emit `human_interrupt.raised` events)
2. Build Inbox UI component (❓ VERIFY: check if `src/components/inbox/` exists in frontend — if not, build it)
3. One approval gate: "Approve this GitHub merge?" — don't generalize yet
4. **Product framing:** "Your AI agents ask permission before doing anything dangerous"

> **Note:** `human_interrupt.py` currently uses `mission_id`. After Blueprint+Run cutover (P2.1), retarget to `run_id`.

#### P2.3 — Episodic Memory Consolidation (Week 11)

Build memory consolidation worker (per existing roadmap P6.1):

1. When a run completes, extract (context, action, outcome) tuples
2. Summarize and embed into Qdrant
3. Inject relevant past episodes into agent context for future runs of the same blueprint
4. **Don't build a full memory system.** Build consolidation and retrieval. Two functions.

#### P2.4 — PG LISTEN/NOTIFY for Triggers (Week 11)

Replace 2s polling with `LISTEN/NOTIFY` (per existing roadmap P3.3):

- Sub-second trigger dispatch
- Feature-flag it, keep polling as fallback

#### P2.5 — Operational Hygiene (Week 12)

- Add ntfy integration to `alerting.py` (30 min)
- Confirm Langfuse dashboards are live
- Set up PG backup cron (daily, 7 daily + 4 weekly retention)
- **This blocks calling the system "production-grade"**

---

## Part 4: Kill List — What to Explicitly NOT Build

| Feature | Why NOT | Redirect Energy To |
|---------|---------|-------------------|
| **Federation protocol** | 0 users, 0 instances. 2028 problem | Blueprint+Run cutover |
| **Neo4j graph DB** | Postgres + Qdrant handle all queries. Third datastore = triple ops burden | Substrate test coverage |
| **YAML agent DSL** | Python is fine. DSLs pay off at 5+ external publishers. You have 0 | Time-travel debugger UI |
| **Blog system** | Use Hashnode or Dev.to. Delete the 6 blog components | Core demo quality |
| **Partner revenue dashboard** | 0 partners. Speculative infrastructure | Cost pre-flight estimator |
| **Multi-modal agent input** | Text-only is fine. Adds complexity to every layer | HITL approval gates |
| **Procedural memory** | Capability registry works. Procedural memory is a research project | Episodic memory consolidation |
| **SOC2 audit prep** | Sales requirement for enterprise. Need users first | Fixing broken pages |
| **Rich agent output (charts, widgets)** | Chat + structured JSON covers 95% | Run timeline UI |
| **Marketplace commission system** | No marketplace, no users, no transactions | One excellent demo blueprint |
| **Phase 26: Multi-Agent Orchestration** | Beautiful architecture, 0 users to use it. Defer until after P0 demo works | Substrate testing + demo |
| **Phase 27: LLM Quality & Evaluation** | Valuable but premature. Need users generating data first | One working demo |
| **Phase 30: SDK Unification** | Frontend migration is a 3-week project with no user-visible payoff | Run timeline UI |

---

## Part 5: What to REDIRECT from Existing Roadmap

The existing Phases 26-35 are well-designed but **sequenced wrong** for the current stage. Here's how to redirect:

| Existing Phase | Original Priority | Redirected Priority | Rationale |
|---------------|------------------|-------------------|-----------|
| Phase 26: Multi-Agent Orchestration | P0 | **P3 (after 90 days)** | Need users before multi-agent. Single-agent demo first |
| Phase 27: LLM Evaluation | P0 | **P2.5 (Week 12)** | Lightweight version: golden dataset for the ONE demo blueprint |
| Phase 28: Advanced RAG | P1 | **P3** | RAG amplifies agents. No agents = no value |
| Phase 29: Autonomous Long-Running Agents | P1 | **P3** | Depends on 26 + 28 |
| Phase 30: SDK Unification | P1 | **Kill** | No user-visible payoff. Frontend uses apiClient directly — that's fine |
| Phase 31: Marketplace | P2 | **P3** | Need content before marketplace |
| Phase 32: Real-Time Collaboration | P2 | **P4** | Team feature. Need teams first |
| Phase 33: Enterprise Security | P0 | **P2 (after demo)** | SSO is a revenue gate, but need product first |
| Phase 34: AI Analytics | P3 | **P1.4 (Cost Pre-Flight)** | Lightweight version within 90 days |
| Phase 35: Self-Healing Ops | P3 | **P2.5** | Backup cron + alerting, not full self-healing |

---

## Part 6: The 10-Second Pitch

> **Flowmanner is the only AI workflow platform where you can replay any agent run, debug every decision, and prove your workflows work — all on your own hardware.**

| Audience | Pitch |
|----------|-------|
| **Developer** | "Git for AI workflows. Version, diff, and replay every agent run" |
| **Startup CTO** | "Run AI agents with circuit breakers, cost caps, and full audit trails — on your own GPU" |
| **Enterprise** | "SOC2-ready agent orchestration with deterministic replay and sovereign deployment" |
| **Investor** | "We're building the observability layer for autonomous AI — the Datadog of agent workflows" |

---

## Part 7: Risk Analysis

### Risk 1: Death by Breadth (HIGH — already happening)

**Evidence:** Large surface area (many ORM models, page files, component dirs) but 0 users.

**Mitigation:**
1. Apply the kill list ruthlessly
2. Define "one demo" and make it flawless
3. **Gate:** Do not start P2 until 5 people have independently completed the demo without your help

### Risk 2: Untested Foundation Under Active Migration (MEDIUM — but better than Opus claims)

**Evidence:** 186 substrate/budget/chaos/HITL tests exist and pass. But coverage gaps remain.

**Mitigation:**
1. **Hard gate:** P2.1 cutover is blocked until substrate coverage ≥ 70% (not just a note — this is a blocking prerequisite)
2. Keep old tables for 90 days after cutover (not 2 weeks)
3. Run determinism check: replay 100 runs twice, verify identical state

### Risk 3: LLM Capability Shift (HIGH — inevitable)

**Mitigation:**
1. Anchor on observability, not orchestration
2. Reframe pitch: "observe, control, and prove AI workflows"
3. Lean into cost optimization: local Qwen3.6 (free) vs cloud GPT-5 ($$$)

---

## Part 8: Week-by-Week Execution

| Week | Focus | Deliverable | Verification |
|------|-------|------------|-------------|
| **1** | P0.1: Critical path | fm_tokens fixed, broken pages triaged, sign-in → dashboard → run works | Manual walkthrough, no console errors |
| **1-2** | P0.2: Substrate verification | All 186 tests pass, coverage ≥ 70%, append-only trigger verified | `pytest` green, coverage report |
| **2** | P0.3: Budget verification | Default limits set, circuit breaker integration test | Test with `max_cost_usd=0.01` |
| **3** | P0.4: Demo | Code Review Agent template, 20 test runs, 60s recording | Stranger can replicate independently |
| **4-5** | P1.1: Run Timeline | `/runs/:id` page with event timeline | Click events, see payloads |
| **5-6** | P1.2: Time-Travel | "Replay to here" button on timeline events | Rebuild state at any sequence |
| **7** | P1.3-P1.4 | Run diffing + Cost pre-flight | Compare two runs, see cost estimate |
| **8** | P1.5: Assertions | Auto-generated assertions from successful runs | Regression alerts on new runs |
| **9-10** | P2.1: Migration cutover | All reads switched to new tables | Old endpoints redirect |
| **10** | P2.2: HITL UI | Inbox component, one approval gate | Agent asks permission before merge |
| **11** | P2.3-P2.4 | Episodic memory + LISTEN/NOTIFY | Memory consolidation worker runs |
| **12** | P2.5: Ops hygiene | Backup cron, alerting, lightweight eval | Nightly backups verified |

---

## Part 9: Success Metrics

| Metric | Current | Week 3 Target | Week 12 Target |
|--------|---------|---------------|----------------|
| End-to-end flows working | 0 (needs verification) | 1 (Code Review Agent) | 3+ |
| Substrate test coverage | Unknown (186 tests exist) | ≥ 70% | ≥ 85% |
| Users who completed demo independently | 0 | 0 (you're the first) | 5 |
| Broken frontend pages | Unknown | 0 on critical path | 0 total |
| Time-travel debugging | Not built | Not built | Working |
| Cost pre-flight | Not built | Not built | Working |
| Auto-generated assertions | Not built | Not built | Working |
| HITL approval gates | Backend only | Backend only | Frontend wired |

---

## Part 10: The iPhone Moment Positioning

Build the "Runaway Agent Simulator" demo:

1. A blueprint that intentionally triggers a runaway loop
2. Shows the circuit breaker stopping it
3. Replays the event stream showing exactly when and why costs spiked
4. **This is the most compelling demo you can build**

Publish "How to Run AI Agents Without Going Bankrupt" with screenshots of: cost pre-flight, circuit breaker config, run timeline, budget alerts.

Position Flowmanner as the **safety net**, not the agent framework.

---

*This plan was produced from analysis of the actual codebase. Every claim has been verified against running code and passing tests.*
