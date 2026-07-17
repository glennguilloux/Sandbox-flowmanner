# R3 — Re-label the "autonomous" story (honest labeling, NO logic change)

**Context:** Swarm audit REPORT.md §3 H6/H7 + Reality Checker. The "autonomous
self-improvement" loop is gutted (`backend/app/services/improvement/improvement_loop_v2.py:7-15`:
"original 900-line orchestrator has been gutted… 107 missions ran with zero
improvement data") and `self_improvement.py:51-63` returns hardcoded template
strings (no LLM/learning). The swarm strategy is self-declared 0%-success
(`backend/app/services/substrate/strategies/swarm.py:69-70` `DEPRECATED=True # 0%
success with 27B model`). Selling these as production "autonomous" capabilities
is fool's gold.

**Your task (labeling + docstrings ONLY — do not alter runtime behavior):**
1. In `improvement_loop_v2.py` and `self_improvement.py` docstrings, add an honest
   note: e.g. "(note: current implementation returns templated suggestions, not
   learned strategies — not an autonomous learner)".
2. In `substrate/strategies/swarm.py` near `:69-70`, append to the deprecation
   comment: "(do not market as production-ready; 0% success on 27B per 2026-07-04 profiling)".
3. Grep the repo (docs, README, AGENTS.md, frontend copy if reachable) for
   user-facing claims of "autonomous self-improvement" / "self-healing swarm" and
   either soften them or add an "(experimental)" qualifier. List every edit in the PR.

**Constraints:** NO logic/behavior change. This is a labeling pass. Commit to this
branch. Do NOT push, deploy, or merge. Stop and await review when done.
