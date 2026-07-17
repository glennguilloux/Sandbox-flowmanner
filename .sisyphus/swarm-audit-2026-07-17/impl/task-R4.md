# R4 — "Swarm in 30 seconds" demo + SDK lead (docs/DX)

**Context:** Swarm audit REPORT.md §4 R4 + Developer Advocate ledger. The most
differentiated call in the API — `POST /api/swarm/protocol/debate` (real, callable,
LLM-judge scored; `backend/app/api/v1/swarm_protocol.py:104`) — is absent from the
first-10-minute experience and from the SDK's headline example.

**Your task:**
1. Add a Quick Start doc page (markdown under `docs/` or `backend/docs/`) whose
   step 1 is a copy-paste `curl` to `/api/swarm/protocol/debate` (use the Advocate's
   example from the audit ledgers; topic + two `agent_a_id`/`agent_b_id` from
   `GET /api/agent-personalities`). Include a recorded-replay landing-demo spec.
2. Update `sdk-python/flowmanner-api-client/README.md` to lead with a `debate()`
   example instead of `create_mission` (add a `debate()` convenience method to the
   client if trivial; otherwise just reorder docs).
3. Fix the `strategy` naming trap: in the `ExecuteRequest` schema
   (`openapi.json:41474` pattern `^(parallel|sequential|debate)$`), either accept
   `swarm` as an alias for `debate`, OR document the enum prominently. Prefer
   adding the alias (1-line schema tweak in the swarm service / `ExecuteRequest`).
   Confirm no live endpoint accepts `strategy:"swarm"` before choosing.

**Constraints:** Docs + SDK + one small schema tweak. Do not touch protocol logic.
Commit to this branch. Do NOT push, deploy, or merge. Stop and await review when done.
