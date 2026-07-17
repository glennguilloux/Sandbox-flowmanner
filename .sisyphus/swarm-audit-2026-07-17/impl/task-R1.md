# R1 — Unlock the 185 invisible personas (backend scan-root + frontend gallery patch)

**Context:** The swarm audit (REPORT.md §3 C2) found `backend/app/api/v1/agent_personalities.py:21`
hard-codes `_DEFINITIONS_DIR` to the single `agent_definitions/agent_personalities/`
subdir, and `_load_all_personalities` (`:100-111`) iterates only that one folder.
Result: 185 of 215 personas are unreachable in-product. This is the single
highest-value-to-effort fix in the whole audit.

**Your task (two halves, one card):**

## Half A — Backend scan-root fix (COMMIT in this worktree)
1. In `backend/app/api/v1/agent_personalities.py`: repoint the scan so it walks
   the **entire** `agent_definitions/` tree (all 16 subdirs), not just
   `agent_personalities/`. Preserve the existing `domain/slug` id scheme
   (`get_agent_personality` at `:125-150`).
2. Add `?domain=` and `?q=` query filters to `list_agent_personalities` (`:120`).
3. Verify by running the loader logic (or a quick `find` count) that the endpoint
   would now surface **215** personas, not 30.
4. Add/extend a test asserting the count = 215.

## Half B — Frontend gallery patch (READ-ONLY of live repo, emit patch)
The frontend repo is NOT in this worktree. READ these live files to ground an
accurate diff (read-only is fine):
- `/home/glenn/FlowmapperV2-frontend/src/data/agents.ts` (`:4-15` `DOMAIN_LABELS` names only 10 domains)
- `/home/glenn/FlowmapperV2-frontend/src/app/[locale]/agents/agents-page-content.tsx` (`:27-41` `groupByDomain`, `:135` empty state)
Author a patch that: extends `DOMAIN_LABELS` / adds a fallback label for every
domain so all 16 render; adds a text search + filter chips + "recommended" row.
WRITE the patch to this worktree as `frontend-agent-gallery.patch` (a `git apply`-ready
unified diff) plus a one-paragraph spec. Do NOT try to commit it here.

**Constraints:** Minimal, surgical change (this persona's whole point). No refactors
outside the two files. Commit Half A to this branch. Do NOT push, deploy, or merge.
When done, stop and await review (block-for-review).
