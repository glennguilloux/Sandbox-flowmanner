# Chunk 5 Re-Verification — DeepSeek Prompt

You are a verification worker. Your job is to independently re-verify **Chunk 5
(Multi-Agent Handoff Packets)** for the FlowManner backend. This is the same
re-verification protocol that was applied to Chunks 2, 3, and 4 (see
`.sisyphus/evidence/chunk-2-3-re-verify-2026-06-24.md` and
`chunk-4-re-verify-2026-06-24.md` for the format).

## Machine context

- You are on the **homelab** (172.16.1.1 / 10.99.0.3).
- Backend root: `/opt/flowmanner/backend/`
- Backend venv Python: `/opt/flowmanner/backend/.venv/bin/python`
- Monorepo root: `/opt/flowmanner/`
- `boulder.json` lives at `/opt/flowmanner/.sisyphus/boulder.json`

## Scope

**Read-only + test execution. No code modifications. No migrations. No deploys.**
If you find a real bug, document it in the report — do NOT fix it.

## What Chunk 5 claims (from boulder.json)

Status: `complete-with-bugfix-by-orchestrator`

Sub-agent commits: `62a008c`, `49dc90f`
Orchestrator bugfix commit: `9a772da`

### Stop gates to verify (12 total)

1. 23/23 unit tests pass in `test_handoff_packet.py` (21 original + 2 orchestrator regression tests)
2. 2/2 unit tests pass in `test_handoff_lease_integration.py` (transfer with/without new_worker_id)
3. 3 integration tests properly marked `@pytest.mark.integration` (skipped in dev env)
4. Backward-compat: old delegate/accept/complete/reject/fail methods still work
5. `HandoffPacket` schema has 7 required fields (goal, success_criteria, retrieved_context_ids, tool_candidates, budget_remaining_usd, hitl_state, depth_policy_state)
6. All 6 substrate event types present in `substrate_models.py`:
   - `HANDOFF_INITIATED = "handoff.initiated"`
   - `HANDOFF_ACCEPTED = "handoff.accepted"`
   - `HANDOFF_COMPLETED = "handoff.completed"`
   - `HANDOFF_FAILED = "handoff.failed"`
   - `HANDOFF_BUDGET_EXHAUSTED = "handoff.budget_exhausted"`
   - `HANDOFF_LEASE_LOST = "handoff.lease_lost"`
7. `delegate_with_packet` emits `HANDOFF_INITIATED` via `event_log.append`
8. `complete_with_packet` with `spent_usd > remaining_usd` raises `BudgetExceededError` AND emits `HANDOFF_BUDGET_EXHAUSTED` (NOT `HANDOFF_COMPLETED`)
9. Cross-workspace HITL item in packet raises `ValueError`
10. `HandoffLeaseIntegration` wraps `LeaseManager` primitives (claim/renew/release/transfer)
11. No breaking changes to `HandoffRecord` schema (all new columns nullable)
12. `git diff --check` clean

### 3 orchestrator-applied bugfixes to verify on disk

**Bugfix #1 — HANDOFF_LEASE_LOST event never emitted**

- **Bug:** Event type defined in enum but zero emission sites.
- **Fix:** In `handoff_protocol.py` `accept_with_packet()`, capture the return of `self.lease_integration.renew(handoff_id)`. If False, emit `HANDOFF_LEASE_LOST`.
- **Verify:** `grep -n "HANDOFF_LEASE_LOST\|lease_lost" app/services/swarm/handoff_protocol.py` — confirm emission site exists.
- **Test:** `test_accept_with_packet_emits_lease_lost_when_renew_fails` must exist and pass.

**Bugfix #2 — `transfer()` never used its params (no real cross-worker transfer)**

- **Bug:** `HandoffLeaseIntegration.transfer()` took `from_agent_id`/`to_agent_id` but never used them — refreshed lease under the SAME worker.
- **Fix:** Extracted `_claim_for_worker(handoff_id, agent_id, worker_id)` as internal primitive. `transfer()` gained optional `new_worker_id` param.
- **Verify:** Read `app/services/swarm/lease_integration.py` — confirm `_claim_for_worker` exists, `transfer()` has `new_worker_id: str | None = None` param.
- **Tests:** `test_transfer_without_new_worker_id_uses_instance_default` and `test_transfer_with_new_worker_id_uses_new_worker` must exist and pass.

**Bugfix #3 — Pre-chunk-5 records crash on budget fallback**

- **Bug:** `_packet_from_record()` called `HandoffBudget(remaining_usd=Decimal('0'), initial_usd=Decimal('0'))` for NULL budget — but `initial_usd` has `gt=0` constraint → ValidationError 500.
- **Fix:** When `handoff.budget_remaining_usd is None`, use `remaining=Decimal('0')`, `initial=Decimal('0.000001')`.
- **Verify:** Read the `_packet_from_record` function in `handoff_protocol.py` — confirm the `0.000001` fallback exists.
- **Test:** `test_packet_from_record_old_record_fallback` must exist and pass.

## File surface to inspect

| File | Path |
|---|---|
| Handoff packet models | `app/models/handoff_packet_models.py` |
| Handoff protocol | `app/services/swarm/handoff_protocol.py` |
| Lease integration | `app/services/swarm/lease_integration.py` |
| Substrate event types | `app/models/substrate_models.py` (lines ~127-132) |
| Migration | `alembic/versions/20260613_handoff_packets_001.py` |
| Unit tests | `tests/test_handoff_packet.py` |
| Lease integration tests | `tests/test_handoff_lease_integration.py` |

## Step-by-step protocol

### Step 1 — Orient

```bash
cd /opt/flowmanner/backend
git log --oneline -5
git status --porcelain
```

### Step 2 — Run the unit tests

```bash
cd /opt/flowmanner/backend
.venv/bin/python -m pytest tests/test_handoff_packet.py tests/test_handoff_lease_integration.py -v --timeout=60 2>&1 | tee /opt/flowmanner/.sisyphus/evidence/chunk-5-re-verify-tests.txt
```

Record the exact pass/fail counts.

### Step 3 — Verify each stop gate

For each of the 12 stop gates above, state **PASS** or **FAIL** with evidence:

- **Stop gates 5-6:** `grep` the source files.
- **Stop gates 7-10:** Read the actual function signatures and code in `handoff_protocol.py` and `lease_integration.py`. Confirm the logic matches the claim (don't trust comments — read the code).
- **Stop gate 11:** Read `alembic/versions/20260613_handoff_packets_001.py` — confirm all new columns are nullable.
- **Stop gate 12:** `git diff --check` must be clean.

### Step 4 — Verify the 3 orchestrator bugfixes

For each bugfix, use the specific verification commands above. Confirm:
1. The buggy code path is gone.
2. The fix is present in the source.
3. The regression test exists and passes.

### Step 5 — Route introspection (bonus check)

Confirm `HANDOFF_LEASE_LOST` emission is actually reachable — not just defined:

```bash
cd /opt/flowmanner/backend
grep -n "lease_lost\|HANDOFF_LEASE_LOST\|lease_integration.renew" app/services/swarm/handoff_protocol.py
```

### Step 6 — Risks and gaps

Document any coverage gaps, missing integration tests, or concerning patterns. Be honest.

## Output

Write your final report to:

```
/opt/flowmanner/.sisyphus/evidence/chunk-5-re-verify-2026-06-24.md
```

Follow the exact format of `chunk-4-re-verify-2026-06-24.md`:

```markdown
# Chunk 5 Re-Verification (2026-06-24)

**Date:** 2026-06-24
**Investigator:** DeepSeek verification worker
**Trigger:** Orchestrator directive — boulder.json documents Chunk 5 as
  `complete-with-bugfix-by-orchestrator` with 3 documented orchestrator bugfixes.
**Scope:** Read-only + test-execution. No code modified. No migrations applied. No deploys.
**Verdict:** Chunk 5 is **GREEN** / **RED** / **YELLOW**. [one sentence summary]

## Side-by-Side: boulder.json claim vs reality

| boulder.json stop_gate | Reality on disk | Status |
|---|---|---|
| ... | ... | ✅/❌ PASS/FAIL |

## Orchestrator-Applied Bugfixes — Verification

### Bugfix #1 — [name]
[finding]

### Bugfix #2 — [name]
[finding]

### Bugfix #3 — [name]
[finding]

## File Surface Inventory

| File | Lines | Touched by commit |
|---|---|---|
| ... | ... | ... |

## Risks / Unknowns Discovered

### Risk R-C5-N — [name]
[description]

## One-Sentence Final Assessment

> [verdict]
```

## Rules

- **Do NOT modify code.** Read-only verification only.
- **Do NOT trust self-reports or docstrings.** Read the actual code.
- **Do NOT claim PASS without running the command.** Every claim needs command output.
- **Use the backend venv Python:** `/opt/flowmanner/backend/.venv/bin/python`
- If a test fails, report it honestly as **FAIL** — do not investigate or fix.
- If the working tree is dirty, note it but continue.
- Keep the report concise and evidence-backed. No speculation.
