# R11 — De-register the deprecated MetaStrategy (safe slice; nexus retirement deferred)

**Context:** Swarm audit REPORT.md §3 M2/M3 + Architect ledger F3/F5.
`backend/app/services/substrate/strategies/meta.py:35` is marked
`DEPRECATED=True # 0% success with 27B model` yet still registered in
`backend/app/services/substrate/strategies/__init__.py:36`, so a `WorkflowType.META`
workflow routes to a self-declared 0%-success strategy (silent failure). Three
overlapping "coordination" concepts (nexus orchestrator, substrate, hollow
improvement loop) confuse new code.

**Your task (safe slice ONLY — do NOT delete nexus in this card):**
1. Add a dispatch guard so `WorkflowType.META` is rejected at submit time (or
   unregister `meta` from `strategies/__init__.py:36`) — pick the lower-risk option
   (unregister is cleanest). Confirm no live router depends on META dispatch.
2. In a follow-up note, recommend retiring `backend/app/services/nexus/orchestrator.py`
   in favor of substrate + a capability registry — but DO NOT delete/migrate nexus
   here.

**Constraints:** Surgical. No nexus deletion, no other refactors. Commit to this
branch. Do NOT push, deploy, or merge. Stop and block-for-review when done.
