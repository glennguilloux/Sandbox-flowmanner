# R8 — Onboarding capability-aware (FRONTEND patch; backend worktree = read-only of live repo)

**Context:** Swarm audit REPORT.md §4 R8 + UX Researcher ledger. The onboarding
wizard never references personas or capabilities, so a new user forms a "form
builder" mental model. Frontend repo is NOT in this worktree.

**Your task (READ live frontend, EMIT a patch — do not commit frontend here):**
1. READ (read-only) `/home/glenn/FlowmapperV2-frontend/src/app/[locale]/(dashboard)/onboarding/page-client.tsx`
   (`:11-75` `CATEGORY_KEYS`, `handleGenerateSampleData`) and the
   `/api/agent-personalities` contract.
2. Author a patch that: after the "what do you automate?" step, recommends 2–3
   personas from the matched domain (wire to `agent-personalities` lookup) and
   shows one "here's what you can build" capability card (mission builder / RAG /
   swarm); replace the generic `generateSampleData` finish with a guided first
   mission using the chosen persona.
3. WRITE the patch to this worktree as `frontend-onboarding.patch` (unified diff) +
   a short spec. Note the backend onboarding hooks already exist
   (`backend/app/api/v1/onboarding.py`).

**Constraints:** Frontend patch only — emit to worktree, do NOT attempt to commit
it here (wrong repo). Backend changes are out of scope. Stop and block-for-review.
