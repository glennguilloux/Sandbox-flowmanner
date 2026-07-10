# Exit Audit — Opus 4.8 Design-QA: Item #9 + Item #3 (P3 batch)

**Date:** 2026-07-08
**Agent:** Buffy (mimo/mimo-v2.5-pro) on homelab (10.99.0.3)
**Plan:** `.sisyphus/plans/OPUS-4.8-DESIGN-QA-PLAN-2026-07-08.md`
**Continued from:** `.sisyphus/handoffs/exit-audit-2026-07-08-opus-4.8-design-qa-p2-provenance.md`

---

## WHAT CHANGED (one bullet per file, what + why)

**Item #9 — Replay assertion headroom (4 files, +1036/-45):**

- `backend/app/services/substrate/assertion_engine.py`: Added `BaselineVersion` frozen dataclass (model_id, pricing_table_version, template_version) + `BASELINE_VERSION` assertion type. `_check_tool_sequence` now supports constrained partial order: `required_edges` (ordering constraints), `forbidden_tools`, `equivalence_classes` (alias merging). `_check_cost` has new token-ceiling mode: recomputes dollar ceiling from current pricing table when `max_tokens` + `pricing_table` + `model_id` are provided. `_check_latency` has p95-based mode with rolling-aggregate breach detection — `p95_headroom` computes ceiling from p95 of baseline distribution, `consecutive_violations` (default 3) required before failure (single spikes are warnings). `evaluate()` accepts `current_baseline_version` and `latency_history` kwargs. **Item #9.**

- `backend/app/services/substrate/baseline_extractor.py`: Default headrooms tightened (cost: 1.5→1.15×, latency: 2.0→1.5×). New params: `model_id`, `pricing_table_version`, `template_version` for baseline metadata; `forbidden_tools`, `required_edges` for tool sequence. Emits `baseline_version` behavior when all 3 version fields provided. Emits `max_tokens` + `model_id` in cost ceiling for dynamic pricing recomputation. Uses `getattr` + `int()` for `total_tokens` to handle MagicMock in tests. **Item #9.**

- `backend/tests/test_assertion_engine.py`: Added `BaselineVersion` dataclass tests (3), partial order tests (5: required_edges pass/fail, forbidden_tools pass/fail, equivalence_classes), token-ceiling cost tests (3: within limit, exceeded, dynamic recomputation), rolling-latency tests (4: single breach warning, consecutive breach failure, no breach, legacy fallback), baseline version assertion tests (4: match, model drift, pricing drift, skip when empty). **Item #9.**

- `backend/tests/test_baseline_extractor.py`: Added `_make_state` `total_tokens` param. New tests: default headroom 1.15×, default latency headroom 1.5×, baseline version added/omitted, token ceiling with tokens, forbidden tools in tool_sequence, required_edges in tool_sequence. **Item #9.**

**Item #3 — Workflow replay idempotency + budget ledger (7 files, +621/-19):**

- `backend/app/models/substrate_models.py`: Added `idempotency_key` column to `SubstrateEvent` (String(256), nullable, indexed). Added `ABORT_REQUESTED = "abort_requested"` to `SubstrateEventType`. **Item #3.**

- `backend/app/services/substrate/event_log.py`: `_compute_idempotency_key()` computes deterministic key via `sha256(run_id:task_id:event_type:sorted_payload_json)`. `append()` now auto-computes idempotency keys and dedup-on-write — calls `_idempotency_key_exists()` before each insert, skips duplicates silently. Added `find_by_idempotency_key()` for LLM output replay lookup. Fixed pre-existing SIM105 lint (`try/except/pass` → `contextlib.suppress`). **Item #3.**

- `backend/app/services/substrate/executor.py`: `abort()` now accepts optional `db` param — when provided, writes `ABORT_REQUESTED` event to log before setting in-memory signal. `execute()` crash recovery path checks for `ABORT_REQUESTED` events and re-arms `asyncio.Event` before resume validation. **Item #3.**

- `backend/app/services/substrate/node_executor.py`: `_handle_llm()` now checks for a recorded `LLM_RESPONSE` event via `find_by_idempotency_key()` before calling the provider — returns cached response instantly (avoids double-billing on crash recovery). After successful LLM call, records `LLM_RESPONSE` event with explicit `idempotency_key` for future replay. `_handle_sub_workflow()` now: (a) reserves worst-case budget via `budget.reserve(child_max_cost)`, (b) creates isolated child `Budget`, (c) refunds unused reservation on completion and on non-budget exception. **Item #3.**

- `backend/app/models/capability_models.py`: Added `Budget.reserve(amount_usd)` — deducts from remaining, raises `BudgetExhausted` if insufficient. Added `Budget.refund(amount_usd)` — returns unused reservation, clamped to `spent_usd`. **Item #3.**

- `backend/alembic/versions/20260708_idempotency_key.py`: New migration adding `idempotency_key` column + regular index + partial unique index (`WHERE idempotency_key IS NOT NULL`). Chains off head `20260708_prov`. **Item #3.**

- `backend/tests/test_idempotency_replay.py`: 17 new tests: idempotency key determinism (5), EventLog dedup-on-write (1), Budget reserve (3), Budget refund (3), durable abort (3), LLM output replay (2). **Item #3.**

---

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- `backend/app/services/substrate/event_log.py`: `SIM105` lint fix (`try/except/pass` → `contextlib.suppress`) on pre-existing blueprint_id guard — cosmetic, no functional change.

---

## TESTS RUN + RESULT

**Local host (homelab) — all new + affected tests:**
```
$ python -m pytest tests/test_idempotency_replay.py tests/test_assertion_engine.py tests/test_baseline_extractor.py -v
78 passed in 4.14s
```

**Breakdown:**
- `test_assertion_engine.py`: 44 passed (27 new for Item #9)
- `test_baseline_extractor.py`: 17 passed (7 new for Item #9)
- `test_idempotency_replay.py`: 17 passed (all new for Item #3)

**Lint (ruff):** All changed source files pass clean (pre-existing SIM105 fixed).

**Mypy:** Passes on all changed files.

---

## STATUS

```
$ git status
On branch main
Your branch is ahead of 'origin/main' by 2 commits.
nothing to commit, working tree clean

$ git log --oneline origin/main..main
53d6a264 feat(substrate): workflow replay idempotency + durable abort + nested budget ledger (Item #3)
9bea79c3 feat(assertions): tighter headrooms, partial-order tool seq, rolling-latency, baseline versioning (Item #9)

$ docker compose exec backend alembic current
20260708_prov (head)   ← new migration 20260708_idem NOT yet applied (needs rebuild)

$ curl -sf http://127.0.0.1:8000/api/health
status: "ok" (langfuse unhealthy — pre-existing, disabled)
```

---

## COMMITS (2 on main, NOT pushed)

```
9bea79c3 feat(assertions): tighter headrooms, partial-order tool seq, rolling-latency, baseline versioning (Item #9)
53d6a264 feat(substrate): workflow replay idempotency + durable abort + nested budget ledger (Item #3)
```

---

## NEXT SESSION HANDOFF

This session completed **Item #9** (Replay assertion headroom) and **Item #3** (Workflow replay idempotency + budget ledger) from the Opus 4.8 Design-QA plan.

**Item #9** tightens assertion headrooms (cost 1.15×, latency 1.5×), adds token-ceiling cost with dynamic pricing recomputation, p95-based latency with rolling-aggregate breach detection, constrained partial order for tool sequences (required edges, forbidden tools, equivalence classes), and baseline versioning for auto-invalidation on drift.

**Item #3** adds deterministic idempotency keys to every event with dedup-on-write, LLM output replay (avoids double-billing on crash recovery), durable abort (abort event written to log, re-armed on replay), and nested budget reservation (reserve worst-case up front, refund unused).

**7 of 10 items now complete (P1+P2+P3 almost done):**
- ✅ Item #1 — SSE seq via Redis Streams (XADD/XRANGE)
- ✅ Item #2 — Typed error hierarchy (AppError → version-aware envelope)
- ✅ Item #3 — Workflow replay idempotency + budget ledger (this session)
- ✅ Item #4 — Gate deprecated strategies (DEPRECATED gate + STRATEGY_ALLOW_DEPRECATED)
- ✅ Item #6 — Provider-fallback provenance
- ✅ Item #8 — Frontend PUBLIC_PATHS segment-aware matcher
- ✅ Item #9 — Replay assertion headroom (this session)

**Remaining (P3+P4):**
- Item #5 — Plan-selection calibration (P3)
- Item #7 — v3 OIDC + webhooks (P4, needs design sign-off)
- Item #10 — Dual-auth consolidation (P4)

**Gotchas for next agent:**
1. **Backend needs rebuild + migration.** The new source files and migration (`20260708_idem`) are in source but NOT in the running container. Run `bash /opt/flowmanner/deploy-backend.sh --migrate` to pick them up and apply the migration.
2. **2 commits NOT pushed.** Run `git push origin main` after verifying the rebuild works.
3. **`EventLog.append()` now dedup-on-write.** Events with identical idempotency keys are silently skipped. This is intentional for crash recovery but means sequence numbers may have gaps. The replay engine handles gaps fine.
4. **`abort()` now has an optional `db` param.** Existing callers that don't pass `db` still work (in-memory only). For durable abort, pass `db=session`.
5. **`_handle_llm()` now records `LLM_RESPONSE` events.** These are informational replay records, not execution events. They carry explicit `idempotency_key` so re-calls are deduped.
6. **`Budget.reserve()` / `Budget.refund()` are new.** `_handle_sub_workflow` now creates an isolated child budget instead of sharing the parent's. The parent reserves worst-case up front and refunds unused after completion.

---

## FILES THIS AGENT DID NOT TOUCH BUT EXIST

**Untracked files:** None (working tree clean).

**Deleted files:** None.

---
