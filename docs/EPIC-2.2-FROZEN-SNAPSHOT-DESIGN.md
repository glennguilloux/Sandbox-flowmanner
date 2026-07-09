# Epic 2.2 — Agent-Side Frozen Snapshot of Canonical Memory

> Status: **LIVE (merged `daa412fe` → deployed `a4475c7a`).** Option A shipped: no migration, no schema change. Verified live 2026-07-09 — seam present in container, `/api/health` ok, E22 suite 6/6 vs live Postgres, ruff clean, regression 10/10 in isolation. Full container suite: 3777 passed, 135 failed; the 135 failures are pre-existing harness/infra debt (auth, event-log, tool-registry, tool-routing) and **not** E22-caused (verified: no failing module imports the snapshot seam). Exit audit: `.hermes/sessions/exit-audit-2026-07-09-epic22-frozen-snapshot.md`.
> Author: Hermes (homelab agent) | Date: 2026-07-09 | Machine: homelab `/opt/flowmanner/backend`
> Sequence context: Epic 2.1 shipped + pushed (HEAD `d1720168`, live). 2.1 re-pointed reviewer writes to `personal_memory_claims` and removed dead `MemoryIntegration`. This doc is the immediate read/snapshot follow-through.
> Source of truth for this doc: the code as read on 2026-07-09 (file:line citations below, all re-verified — 2.1's `:441`/`:484`/`:476` citations still hold).
> Companion issues: **2.3** (conflict-resolution policy). 2.2's snapshot *wiring* is described by 2.1 as "Epic 3.1" — see §5 for the boundary clarification.

---

## 0. TL;DR — the decision

**Capture one `recall_for_chat` result per chat session (per `thread_id`), freeze it, and inject the frozen set into every message in that session instead of re-calling recall per message. Hold the frozen snapshot in in-memory per-session state — NO new table, NO migration, NO schema change. Invalidate the snapshot on any new reviewer write to `(user_id, workspace_id)` during the session, or after a bounded TTL.**

Rationale in one line: the read path (`chat_service` → `recall_for_chat` → `PersonalMemoryService.recall` → `personal_memory_claims`) is already correct and governed after 2.1, and `PersonalMemoryClaim` already carries `last_used_at` for staleness tracking. The only thing missing is *when* the expensive recall is run. Today it runs **per message** (`chat_service.py:441`, inside `stream_message_to_llm`), which (a) re-fetches + re-touches `last_used_at` on every turn, (b) lets each message see a subtly different view, and (c) wastes tokens/DB round-trips on a set that barely changes within a conversation. Freezing once per session is a pure win in stability, cost, and determinism — and it is mostly wiring, exactly as 2.1 predicted.

This is **not** a research spike. It is a scoping + placement decision: *what* the agent holds, *where* it lives, *when* it is captured, *when* it is invalidated, and *how stale* is acceptable. All building blocks already exist.

---

## 1. The problem (verified against code)

Today the live agent path calls recall **once per outgoing message**, and the recall is **query-driven** (substring match on the current message text).

### 1.1 The live call site

- `stream_message_to_llm(db, user_id, thread_id, content, ...)` is the per-message entry point (`chat_service.py:284`).
- Inside it, when `settings.CHAT_MEMORY_CITATIONS_ENABLED` is on, it calls `recall_for_chat(db, user_id=, workspace_id=, query=content)` **on every message** (`chat_service.py:437-446`). The `query` is the *current user message text* (`content`).
- The returned `memory_recall_claims` is injected into the LLM prompt via `_prepare_step_inject` (`:476`) or `_inject_memory_context` (`:484-485`), then the user message is saved and the DB session is **committed and closed** at `:491-493`.
- Effect: each message in a thread triggers its own `recall_for_chat` → `recall()` round-trip.

### 1.2 What `recall()` does (and why per-message hurts)

`PersonalMemoryService.recall()` (`personal_memory_service.py:601`):

- Filters by `(user_id, workspace_id, NOT deleted, NOT expired, confidence >= min_confidence, scope IN scopes)` and a **case-insensitive substring match on `(subject, predicate)`** against `query` (`:629-653`).
- Orders by `confidence DESC, importance DESC, last_used_at DESC NULLS LAST` and `.limit(top_k)` (`:663-672`).
- **Bumps `last_used_at = now()` on every returned row** before returning (`:675-681`).

Two consequences follow directly from the code:

1. **Query-driven variance.** Because the match is a substring of the *current message*, the recalled set differs message-to-message as the user's words change — even in the same conversation. Two adjacent turns can surface different claims for the same underlying user fact. This is non-deterministic context for the LLM.
2. **`last_used_at` churn.** Every recalled row is timestamped on every message, so `last_used_at` conflates "used in this message" with "used recently" and is re-touched constantly. This pollutes the recency signal that 2.3 (conflict resolution) and the calibration loop rely on.

### 1.3 The cost/stability waste

- `recall_for_chat` defaults to `top_k=5`, `min_confidence=0.7` (`memory_citation_service.py:57,62`). The frozen set is therefore tiny (≤5 claims). Re-fetching 5 rows per message across a multi-turn thread is pure overhead.
- The streaming caller wraps `recall_for_chat` in try/except and degrades to "no context" on failure (`chat_service.py:453-459`). A frozen snapshot makes that degradation deterministic: the session is either seeded with a snapshot or it isn't, instead of flickering per turn.

### 1.4 What 2.1 already settled (so 2.2 does not re-litigate it)

- The snapshot source is unambiguously `personal_memory_claims`, surfaced via `recall_for_chat`. 2.1 removed the only other candidate (`MemoryIntegration`/`memory_entries`) from the read path.
- "Claims already support `last_used_at`" is TRUE — it is a real nullable `DateTime` column (`personal_memory_models.py:166`).
- The defensive T33 filter in `recall_for_chat` (drops `sensitivity ∈ {sensitive, restricted}`, `scope ∈ {private}`) is the right final scrub and needs no change (`memory_citation_service.py:66-67, 214-230`).

So 2.2 is *mechanics + placement*, not new schema. That is the entire scope.

---

## 2. The candidate resolutions

| Option | What | Verdict |
|---|---|---|
| **A. Freeze once per session, in-memory** | Capture `recall_for_chat` once at session start (or first message), hold `list[PersonalMemoryClaim]` in per-session state, inject the same frozen set on every turn. | **RECOMMENDED.** Lowest blast radius (no table, no migration). Deterministic context. Removes per-message `last_used_at` churn (bump happens once, at capture). Matches 2.1's "mostly wiring" framing. |
| **B. Freeze once per session, persisted to a new `memory_snapshots` table** | Like A but the frozen set is written to a table keyed by `(session/thread, workspace)` with a TTL column, so it survives backend restarts. | Deferred. Cross-restart durability is real but not required for correctness; it adds schema + migration + a reader/writer. Document it explicitly as a later extension (§3.2). |
| **C. Re-recall per message (status quo)** | Keep calling `recall_for_chat` on every turn with the live message text. | Rejected as the default. It is the current behavior and the thing we are fixing — non-deterministic context + `last_used_at` churn + per-turn cost. C remains a valid *fallback* if snapshot invalidation proves too complex, but it is not the target. |

**Decision: Option A**, with B documented as a future extension if cross-restart durability is later required.

---

## 3. Design (Option A) — the five decisions

Each open question from the task is answered with a **RECOMMENDED default** and the **alternative**, so the build task is unambiguous.

### 3.1 Q1 — Definition of "frozen snapshot"

**RECOMMENDED:** A frozen snapshot is a captured `list[PersonalMemoryClaim]` produced by **exactly one** `recall_for_chat(...)` call per session, held in memory, and re-injected verbatim into every subsequent message in that session. The agent "holds" the same fixed claim objects for the whole conversation.

Formal shape (for the build task — not code this doc writes):

```
FrozenMemorySnapshot = {
    thread_id: int,
    user_id: int,
    workspace_id: str,
    captured_at: datetime,                  # UTC, set at capture
    query_used: str,                        # see §3.3 (empty/seed query)
    claims: list[PersonalMemoryClaim],      # the frozen set, ready to inject
    invalidated: bool,                      # set True on write/invalidation (§3.3)
}
```

**ALTERNATIVE:** Re-recall per message (Option C). Holds a fresh set each turn. Rejected as default (§2) but valid as a degradation path.

**Injection is unchanged.** The frozen `claims` list is fed to the exact same `_prepare_step_inject` / `_inject_memory_context` calls (`chat_service.py:476, 484-485`); only the *source* of the list changes (frozen set instead of a fresh per-message recall).

### 3.2 Q2 — Where the snapshot lives

**RECOMMENDED:** **In-memory per-session state**, scoped by `thread_id`. No new table, no migration, no schema change.

Placement options (all in-memory, pick one in build):

- A small module-level / service-level cache keyed by `thread_id`, e.g. `frozen_snapshots: dict[int, FrozenMemorySnapshot]` in a new thin `memory_snapshot_service.py` (or a slot on the chat service's existing cache infrastructure). The cache entry is created at capture and read at injection.
- Lifetime = the backend process lifetime of the session. When the process restarts, the next message in that thread simply re-captures (fallback to Option C behavior for that one message). This is acceptable because a snapshot is a *performance/cache* optimization, not a source of truth — `personal_memory_claims` remains authoritative.

**ALTERNATIVE (future extension, NOT this epic):** A `memory_snapshots` table `(id, thread_id FK, workspace_id, user_id, captured_at, expires_at, serialized_claims JSONB)` so the frozen set survives backend restarts and can be inspected/debugged. This adds: a model + Alembic migration + a writer at capture + a reader at injection + TTL cleanup. **Explicitly out of scope for 2.2** (would break the "no migration" stop gate). Document it here so the build task knows *not* to build it, and so a later epic can pick it up cleanly. The in-memory design must not paint itself into a corner: keep the snapshot behind a single `get_snapshot(thread_id)` / `store_snapshot(...)` seam so the backing store can be swapped to a table later without touching call sites.

### 3.3 Q3 — Capture trigger + invalidation

**RECOMMENDED — capture trigger:**
Capture at **first user message of the session** (lazy capture): the first call to the snapshot seam for a `thread_id` with no entry triggers one `recall_for_chat` and stores the result. Subsequent calls in the same thread return the frozen entry. This avoids capturing for threads that never need memory and naturally aligns with "session start" without a separate session-init hook.

**Seed query for capture.** Because recall is substring-driven on the message text, a frozen snapshot should NOT be keyed to one message's words. RECOMMENDED: capture with an **empty/seed query** (`query=""`) so the subtitle filter matches everything and the snapshot returns the top-`top_k` claims by `(confidence, importance, last_used_at)` for the user/workspace — i.e. the "standing personal context," not "what matched this one sentence." Verify `recall()` with `query=""`: the substring predicate is `lower("") = ""` which `contains("")` is TRUE for every string in Postgres (`str.contains("")` matches all), so an empty query returns the full scope/confidence-filtered ordered set, then `.limit(top_k)`. This is exactly the deterministic, query-agnostic seed we want. (The build task must confirm this empirically — see §6 test.)

**RECOMMENDED — invalidation (two triggers):**
1. **New reviewer write to `(user_id, workspace_id)`.** Whenever the 2.1 write path lands a new/expired/soft-replaced claim for the same user+workspace (the `create_from_proposal` / soft-replace surface), mark the cached snapshot for that `thread_id` (and any thread in that workspace for that user) `invalidated = True`, so the next message re-captures. This keeps a session from going stale the moment the user's own reviewed memory changes mid-conversation.
2. **Bounded TTL.** Each snapshot carries `captured_at`; if `now - captured_at > SNAPSHOT_TTL`, force re-capture on next access. RECOMMENDED: **reuse no new constant** — document TTL as a configured value defaulting to the session's natural length; if a constant is needed, derive it from an existing config (e.g. a chat session idle timeout) rather than inventing `SNAPSHOT_TTL`. (See §3.4 — we prefer "no new constants" per the task.)

**On invalidation:** simplest correct behavior is *drop the entry* from the in-memory cache (not a flag + branch); the next access re-captures via the lazy path. This avoids serving a half-stale frozen set.

**ALTERNATIVE:** Capture strictly at "session start" via an explicit init hook (more wiring, easy to miss for threads created out-of-band); or never invalidate (simpler but allows a session to run on memory that was edited mid-conversation). Lazy-capture + dual-invalidation is the recommended balance.

### 3.4 Q4 — Staleness / token-cost policy

**RECOMMENDED — token-cost ceiling:** The frozen set inherits the **existing** `CHAT_RECALL_TOP_K = 5` and `CHAT_RECALL_MIN_CONFIDENCE = 0.7` from `memory_citation_service.py:57,62`, used unchanged in the single capture call. No new constants. The token ceiling is therefore identical to today's per-message cost but paid **once per session instead of once per message** — a strict improvement. The `format_memory_block` serializer (`memory_citation_service.py:240`) is reused as-is to render the frozen `claims`.

**RECOMMENDED — staleness:** Bound by the §3.3 TTL (recommended: tie to existing session-length config) and by write-invalidation. Between invalidations, the frozen set is by definition "stale" — but that is *intended*: within a single conversation the user's standing facts do not change, so a stable view is a feature, not a bug. The staleness-vs-cost tradeoff:

| | Per-message (status quo) | Frozen per-session (2.2) |
|---|---|---|
| Recall DB round-trips / thread | N (one per message) | 1 (+ re-captures on invalidation) |
| `last_used_at` bumps / thread | N×rows | 1×rows (once, at capture) |
| Context stability across turns | Varies with message words | Fixed for the session |
| Worst-case staleness | ~0 | ≤ TTL or until next write |
| Token cost | N×≤5 claims serialized | 1×≤5 claims serialized |

The only cost 2.2 accepts is bounded staleness (≤ TTL / until next write), which is acceptable because the canonical store is still the live source on every re-capture and the frozen set is a cache, not truth.

**ALTERNATIVE:** Lower `top_k` further for ultra-cheap sessions, or add a `SNAPSHOT_TTL` constant. Both are optional tuning, not required — the build task should ship with the existing constants and the documented TTL linkage, not introduce new knobs.

### 3.5 Q5 — 2.2 ↔ 3.1 boundary

The 2.1 doc said 2.2's snapshot "wiring is Epic 3.1." That phrasing conflated two different layers. Clarification:

- **2.2 (this epic) = the SNAPSHOT mechanism on the now-canonical store.** Owns:
  - The capture/freeze/inject seam (`get_snapshot` / `store_snapshot` / lazy capture at first message).
  - The in-memory per-session holder.
  - The invalidation triggers (new write to `(user, workspace)`, TTL).
  - Reuse of `recall_for_chat` + `format_memory_block` unchanged.
  - No changes to `recall()`'s filtering, ordering, or `last_used_at` bump; no new model/table; no migration.

- **3.1 (recall-hardening epic) = the RECALL substrate the snapshot sits on top of.** Owns:
  - Scope-isolation guarantees (multi-tenant correctness of `(user_id, workspace_id)` filtering — already present at `recall()` `:632-633` but needs the 3.7 scope-isolation test).
  - Hardened failure modes (today the streaming caller swallows recall errors at `chat_service.py:453-459`; 3.1 may add circuit-breaking, partial-result semantics, or metrics).
  - Semantic/embedding recall (T20+) replacing the substring match at `personal_memory_service.py:645-653`.
  - Multi-tenant test coverage that proves the read path never leaks across workspaces.

**Boundary rule for workers:** 2.2 must NOT touch `recall()` internals, the T33 filter, or add semantic search — those are 3.1's. 3.1 must NOT add snapshot caching/invalidation — that is 2.2's. The build task for 2.2 calls `recall_for_chat` as a *black box* and only changes *when* it is called and *where the result is kept*. This separation is what prevents double-building.

### 3.6 Q6 (framing) — how 2.2 feeds 2.3

2.3 (conflict-resolution policy) operates on claims: `source priority > recency > confidence`, surfacing unresolved overlaps (multiple live claims with overlapping subject/predicate) in the Inspector, never silently merged. 2.2 is orthogonal: it freezes *whatever* the canonical store returns at capture time. The frozen set is just a cached view of the store's current resolution. **Implication for the build task:** 2.2 must capture the snapshot *after* any 2.3 resolution has been applied to the store (i.e. it freezes resolved claims), and invalidation (§3.3) guarantees a re-capture picks up a new resolution. 2.2 does not implement conflict policy — it only ensures the snapshot reflects the store's policy as of capture. Out of scope for this doc beyond this note.

---

## 4. Risks / open questions (to resolve before build)

1. **Empty-query recall semantics.** The seed-capture uses `query=""`. We reason `str.contains("")` matches all in Postgres, so the snapshot is the top-`top_k` standing claims — but this MUST be confirmed empirically (write a test asserting a non-empty, ordered result for `query=""`). If the ORM/DB dialect behaves otherwise, the capture query becomes a dedicated "standing context" call (a thin `recall_standing(...)` that omits the substring predicate) — still no schema change. *Owner: 2.2 build.*
2. **Write-invalidation fan-out.** Invalidating on every new claim write to `(user, workspace)` could invalidate many concurrent threads for one user. RECOMMENDED mitigation: invalidate by `thread_id` lazily — rather than tracking all threads, on each new write bump a `(user, workspace) -> generation counter`; each snapshot stores the generation it was captured at and re-captures if the counter moved. This scales to many threads without a thread registry. *Owner: 2.2 build.*
3. **`last_used_at` semantics shift.** Today `last_used_at` is bumped per message. Under 2.2 it bumps once at capture (per session). This is *better* for the recency signal (no constant churn) but is a behavior change the calibration loop / 2.3 should be aware of. Document it; do not revert to per-message bumping. *Owner: 2.2 build + note to 2.3.*
4. **Cross-restart durability.** In-memory snapshots vanish on backend restart; the next message re-captures transparently. Acceptable for a cache. If Glenn later wants persistence (inspectability, no cold-recall on restart), that is the deferred B option (§3.2) — a separate migration epic. *Owner: defer.*
5. **TTL constant.** Recommended to reuse an existing session-length config rather than add `SNAPSHOT_TTL`. If none exists, reuse `CHAT_RECALL_*` family naming and document it; do not invent unrelated knobs. *Owner: 2.2 build.*

---

## 5. Acceptance criteria (for the FOLLOW-UP build task — this doc does NOT build it)

- [ ] A new thin seam (`memory_snapshot_service` or equivalent) exposes `get_snapshot(thread_id)` / `store_snapshot(...)`; in-memory only, keyed by `thread_id`. No new DB table, no Alembic migration.
- [ ] `stream_message_to_llm` calls the snapshot seam instead of `recall_for_chat` per message. On cache miss it performs exactly ONE `recall_for_chat` (seed query `""`, defaults `top_k=5`/`min_confidence=0.7`) and stores the result. On cache hit it reuses the frozen `claims`.
- [ ] The frozen `claims` are injected via the existing `_prepare_step_inject` / `_inject_memory_context` path — **no change to prompt injection shape**.
- [ ] A test proves `recall_for_chat(query="")` returns the ordered standing claim set (top-`top_k` by `confidence, importance, last_used_at`) — i.e. the seed-capture assumption in §3.3/§4.1 holds.
- [ ] Invalidation is observable: a test writes a new claim to `(user, workspace)` via the canonical `PersonalMemoryService` surface and asserts the next snapshot access for that thread re-captures (generation-counter or drop-on-write). TTL invalidation also testable.
- [ ] `last_used_at` is bumped ONCE per capture (per session), not per message — asserted by a test counting bumps across N messages in one thread.
- [ ] No live-path regression in `recall_for_chat` / `recall` — existing `test_personal_memory_service.py`, `test_memory_citation_service.py`, `test_memory_feedback_loop.py` stay green. `recall()` internals, the T33 filter, and `format_memory_block` are untouched.
- [ ] 2.2 does NOT implement semantic search, scope-isolation tests, or circuit-breaking (those are 3.1) and does NOT implement conflict-resolution policy (that is 2.3).
- [ ] Migration: **none.** Table option explicitly deferred.

---

## 6. Verification done for this doc (evidence ledger)

- Live call site, per-message: `chat_service.py:284` (`stream_message_to_llm`), `:437-446` (`recall_for_chat(query=content)`), `:476` (`_prepare_step_inject`), `:484-485` (`_inject_memory_context`), `:491-493` (commit + session close per message).
- `recall()` mechanics: `personal_memory_service.py:601` (def), `:629-653` (filters + substring match on `(subject, predicate)`), `:663-672` (order by `confidence/importance/last_used_at` + `.limit(top_k)`), `:675-681` (`last_used_at` bump per call).
- `recall_for_chat()` wrapper + T33 filter: `memory_citation_service.py:174` (def), `:180-181` (defaults `CHAT_RECALL_TOP_K`/`CHAT_RECALL_MIN_CONFIDENCE`), `:205-213` (scopes `["personal","workspace","program"]`), `:214-230` (sensitivity/scope drop), `:240` (`format_memory_block`).
- Constants: `memory_citation_service.py:57` (`CHAT_RECALL_TOP_K = 5`), `:62` (`CHAT_RECALL_MIN_CONFIDENCE = 0.7`).
- `last_used_at` column: `personal_memory_models.py:166` (nullable `DateTime` on `PersonalMemoryClaim`, table `personal_memory_claims` at `:89`).
- 2.1 framing of 2.2: `docs/EPIC-2.1-CANONICAL-STORE-DESIGN.md:161` ("snapshot is a frozen recall_for_chat result … claims already support last_used_at … wiring is Epic 3.1"). 2.1 shipped at HEAD `d1720168` (per task body; live and healthy).
- No existing per-session memory cache found in `chat_service.py` (grep for `_sessions`/`_cache`/per-session dict → only prompt-version cache + scope pre-fetch; no recall snapshot holder). Confirms 2.2 introduces the holder.

---

*Next: Glenn reviews this design. If approved, the build is a thin snapshot seam + lazy capture + dual invalidation, reusing `recall_for_chat`/`format_memory_block` unchanged — no migration, low blast radius, matches 2.1's "mostly wiring" prediction. 2.3 (policy) and 3.1 (recall hardening) follow on the settled snapshot.*
