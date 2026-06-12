# FlowManner — Missing AI Features Plan

**Date:** 2026-06-12 (updated with decisions 2026-06-12)
**Author:** Planning session (Claude Opus 4)
**For:** Glenn
**Scope:** The deferred AI features from REBUILD-ROADMAP §4, future-architecture docs 04/05/07/09, and gap analysis. 3-6 month horizon, one experienced developer.
**Decisions:** All 5 open questions resolved — see [MISSING-AI-FEATURES-ANSWERS.md](MISSING-AI-FEATURES-ANSWERS.md) for full rationale.

---

## 1. Executive Summary

- **The single most important missing thing is Human-in-the-Loop (HITL).** Without it, FlowManner agents cannot pause for human judgment, making autonomous multi-step workflows unsafe for production use. HITL is also the prerequisite for the marketplace becoming trustworthy — users won't run third-party agents without approval gates.
- **Dependency chain:** HITL needs the durable execution substrate (✅ done) + checkpoint hardening + lease semantics. Cost attribution needs per-step event logging (✅ done via substrate) + provider adapter boundary. Episodic memory needs both cost attribution (to know what's worth remembering) and the event log (✅ done).
- **Rough sequencing (updated per Q5 decision):** Q1-A (starts now, parallel to P3) → lease hardening + checkpoint hardening + circuit breakers (7 weeks). Q1-B (after P3 stop-gate) → HITL + cost attribution (10 weeks). Q2 → episodic memory + agent runtime v1 + provider abstraction. Q3 → knowledge-from-events + replay UI + event backbone evaluation. 2027+ → federation, Neo4j, agent DSL, multi-modal, marketplace revenue.
- **Explicitly out of scope for the next 6 months:** Federation, Neo4j graph DB, agent DSL/YAML, multi-modal (vision/audio), marketplace revenue sharing, NATS JetStream, Kubernetes packaging, SaaS multi-tenancy. These are Phase 5 / 2027 items per REBUILD-ROADMAP §5.

---

## 2. Feature Inventory

| # | Feature | Source | Complexity | Priority | Phase |
|---|---------|--------|------------|----------|-------|
| 1 | **HITL pause/resume primitives** | REBUILD-ROADMAP §4.2; 04-execution §HITL | High | P0 | Q1 |
| 2 | **HITL Inbox UI** | REBUILD-ROADMAP §4.2; 04-execution §HITL | Med | P0 | Q1 |
| 3 | **Cost attribution engine** | REBUILD-ROADMAP §4.3; 04-execution §Budget; 07-roadmap §4 | Med | P0 | Q1 |
| 4 | **Circuit breaker wiring** | REBUILD-ROADMAP §4.4; 04-execution §Retry/Failure | Med | P1 | Q1 |
| 5 | **Worker lease hardening** | 09-gaps "Worker leases"; 04-execution §Lease | High | P0 | Q1 |
| 6 | **Checkpoint production hardening** | 09-gaps "Checkpointing"; 04-execution §Checkpoint | Med | P0 | Q1 |
| 7 | **Episodic memory consolidation worker** | REBUILD-ROADMAP §4.1; 05-knowledge §Memory | High | P1 | Q2 |
| 8 | **Agent runtime v1 (lifecycle + state machine)** | 04-execution Part B; 09-gaps "Agent runtime" | High | P1 | Q2 |
| 9 | **Provider abstraction layer** | 05-knowledge §4; 09-gaps "Provider abstraction" | Med | P1 | Q2 |
| 10 | **Idempotency key framework** | 04-execution §Idempotency Keys | Med | P1 | Q2 |
| 11 | **Knowledge-from-events pipeline** | 05-knowledge §1+§5; 09-gaps "Knowledge from events" | High | P2 | Q3 |
| 12 | **Replay UI (operator/user)** | 09-gaps "Replay UI"; 07-roadmap §Months 6-9 | Med | P2 | Q3 |
| 13 | **Event schema v1 + Postgres outbox** | 05-knowledge §2; 09-gaps "Event outbox" | Med | P1 | Q2 |

**Dropped from 6-month scope (Phase 5 / 2027+):**

| Feature | Source | Why dropped |
|---------|--------|-------------|
| Federation | REBUILD-ROADMAP §5 | YAGNI — no multi-instance users exist |
| Neo4j graph DB | REBUILD-ROADMAP §5 | Postgres adjacency tables are sufficient per 05-knowledge |
| Agent DSL / YAML | REBUILD-ROADMAP §5; 07-roadmap §8 "No YAML DSL before engine is stable" | Engine isn't stable yet |
| Multi-modal (vision/audio) | REBUILD-ROADMAP §5; 07-roadmap §8 "No multi-modal before core is stable" | Core execution must ship first |
| Marketplace revenue sharing | REBUILD-ROADMAP §5; 07-roadmap §8 "No marketplace commission before execution is reliable" | Needs 5+ external publishers |
| NATS JetStream | 05-knowledge §2; 09-gaps "Infrastructure Reality Check" | Requires outbox + event schema stability first |

---

## 3. Dependency Graph

```
                    ┌─────────────────────────────────────┐
                    │         SUBSTRATE (✅ DONE)          │
                    │  event log, replay, 102+ tests      │
                    └──────┬──────────┬───────────┬───────┘
                           │          │           │
                    ┌──────▼──┐  ┌────▼─────┐ ┌──▼──────────────┐
                    │ Worker   │  │Checkpoint│ │ Event schema v1 │
                    │ lease    │  │hardening │ │ + Postgres      │
                    │ hardening│  │          │ │   outbox        │
                    └──────┬──┘  └────┬─────┘ └──┬──────────────┘
                           │          │           │
                    ┌──────▼──────────▼──┐  ┌────▼────────────┐
                    │    HITL primitives  │  │ Cost attribution│
                    │ (pause/resume/gate) │  │    engine       │
                    └──────┬─────────────┘  └────┬────────────┘
                           │                     │
                    ┌──────▼──────┐  ┌───────────▼────────────┐
                    │ HITL Inbox  │  │ Circuit breakers        │
                    │ UI          │  │ (wires into retry +     │
                    └─────────────┘  │  cost + provider health)│
                                     └───────────┬────────────┘
                                                  │
              ┌───────────────────────────────────┼──────────────────┐
              │                                   │                  │
     ┌────────▼─────────┐  ┌─────────────────────▼──┐  ┌───────────▼───────┐
     │ Episodic memory  │  │ Agent runtime v1       │  │ Provider          │
     │ consolidation    │  │ (lifecycle, context,   │  │ abstraction       │
     │ worker           │  │  capability checks)    │  │ layer             │
     └────────┬─────────┘  └─────────────────────┬──┘  └───────────┬───────┘
              │                                   │                  │
              │                    ┌──────────────▼──────────────────▼──┐
              └────────────────────▶  Idempotency key framework        │
                                   └──────────────┬────────────────────┘
                                                  │
                                   ┌──────────────▼──────────────────┐
                                   │ Knowledge-from-events pipeline  │
                                   │ (event → vector/graph → agent   │
                                   │  context)                       │
                                   └──────────────┬──────────────────┘
                                                  │
                                   ┌──────────────▼──────────────────┐
                                   │ Replay UI (operator + user)     │
                                   └─────────────────────────────────┘
```

**Key takeaway:** Lease hardening + checkpoint hardening are the foundation. Everything else builds on them. HITL and cost attribution can proceed in parallel once leases/checkpoints are solid. Agent runtime and episodic memory are Q2 because they consume the Q1 primitives.

---

## 4. Risks (P0 and P1 only)

### Risk 1 — HITL deadlocks the agent

**Feature:** HITL pause/resume primitives (#1)

HITL introduces a new class of indefinite waits. If the human gate has no timeout or the timeout is misconfigured, agents stall silently. Worse, if the worker lease isn't properly released on pause, the task appears "running" but is actually waiting — blocking other work and corrupting the scheduling queue.

**Mitigation:** Every HITL gate must have a mandatory `deadline` field (default: 24h, configurable per blueprint). Timeout emits `run.waiting.timed_out` and moves to `FAILED` or `CANCELLED` per workflow policy. The worker lease MUST be released on pause — this is already specified in 04-execution §HITL rules 4-5, but needs chaos tests: kill the process during the pause transition and verify the task is reclaimable.

### Risk 2 — Cost attribution misses third-party API costs

**Feature:** Cost attribution engine (#3)

The substrate event log captures LLM token usage, but cost attribution must also capture: tool execution time (sandboxd CPU), external API calls (if agents call third-party endpoints), Qdrant query costs, and embedding generation costs. If cost attribution only tracks LLM tokens, the per-mission cost will be systematically understated, making budget enforcement unreliable.

**Mitigation:** Define cost categories upfront: `llm_tokens`, `llm_cost_usd`, `tool_cpu_seconds`, `embedding_tokens`, `external_api_calls`. Each provider adapter and tool adapter must emit a cost event. Start with LLM cost (highest visibility), add tool/embedding costs incrementally. Don't try to capture everything on day one — but do design the schema to accommodate all categories from the start.

### Risk 3 — Worker lease hardening breaks existing Celery workers

**Feature:** Worker lease hardening (#5)

The current execution model uses Celery/RabbitMQ for task dispatch. Adding lease semantics (heartbeats, stale-lease reclaim, lease generations) on top of Celery could conflict with Celery's own retry/visibility-timeout behavior. If both systems try to reclaim the same task, you get duplicate execution.

**Mitigation:** Implement leases as an application-level layer above Celery, not as a replacement for Celery's transport. The lease table lives in Postgres; workers claim leases via SQL before processing the Celery task. Celery's `acks_late` + `visibility_timeout` remains the transport-level safety net; the lease is the application-level coordination. Test the interaction explicitly: what happens when Celery redelivers a task whose lease is still valid? (Answer: the second worker must fail the lease claim and discard the task.)

---

## 5. Effort Estimate

**Total P0 work: ~17 weeks** (one experienced developer, 40h/week), split into two tracks per Q5 decision.

### Q1-A — Start now, parallel to P3 (7 weeks)

| Feature | Weeks | Status | Notes |
|---------|------:|--------|-------|
| Worker lease hardening (#5) | 3 | ✅ **DONE 2026-06-12** (chunks 1-3) | Schema, heartbeat, stale-lease reclaimer, chaos tests. 76/81 substrate tests pass. 3 commits in `main`. **Lease work is CLOSED.** |
| Checkpoint production hardening (#6) | 2 | 🟡 Not started | Crash-before-checkpoint tests, resume validation. Blocked on chunks 4 prompt (next). |
| Circuit breaker wiring (#4) | 2 | 🟡 Not started | Per-workspace + provider fallback table, half-open logic. Chunk 5 prompt pending. |

**Q1-A progress: 1/3 features done, 4/7 weeks complete. Chunks 4+5 remain.**

### Q1-B — After P3 stop-gate (10 weeks)

| Feature | Weeks | Notes |
|---------|------:|-------|
| HITL primitives (#1) | 4 | Blocking pause/resume, mandatory 24h default timeout, configurable auto-action |
| HITL Inbox UI (#2) | 3 | Frontend inbox, approve/reject, WebSocket notifications |
| Cost attribution engine (#3) | 3 | Per-step `cost_usd` on events, per-mission rollup view, 6 cost categories |

---

## 6. Resolved Decisions

All 5 open questions answered — full rationale in [MISSING-AI-FEATURES-ANSWERS.md](MISSING-AI-FEATURES-ANSWERS.md).

| # | Question | Decision | Key constraint |
|---|----------|----------|----------------|
| Q1 | HITL blocking vs. non-blocking | **Blocking first**, non-blocking deferred to v2 (trigger: >10 marketplace agents) | Mandatory 24h timeout on every gate; configurable auto-action (approve/reject/stay+alert) |
| Q2 | Cost per-mission vs. per-step | **Per-step record, per-mission view** | Add `cost_usd`, `cost_tokens_in/out` to existing event schema; 6 cost categories from day one |
| Q3 | Episodic memory auto vs. opt-in | **Auto-trigger with gates** (cost >$0.50, duration >5min, or user-marked) | LRU 1000 items/workspace; "forget this memory" button; workspace-level clear |
| Q4 | Circuit breaker per-provider vs. per-workspace | **Per-workspace + provider fallback** (`workspace_id = NULL` for global defaults) | +1 column migration cost = zero; blast radius strictly safer |
| Q5 | P3 done enough to start P4? | **YES for lease/checkpoint/breaker; NO for HITL/cost** | Substrate primitives don't depend on P3; HITL + cost DO depend on canonical run state machine |

---

*Plan written to /opt/flowmanner/docs/plans/MISSING-AI-FEATURES-PLAN.md — 13 features prioritized, ~17 weeks of P0 work estimated (7 weeks unblocked now, 10 weeks after P3 gate).*
