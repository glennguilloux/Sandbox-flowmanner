# Flowmanner Memory System — Verification Checklist (reconciled, 5 items)

> Owner of verification: the agent (Hermes) — GitHub repo is outside the Opus reviewer's GitLab-only reach.
> Repo: `https://github.com/glennguilloux/Sandbox-flowmanner` (branch `main`, last verified commit `58e434a`, 2026-07-08).
> Method: `grep` + targeted file reads. Each item has a one-shot command to re-verify.
> Reconciliation: down-scoped from 8 anchors to 5 load-bearing items per Opus's second-trace review
> (which used the on-disk `HERMES-MEMORY-PATTERNS-FOR-FLOWMANNER.md` as a second, same-day read-based trace).
> Honest caveat: both traces are read-based and dated the same day — consistent, not independent.

---

## The 5 load-bearing checks

### C1 — `pending_writes` is a write-only sink
```bash
grep -rn "pending_writes" backend/app/api
```
- **Result:** NONE. No endpoint reads, lists, approves, or rejects `pending_writes`.
- **Verdict:** ✅ CONFIRMED. Writer: `services/memory/background_review_service.py` `stage_pending_write` (L235). No drain.
- **Impact:** GOV-1 (drain via HITL) is the foundation issue.

### C2 — HITL gates destructive tool paths (determines GOV-1/4.1 cost)
```bash
grep -rn "create_interrupt\|HumanInterruptType.APPROVAL" backend/app/services/substrate/node_executor.py
grep -rn "InboxItem" backend/app/api/v1/hitl.py
```
- **Result:** `node_executor.py:1413-1463` calls `HITLService.create_interrupt(HumanInterruptType.APPROVAL)` for destructive interrupts; `hitl.py` serves those `InboxItem`s (`approve_item`/`reject_item` L244/L280).
- **Verdict:** ✅ CONFIRMED + strengthened. Destructive tools already route into the *same* inbox GOV-1 proposes to reuse. (LangGraph `approval_workflow.py` is the other executor path — both gate via HITL conceptually, but the substrate `node_executor` path is the confirmed live one for missions.)
- **Impact:** GOV-1 is a routing change, not a UI build. 4.1 ("wire constraint into existing gate") is cheaper than building a new gate.

### C3 — what `memory_correction_service` does + does it feed back?
```bash
sed -n '1,8p;95,147p' backend/app/services/memory_correction_service.py
grep -rn "_safe_audit\|MemoryCorrectionService" backend/app/services/personal_memory_service.py
```
- **Result:** `MemoryCorrectionService` persists `memory_correction_events` (audit table) with `record_event` + `list_for_user`/`list_for_claim`/`get_provenance`. Docstring L5-6: `PersonalMemoryService._safe_audit` hook **no-ops today**; integrating this service is deferred (T29 = foundation only). Inspector surfaces corrections per claim (`personal_memory.py v2` `/claims/{id}/provenance`).
- **Verdict:** ⚠️ PARTIAL — confirms Opus's nuance. Override-what-was-kept = real at data/API layer (PATCH/DELETE claims + correction audit). Feedback loop = **NOT closed** (hook unwired).
- **Impact:** GOV-6 is *wiring*, not *building*. Rescopes #5: gap = (a) no visibility of dropped candidates, (b) corrections don't feed back into decay/reviewer.

### C4 — expiry sweeper: silent delete or audited decision?
```bash
grep -n "expires_at\|PendingWriteStatus.EXPIRED" backend/app/models/memory_models.py
grep -rn "PendingWrite\|pending_write" backend/app/tasks --include=*.py | grep -iE "expire|sweep|stale|delete|reject" || echo "NO pending_writes sweeper in tasks/"
sed -n '177,194p' backend/app/services/hitl_service.py
```
- **Result:** `PendingWrite` has `expires_at` (L282) + `PendingWriteStatus.EXPIRED` enum (L186), but **NO sweeper transitions `PendingWrite`→`EXPIRED`**. Only `hitl_service.expire_and_act` (L194) + `tasks/hitl_expiry.py` sweep *InboxItem* (and log the auto-action).
- **Verdict:** ⚠️ PARTIAL REFUTE of "expiry sweeper already exists for pending_writes." The *schema* is stubbed; no transition code. The HITL inbox sweeper *does* audit (logs auto-reject), but `pending_writes` is not covered.
- **Impact:** GOV-1.4 is *more* load-bearing than assumed — routing `pending_writes` through HITL is the only path to audited expiry. 1.4 = "verify HITL sweeper covers routed pending_writes," not "build a sweeper."

### C5 — does the Inspector expose dropped extraction candidates?
```bash
grep -n "inspector\|dropped\|below_threshold\|candidate" backend/app/api/v2/personal_memory.py
grep -n "dropped\|validation layer" backend/app/services/memory/background_review_prompt.py
```
- **Result:** `personal_memory.py v2` `/inspector` lists kept + deleted claims + provenance. Reviewer drops happen at `background_review_prompt.py:35` validation layer with no persistence.
- **Verdict:** ✅ CONFIRMED GAP. Dropped-candidate visibility = absent.
- **Impact:** GOV-5 (calibration) must add dropped-candidate logging; GOV-6 must expose it in the Inspector.

---

## Standing decisions (record so instantiation doesn't drift)

1. **Reject the doc's "auto-approve writes older than 7 days."** Auto-approve-on-staleness is the inverse of the provenance gate — it converts operator inattention into an attack window (submit poison, wait a week). Fatigue mitigation = batch-review UX + digest notifications, **never** default-approve. **Expiry = auto-reject with audit trail** (per GOV-1.4).
2. **Don't-capture list (doc pattern #16)** belongs in the backlog as 4.2 — cheap, prevents "I failed once so never again" hardening. Pairs with 4.1.
3. **`last_used_at` is two issues, not one:** (3.1) instrument on claim recall (column exists, never written); (3.2) migrate + instrument on `MemoryEntry` (column absent — Section D migration never applied).

## Confidence

- **High (single-command grep):** C1, C2, C4, C5.
- **Medium (read + docstring):** C3 — the unwired `_safe_audit` is stated in the service docstring; I did not execute to confirm the no-op at runtime, but the service self-documents the deferral.

## Original 8 anchors (for reference)
The earlier 8-anchor pass is superseded by the 5 items above; the 3 dropped (schema drift, reviewer-snapshot-side, no-forbidden-type) remain corroborated by the doc's as-built block and need no re-check.
