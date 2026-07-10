# Flowmanner Memory System — Backlog Skeleton (DRAFT, reconciled)

> Status: **DRAFT, NOT CREATED.** Do not instantiate issues until `FLOWMANNER-MEMORY-VERIFY-CHECKLIST.md` (5 items) confirms and Opus says "go."
> Source: `HERMES-MEMORY-PATTERNS-FOR-FLOWMANNER.md` (as-built) + Opus PM review + agent verification (5-item checklist, 2026-07-08).
> Key refinement from verification: GOV-1 (drain via HITL) is the *only* path to audited expiry (C4), and GOV-6 is *wiring* not *building* (C3).
> **Sequencing principle (Opus):** dependency-critical ≠ sequence-first. 1.1 is the highest-*blocking* node (most issues depend on it) but it is NOT first to execute — four independent items ship around it while it's built. Don't conflate the two.

---

## Epic 1: Memory Governance Layer — revised execution ordering

> 1.3 originally bundled two controls with different code paths (`stage_pending_write` vs `_inject_memory_context`), different dependency profiles, and different failure modes. Bundling manufactured a false shared blocker so the independent win (1.3b) inherited the slower item's timeline. **Split into 1.3a / 1.3b / 1.3c.** (Flagged by the agent's reconciliation; Opus confirmed.)

**Revised order:**

| Seq | Issue | Dependency | Notes |
|-----|-------|-----------|-------|
| **1st** | **1.3b — Read-side fencing at `_inject_memory_context`** | None — independent, defends live path | `<memory-context>` wrap + scrubber on recall (`chat_service.py:28/436`). The *only* Epic-1 control defending the live agent today, and it defends against poison **already in the store**, not just future writes. Pull to position one. **Caveat (harm reduction):** fencing is mitigation, not neutralization — a wrapped injected instruction is still visible to the model; framing + scrubbing reduce efficacy, they don't zero it. 1.3b shipping must NOT relieve pressure on 1.1/1.2; status must never read "poisoning is handled." Frame as harm reduction while the real gate is built, in those words. |
| **Parallel** | **1.2 — Provenance-gated approval policy** | None (writes route to staging, which exists) | `source_type ∈ {fetched, tool_output, third_party}` → mandatory human approval, **no confidence bypass**. Deterministic policy control — the reliable control. Reuses existing columns; ships before any sanitizer. |
| **Parallel** | **1.3a — Extraction-time scan at `stage_pending_write`** | None; pairs with 1.2 | Heuristic regex/Unicode pattern match at `background_review_service.py:235` (doc #4/#21) to catch poison *before* persist. Triage aid, **not** the reliable control. **Escalate-only hard rule (acceptance criterion):** scan output may ESCALATE (flag, annotate, prioritize for review) but NEVER de-escalate. It must never downgrade a provenance-mandated approval. (Failure mode to design out: 6 months from now "scan passed, so auto-apply this fetched-source write" — reintroduces the confidence-bypass hole via a side door. Scan-pass, like confidence, is a signal an attacker optimizes against. Write this sentence into 1.3a's acceptance criteria.) |
| **Parallel** | **1.7 — Reviewer reliability** | None | Retry policy on `review_mission`; log gaps when reviewer crashes (no silent memory holes). |
| **Then** | **1.1 — Drain `pending_writes` via existing HITL inbox** | Blocks 1.4, 1.5, 1.6, 1.3c, Epic 2, 4.1 | Routing change, not UI build. Conditions (Opus): separate queue/filter from action approvals (no SLA contention); memory writes never block missions. **Bonus (C4):** routing inherits `hitl_expiry.py`'s audited auto-reject for free — the *only* path to expiry-as-decision (native `pending_writes` sweeper absent). **Audit-path check (C3):** verify the audit write path actually persists — do NOT inherit `PersonalMemoryService._safe_audit`'s no-op. A drain built on a logging path that swallows everything would make 1.4's audit trail silently empty; check this before relying on either issue's audit assumption. |
| **Then** | **1.3c — One-time retroactive store sweep** | Scanner from 1.3a; review surface from 1.1 | Run the 1.3a scanner over existing `personal_memory_claims` + `memory_entries` (never scan-protected — store may already be poisoned; 1.3a only protects future writes). Flag hits for human review via 1.1's drain once it exists, or a simple report before then. Cheap; reuses 1.3a's scanner; clears the historical exposure window. |
| **Then** | **1.4 — Expiry-as-decision audit** | Blocked by 1.1 | Verify HITL sweeper (`hitl_expiry.py`) covers routed pending_writes. Expired = auto-rejected + logged + counted. **Explicitly rejects the doc's auto-approve-after-7-days proposal** (Standing Decision 1). **Acceptance criteria:** (a) **Sweeper-race check (C4 conflict resolution):** confirm no *native* `pending_writes` sweeper exists (one grep settles it) — if one does, **disable it as part of the HITL routing cutover**. A silent sweeper would delete staged writes before a human reviews them, silently undermining the entire drain. (b) **Audit-path check (C3):** verify the audit write path actually persists — do not inherit `PersonalMemoryService._safe_audit`'s no-op. |
| **Then** | **1.5 — Threshold calibration instrumentation** | Blocked by 1.1 | Log dropped candidates with scores (C5: none today); calibrate the 0.85 gate on **trusted-source** writes only (untrusted are policy-gated by 1.2). |
| **Then** | **1.6 — Close feedback → durable memory loop** | Blocked by 1.1 | **Wiring not building (C3):** `PersonalMemoryService._safe_audit` no-ops; `MemoryCorrectionService` exists but is unwired — connect it + make corrections influence decay/reviewer. Also expose dropped candidates in Inspector (C5). |

## Epic 2: Store Reconciliation — blocked by Epic 1 (blast-radius argument)

| # | Issue | Notes |
|---|-------|-------|
| 2.1 | **Canonical-store decision + promotion pipeline design** | Design doc first: `MemoryEntry` → claim promotion vs union-at-recall vs single store. All promoted writes route through 1.1/1.2. |
| 2.2 | **Agent-side frozen snapshot** | Doc #7 at agent layer; assess token cost + stale-vs-live policy. |
| 2.3 | **Conflict resolution policy** | Source priority > recency > confidence; surface unresolved conflicts in Inspector, never silently resolve. |

## Epic 3: Retrieval & Lifecycle

| # | Issue | Notes |
|---|-------|-------|
| 3.1 | **Instrument `last_used_at` on claim recall** | Column exists, never written (verified). Small; blocks 3.3. |
| 3.2 | **Migrate `last_used_at` (+ importance decay fields) onto `MemoryEntry`** | Section D migration never applied (doc confirms `MemoryEntry` lacks the column). Write fresh migration. Blocks 3.3. |
| 3.3 | **Decay job** | Soft-archive + importance decay weighted by recency; negative constraints immortal (doc §C); hard-delete only expired `sensitive`. Blocked by 3.1 + 3.2. |
| 3.4 | **Unify retrieval** | Vector-index or rank claims; retire pure substring recall (fails on fuzzy preferences). |
| 3.5 | **Enforce injection token cap with ranked top-k** | Ranking = importance × recency × confidence; no silent truncation. |
| 3.6 | **Provenance trace surface** | "Why does the agent believe X" — data exists (`source_mission_id`, SSE events); expose it. |
| 3.7 | **Scope isolation test** | `workspace_id`/`user_id` composition under test — multi-tenant privacy. Independent, cheap, do early. |

## Epic 4: Constraints & Procedural Memory

| # | Issue | Notes |
|---|-------|-------|
| 4.1 | **Constraint/negative claim type + enforcement at tool dispatch** | Wire into existing HITL gate — "connect type to gate," not "build gate" (C2 confirms HITL gates destructive tools via `node_executor`). Contingent on verifying hitl.py intercepts risky paths (C2 confirmed). |
| 4.2 | **Don't-capture list in reviewer prompt** | Doc pattern #16; pairs with 4.1; very cheap; prevents "I failed once so never again" hardening. |
| 4.3 | **Skill model + write hierarchy** | PATCH > ADD support > CREATE (pattern #15); skill writes route through Epic 1's gate. Largest; last. |

---

## Dependency graph
```
EXEC ORDER (not = dependency!):
 1.3b (independent) ── first
 1.2 (parallel) ─┐
 1.3a (parallel) ─┤  escalate-only vs 1.2 (never de-escalate provenance-mandated approval)
 1.7 (parallel) ─┘
        │
        ▼
 1.1 (drain — highest-BLOCKING node, but not first to execute)
        │  blocks:
        ├── 1.3c (retroactive sweep; scanner=1.3a, review surface=1.1)
        ├── 1.4 (expiry — relies on 1.1's HITL routing for audited sweep)
        ├── 1.5 (calibration, blocked on 1.1)
        ├── 1.6 (feedback wiring, blocked on 1.1; C3 = wiring not building)
        ├── Epic 2 (2.1/2.2/2.3, blast-radius argument)
        └── 4.1 (shares gate; C2 confirmed HITL gates destructive tools)
3.1 ──► 3.3   (3.2 ──► 3.3)   hidden blocker pair inside Epic 3
1.3b, 1.2, 1.3a, 1.7, 3.7 independent of 1.1
```

## Sequencing summary (Opus's revised ordering, verification-refined)
1. **Ship in parallel (while 1.1 is built):** 1.3b (read-side fencing, *first* — defends live path + clears present exposure), 1.2 (provenance gate — deterministic reliable control), 1.3a (extraction scan — heuristic triage, escalate-only vs 1.2), 1.7 (reviewer reliability).
2. **Then drain:** 1.1 (HITL routing; gives audited expiry via C4). Highest *blocking* count, but executed after the four independent wins.
3. **Then retrospective:** 1.3c (retroactive store sweep reusing 1.3a's scanner; review via 1.1's drain).
4. **Then locked sequence:** 1.4 → 1.5 → 1.6 (all blocked on 1.1; 1.6 wiring not building per C3).
5. **Store reconciliation:** 2.1/2.2/2.3 — blocked on Epic 1 (blast-radius argument).
6. **Retrieval & lifecycle:** 3.4/3.5/3.6/3.7 open; **3.1 + 3.2 must land before 3.3** (the two-part `last_used_at` hidden dependency).
7. **Constraints & procedural:** 4.1 (cheap, gate-reuse, C2-confirmed) + 4.2 (don't-capture, cheap) + 4.3 (skill store, last).

## Standing decisions (locked, do not drift on instantiation)
1. **No auto-approve-after-7-days.** Expiry = audited auto-reject. Fatigue mitigation = batch UX + digests.
2. **Don't-capture list (doc #16) = Epic 4 issue 4.2.**
3. **`last_used_at` = two issues (3.1 claims, 3.2 entries).**

## Before instantiation (Opus gate)
- [x] 5-item checklist run by agent (2026-07-08) — C1/C2/C5 confirmed, C3/C4 partial (refinements applied above).
- [x] Anchor-8 caveat resolved: HITL gates destructive tools via `substrate/node_executor.py` (C2 confirmed).
- [ ] Opus confirms none of C3/C4 refutes the affected issues (they refine, not refute).
- [ ] Opus says "go."
