# FlowManner — Answers to Opus's Open Questions

**Status:** DRAFT by in-session agent on 2026-06-12. Glenn should review and edit before this becomes the official scoping input.

**Source plan:** `/opt/flowmanner/docs/plans/MISSING-AI-FEATURES-PLAN.md`
**Perspective:** Solo dev / 1-2 dev team, self-hosted, single-tenant today, freelancer+consultants market.

---

## Q1. HITL: blocking vs. non-blocking?

**Answer: Blocking first, non-blocking as v2.**

- **Why blocking:** Simpler state machine, simpler UI, easier to reason about. For freelancer+consultant use case (most users run missions, not 24/7 swarms), blocking matches the mental model: "I see the agent's plan, I approve, it continues." Non-blocking is needed for marketplace agents where the user might not be at the computer — but that's a v2 concern.
- **Mandatory deadline on every gate.** Default 24h, configurable per blueprint. Auto-action on timeout: configurable per blueprint (auto-approve, auto-reject, or stay paused and alert). This kills the deadlock risk from risk #1 in Opus's plan.
- **v2 trigger:** marketplace adoption >10 external agents. By then we have data on whether non-blocking is actually wanted.

---

## Q2. Cost attribution: per-mission or per-step?

**Answer: Per-step recording, per-mission rollup view.**

- **Why per-step:** The substrate event log already records per-step events. Adding `cost_usd` (and `cost_tokens_in`, `cost_tokens_out`) to the existing event schema is incremental — no new table, no migration drama. Per-step is the only granularity that lets you answer "which step in this run is expensive?" — per-mission hides hot spots.
- **Per-mission rollup** is just a SQL view: `SUM(cost_usd) WHERE run_id = X`. Free.
- **Cost categories to record from day one:** `llm_tokens_in/out`, `llm_cost_usd`, `embedding_tokens`, `sandbox_cpu_seconds`, `external_api_cost_usd` (even if zero today — schema is future-proof).
- **Tradeoff:** ~2x the event rows for cost events. Acceptable; substrate already writes 100+ events per mission, adding cost rows is noise-level.

---

## Q3. Episodic memory: auto-trigger or opt-in?

**Answer: Auto-trigger with a quality gate.**

- **Trigger condition (any of):**
  - Run cost > $0.50
  - Run duration > 5 min
  - User explicitly marks "remember this run"
  - User's workspace has a "learn from every run" toggle on
- **Why auto-trigger:** If it requires opt-in, most users never opt in. The whole point of episodic memory is to surface learnings from runs the user didn't pay close attention to.
- **Why with a gate:** Trivial runs (greetings, 1-turn queries, "<$0.01 cost") are noise. They don't teach the system anything useful. Skipping them keeps Qdrant clean and the retrieval signal high.
- **Storage budget:** per workspace, max 1000 memory items. LRU eviction. If you exceed that, you're probably not curating, and the system is filling with junk.
- **User control:** "Forget this memory" button on every memory item surfaced in agent context. Plus workspace-level "clear all my memories" in settings.

---

## Q4. Circuit breaker: per-provider or per-workspace?

**Answer: Per-workspace from day one, with `workspace_id = '*'` (or NULL) for global per-provider fallback.**

- **Why per-workspace:** FlowManner is single-tenant today but the data model is the same cost either way (one extra column on the breaker table). Migrating per-provider → per-workspace later is a painful production migration with rate-limit implications. Per-workspace is the right default and the migration cost is now zero.
- **Provider-fallback mode:** if a user doesn't set workspace-specific breaker config, the breaker uses provider-level defaults. This means a fresh user gets sensible behavior out of the box; advanced users can tune per-workspace.
- **Blast radius:** per-workspace is strictly safer — one bad workspace doesn't trip the breaker for everyone.
- **State table shape (rough):**
  ```sql
  breaker_state (
    workspace_id UUID,           -- NULL = global default
    provider    TEXT,            -- 'anthropic' | 'openai' | 'deepseek' | ...
    state       TEXT,            -- 'closed' | 'open' | 'half_open'
    opened_at   TIMESTAMP,
    error_count INT,
    PRIMARY KEY (workspace_id, provider)
  )
  ```

---

## Q5. Blueprint+Run gate: is P3 done enough to start P4?

**Answer: YES, start in parallel — but ONLY the substrate-primitive work (#5, #6: lease hardening + checkpoint hardening). Defer HITL and cost attribution until P3 stop-gate is met.**

- **The split is clean:** Opus correctly identified that lease + checkpoint hardening DON'T depend on Blueprint+Run (they're substrate primitives below the run state machine). HITL and cost attribution DO depend on the run state machine being canonical.
- **So:**
  - **Start now (Q1, parallel to P3):** worker lease hardening (#5), checkpoint hardening (#6), circuit breaker (#4)
  - **Defer until P3 done:** HITL primitives (#1), HITL Inbox UI (#2), cost attribution engine (#3)
- **Why this respects the strict sequencing:** the work that "needs P3 done" (HITL, cost) won't be touched until P3 stop-gate. The work that's safe to start (lease/checkpoint) gets unblocked. P3 and P4 progress in parallel without conflict.
- **Updated Q1 plan:**
  - **Q1 part A (now):** lease hardening (3w) + checkpoint hardening (2w) + circuit breaker (2w) = 7 weeks
  - **Q1 part B (after P3 stop-gate):** HITL primitives (4w) + HITL Inbox (3w) + cost attribution (3w) = 10 weeks
  - Total: still ~16-17 weeks, but part A doesn't block on P3

---

## Summary table

| Q | Answer | Cost | Defers? |
|---|--------|------|---------|
| Q1 HITL | Blocking first, v2 non-blocking | Default 24h timeout, configurable | Non-blocking to v2 |
| Q2 Cost | Per-step record, per-mission view | ~2x event rows | Nothing |
| Q3 Memory | Auto with cost/duration/user-marked gates | LRU 1000/workspace | All-trivial runs |
| Q4 Breaker | Per-workspace + provider fallback | +1 column | Nothing |
| Q5 P3 gate | Start lease/checkpoint now; defer HITL+cost | Lease+checkpoint parallel to P3 | HITL+cost until P3 |

---

*Ready for Glenn to review and edit. After sign-off, the answers get merged into the plan as a "Decisions" appendix, or live as this standalone answers doc — your call.*
