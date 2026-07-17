# R4 — "Swarm in 30 seconds" demo + SDK lead (docs / DX)

**Origin:** Part of the 2026-07-17 Flowmanner swarm audit (REPORT.md §4 R4 + Developer Advocate
ledger). Branch context: `agent/2026-07-17-impl/r4` (currently `blocked` on the kanban board;
code NOT yet merged to main). HELD from the R1+R2+R5+R11+R12 bundle because it's DX/marketing
surface, not a backend fix.

**The opportunity (verified by orchestrator):**
- `POST /api/swarm/protocol/debate` is REAL, callable, and LLM-judge scored:
  `backend/app/api/v1/swarm_protocol.py:104` handles it; it takes a topic + two agent ids
  (`agent_a_id` / `agent_b_id`) and returns a structured verdict. This is the single most
  differentiated call in the API but it is absent from the first-10-minute experience and from the
  SDK's headline example.
- The list of valid agents comes from `GET /api/agent-personalities` (now 215 after R1; see
  `backend/app/api/v1/agent_personalities.py`).
- **Naming trap (VERIFIED):** the `ExecuteRequest` schema (see `backend/openapi.json:41474`,
  pattern `^(parallel|sequential|debate)$`) accepts `strategy:"debate"` but the user-facing copy
  elsewhere calls the capability "swarm." A user sending `strategy:"swarm"` gets rejected. Pick one
  of: (a) accept `swarm` as an alias for `debate` in the schema/service, OR (b) document the enum
  prominently. Prefer (a) if it's a 1-line schema tweak — but FIRST confirm no live endpoint
  already accepts `strategy:"swarm"` (it should not).

**Your task:**
1. Add a Quick Start doc page (markdown under `backend/docs/` or `docs/`) whose step 1 is a
   copy-paste `curl` to `/api/swarm/protocol/debate` — topic + two `agent_*_id` pulled from
   `GET /api/agent-personalities`. Include a recorded-replay landing-demo spec (a curl that
   produces a shareable result).
2. Update `sdk-python/flowmanner-api-client/README.md` to LEAD with a `debate()` example instead
   of `create_mission`. If trivial, add a `debate()` convenience method to the client
   (`sdk-python/flowmanner_api_client/`); otherwise just reorder the docs.
3. Fix the `strategy` naming trap per the choice above (alias preferred).

**Constraints:**
- Docs + SDK + one small schema tweak only. Do NOT touch the debate protocol logic itself.
- Work on your OWN exclusive branch + worktree. Suggested branch: `agent/2026-07-17-impl/r4`.
- Do NOT push, deploy, or merge. Commit and leave for review.
- Persona to inject: use `specialized-developer-advocate` (a FIX persona) — NEVER a reviewer.
  Load via:
  `python3 ~/.hermes/skills/autonomous-ai-agents/persona-delegation/scripts/persona.py load specialized-developer-advocate`
- Note: R4 touches `sdk-python/` (a separate package) and `backend/docs/` — both are in-repo, so
  this card CAN commit normally (unlike R1/R8 which need cross-repo frontend patches).

**Verification (for the reviewer):** `git diff` should add a quickstart doc + SDK README change +
optionally a small schema alias; zero changes to `swarm_protocol.py` route logic. The `curl` in
the doc should be copy-paste runnable against a running backend.
