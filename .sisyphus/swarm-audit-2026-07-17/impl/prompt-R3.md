# R3 — Re-label the "autonomous" story (honest labeling, NO logic change)

**Origin:** Part of the 2026-07-17 Flowmanner swarm audit (REPORT.md §3 H6/H7 + Reality
Checker). Branch context: `agent/2026-07-17-impl/r3` (currently `blocked` on the kanban
board; code NOT yet merged to main). This card was deliberately HELD from the R1+R2+R5+R11+R12
bundle because it's doc-only and lower urgency — but the user explicitly likes it and wants
it landed.

**The problem (verified by orchestrator, not just the worker):**
- `backend/app/services/improvement/improvement_loop_v2.py:7-15` — the original ~900-line
  self-improvement orchestrator is **gutted**; a docstring/adjoining code states "107 missions
  ran with zero improvement data." It is not an autonomous learner.
- `backend/app/services/self_improvement.py:51-63` — returns **hardcoded template strings**,
  no LLM call, no learning. The "self-improvement" output is static.
- `backend/app/services/substrate/strategies/swarm.py:69-70` —
  `DEPRECATED = True  # 0% success with 27B model` (self-declared 0%-success swarm strategy).
Selling any of these as production "autonomous self-healing / self-improving" capability is
fool's gold and a credibility liability.

**Your task (labeling + docstrings ONLY — do NOT alter runtime behavior):**
1. In `improvement_loop_v2.py` and `self_improvement.py` docstrings, add an honest note such as:
   "(note: current implementation returns templated suggestions, not learned strategies — not an
   autonomous learner)."
2. At `substrate/strategies/swarm.py:69-70`, append to the deprecation comment:
   "(do not market as production-ready; 0% success on 27B per 2026-07-04 profiling)."
3. Grep the repo (docs, README, AGENTS.md, frontend copy if reachable) for user-facing claims of
   "autonomous self-improvement" / "self-healing swarm" and either soften them or add an
   "(experimental)" qualifier. List EVERY edit in your PR body.

**Constraints:**
- NO logic/behavior change. This is a labeling pass only. If you are tempted to "make it actually
  work," STOP and file a separate card — that is out of scope here.
- Work on your OWN exclusive branch + worktree (repo rule). Suggested branch:
  `agent/2026-07-17-impl/r3`.
- Do NOT push, deploy, or merge. Commit and leave for review.
- Persona to inject as the worker (this persona-delegation skill rule): use
  `engineering-minimal-change-engineer` (a FIX persona) — NEVER a reviewer persona on an impl card.
  Load it via the persona-delegation skill scripts:
  `python3 ~/.hermes/skills/autonomous-ai-agents/persona-delegation/scripts/persona.py load engineering-minimal-change-engineer`
- Doc-only change → per AGENTS.md verification scoping, skip `make test/lint/build`; the session
  ritual checklist covers verification for doc-only work.

**Verification (for the reviewer):** `git diff` should show only docstring/comment/markdown text
additions — zero `.py` executable-line changes. Confirm by grepping the diff for any change
outside string literals/comments.
