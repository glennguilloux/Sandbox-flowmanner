# R12 — Purge phantom-module references from AGENTS.md / BRIEF

**Context:** Swarm audit REPORT.md §5 (orchestrator VERIFIED). `app/api/v1/AGENTS.md`
(`:94,183`) references `swarm.py` router + `app.services.swarm.orchestrator` that do
NOT exist (real surface is `swarm_protocol.py`). `nexus/meta_loop_orchestrator.py`
is also phantom. Template-count drift exists (`templates/README.md` says 59; brief
repeated a stale 35). Note: the Reality Checker erroneously claimed `seed_templates.py`
doesn't exist — it DOES (267 KB at repo root); correct that in any doc that repeated
the error.

**Your task:**
1. In `backend/app/api/v1/AGENTS.md` (`:94,183`) + `backend/AGENTS.md` + any BRIEF in
   this audit dir, remove/repair references to `swarm.py` router,
   `swarm/orchestrator.py`, `meta_loop_orchestrator.py` (point at real files:
   `swarm_protocol.py`, `substrate/strategies/swarm.py`).
2. Fix the built-in mission-template count (verify against `templates/README.md` and
   `seed_templates.py`) — use the accurate number.
3. Correct any "seed_templates.py does not exist" claim to "seed_templates.py (267 KB)".

**Constraints:** Doc-only. No code changes. Commit to this branch. Do NOT push, deploy,
or merge. Stop and block-for-review when done.
