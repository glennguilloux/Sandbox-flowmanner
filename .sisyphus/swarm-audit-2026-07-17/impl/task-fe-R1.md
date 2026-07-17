# R1 (frontend half) — Apply the agent-gallery patch to the Flowmanner frontend

**Origin:** 2026-07-17 swarm audit. The backend half (scan-root unlock → 215 personas) is
MERGED to backend `main`. This card lands the FRONTEND half so users can actually see/browse
all 215 personas. The backend worker already authored a ready-to-apply patch.

**Repo:** `/home/glenn/FlowmannerV2-frontend` (Flowmanner = double-n, zero P's). It is a
separate git repo from the backend. Currently on branch `agent/2026-07-14-chat-bin-byok-fixes`.

**Your task:**
1. In the frontend repo, create your OWN exclusive branch (e.g.
   `agent/2026-07-17-frontend-r1-gallery`) and worktree — do NOT commit to the current branch.
2. The patch lives at `/opt/flowmanner/frontend-agent-gallery.patch` (committed in backend main).
   Apply it: `git apply /opt/flowmanner/frontend-agent-gallery.patch`. It MODIFIES
   `src/data/agents.ts` (extends `DOMAIN_LABELS` + adds fallback so all 16 domains render) and
   adds search/filter chips + a "recommended" row to the agent gallery. VERIFIED: it applies
   cleanly to current frontend HEAD.
3. If `git apply` fails for any reason, regenerate the equivalent change by reading the live
   `src/data/agents.ts` + the gallery component and editing directly — do not silently skip.
4. Run the frontend typecheck/build if a fast command exists (check package.json scripts); if it
   needs a long install, skip and note it.
5. Commit. Do NOT push, deploy (frontend deploy is Glenn's `deploy-frontend.sh`, ~4 min), or merge.

**Constraints:**
- Frontend-only. Do not touch the backend repo.
- Use persona `engineering-frontend-developer` (FIX persona) — load via
  `~/.hermes/skills/autonomous-ai-agents/persona-delegation/scripts/persona.py load engineering-frontend-developer`
- Leave the card `blocked` for review when done.

**Verify (reviewer):** `git diff` shows `src/data/agents.ts` + gallery component changes; all 16
domain labels render; no backend files touched.
