# Q2-Q3 2026 — Agentic Workflow Plan for FlowManner

**Status:** SKELETON — basic structure + seed ideas. To be expanded by Opus (or whoever runs the Q2 planning pass).
**Created:** 2026-06-12 by hermes-agent
**Owner:** Glenn (decisions), Opus (plan expansion), coding agents (execution)
**Supersedes:** `docs/REBUILD-ROADMAP.md` (archived to `.sisyphus/plans/OLD/REBUILD-ROADMAP-2026-06-12.md`)

---

## 1. Strategic Position

> [Opus: fill in. Where does FlowManner sit vs LangGraph / CrewAI / AutoGen / Claude Agent SDK / OpenAI Agents SDK? What's the wedge?]

**Seed idea:** FlowManner's substrate advantage is first-class HITL + cost attribution + leases + circuit breaker. Most competitors don't have HITL or cost at the platform level — they bolt it on. The wedge: "the agentic platform where you can see what every step costs and pause/resume any workflow with a human in the loop." That's not marketing — it's the substrate that already shipped across Q1-A + Q1-B.

**Capabilities that would make FlowManner the obvious choice for [X]:**
- [Opus: define X — long-running research agents? multi-step coding? data-pipeline orchestration? enterprise workflow automation?]
- [Opus: 3-5 capabilities, ranked by impact]

**What to NOT build (be ruthless):**
- [Opus: 3-5 things to explicitly skip. Probably: agent marketplace, multi-modal (out of scope), federation (Phase 5), self-improving agents (Phase 5)]

---

## 2. Q2-Q3 Roadmap — 4-6 Chunks

> [Opus: 4-6 chunks. For each, use the exact template below. Don't pad — if you can't fill in Code surface concretely, the chunk is too vague.]

### Chunk template (copy per chunk)

```
### Chunk N: <name>
**Summary:** <1 line>
**Why now:** <which gap it closes, 1-2 lines>
**Code surface:** <specific files/modules, not "backend changes">
**Dependencies:** <what must exist first; can this run in parallel with others?>
**Success criteria:** <3-5 testable outcomes, not "feels better">
**Risk:** <1-2 things that could go wrong + mitigation>
**Estimate:** <1w / 2w / 4w>
```

### Chunk candidates (Opus: pick 4-6, reorder by value)

- **A. Episodic memory with sparse retrieval** — store mission outcomes + step traces, retrieve top-k by relevance for future runs. Foundation for "agents that learn from past runs."
- **B. Tool routing (sparse tool selection)** — given a step's context, pick the right tool without enumerating all options. MoE-style or learned selector.
- **C. Multi-agent coordination** — agents that hand off tasks, share state, coordinate. Substrate: HITL pause + leases + cost attribution already supports this.
- **D. Adaptive reasoning depth** — agent decides when to plan deeply vs act shallowly. HITL integration: when depth is exhausted, surface to human.
- **E. Long-horizon context management** — sparse attention over mission history. Token-efficient summaries + selective retrieval.
- **F. Self-correction / retry with cost ceiling** — agents that detect failure and retry within a cost budget, not blindly. Uses cost attribution substrate directly.

---

## 3. Sparse Attention Translation

> [Opus: pick 3 of the chunks above and show how "sparse by default" shaped the design. ~1 page.]

**Three decisions to expand:**

1. **Context retrieval** (Chunk A or E) — how does an agent decide which prior steps to attend to? Sparse retrieval (BM25+vector over mission history) vs full-context replay? Cap at N episodes per query.
2. **Tool routing** (Chunk B) — how does it avoid calling irrelevant tools? MoE-style routing vs brute-force tool enumeration?
3. **Reasoning depth** (Chunk D) — when to plan deeply vs when to act shallowly? Adaptive compute based on step criticality?

> [Opus: write 1 paragraph per decision, showing the design trade-off + the chosen approach.]

---

## 4. Integration Points

> [Opus: for each chunk in §2, show how it uses the existing substrate.]

**Substrate primitives available (all shipped):**
- Worker leases: `claim/release/renew` in `backend/app/services/leases.py`, stale reclaimer
- HITL: `backend/app/services/hitl_service.py` (bulk_resolve, get_by_mission, SSE wrapper)
- Cost attribution: per-step, 6 categories (Q1-B chunk 4)
- Sandbox: code execute + preview
- Circuit breaker: per-workspace+provider with fallback (Q1-A chunk 5)

> [Opus: for each chunk, name the substrate primitives it uses. If new substrate is needed, say so and whether it belongs in this quarter or later.]

---

## 5. Risk Register

> [Opus: 5-8 risks. For each: probability (L/M/H), impact (L/M/H), mitigation, owner-role.]

**Seed risks to consider:**
- Cost: long-running agents on a hosted LLM could blow the per-step cost ceiling. Mitigation: cost attribution already in place, but need hard caps per mission.
- Latency: sparse retrieval adds a DB hop per step. Mitigation: cache hot episodes.
- Privacy: episodic memory may retain sensitive step content. Mitigation: redaction at write time.
- Adoption: Q2 capabilities may not match what users actually want. Mitigation: ship 1 chunk, measure usage, iterate.

---

## 6. Roadmap Corrections

> [Opus: optional. If you find REBUILD-ROADMAP.md (now archived) is wrong, flag here. Don't fix — just flag.]

- [Opus: 0-5 items]

---

## Stop Rule

- 90 min max planning time.
- 5-8 page deliverable.
- If REBUILD-ROADMAP.md is wrong, flag in §6, don't fix.
- When done, send Glenn a 1-paragraph summary: (a) this file path, (b) most surprising decision, (c) biggest risk.

---

## Provenance

This skeleton was created on 2026-06-12 by hermes-agent after:
- 4 P0 investigation files committed (`ca206ff`)
- REBUILD-ROADMAP.md updated with P0 findings (`fb8ec77`)
- Plan hygiene pass: 35774f3..49ec92e (10 stale plans removed, REBUILD-ROADMAP archived)

The full prompt that guided this skeleton is in `.hermes/plans/q2-opus-agentic-workflow-prompt.md` (gitignored, but the plan output target was changed from there to this file).
