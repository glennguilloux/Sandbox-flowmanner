# Epic 2.3 — Conflict-Resolution Policy for Canonical Memory

> Status: **DESIGN DOC (first deliverable of Epic 2.3).** No code, no migration, no deploy.
> Author: Hermes (homelab agent) | Date: 2026-07-09 | Machine: homelab `/opt/flowmanner/backend`
> Sequence context: Epic 2.1 shipped + pushed (`d1720168`, live). Epic 2.2 shipped + live (`a4475c7a`) — frozen snapshot of the canonical store. This doc is the **policy** epic 2.2 explicitly deferred to (see `EPIC-2.2-FROZEN-SNAPSHOT-DESIGN.md:161`, §3.6). 2.2 freezes *whatever the store returns*; 2.3 defines *what the store should return* when multiple live claims overlap.
> Source of truth for this doc: the code as read on 2026-07-09 (file:line citations below, all re-verified against `main` @ `a4475c7a`).

---

## 0. TL;DR — the decision

**Detect overlapping live claims (multiple live claims with the same `(subject)` and overlapping `predicate`), compute a deterministic resolution *ordering* using the precedence `source priority > recency > confidence`, surface unresolved overlaps in the Inspector (never silently merge), and apply the same ordering to `recall()` so the frozen snapshot (2.2) propagates a resolved view. No automatic deletion, no silent merge — surfacing + deterministic ordering only.**

Rationale in one line: today `PersonalMemoryClaim` rows are written independently with no notion of "these two claims contradict each other." The reviewer (`create_from_proposal`) and the direct `create()` path (verified: `personal_memory_service.py:308-347`) both just `db.add(claim)` with **zero overlap detection**. So a user can accumulate several live claims about the same subject that silently disagree, and `recall()` just returns the top-N by `confidence DESC` (`personal_memory_service.py:675-679`) — meaning the *highest-confidence* claim wins by luck, not by policy, and the rest vanish from context with no signal to the human. 2.3 makes the overlap explicit and the winner deterministic.

This is **not** a research spike. It is a scoping + placement decision: *what counts as a conflict*, *what precedence governs the winner*, *where overlaps are surfaced*, and *what the read path returns*. All building blocks (the claim model, `recall()`, the Inspector endpoint) already exist.

---

## 1. The problem (verified against code)

### 1.1 No overlap detection on write

- `PersonalMemoryService.create()` (`personal_memory_service.py:308-347`) builds a `PersonalMemoryClaim`, `db.add`, flush, refresh, audits `claim_created`, then (new in 2.2) `bump_generation`. There is **no check** for an existing live claim with the same `subject`/`predicate`. Confirmed: `grep -n "overlap\|duplicate\|conflict\|existing claim" personal_memory_service.py` → 0 hits.
- `create_from_proposal()` (the reviewer path, `:349+`) is a thin adapter that bridges the reviewer's `source_type` vocabulary to `ALL_SOURCE_TYPES` and calls `create()`. It inherits the same no-dedup behavior. Confirmed `grep` on the whole service for `conflict|overlap|duplicate` → 0 hits.
- Consequence: the same user can have, e.g., ("Glenn", "prefers", {coffee: espresso}) and ("Glenn", "prefers", {coffee: tea}) both live simultaneously. Neither is wrong structurally; they are *in tension*. Nothing flags it.

### 1.2 The read path picks a winner by accident, not policy

- `recall()` (`personal_memory_service.py:620-682`) filters by `(user_id, workspace_id, NOT deleted, NOT expired, confidence >= min_confidence, scope IN scopes)` and a substring match on `(subject, predicate)`, then **orders by `confidence DESC, importance DESC, last_used_at DESC NULLS LAST`** and `.limit(top_k)` (`:675-679`).
- When two overlapping claims exist, the one with the higher `confidence` simply sorts first and the other is dropped by `top_k` — but **only if it's in the same `top_k` window**, and with **no signal** that a competing claim was suppressed. There is no `source priority` or `recency` tiebreak in the ordering — `last_used_at` is the only recency proxy, and 2.2 deliberately bumped it *once per session* (not per message), so it no longer reflects "most recent write" for the live set.
- Because 2.2 froze this set (the snapshot captures `recall()` once at session start), **whatever `recall()` returns is now the stable context for the whole conversation**. That makes a *deterministic, policy-driven* resolution ordering more important than ever — a frozen snapshot of an accidentally-arbitrary winner is worse than a per-message view. This is exactly the dependency 2.2's §3.6 foresaw: "2.2 must capture the snapshot *after* any 2.3 resolution has been applied."

### 1.3 The Inspector can't show conflicts

- `GET /personal_memory/inspector` (`app/api/v2/personal_memory.py:163-190`) returns a **flat paginated list** of claims via `service.list_for_user(...)` — no grouping, no overlap flag, no "these two conflict" signal. A human reviewing memory sees a list, not a conflict map.

### 1.4 What the model already carries

`PersonalMemoryClaim` (`app/models/personal_memory_models.py:79-178`) has exactly the fields 2.3 needs to reason about precedence:

| Column | Type | Role in 2.3 precedence |
|---|---|---|
| `subject` | `str(255)` | Conflict key (who/what the claim is about) |
| `predicate` | `str(100)` | Conflict key (the relation — "prefers", "works_at", …) |
| `object` | `JSONB` | The value; two claims conflict when `subject`+`predicate` match but `object` differs |
| `source_type` | `str(30)` ∈ `{mission, conversation, program_learning}` | **Source priority** axis (see §3.1) |
| `confidence` | `float` `[0,1]` | Confidence axis (already in `recall()` order) |
| `last_used_at` | `DateTime?` | Recency axis (weaker post-2.2, but still a tiebreak) |
| `created_at` | (TimestampMixin) | True "recency of write" — better than `last_used_at` for recency |
| `importance` | `float` | Secondary sort in `recall()`; available as a soft signal |
| `scope`, `sensitivity` | str | Filtering/scrub axes; not precedence |

There is **no `source_priority` numeric column and no `resolution_status` column** — both would be *additive* if we chose the migration path (§2, Option B). Today source priority must be *derived* from `source_type` via a fixed ranking table (§3.1).

---

## 2. The candidate resolutions

| Option | What | Verdict |
|---|---|---|
| **A. Detection + surfacing + ordering, migration-free** | Add an `overlaps_with` / `resolution` *view* computed at query time (no new column): (1) a pure function `resolve_claims(claims)` that groups live claims by `(subject)` + overlapping `predicate` and ranks within a group by `source_priority > created_at > confidence`; (2) `recall()` applies this ranking so the top claim of each group wins deterministically and the suppressed ones are annotated; (3) the Inspector gets an `?overlaps_only=true` query param (or a new `/conflicts` route) returning only groups with >1 live claim, each with the chosen winner + the losers. **No schema change, no Alembic migration** — matches 2.2's "mostly wiring" stop-gate. | **RECOMMENDED.** Same blast-radius discipline as 2.2. Resolution is *computed*, not *stored*, so it's always consistent with the current claim set and never drifts. Surfacing is additive to the Inspector. |
| **B. Detection + persistence (new columns + migration)** | Add `resolution_status` (`live`/`superseded`/`conflict_winner`/`conflict_loser`) and optionally `source_priority` (int) columns, an Alembic migration, and write-time bookkeeping that flips statuses when a conflicting claim lands. | Deferred. Storing resolution status creates a consistency burden (every write must re-resolve the group) and breaks the "no migration" discipline that 2.1/2.2 held. Keep it as a future extension (§3.5) if Glenn later wants materialized conflict state for analytics/inspectability. |
| **C. Silent auto-merge** | On overlap, merge the two `object`s or delete the lower-precedence claim automatically. | **Rejected.** The 2.2 doc explicitly says 2.3 "never silently merged." Auto-merge destroys provenance and can erase a correct claim. Humans resolve; the system surfaces + orders. |

**Decision: Option A** — surfacing + deterministic ordering, computed at read time, no migration. B documented as a future extension.

---

## 3. Design (Option A) — the five decisions

### 3.1 Q1 — Precedence definition (the core policy)

**RECOMMENDED precedence (highest → lowest), applied within a conflict group:**

1. **Source priority** (derived from `source_type`, not a stored column):
   - `mission` > `conversation` > `program_learning`
   - Rationale: a `mission` claim is a deliberate, user-orchestrated fact; a `conversation` claim is something said in chat; `program_learning` (the reviewer/background path) is the *lowest* authority and is already gated by `GOV-1.2` human approval (`personal_memory_service.py:365-366`). So when a human-stated fact (`conversation`) and a reviewer-inferred fact (`program_learning`) disagree, the reviewer inference does **not** silently override the human — it surfaces as a conflict for review. Encode as a module-level `SOURCE_PRIORITY: dict[str, int] = {"mission": 3, "conversation": 2, "program_learning": 1}`.
2. **Recency of write** (`created_at` DESC) — the *true* write time, not `last_used_at` (which 2.2 repurposed to mean "captured into a snapshot", not "most recently written"). Tiebreak when source priority is equal.
3. **Confidence** (`confidence` DESC) — the model's own belief score. Final tiebreak.
4. (Soft) `importance` DESC — available as a further tiebreak but not in the primary precedence (kept out to keep the policy explainable; documented as a knob).

**Within a group, the winner = highest source priority; on tie, newest `created_at`; on tie, highest `confidence`.** All *other* live claims in the group are "suppressed" (still live, still in the store, still shown in the Inspector conflict view) but ranked below the winner for `recall()` injection.

**ALTERNATIVE precedence:** `confidence > recency > source` (trust the model's score first). Rejected as the default because it lets a high-confidence `program_learning` reviewer claim override a lower-confidence human `conversation` claim — exactly the silent-override 2.2 warns against. Confidence stays a *tiebreak*, not the primary axis.

### 3.2 Q2 — What counts as a "conflict"

**RECOMMENDED:** Two live, non-deleted, non-expired claims conflict iff they share the same `subject` (exact, case-insensitive) **and** their `predicate` overlaps (exact match OR one is a sub-relation — start with exact `predicate` match; document semantic predicate grouping as a later refinement, §3.5), **and** their `object` values differ (by a shallow equality on the `object` dict). Same `subject`+`predicate`+`object` = a *duplicate*, not a *conflict* (handle duplicates separately — see §4.3).

Grouping is by `subject` (case-insensitive), then within a subject-group, pairs are evaluated on `predicate`+`object`. A subject with N differing claims forms one conflict group of size N.

**ALTERNATIVE:** conflict = same `subject` only (ignore `predicate`). Too coarse — ("Glenn","works_at","Acme") and ("Glenn","prefers","espresso") would false-positive. Rejected.

### 3.3 Q3 — Where resolution is computed (read-time, computed)

**RECOMMENDED:** A new thin `memory_conflict_service.py` exposing:

- `group_conflicts(claims: list[PersonalMemoryClaim]) -> list[ConflictGroup]`
  where `ConflictGroup = {subject, predicate, members: list[ClaimWithRank], winner: PersonalMemoryClaim, losers: list[PersonalMemoryClaim]}`.
  Pure function; ranks each member by §3.1; marks `winner`/`losers`. No DB.
- `rank_for_recall(claims) -> list[PersonalMemoryClaim]`
  Reorders `recall()`'s result: within each conflict group, the winner sorts first; losers sort after, still present (so a human reading full context can see them) but the *injected top-k* naturally surfaces the winner first. Optionally annotates each claim with `_conflict_rank` / `_superseded_by` for the serializer.
- `list_conflicts(db, user_id, workspace_id, scope=None) -> list[ConflictGroup]`
  The Inspector conflict source: fetches live claims, groups, returns only groups with `len(members) > 1`.

**Integration points (both read-time, no write change):**
- `recall()` (`:620`) calls `rank_for_recall(items)` *before* `.limit(top_k)` so `top_k` slices a resolved-ordered list (winner-first). **This is the 2.2 handoff requirement**: the frozen snapshot captures a *resolved* view.
- Inspector: add `?conflicts_only=true` to `GET /personal_memory/inspector` (or a new `GET /personal_memory/conflicts` v2 route) returning `list_conflicts(...)`. **No silent merge — the human sees both winner and losers.**
- `format_memory_block` (reused from 2.2) renders the ordered claims unchanged; the winner-first ordering is the only behavior change.

**ALTERNATIVE:** compute resolution at *write* time and store statuses (Option B). Rejected by default (§2).

### 3.4 Q4 — Surfacing in the Inspector (never silent)

**RECOMMENDED:** The conflict view returns, per group:
```json
{
  "subject": "Glenn",
  "predicate": "prefers",
  "winner": { "id": "...", "object": {"coffee": "espresso"}, "source_type": "conversation", "confidence": 0.85 },
  "losers": [
    { "id": "...", "object": {"coffee": "tea"}, "source_type": "program_learning", "confidence": 0.9,
      "superseded_because": "lower source priority (program_learning < conversation)" }
  ]
}
```
The `superseded_because` string makes the policy *explainable* — the human sees *why* the reviewer claim lost, not just that it did. This is the audit trail 2.3 owes the user.

**RECOMMENDED — no auto-action:** 2.3 writes nothing back. It does not flip `deleted_at`, does not set a `resolution_status`, does not email anyone. It *computes and shows*. If Glenn later wants a "resolve" action (mark loser `deleted_at` / `expired_at` / `superseded`), that is a separate write epic (Option B territory) with its own governance.

### 3.5 Q5 — 2.3 ↔ 2.2 ↔ 3.1 boundary

- **2.2 (shipped)** = the *snapshot mechanism*. It must capture *after* 2.3 resolution. Verified the seam supports this: `get_or_capture_snapshot` calls `recall_for_chat` (which calls `recall()`); once 2.3 reorders `recall()`'s output (§3.3), the snapshot automatically freezes the *resolved* view, and `bump_generation` (on every write, `personal_memory_service.py:344-346`) guarantees a re-capture picks up a new resolution. **No change to 2.2 code is required** — 2.3's `recall()` reorder is transparent to the snapshot.
- **2.3 (this epic)** = the *policy*: conflict detection + deterministic ordering + Inspector surfacing. Owns `memory_conflict_service.py`, the `recall()` reorder hook, the Inspector conflict route. **Does NOT** delete/merge claims, **does NOT** add semantic predicate grouping (that's 3.1's), **does NOT** touch the snapshot cache itself.
- **3.1 (recall-hardening)** = the *substrate*: semantic/embedding recall (replacing the substring match at `:656-662`), scope-isolation tests, circuit-breaking. 3.1 may later *upgrade* `group_conflicts`'s `predicate` match from exact to semantic — but 2.3 ships with exact match and leaves the predicate-matching function as a single swappable seam so 3.1 can extend it without touching the policy.

**Boundary rule for workers:** 2.3 must NOT add a migration (Option A), must NOT delete/merge claims, must NOT replace the substring recall (that's 3.1). It ONLY adds a read-time ranking + an Inspector read endpoint. The `predicate`-match function lives behind one named helper (`_predicates_conflict(a, b)`) so 3.1 can later make it semantic.

---

## 4. Risks / open questions (to resolve before build)

1. **`recall()` reorder changes injected context.** Today `recall()` returns by `confidence DESC`; 2.3 reorders by `source priority > recency > confidence`. The *set* of claims in `top_k` may shift (a high-confidence `program_learning` loser could move below a lower-confidence `conversation` winner). This is the *intended* policy change, but it is a behavior change the calibration loop should know about (parallel to 2.2's `last_used_at` note). *Owner: 2.3 build + note to calibration.*
2. **`created_at` vs `last_used_at` for recency.** 2.3 uses `created_at` (true write time) as the recency axis, deliberately NOT `last_used_at` (repurposed by 2.2 to mean "captured into snapshot"). Confirm `TimestampMixin` exposes `created_at` on the claim (it does — `Base, TimestampMixin` at `:79`). *Owner: 2.3 build.*
3. **Duplicate vs conflict.** Same `subject`+`predicate`+`object` is a *duplicate*, not a conflict. 2.3 should *not* flag duplicates as conflicts (noise). Recommend a separate, lighter `find_duplicates()` (exact `object` equality) surfaced distinctly, or folded into the conflict view as `is_duplicate=true`. *Owner: 2.3 build.* (Out of strict scope if time-constrained — document.)
4. **Performance of grouping.** `list_conflicts` fetches all live claims for `(user, workspace)` then groups in Python. For a personal-memory store (hundreds–low-thousands of claims per user) this is fine; if it ever grows, push grouping into SQL (a window function on `subject`+`predicate`). *Owner: 2.3 build (note scaling).*
5. **Cross-restart / snapshot interaction.** Because 2.2 freezes `recall()` output, a conflict resolved *after* a snapshot is captured won't appear until the next `bump_generation` re-capture. This is already governed by 2.2's write-invalidation — adding/removing a claim triggers `bump_generation` (`:344-346`), so the next message re-captures the resolved view. Verified consistent. *Owner: defer (covered by 2.2).*
6. **T33 / sensitivity scrub still applies.** The conflict grouping and Inspector conflict view must respect the existing sensitivity/scope drop (`memory_citation_service.py:214-230`) — never surface `sensitivity ∈ {sensitive, restricted}` or `scope = private` in the conflict view. *Owner: 2.3 build.*

---

## 5. Acceptance criteria (for the FOLLOW-UP build task — this doc does NOT build it)

- [ ] New `memory_conflict_service.py` with pure `group_conflicts(claims) -> list[ConflictGroup]` and `rank_for_recall(claims) -> list[PersonalMemoryClaim]`, plus `list_conflicts(db, user_id, workspace_id, scope=None)`.
- [ ] `ConflictGroup` shape: `{subject, predicate, members, winner, losers}`, each member ranked by `source priority > created_at > confidence` (§3.1). `SOURCE_PRIORITY` table defined as a module constant.
- [ ] `recall()` (`:620`) calls `rank_for_recall(items)` *before* `.limit(top_k)` so the winner of each conflict group sorts first. **No change to filtering, substring match, or `last_used_at` bump** — only the ordering of the returned list is augmented by group ranking.
- [ ] Inspector surfacing: `GET /personal_memory/inspector?conflicts_only=true` (or new `GET /personal_memory/conflicts`) returns only groups with `len(members) > 1`, each with `winner` + `losers` + `superseded_because` explanation. **No claim is deleted, merged, or status-flipped.**
- [ ] A test asserts: given a `conversation` claim (conf 0.85) and a `program_learning` claim (conf 0.9) on the same `(subject, predicate, differing object)`, `group_conflicts` picks the `conversation` claim as winner and explains "lower source priority" — i.e. confidence does **not** override source priority.
- [ ] A test asserts `recall()` returns the winner first within a conflict group (the 2.2 handoff requirement).
- [ ] A test asserts `list_conflicts` returns an empty list when there are no overlapping live claims (no false positives), and that exact-duplicate `object`s are NOT reported as conflicts (or flagged `is_duplicate`).
- [ ] Sensitivity/scope scrub (T33) applies to the conflict view — `sensitive`/`restricted`/`private` claims never appear.
- [ ] No live-path regression: existing `test_personal_memory_service.py`, `test_memory_citation_service.py`, `test_memory_feedback_loop.py`, and the 2.2 `test_epic22_frozen_snapshot.py` stay green. The `recall()` reorder is a pure reordering of an already-fetched list, so regression risk is low but must be asserted.
- [ ] 2.3 does NOT add a migration, does NOT delete/merge claims, does NOT replace substring recall (that's 3.1). `predicate`-match lives behind a single swappable `_predicates_conflict(a, b)` helper.
- [ ] Migration: **none** (Option A). Persistence option (Option B) explicitly deferred.

---

## 6. Verification done for this doc (evidence ledger)

- Claim columns + enums: `app/models/personal_memory_models.py:79` (class), `:142-178` (subject/predicate/object/source_type/sensitivity/confidence/importance/last_used_at/expires_at/deleted_at), `:51-68` (`ALL_CLAIM_TYPES`, `ALL_SCOPES`, `ALL_SOURCE_TYPES = (mission, conversation, program_learning)`, `ALL_SENSITIVITIES`). Confirmed **no `source_priority` / `resolution_status` column exists**.
- No conflict code: `grep -n "overlap\|duplicate\|conflict\|existing claim" app/services/personal_memory_service.py` → 0 hits. The only "conflict" mentions in the repo are unrelated (auth/mission domain, test names).
- `create()` write path: `personal_memory_service.py:308-347` — `db.add` + flush + refresh + audit `claim_created` + `bump_generation`; **no overlap/dedup check**. `create_from_proposal()` (`:349+`) bridges `source_type` and calls `create()` (`:365-366` notes `program_learning` forces GOV-1.2 approval).
- `recall()` ordering: `personal_memory_service.py:675-679` → `order_by(confidence.desc(), importance.desc(), last_used_at.desc().nulls_last()).limit(top_k)`. Substring match: `:656-662`. Filters: `:640-653`.
- 2.2 seam + write-invalidation: `app/services/memory_snapshot_service.py` (`get_or_capture_snapshot` → `recall_for_chat`); `personal_memory_service.py:344-346` `bump_generation(user_id, workspace_id)` on every write. 2.2 shipped live at `a4475c7a`.
- Inspector endpoint: `app/api/v2/personal_memory.py:163-190` (`GET /personal_memory/inspector`, flat paginated `list_for_user`, **no overlap grouping**).
- 2.2 framing of 2.3: `docs/EPIC-2.2-FROZEN-SNAPSHOT-DESIGN.md:161` (§3.6) — "2.3 operates on claims: `source priority > recency > confidence`, surfacing unresolved overlaps … never silently merged … 2.2 must capture the snapshot *after* any 2.3 resolution has been applied."
- T33 scrub: `memory_citation_service.py:214-230` (drops `sensitivity ∈ {sensitive, restricted}`, `scope ∈ {private}`). Reused unchanged.

---

*Next: Glenn reviews this design. If approved, the build is a read-time `memory_conflict_service` (grouping + ranking) + a `recall()` reorder hook + an Inspector conflict view — no migration, low blast radius, consistent with 2.1/2.2's "mostly wiring" discipline. 3.1 (semantic recall + scope-isolation) can later upgrade the `predicate`-match from exact to semantic without touching the policy.*
