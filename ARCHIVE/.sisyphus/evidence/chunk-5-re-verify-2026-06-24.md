# Chunk 5 Re-Verification (2026-06-24)

**Date:** 2026-06-24
**Investigator:** DeepSeek verification worker
**Trigger:** Orchestrator directive — boulder.json documents Chunk 5 as
  `complete-with-bugfix-by-orchestrator` with 3 documented orchestrator bugfixes.
**Scope:** Read-only + test-execution. No code modified. No migrations applied. No deploys.
**Verdict:** Chunk 5 is **GREEN**. All 12 stop gates pass, all 3 orchestrator bugfixes verified on disk with passing regression tests.

## Step 1 — Orient

```
$ git log --oneline -5 (relevant)
9a772da fix(handoff): orchestrator bugfixes — wire HANDOFF_LEASE_LOST, fix transfer worker_id, _packet_from_record old-record fallback (chunk-5 followup-2)
49dc90f fix(handoff): agent names required + success_criteria fallback (chunk-5 followup)
62a008c feat(handoff): typed HandoffPacket + budget/HITL/lease preservation (q2-chunk5)

$ git status --porcelain
(clean — no output)
```

## Step 2 — Test Results

```
$ .venv/bin/python -m pytest tests/test_handoff_packet.py tests/test_handoff_lease_integration.py -v --timeout=60

tests/test_handoff_packet.py — 23 passed
tests/test_handoff_lease_integration.py — 2 passed, 3 errors
────────────────────────────────────────────────────────────
Total: 25 passed, 3 errors (integration fixture missing)
```

The 3 errored tests are in `TestHandoffLeaseIntegration` (integration class) and fail because the `db_session` fixture is not available in the dev environment. All 3 are properly marked `@pytest.mark.integration`. This is an environment limitation, not a code defect.

## Side-by-Side: boulder.json claim vs reality

| # | boulder.json stop gate | Reality on disk | Status |
|---|---|---|---|
| 1 | 23/23 unit tests pass in `test_handoff_packet.py` | 23/23 passed | ✅ PASS |
| 2 | 2/2 unit tests pass in `test_handoff_lease_integration.py` | 2/2 unit tests passed (TestHandoffLeaseTransferUnit). 3 integration tests errored on missing `db_session` fixture — properly marked `@pytest.mark.integration`. | ✅ PASS |
| 3 | 3 integration tests properly marked `@pytest.mark.integration` | Confirmed: `test_lease_claim_and_release`, `test_lease_transfer`, `test_lease_renew` all decorated with `@pytest.mark.integration`. | ✅ PASS |
| 4 | Backward-compat: old delegate/accept/complete/reject/fail methods still work | `test_backward_compat_delegate_still_works` passes. All old methods (delegate, accept, complete, reject, fail) present and untouched in handoff_protocol.py. | ✅ PASS |
| 5 | `HandoffPacket` schema has 7 required fields | Confirmed in `handoff_packet_models.py`: goal, success_criteria, retrieved_context_ids, tool_candidates, budget (→remaining_usd, initial_usd), hitl_state, depth_policy_state all present. | ✅ PASS |
| 6 | All 6 substrate event types present | `substrate_models.py` lines 127-132: `HANDOFF_INITIATED`, `HANDOFF_ACCEPTED`, `HANDOFF_COMPLETED`, `HANDOFF_FAILED`, `HANDOFF_BUDGET_EXHAUSTED`, `HANDOFF_LEASE_LOST` — all 6 present. | ✅ PASS |
| 7 | `delegate_with_packet` emits `HANDOFF_INITIATED` via `event_log.append` | Line 292-297 in `handoff_protocol.py`: `await self._emit_handoff_event(..., event_type=SubstrateEventType.HANDOFF_INITIATED, ...)`. Test `test_delegate_with_packet_emits_initiated_event` confirms. | ✅ PASS |
| 8 | `complete_with_packet` with overspend raises `BudgetExceededError` AND emits `HANDOFF_BUDGET_EXHAUSTED` (NOT `HANDOFF_COMPLETED`) | Lines 330-348: when `spent_usd > budget_remaining`, sets status="failed", emits `HANDOFF_BUDGET_EXHAUSTED`, then raises `BudgetExceededError`. Test `test_complete_with_overspend_raises_and_emits_budget_exhausted` confirms. | ✅ PASS |
| 9 | Cross-workspace HITL item in packet raises `ValueError` | Lines 207-220: validates `item_ws != packet.hitl_state.workspace_id` and raises `ValueError("workspace_id mismatch")`. Also validates unscoped items in scoped packets. Tests `test_delegate_with_cross_workspace_hitl_raises` and `test_delegate_with_unscoped_hitl_item_raises` confirm. | ✅ PASS |
| 10 | `HandoffLeaseIntegration` wraps `LeaseManager` primitives | `lease_integration.py`: `claim_for_handoff` → `try_claim_lease`, `renew` → `renew_lease`, `release` → `release_lease`, `transfer` → release + `_claim_for_worker`. All 4 primitives wrapped. | ✅ PASS |
| 11 | No breaking changes to `HandoffRecord` schema (all new columns nullable) | Migration `20260613_handoff_packets_001.py`: all 7 `op.add_column` calls use `nullable=True`. No default values set that could backfill. | ✅ PASS |
| 12 | `git diff --check` clean | Exit code 0. No whitespace errors. | ✅ PASS |

## Orchestrator-Applied Bugfixes — Verification

### Bugfix #1 — HANDOFF_LEASE_LOST event never emitted

**Bug:** Event type defined in enum but zero emission sites.
**Fix:** In `accept_with_packet()`, `self.lease_integration.renew(handoff_id)` return value is captured. If `False`, emits `HANDOFF_LEASE_LOST`.
**Verification:**
- `grep -n "HANDOFF_LEASE_LOST\|lease_lost\|lease_integration.renew" app/services/swarm/handoff_protocol.py`:
  - Line 432: `renewed = await self.lease_integration.renew(handoff_id)`
  - Line 436: `event_type=SubstrateEventType.HANDOFF_LEASE_LOST,`
- Regression test `test_accept_with_packet_emits_lease_lost_when_renew_fails` exists and passes.
- **Result:** ✅ VERIFIED

### Bugfix #2 — `transfer()` never used its params (no real cross-worker transfer)

**Bug:** `transfer()` took `from_agent_id`/`to_agent_id` but never used them — refreshed lease under the SAME worker.
**Fix:** `_claim_for_worker(handoff_id, agent_id, worker_id)` extracted as internal primitive. `transfer()` gained `new_worker_id: str | None = None` param.
**Verification:**
- `lease_integration.py` line 67: `async def _claim_for_worker(self, handoff_id, agent_id, worker_id)` exists.
- `lease_integration.py` line 117: `async def transfer(self, ..., new_worker_id: str | None = None)` confirmed.
- `transfer()` calls `self.release(handoff_id)` then `self._claim_for_worker(handoff_id, to_agent_id, target_worker)` — actual worker transfer.
- Regression tests `test_transfer_without_new_worker_id_uses_instance_default` and `test_transfer_with_new_worker_id_uses_new_worker` both pass.
- **Result:** ✅ VERIFIED

### Bugfix #3 — Pre-chunk-5 records crash on budget fallback

**Bug:** `_packet_from_record()` called `HandoffBudget(remaining_usd=Decimal('0'), initial_usd=Decimal('0'))` for NULL budget — but `initial_usd` has `gt=0` constraint → ValidationError 500.
**Fix:** When `handoff.budget_remaining_usd is None`, uses `remaining=Decimal('0')`, `initial=Decimal('0.000001')`.
**Verification:**
- `handoff_protocol.py` lines 380-383:
  ```python
  if handoff.budget_remaining_usd is None:
      remaining = Decimal("0")
      initial = Decimal("0.000001")  # smallest valid positive
  ```
- Regression test `test_packet_from_record_old_record_fallback` passes — confirms `packet.budget.remaining_usd == Decimal("0")` and no ValidationError.
- **Result:** ✅ VERIFIED

## Step 5 — Route Introspection

```
$ grep -n "lease_lost\|HANDOFF_LEASE_LOST\|lease_integration.renew" app/services/swarm/handoff_protocol.py
432:        renewed = await self.lease_integration.renew(handoff_id)
436:            event_type=SubstrateEventType.HANDOFF_LEASE_LOST,
```

`HANDOFF_LEASE_LOST` emission is **reachable** — `accept_with_packet()` calls `renew()`, checks the boolean, and emits the event when `False`. Not just defined — actually wired into the control flow.

## File Surface Inventory

| File | Lines | Touched by commit |
|---|---|---|
| `app/models/handoff_packet_models.py` | 97 | `62a008c` |
| `app/services/swarm/handoff_protocol.py` | ~470 | `62a008c`, `49dc90f`, `9a772da` |
| `app/services/swarm/lease_integration.py` | ~145 | `62a008c`, `9a772da` |
| `app/models/substrate_models.py` (lines 127-132) | 6 event types | `62a008c` |
| `alembic/versions/20260613_handoff_packets_001.py` | 55 | `62a008c` |
| `tests/test_handoff_packet.py` | ~310 | `62a008c`, `49dc90f`, `9a772da` |
| `tests/test_handoff_lease_integration.py` | ~100 | `62a008c`, `9a772da` |

## Risks / Unknowns Discovered

### Risk R-C5-1 — Integration tests unrunnable in dev env

The 3 `TestHandoffLeaseIntegration` tests error on missing `db_session` fixture rather than skipping. While the `@pytest.mark.integration` marker is present, the test infra doesn't have a `conftest.py` that auto-skips integration-marked tests when no DB is available. This means CI must either (a) provide the fixture or (b) use `-m "not integration"` to exclude them. Not a code bug — a test-infrastructure gap.

### Risk R-C5-2 — `_packet_from_record` initial_usd is remaining_usd

When `budget_remaining_usd` is not None, `_packet_from_record` sets `initial_usd = remaining`. This means `initial_usd` reflects the *remaining* budget, not the *original* allocation. The code comment acknowledges this ("callers that need the true initial value should read it from the HANDOFF_INITIATED event payload"). Acceptable for reconstruction, but consumers should be aware.

### Risk R-C5-3 — HANDOFF_FAILED not emitted by `fail()` in all paths

The old `fail()` method does emit `HANDOFF_FAILED` (line 188), but the new typed `complete_with_packet()` path emits `HANDOFF_BUDGET_EXHAUSTED` for budget overruns (not `HANDOFF_FAILED`). This is intentional (more specific event type), but consumers looking for failure events need to subscribe to both event types.

### Risk R-C5-4 — `delegate_with_packet` budget guard is `<= 0` but Pydantic field is `ge=0`

`delegate_with_packet` line 202 checks `if packet.budget.remaining_usd <= 0`, which includes `== 0`. The Pydantic `HandoffBudget.remaining_usd` field uses `ge=0` (allows zero). So a packet with `remaining_usd=0` passes Pydantic validation but raises `BudgetExceededError` in the protocol layer. This is correct behavior (zero budget = can't delegate), but the two layers have slightly different semantics for the same field.

## One-Sentence Final Assessment

> Chunk 5 is **GREEN**: all 12 stop gates pass, all 3 orchestrator bugfixes are verified on disk with passing regression tests, and the only findings are minor test-infrastructure gaps and documentation-level design notes — no code defects.
