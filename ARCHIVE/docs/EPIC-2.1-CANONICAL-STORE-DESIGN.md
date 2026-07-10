# Epic 2.1 — Canonical-Store Decision & Promotion Pipeline Design

> Status: **IMPLEMENTED** — commit `84403041` (`feat(memory): Epic 2.1 re-point reviewer writes to personal_memory_claims`). Originally a DESIGN DOC (2026-07-09, "no code"). The build landed 2026-07-10. This file is now a **design record**, not an open task.
> Author: Hermes (homelab agent) | Date: 2026-07-09 | Machine: homelab `/opt/flowmanner/backend`
> Sequence context: GOV-1.1–1.6 (Epic 1) locked + pushed (HEAD `050af5f0`). Epic 2 unblocked.
> Source of truth for this doc: the code as read on 2026-07-09 (file:line citations below).
> Companion issues: **2.2** (agent-side frozen snapshot), **2.3** (conflict resolution policy).

---

## 0. TL;DR — the decision

**Make `personal_memory_claims` the single canonical store for governed personal memory. Demote `memory_entries` to a legacy/agent-KV substrate. Route *every* reviewer write — direct and HITL-approved — through `PersonalMemoryService` so it lands in claims, not entries.**

Rationale in one line: the live read path (`chat_service` → `recall_for_chat` → `PersonalMemoryService.recall`) **already** reads only `personal_memory_claims`, and that store is the one Epic 1's entire governance layer (1.1–1.6) defends. `memory_entries` is where the reviewer actually *writes* today — an orphaned write that no live path consumes. The only way to make the governance layer mean anything is to make it the only thing the writer can target.

This is **not** a research spike. It is a structural finding: the two stores are already split across the read/write seam, the read side already won, and the write side is the only thing that needs moving.

---

## 1. The problem (verified against code)

Flowmanner has **two disjoint per-user/per-workspace memory tables**, and they sit on opposite sides of the read/write seam.

### 1.1 `personal_memory_claims` — the *governed* store (read side)

- Model: `app/models/personal_memory_models.py:80` `class PersonalMemoryClaim`, table `personal_memory_claims` (`:90`).
- Schema guards (the governance backbone):
  - `workspace_id` **NOT NULL**, `user_id` NOT NULL (`:130`, `:136`) — workspace isolation is DB-enforced.
  - `(subject, predicate, object)` triple + `claim_type`/`scope`/`source_type`/`sensitivity` with **CHECK constraints** (`:92–107`).
  - `confidence`, `importance`, `source_id` provenance (`:159–164`).
  - `last_used_at`, `expires_at`, `deleted_at` — **soft-delete + TTL** (`:167–179`).
- **Every read filters by `(user_id, workspace_id)` together** and hides soft-deleted / expired rows (`app/services/personal_memory_service.py:14–23`, `recall` at `:425`). This is the only store the Epic-1 controls actually fence.
- Consumed by the live agent path: `chat_service.py:441` → `recall_for_chat` (`app/services/memory_citation_service.py:174`) → `PersonalMemoryService.recall` (`:206`, `:425`). After the defensive scrub + sensitivity/scope filter, these claims are injected into the LLM prompt (`chat_service.py:484` `_inject_memory_context`, or the prepareStep hook at `:476`).

### 1.2 `memory_entries` — the *legacy* store (write side)

- Model: `app/models/memory_models.py:64` `class MemoryEntry`, table `memory_entries` (`:74`).
- Schema: `workspace_id` **NULLABLE** (`:81`), `user_id` nullable; supports KV (`namespace`+`key`) and agent memory (`agent_id`+`content`+`memory_type`+`importance`). **No `claim_type`/`scope`/`sensitivity`/soft-delete/expiry columns.** No `(user_id, workspace_id)` composite isolation index.
- This is the table the **background reviewer writes to**:
  - `BackgroundReviewService.add_reviewed_entry` (`app/services/memory/background_review_service.py:257`) — direct write to `memory_entries` (per its own docstring "direct write to `memory_entries`").
  - `apply_proposed_writes` (`:833`): when `write_approval=False`, direct ADD writes go to `add_reviewed_entry` → `memory_entries` (`:874`); REPLACE supersedes an existing entry (`:928`).
  - `resolve_pending_write` (`:461`): **HITL-approved** writes also land in `memory_entries` via `add_reviewed_entry` (`:525`, `:548`).
- **Read of `memory_entries` in the live agent path: NONE.** `grep` for `memory_entries|MemoryEntry` across `chat_service.py`, `memory_citation_service.py`, `personal_memory_service.py`, `chat_context.py` returns zero hits.

### 1.3 The disconnect (the actual Epic 2.1 bug)

```
          reviewer LLM
                │
   write_approval=false ──► apply_proposed_writes ──► add_reviewed_entry ──► memory_entries   (UNGOVERNED, orphaned)
                │
   write_approval=true  ──► pending_writes ──► HITL approve ──► resolve_pending_write ──► memory_entries  (UNGOVERNED, orphaned)
                │
   GOV-1.x gates (1.1/1.2/1.3abc) only defend the staging + claims path, not memory_entries

   live chat ──► recall_for_chat ──► PersonalMemoryService.recall ──► personal_memory_claims  (GOVERNED, but never receives reviewer writes)
```

- The reviewer **writes** to `memory_entries`. The live agent **reads** `personal_memory_claims`.
- Net effect: **approved/auto-applied reviewer memory is written to a table the agent never reads.** It is effectively invisible to the running agent. The whole Epic-1 governance investment (provenance gate, read-side scrub, audit trail, expiry-as-decision) protects `personal_memory_claims` — but the writer bypasses it entirely.
- `memory_entries` *does* have readers, but they are **dead/orphaned**:
  - `MemoryService.retrieve_by_query` (`app/services/memory_service.py:305`) reads `memory_entries` filtered by `agent_id` + `importance`, **no workspace isolation** (`:322–328`).
  - `MemoryIntegration.inject_memories` (`app/services/nexus/memory_integration.py:47`) calls `retrieve_by_query` — but `inject_memories` / `MemoryIntegration` has **no caller anywhere** outside its own module (`grep` for `inject_memories|MemoryIntegration|get_memory_integration` across `app/` returns only the definition + the factory). It is not wired into `chat_service` (the only memory flag there is `CHAT_MEMORY_CITATIONS_ENABLED`, `chat_service.py:437`, which routes to `recall_for_chat` → claims).

### 1.4 Why this is a governance hole, not just duplication

Epic 1 spent 6 issues building controls *around* `personal_memory_claims` (read-side scrub, provenance gate, audit, expiry, calibration, feedback loop). Those controls are **circumvented by construction** as long as the reviewer's durable write target is `memory_entries`:

- No `source_type` provenance on `memory_entries` → GOV-1.2 (mandatory human approval for `fetched`/`tool_output`/`third_party`) has nothing to enforce on the reviewer's own writes.
- No soft-delete/expiry on `memory_entries` → GOV-1.4 (expiry-as-decision) does not apply to reviewer-written memory.
- No sensitivity/scope → GOV-1.3b scrub + `memory_citation` sensitivity filter cannot run (there is nothing to filter).
- No `workspace_id` NOT NULL → the multi-tenant isolation guardrail (Epic 3.7 scope-isolation test) is not enforced on `memory_entries` rows.

So 2.1 is not "which store is nicer" — it is "make the governed store the only write target, or admit Epic 1's controls are decorative."

---

## 2. The three candidate resolutions

| Option | What | Verdict |
|---|---|---|
| **A. Promote `MemoryEntry` → claim** (migrate writer to claims) | Re-point reviewer writes to `PersonalMemoryService.create`. Retire `memory_entries` from the personal-memory path. | **RECOMMENDED.** Reuses the already-governed store + read path; no dual read path to maintain. |
| **B. Union-at-recall** (read both stores, merge) | Read claims + entries, rank/merge in `recall_for_chat`. | Rejected. Keeps the ungoverned `memory_entries` writable forever; doubles the governance surface; GOV-1.2/1.3b/1.4 still don't apply to entries. Perpetuates the hole. |
| **C. Single new store** (model `MemoryEntry` on `PersonalMemoryClaim`, migrate both) | Big-bang rewrite of one table to absorb the other. | Rejected for 2.1 scope. Claims already have the right shape + constraints + read path. Don't throw that away. (Could be revisited in a later epic if KV-agent-memory needs its own home — see §6.) |

**Decision: Option A**, with `memory_entries` retained only for its *intended* legacy role (non-governed agent KV / `namespace`+`key` substrate) and explicitly **removed from the personal-memory write/read path**.

---

## 3. Promotion pipeline design (Option A)

### 3.1 Target write surface

All reviewer writes route through `PersonalMemoryService` (the existing canonical surface, `app/services/personal_memory_service.py`). The reviewer's `ProposedWrite` (action `add`/`replace`/`remove`) maps onto claim operations:

| Reviewer action | Today (bad) | After 2.1 |
|---|---|---|
| `ADD` (write_approval=false) | `add_reviewed_entry` → `memory_entries` (`:874`) | `PersonalMemoryService.create(...)` → `personal_memory_claims` |
| `ADD` (staged → HITL approve) | `resolve_pending_write` → `add_reviewed_entry` → `memory_entries` (`:525`) | `resolve_pending_write` → `PersonalMemoryService.create` → `personal_memory_claims` |
| `REPLACE` | `supersede_entry` on `MemoryEntry` (`:928`) | soft-replace a claim: create successor + set `supersedes` link; old claim `deleted_at` set (immortal-negative-constraint rule preserved — **never hard-delete**, per `background_review_service.py:560` doc) |
| `REMOVE` | row marked resolved, comment "left to store-reconciliation epic" (`:559–563`) | soft-delete the claim (`deleted_at`, never hard delete) — this is exactly Epic 2.3's conflict-resolution surface; 2.1 wires the *mechanism*, 2.3 defines *policy* |

### 3.2 Mapping `MemoryEntry` fields → `PersonalMemoryClaim` fields

`MemoryEntry` has no triple, no taxonomy, no provenance. The promotion needs a deterministic mapping so we don't silently drop governance fields:

| `MemoryEntry` | → `PersonalMemoryClaim` | Notes |
|---|---|---|
| `content` (free text) | `subject` / `predicate` / `object` | Heuristic parse: if content is a single fact, `subject`=inferred user/agent, `predicate`=`is`/`prefers`, `object`=`{ "text": content }`. **Caveat:** free-text→triple is lossy; the extractor must do this, not a dumb copy. Flag low-confidence parses for human review (reuse GOV-1.5 calibration). |
| `memory_type` (`episodic`/`semantic`/…) | `claim_type` ∈ `{fact, preference, observation, sensitive}` | Map `episodic`→`observation`, `semantic`→`fact`. No `sensitive` unless the defensive scan (1.3a) flags it. |
| `importance` | `importance` | Direct copy. |
| (absent) | `confidence` | Set from reviewer score if present, else default `0.5` + flag for calibration. |
| `source_mission_id` | `source_id` (UUID) + `source_type` | `source_type` must be set to a real value (`fetched`/`tool_output`/`agent`/`third_party`) so GOV-1.2 can evaluate it. **This is the load-bearing fix** — today entries carry no `source_type`, so the provenance gate cannot fire. |
| `workspace_id` / `user_id` | `workspace_id` (NOT NULL) / `user_id` | Carry through. If `workspace_id` is null on an entry, **this is a data-integrity error** → fail the promotion + log (do not write a claim with a guessed workspace). |
| `scope` | default `personal` | Reviewer writes are user-scoped by default; never `private` (would be filtered from chat) unless explicitly derived. |
| `sensitivity` | default `normal` | Unless scan flags it. |

### 3.3 `PersonalMemoryService` gap: needs a "create from reviewer proposal" method

`PersonalMemoryService.create` exists but must accept the governance fields above (it does). The 2.1 build task is to add a thin adapter (e.g. `PersonalMemoryService.create_from_proposal(proposed, *, workspace_id, user_id, source_mission_id)`) that:
1. Enforces `workspace_id` NOT NULL (raises if missing — never silently defaults).
2. Sets `source_type` from the proposal (reject `None`/`unknown`).
3. Runs the existing GOV-1.3a scan + GOV-1.3b scrub *on the way in* (today the scan is only at `stage_pending_write`; promotion must also scan direct writes — see §3.5).
4. Writes the audit event via the existing `_MemoryCorrectionAudit` adapter (so GOV-1.4/1.6 trails cover reviewer writes too — today they don't, because entries bypass claims).

### 3.4 Re-point the writer (the actual code change)

- `BackgroundReviewService.add_reviewed_entry` (`:257`): **replace body** to delegate to `PersonalMemoryService.create_from_proposal`. Keep the signature (callers at `:525`,`:548`,`:874`). Keep the no-raise / return-`None`-on-failure contract so the Celery worker behavior is unchanged.
- `BackgroundReviewService.supersede_entry` (`:644`): replace `MemoryEntry` supersede with claim soft-replace (create successor + link + `deleted_at` on old).
- `resolve_pending_write` (`:461`): the `add_reviewed_entry` calls already route through `add_reviewed_entry`, so they pick up the change for free.
- `apply_proposed_writes` (`:833`): no structural change needed — it already calls `add_reviewed_entry`/`supersede_entry`. Good: the re-point is *localized* to two methods.

### 3.5 Governance must apply to direct (non-HITL) writes too

Today `apply_proposed_writes` direct-writes (`write_approval=false`) skip staging and go straight to `memory_entries` (`:872–888`). After 2.1 they go to claims — which means the GOV-1.2 provenance gate and GOV-1.3a scan **must run on these too**. Confirm the proposed-write validator (`compute_write_approval` + `is_destructive()`) still gates them; if `write_approval=false` currently means "skip all gates," that is a pre-existing hole that 2.1 *must not* inherit. 2.1's acceptance criterion: **every reviewer write, direct or approved, passes through the same `create_from_proposal` gate** — no fast-path that bypasses `source_type` enforcement or the scan.

---

## 4. What happens to `memory_entries`

- **Keep the table** (don't drop — backward-compat, and it backs the agent-KV / `namespace`+`key` use the model doc cites at `memory_models.py:64`).
- **Remove it from the personal-memory path.** No reviewer write, no chat recall, touches it for *personal* memory.
- **Audit existing rows.** A one-time `SELECT COUNT(*) FROM memory_entries` (and by `workspace_id IS NULL`) to size the backfill. Likely small (the feature is young). Decision on backfilling old entries → claims: **out of scope for 2.1** (it's a data-migration task; flag for 2.2/2.3 or a dedicated migration issue). If any `memory_entries` rows are currently being *read* by a live path, that path is the dead `MemoryIntegration` — confirm and disable (see §1.3) rather than migrate.
- **Epic 3.7 scope-isolation test** should add `memory_entries` to its negative cases (workspace isolation is nullable there) — but only as a "this legacy table is out of governance scope" assertion, not a fix.

---

## 5. Risks / open questions (to resolve before build)

1. **Free-text→triple lossiness** (§3.2). Low-confidence parses must surface in the Inspector, not silently degrade. Needs the extractor + a calibration threshold. *Owner: 2.1 build, pairs with GOV-1.5 calibration.*
2. **`source_type` source of truth.** The reviewer LLM must emit a real `source_type` per proposed write, or GOV-1.2 cannot gate it. Confirm `ProposedWrite` schema carries it; if not, extend it (small schema change, no migration — string constant).
3. **REPLACE semantics.** Claim soft-replace must preserve the "negative constraints are immortal" rule (`background_review_service.py:560`). Confirm `create_from_proposal` never hard-deletes.
4. **Backfill of pre-2.1 entries.** Size it (§4); decide migrate-vs-leave. Likely leave + document, since live path never read them anyway.
5. **Does any live path read `memory_entries`?** Verify the dead `MemoryIntegration` is truly unwired (§1.3) and disable it so nothing resurrects the orphan read. This is a cheap, high-value cleanup that *should* ship with 2.1.

---

## 6. How 2.1 frames 2.2 and 2.3

- **2.2 (agent-side frozen snapshot):** Once claims are canonical, the "snapshot" is a frozen `recall_for_chat` result (claims already support `last_used_at` at `:167` — wiring is Epic 3.1). 2.1 makes the snapshot source unambiguous: it's `personal_memory_claims`. Token-cost/staleness policy is unchanged by store choice.
- **2.3 (conflict resolution):** Resolution operates on claims: `source priority > recency > confidence`, surface unresolved in Inspector. 2.1's soft-replace (§3.4) is the *mechanism* 2.3's *policy* drives. Unresolved conflicts live in `personal_memory_claims` (multiple live claims with overlapping subject/predicate) — never silently merged, per the backlog note.

---

## 7. Acceptance criteria (for the build task that follows this doc)

- [ ] `BackgroundReviewService.add_reviewed_entry` + `supersede_entry` write to `personal_memory_claims` (proven by a test that asserts the row lands in claims, not entries).
- [ ] `PersonalMemoryService.create_from_proposal` enforces `workspace_id` NOT NULL and rejects `source_type=None/unknown`.
- [ ] Direct (non-HITL) reviewer writes pass through the same gate as staged writes (no bypass path).
- [ ] GOV-1.3a scan + GOV-1.3b scrub + GOV-1.4 audit apply to reviewer writes (claims now carry the audit trail).
- [ ] `memory_entries` receives no personal-memory write from the reviewer path; `MemoryIntegration` confirmed unwired and disabled.
- [ ] Recall path unchanged (still `personal_memory_claims` only) — no live-path regression; existing `test_personal_memory_service.py` / `test_memory_feedback_loop.py` still green.
- [ ] Migration: **none required** for 2.1 (only the dead `MemoryIntegration` removal, which is a code delete, not a schema change). Backfill, if any, is a separate issue.

---

## 8. Verification done for this doc (evidence ledger)

- `personal_memory_claims` schema + NOT NULL workspace_id: `app/models/personal_memory_models.py:80–179`.
- Read path → claims only: `chat_service.py:436–446`, `memory_citation_service.py:174–213`, `personal_memory_service.py:14–23,425`.
- Write path → entries: `background_review_service.py:257–307 (add_reviewed_entry)`, `:461–591 (resolve_pending_write)`, `:833–958 (apply_proposed_writes)`, HITL wiring `app/api/v1/hitl.py:262–284`.
- `memory_entries` readers unwired: `memory_service.py:305–361`, `nexus/memory_integration.py:47–84`; no external caller (`grep inject_memories|MemoryIntegration` → definition only).
- GOV-1.6 closed + pushed: HEAD `050af5f0`; `git status` clean; `origin/main` up to date (verified 2026-07-09).

---

*Next: Glenn reviews this design. If approved, the build is a localized writer re-point (§3.4) + a `create_from_proposal` adapter (§3.3) + dead `MemoryIntegration` disable (§5.5) — no migration, low blast radius. 2.2/2.3 follow.*
