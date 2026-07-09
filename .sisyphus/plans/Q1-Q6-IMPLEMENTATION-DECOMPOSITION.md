# Q1–Q6 Implementation Decomposition (verified against live tree)

**Source:** `.sisyphus/drafts/Q1-Q6-DESIGN-QA.md` (browser-LLM answers) + repo verification at commit `2160c6a1`.
**Verification rule applied (per draft §"Anti-fabrication rule"):** every premise grepped against store + consumers, not taken from the draft's prose. See §0 for five discrepancies found.

**Dependency spine:** Epic 2.3 (lexicographic ranking + `agent_id`) is built FIRST. Q1, Q2, Q5 lean on it; Q3, Q4, Q6 are independent and can start now.

---

## §0 — Anti-fabrication corrections (verify before you build)

These were stated as fact in the draft/answers and are **NOT true in the current tree**:

| # | Premise (draft/answer) | Reality (verified) | Impact on task |
|---|------------------------|--------------------|----------------|
| C1 | "Memory write path has **NO** injection scanner" (Q4; draft grep `sanitize_for_injection\|scan_for_injection` = 0) | `scan_for_poison()` **exists** at `app/services/memory/poison_scan.py:78`. Called at staging (`background_review_service.py:398`), direct writes (`personal_memory_service.py:438`), retroactive sweep (`retroactive_memory_sweep.py:151`). Regex-only (invisible/control chars incl. U+202A–202E RTL override, block-escape, code-fence, directive phrases). | Q4 is **EXTEND the existing scanner to hybrid**, not "build the missing piece." |
| C2 | Q1 constraint lane partitioned on `is_negative=true OR claim_type=constraint` | **No `is_negative` column exists** anywhere (0 repo-wide hits). Constraints are `claim_type='constraint'` only (`ALL_CLAIM_TYPES`, `personal_memory_models.py:51`; loaded at `pre_tool_constraints.py:127`). | Q1 constraint lane = `claim_type='constraint'`. The vector-inversion trap still applies (never vector-match a constraint claim); design holds, key on claim_type. |
| C3 | Q3 storage hedge: "use `MemoryEntry` KV if it carries governance columns" | `MemoryEntry` (`memory_entries`) has **no governance columns** — id, workspace_id, user_id, agent_id, session_id, namespace, key, memory_type, content, importance, last_used_at, supersedes_id, source_mission_id, meta(JSONB), deleted_at. No provenance/source_type/trust_tier/confidence/approval. | **Use minimal `skills` table** (Q3-A). `MemoryEntry` reuse is out. |
| C4 | Q5: "PersonalMemoryClaim has no agent_id" | TRUE for `PersonalMemoryClaim` (cols: user_id, workspace_id, subject, predicate, object, claim_type, scope, source_type, sensitivity, confidence, importance, source_id, last_used_at, expires_at, deleted_at — no agent_id). BUT `MemoryEntry.agent_id` **already exists** (`memory_models.py:92`). | `agent_id` migration needed **only on `PersonalMemoryClaim`** (E23-D). |
| C5 | Draft cited `background_review_service.py:358` under `app/services/`; "stage_pending_write only handles MEMORY today" | Real path: `app/services/memory/background_review_service.py:358`. `PendingWriteType.SKILL` **is already in `ALL_PENDING_WRITE_TYPES`** (`memory_models.py:233`) — validator accepts SKILL. | Q3-B: what's missing is reviewer emission + skill-specific ingestion path, NOT the type enum. |

**Positive verifications (spine confirmed real):**
- `recall()` orders by `(confidence DESC, importance DESC, last_used_at DESC NULLS LAST)` (`personal_memory_service.py:675`). **No `source_priority` column exists on `PersonalMemoryClaim`.** → Epic 2.3 ranking is genuinely not code. Q1/Q2 correctly blocked on E23.
- Gate fix live: `2160c6a1` on `main`, clean tree, `workspace_id` threaded through Workflow adapters.

---

## §1 — Verified dependency graph

```
Epic 2.3 (SPINE, build first)
  E23-A  add source_priority column + index (migration)        ─┐
  E23-B  lexicographic comparator (source_priority > recency   ├─► unblocks Q1 (ranking), Q2, Q5-C
          band > confidence > importance), wire into recall()  ─┘
  E23-C  conflict key (subject,predicate) + claim-type prec.   ─┐
  E23-D  agent_id (nullable) on PersonalMemoryClaim (migr.)    ├─► unblocks Q5-A/B/C/D
                                                              ─┘

Q1  Hybrid retrieval      → needs E23-B for competitive ranking; constraint lane (Q1-B) independent
Q2  Ranking + token budget→ needs E23-A + E23-B
Q3  Skill architecture    → INDEPENDENT (but shares governance rails with Q4)
Q4  Injection defense     → INDEPENDENT (extends existing scan_for_poison)
Q5  Multi-agent sharing   → needs E23-D + E23-C
Q6  Reviewer hallucination→ INDEPENDENT
```

---

## §2 — Epic 2.3 (SPINE — build first, code-only epic; design doc at `docs/EPIC-2.3-CONFLICT-RESOLUTION-POLICY-DESIGN.md` is doc-only, 182 lines, zero code at `1234fdbe`)

- **E23-A** — Migration: add `source_priority: Mapped[int]` to `PersonalMemoryClaim` + index. Define precedence map (`source_type` → int; `user_explicit` > `conversation` > `mission` > `program_learning`). Seed from existing `source_type` on migration. Files: `app/models/personal_memory_models.py`, new alembic migration. *See backend AGENTS.md sentinel-UPDATE convention for any NULL handling.*
- **E23-B** — Implement `lexicographic_rank()` (Python, deterministic): `source_priority > recency_half_life_band > confidence > importance` (integer comparisons; recency bucketed into half-life bands so tiny deltas don't flip order). Replace the SQL `order_by` in `recall()` (`personal_memory_service.py:675`) with `source_priority` primary + a final stable Python secondary sort to guarantee cross-machine reproducibility (floating weighted sums can't). Frozen-snapshot capture reuses this ordering.
- **E23-C** — Extend conflict-resolution key from `subject` to `(subject, predicate)` with opposing `object`/`is_negative` (see C2: negation is via `claim_type='constraint'`, not a bool). Resolve by claim-type precedence (constraint/fact > preference/observation) then provenance. Surface contradictions (don't auto-collapse) for Q5 debate.
- **E23-D** — Migration: add `agent_id: Mapped[str | None]` (nullable) to `PersonalMemoryClaim` + index. `NULL` = human-authored (highest trust). (MemoryEntry already has agent_id per C4 — no change there.)

---

## §3 — Q1 — Hybrid recall architecture (after E23-B)

- **Q1-A** (independent of ranking) — Qdrant collection + query-builder wrapper with **fail-closed** tenant filter: mandatory `must={user_id, workspace_id}`, raises if either key missing (mirrors today's SQL WHERE). Payload indexes on user_id, workspace_id, claim_type, is_negative→n/a (use claim_type). One global collection, not per-workspace.
- **Q1-B** (CORRECTION C2) — **Constraint lane = `claim_type='constraint'`**, exact/lexical retrieval (trigram/keyword on (subject,predicate) + exact object match). Never vectorized. This is the trap guard: a "never deploy Fridays" constraint must not be cosine-matched against "deploy Fridays."
- **Q1-C** (independent) — Fuzzy lane (fact/preference/observation): dense (all-MiniLM-L6-v2, 384d, already deployed) + BM25, merge via Reciprocal Rank Fusion `Σ 1/(k+rank)`. Constraints never enter RRF.
- **Q1-D** — Embed canonical triple sentence (`"prefers theme: dark"`), NOT raw JSONB. Keep `object` JSONB in payload for exact filtering/constraint match.
- **Q1-E** — Union lanes by `claim_id`; each claim lives in exactly one lane (partition on claim_type) → dedup-safe, no double-count.

---

## §4 — Q2 — Ranking + token budget (after E23-A + E23-B)

- **Q2-A** — Tier 0 (protected): `claim_type='constraint'` (immortal, `expires_at IS NULL`) gets a reserved budget slice before anything else; never truncated, never ranked vs preferences. Overflow → offline compression at review time, never drop a constraint.
- **Q2-B** — Tier 1 (competitive): rank by E23-B lexicographic policy; bucket recency into half-life bands for determinism.
- **Q2-C** — Token-budget enforcement in `_inject_memory_context` / `recall_for_chat` (`chat_context.py:86`, `memory_citation_service.py:174`): drop lowest-ranked in competitive tier on overflow. **No LLM consolidation at inject time** (non-deterministic, kills prompt cache).
- **Q2-D** — Freeze ranking at snapshot capture (`memory_snapshot_service.py`): store ordered+budgeted set against `thread_id`; reuse verbatim until generation bump / TTL.

---

## §5 — Q3 — Skill architecture (INDEPENDENT)

- **Q3-A** (CORRECTION C3) — Create minimal `skills` table: `name, body, frontmatter(JSONB), trust_tier, version(int), provenance, workspace_id, user_id, agent_id(nullable)`. Migration. **Not** MemoryEntry KV.
- **Q3-B** (CORRECTION C5) — `stage_pending_write` already validates `SKILL` (`ALL_PENDING_WRITE_TYPES`, `memory_models.py:233`). Add: reviewer emission of skill writes + a skill-specific ingestion path distinct from memory (today only MEMORY is produced).
- **Q3-C** — Route skills through existing governance: provenance gate (GOV-1.2), Q4 scanner (mandatory, escalate-only, HITL), same rails as memory.
- **Q3-D** — `skills_list()` (names+descriptions, ~3k tokens) in cached stable tier; `skill_view(name)` loads full body on-demand as a tool call (after cache boundary) → progressive disclosure keeps expensive bodies out of cached prefix.
- **Q3-E** — PATCH > ADD > CREATE, enforced twice: reviewer prompt (PATCH first, class-level names) + hard guard before CREATE — similarity check (reuse vector index) vs existing skill names/descriptions; over threshold → reject CREATE, suggest PATCH. Back with regex rejecting date/task suffixes + per-workspace cap.
- **Q3-F** — Versioning: `version int` + provenance; PATCH bumps; keep last-N bodies for rollback.

---

## §6 — Q4 — Injection defense, write + read (INDEPENDENT; EXTENDS existing)

- **Q4-A** (CORRECTION C1) — `scan_for_poison()` already exists (regex-only, escalate-only, fail-open). Extend to **hybrid**: add homoglyph→ASCII skeletonization (currently missing) + a **semantic/LLM-judge pass** ("does this redirect behavior or exfil credentials?") to catch the `/tmp/keys.env` trap that matches no regex. Keep escalate-only + fail-open invariant (never short-circuits staging).
- **Q4-B** — Indirect-injection defense: fence reviewer *inputs* (transcripts/scraped content) as untrusted before the reviewer reads them; claims derived from untrusted source content inherit lower trust tier + route to HITL. Scan inputs, not just outputs.
- **Q4-C** — Keep read-path fence GOV-1.3b (`chat_context.py:100` `<memory-context>` "not instructions" wrapper) as runtime backstop.
- **Q4-D** — Escalate-only lock mechanically: `final_severity = max(provenance_requirement, scan_requirement)` on ordered scale. Quarantine (not hard-block) for ambiguous middle; reserve hard-block for high-confidence malicious. Scanner can only push scrutiny up.

---

## §7 — Q5 — Multi-agent memory sharing (after E23-D + E23-C)

- **Q5-A** (CORRECTION C4) — `agent_id` (nullable) on `PersonalMemoryClaim` via E23-D. NULL = human-authored (highest trust).
- **Q5-B** — Shared workspace pool, every claim attributed. Agent-authored `program_learning` claims get lower default trust tier → `source_priority` down-ranks so one agent's hallucination can't become another's "fact." Cross-agent consumption still passes governance gate.
- **Q5-C** — DebateProtocol contradiction: key on `(subject, predicate)` with opposing object; resolve by claim-type precedence then provenance; **surface** ("A asserts X, B asserts ¬X") to orchestrator, don't auto-collapse. Needs E23-C.
- **Q5-D** — Snapshot per-`(thread_id, agent_id)`; workspace write bumps generation for all agents; `workspace_id` stays mandatory.

---

## §8 — Q6 — Reviewer hallucination prevention (INDEPENDENT)

- **Q6-A** — Groundedness verification: for each proposed write, retrieve the transcript span it allegedly came from + entailment check. No supporting span = reject/HITL **regardless of stated confidence** (the trap: trusting the reviewer's confidence lets a 0.9 hallucination sail through).
- **Q6-B** — Second-pass verifier, different model family (decorrelated errors); narrow task (does transcript support this claim? yes/no + evidence span) → cheap model reliable. Cheap reviewer + cheap verifier < one expensive reviewer, costs less.
- **Q6-C** — Calibration: don't store raw LLM confidence. Fit isotonic/Platt map `stated → empirical-accuracy` from GOV-1.5 drop logs + HITL outcomes; store calibrated value.
- **Q6-D** — Systemic degradation: track grounding-pass rate, HITL-rejection rate, verifier-disagreement rate + fixed labeled **canary transcript set** re-run on every model/provider change. Jump in verifier disagreement after an update = "model got worse" alarm (per-claim checks miss this).
- **Q6-E** — Verification is escalate-only (composes with Q4-D lock).

---

## §9 — Open sub-checks before build (don't assume)

1. `ALL_PENDING_WRITE_ACTIONS` (memory_models.py) — confirm it covers skill CRUD actions, or Q3-B needs to extend it.
2. `recall_for_chat` determinism — confirm frozen-snapshot capture point can accept E23-B ordering without breaking the existing `(user_id,workspace_id)->generation` counter.
3. Qdrant payload filter `must={user_id,workspace_id}` — confirm existing episodic collection usage (`agent_registry_service.py`) is the pattern to mirror; reuse its client/wrapper.
4. E23 recency half-life band constants — pick band boundaries (e.g. <1d, <7d, <30d, older) and document; must be deterministic + reproducible.
