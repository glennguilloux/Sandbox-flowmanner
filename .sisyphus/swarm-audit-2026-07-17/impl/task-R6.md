# R6 — v1→substrate cutover: DESIGN + safe slice ONLY (block-for-review, NO destructive delete)

**Context:** Swarm audit REPORT.md §3 H5 + Architect ledger. Two execution engines
serve traffic: the GA `substrate` `UnifiedExecutor` AND the legacy
`mission_executor.py` (1,387 LOC) still wired by v1 routes. `FLOWMANNER_UNIFIED_EXECUTOR=all`
was never flipped (`backend/app/services/substrate/AGENTS.md` "Current state").
This is L-effort and RISKY — do NOT delete or flip anything in this card.

**Your task (produce a plan + the safe, reviewable first slice):**
1. Write an ADR (`docs/` or this worktree) covering: parity-test gate, the
   `FLOWMANNER_UNIFIED_EXECUTOR=all` flip sequence, deletion of `mission_executor.py`,
   and migration of the inline v1 routers (`backend/app/api/v1/graph.py:323`,
   `substrate.py:235` "no substrate run" branches) to substrate strategies.
2. Implement ONLY the safe slice: add parity/regression tests under
   `backend/app/tests/test_substrate_*` + `test_unified_executor_*` that would catch
   behavior change, and add a guard that warns if `FLOWMANNER_UNIFIED_EXECUTOR != all`
   in production.
3. **DO NOT** flip the flag, delete `mission_executor.py`, or modify legacy router
   execution paths in this card.

**Constraints:** Design + tests + guard only. No destructive change. Commit to this
branch. Do NOT push, deploy, or merge. When the plan + safe slice are done, STOP and
block-for-review (the destructive cutover needs explicit human approval).
