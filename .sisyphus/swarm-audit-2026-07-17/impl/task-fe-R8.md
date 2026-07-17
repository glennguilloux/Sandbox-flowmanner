# R8 (frontend half) — Make onboarding capability-aware (Flowmanner frontend)

**Origin:** 2026-07-17 swarm audit (REPORT.md §4 R8 + UX Researcher). The backend onboarding
hooks already exist (`backend/app/api/v1/onboarding.py`); this card makes the FRONTEND onboarding
wizard surface personas + capabilities so a new user doesn't form a "form builder" mental model.

**Repo:** `/home/glenn/FlowmapperV2-frontend` (Flowmanner = double-n, zero P's), separate git repo.
On branch `agent/2026-07-14-chat-bin-byok-fixes`.

**Context / files to read (read-only first):**
- `src/app/[locale]/(dashboard)/onboarding/page-client.tsx` — `CATEGORY_KEYS`,
  `handleGenerateSampleData` (the generic sample-data finish).
- `src/app/[locale]/(dashboard)/onboarding/page.tsx` — wizard step structure.
- The `GET /api/agent-personalities` contract (now returns 215 personas after the merged R1
  backend fix) — read `backend/app/api/v1/agent_personalities.py` if you need the response shape
  (read-only; do not edit backend).

**Your task:**
1. Create your OWN exclusive branch (e.g. `agent/2026-07-17-frontend-r8-onboarding`) + worktree.
2. After the "what do you automate?" step, recommend 2–3 personas from the matched domain (wire a
   lookup to `GET /api/agent-personalities`, filter by the chosen category), and show one
   "here's what you can build" capability card (mission builder / RAG / swarm debate).
3. Replace the generic `generateSampleData` finish with a guided first mission using the chosen
   persona (or at minimum, surface the recommended persona as the starting point).
4. Run the frontend typecheck/build if a fast command exists; if a long install is needed, skip and
   note it.
5. Commit. Do NOT push, deploy, or merge.

**Constraints:**
- Frontend-only. Backend changes are out of scope here.
- Use persona `engineering-frontend-developer` (FIX persona) — load via
  `~/.hermes/skills/autonomous-ai-agents/persona-delegation/scripts/persona.py load engineering-frontend-developer`
- Leave the card `blocked` for review when done.

**Verify (reviewer):** `git diff` shows onboarding component changes only; a persona/capability
recommendation appears in the wizard flow; no backend files touched. The original R8 worktree
patch was lost on reclaim, so this is a fresh implementation from current frontend code.
