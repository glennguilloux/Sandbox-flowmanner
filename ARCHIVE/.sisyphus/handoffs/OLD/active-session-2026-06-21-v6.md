# Session Handoff — 2026-06-21 (Sun), v6

**Machine:** homelab (172.16.1.1)
**Active agent:** hermes (M3)
**User:** Glenn
**Status:** ACTIVE — Clean exit. (a) PR #15 (c) Programs → 'Automations'
wired into authed nav — DEPLOYED. **NOT YET MERGED TO MASTER** (deploy-from-
branch pattern, see §"Anomalies" below). (b) Previous session (v5) handoff
archived to OLD/active-session-2026-06-21.md.
**Master HEAD (frontend):** `3ef0b83` (origin/master in sync, UNCHANGED this session)
**Main HEAD (backend):**   `bf58a8a` (origin/main in sync, UNCHANGED this session)
**feat/nav-automations:**  `76410f0` (pushed, DEPLOYED, awaiting merge)

---

## TL;DR

One task done this session, in product (not GitHub housekeeping):

**(c) Programs → 'Automations' nav wire-up — shipped, deployed, NOT MERGED.**

Per Q2 (confirmed 2026-06-17): the Programs backend entity surfaces in the
UI as "Automations". PR #13 did the i18n relabel on the page tree
(`/dashboard/programs/*`) but left `nav-config.ts` untouched — so signed-in
users had no top-nav way to reach the surface. PR #15 closes that gap:
new 9th top-tier group `automations` (between `missions` and `run`),
2 items (`/dashboard/programs` + `/dashboard/programs/new`), i18n keys in
all 5 locales, test updated 8→9 groups + new 2-items assertion. 7 files,
+40/-2.

**Anomaly: deploy happened from `feat/nav-automations` branch BEFORE
PR #15 was merged.** Glenn's deploy-frontend.sh rsyncs the working tree
regardless of branch. The live container has the new code (verified via
grep on compiled `.next/static/chunks` for `nav.automations` and
`/dashboard/programs`). Master is still at `3ef0b83`. Next deploy from
master will revert production. See §"Anomalies" for details + remediation.

---

## Recommended next-session prompt

```
OPENING RITUAL — 2026-06-21 handoff v6:
- Read /opt/flowmanner/.sisyphus/handoffs/active-session-2026-06-21.md (this file)
- Master is at 3ef0b83. Backend main at bf58a8a. Both trees clean, unchanged this session.
- CRITICAL ANOMALY: PR #15 is OPEN + DEPLOYED, master is at 3ef0b83 (PR not merged).
  Live container has the new nav (verified via grep on .next/static/chunks for
  'nav.automations' and '/dashboard/programs'). Next deploy from master reverts it.
  Sanity check: cd /home/glenn/FlowmannerV2-frontend && git status && git log --oneline -3 origin/master first.
- Decide on one of:
  (a) Merge PR #15 now (master catches up to production, no further action needed)
  (b) Switch dev tree to master, accept production is 1 commit ahead (run a follow-up
      to fold feat/nav-automations into master later)
  (c) Roll back production (revert deploy, do the merge properly, then re-deploy)
- After the master reconciliation, queued tasks (your call, in priority order):
  (d) Fill pre-existing fr/es/de/ja gaps (admin/agents/citation) — these are
      translator review, not new keys (PR #13 already filled programs.* placeholders)
  (e) Naming-drift follow-ons: /workflows marketing copy (A1-A3) per Q3
- Still open from prior sessions: PR #3, PR #4
- DO NOT deploy backend (no backend code changed; gate green at 965 pass / 3 skip)
- DO NOT deploy frontend until the master-vs-prod anomaly is resolved
```

That gives me: where to read, current SHAs, the deploy anomaly, the decision
points, and the queued tasks. ~12 lines.

---

## State at session end

**Frontend `/home/glenn/FlowmannerV2-frontend/`:**
- On branch: `feat/nav-automations` (NOT master — see §"Anomalies")
- HEAD: `76410f0` — feat(nav): wire Programs into authed nav as 'Automations' (#15)
- Pushed to origin: ✓
- Working tree: clean
- Untracked (pre-existing, NOT mine): `plans/memory-citations-t33-handoff.md`

**Backend `/opt/flowmanner/`:**
- On branch: `main`
- HEAD: `bf58a8a` (unchanged this session — no backend code changes)
- Working tree: clean
- `make validate-migration` → green (per handoff v5 baseline)
- `python -m pytest` in container → 965 passed, 3 skipped (re-verified this session)
- `alembic current` → `20260617_pending_writes (head)` (re-verified this session)

**VPS (74.208.115.142):**
- `/opt/flowmanner/frontend/` (rsync target): has new code (mtime 18:54 UTC, 3× "automations" in nav-config.ts)
- Running container `flowmanner-frontend`: rebuilt 18:54 UTC, age ~3 min when checked
- Compiled chunks verified: `nav.automations` key in `.next/static/chunks/170d8uz7nvc2s.js`, `/dashboard/programs` in 3 chunks

**Open PRs (Glenn reviews):**
- PR #3 — from earlier session (untouched)
- PR #4 — from earlier session (untouched)
- PR #15 — **OPEN, NOT MERGED, BUT DEPLOYED** (this session)

**Closed issues this session:** none.

---

## Session-3 deliverable: Programs → 'Automations' nav wire-up (PR #15)

**Shipped in PR #15 (7 files, +40/-2):**

| File | Change |
|------|--------|
| `src/components/layout/nav-config.ts` | +12: 9th top-tier group `automations`, 2 items, comment block |
| `src/components/layout/__tests__/floating-nav.test.tsx` | +20/-2: 8→9 groups assertion, new "automations has 2 items" test |
| `src/i18n/locales/en.json` | +2: `nav.automations` + `nav.automationCreate` |
| `src/i18n/locales/fr.json` | +2: same keys, English placeholders |
| `src/i18n/locales/es.json` | +2: same keys, English placeholders |
| `src/i18n/locales/de.json` | +2: same keys, English placeholders |
| `src/i18n/locales/ja.json` | +2: same keys, English placeholders |

**Why a new top-tier group (not a sub-item under Missions):**
1. Programs/Missions are distinct concepts — Missions = visual builder for
   one mission, Automations = saved programs that fire on schedule/webhook.
2. Per the Q2 decision record: backend entity name stays "program";
   UI label is "Automations" with its own surface.
3. Other multi-item groups (market, tools, swarm) follow the same
   "promote-to-top-tier" pattern in nav-config.ts.

**Why slot between `missions` and `run`:**
Semantic chain: build mission → save as automation → view run history.
The nav reads left-to-right as the user flow.

**Verifications run this session (all on the branch before deploy):**
- `pnpm validate-nav-routes` → 43/43 OK (was 41; +2 new routes resolve)
- `npx tsc --noEmit` → 0 errors
- `pnpm test` → 808/808 pass (68 files, 9.11s; was 807, +1 new test)
- All 5 locale files parse as valid JSON

**Deployment verifications (after Glenn's deploy):**
- VPS rsync target `/opt/flowmanner/frontend/`: nav-config.ts has 3× "automations", en.json has it, fr.json has it, test file has the new assertion, mtime 18:54 UTC
- Running container `flowmanner-frontend`: rebuilt 18:54 UTC, healthy, age ~3 min when checked
- Compiled chunks: `nav.automations` key in `.next/static/chunks/170d8uz7nvc2s.js`, `/dashboard/programs` in 3 chunks (nav config + 2 routing chunks)

**Out of scope (deliberate):**
- The duplicate `/missions` href in the missions group (pre-existing; separate concern)
- The `visualWorkflows` → `visualMissionBuilder` i18n key rename (internal name, deferred)
- `/workflows` marketing copy (A1-A3, separate task per handoff v5)
- fr/es/de/ja translations (English placeholders pending translator review; PR #13 pattern)
- `pnpm lint` not run (display text only, baseline-equal expected)

---

## Anomalies

**PR #15 deployed from `feat/nav-automations` before merge.**

- **What happened:** Glenn said "deploy OK!" after the session paused for his review. He ran `bash /opt/flowmanner/deploy-frontend.sh`, which rsyncs the working tree regardless of branch (see `deploy-frontend.sh:134-138` — `rsync ... /home/glenn/FlowmannerV2-frontend/ ...`). The dev tree was on `feat/nav-automations` (where I left it), so the new code went to production. The PR is still open; master is still at `3ef0b83`.
- **Why this matters:** The canonical source (master) is now 1 commit behind production. Next deploy from master will revert the new nav. The handoff-v5 post-merge-stop lesson still applies: I did NOT auto-merge, I did NOT auto-cleanup, I flagged it.
- **What's NOT broken:** The running container has the new code, compiled chunks include the new strings, no in-flight issues. This is a workflow anomaly, not a runtime bug.
- **Remediation options (Glenn's call, listed in next-session prompt):**
  - (a) Merge PR #15: master catches up. One `gh pr merge 15 --squash` from the homelab. Safe.
  - (b) Switch dev tree to master now, fold feat/nav-automations in later: more conservative, accepts prod-ahead state.
  - (c) Roll back production: re-deploy master, re-merge properly, re-deploy. Highest cost.

**Live-curl 307 caveat (recorded for next session):**

All `/en/*` paths return 307 to `/en/signin?from=...` regardless of whether the
route exists on the live site. The auth middleware catches everything before
the route handler. This means HTTP code alone CANNOT verify a route is
deployed — only the auth-gated layout is reached. To verify a route, you
must be authed, OR check the compiled JS chunks (the nav-config bundle and
the i18n bundle). The verification approach used in this session was
`docker exec <front> sh -c "grep -rl 'nav.automations' .next/static/chunks"`
on the VPS, which is the definitive proof for static route assets.

---

## Mistakes and lessons

**No new mistakes this session.** The handoff-v5 post-merge-stop lesson
held: I opened the PR, did not auto-merge, did not auto-cleanup, did not
chain into branch-delete or issue-comment hygiene. The deploy-from-branch
anomaly is a user-side action (Glenn chose to deploy before merging),
not an agent mistake.

**New memory candidate (deferred until Glenn decides what to do):**
If Glenn goes with remediation (a) and merges PR #15, the lesson is:
"deploy-frontend.sh rsyncs from working tree, not from master. Pre-merge
deploys leave master stale." This is a fact about the deploy tool, not
an agent lesson, and would belong in a deploy-runbook, not agent memory.

---

## Delegations

**None this session.** All work done in this agent. No subagents, no
Copilot review fired, no DeepSeek.

---

## End-of-session ritual checklist

- [x] Code committed locally (76410f0 on feat/nav-automations)
- [x] Code pushed to origin (origin/feat/nav-automations @ 76410f0, in sync)
- [x] Local working tree clean (modulo pre-existing untracked file)
- [x] Pre-deploy verifications green (tsc 0, vitest 808/808, validate-nav-routes 43/43)
- [x] `make validate-migration` green on backend (baseline-equal, no backend changes)
- [x] `python -m pytest` green on backend (965 pass, 3 skip — re-verified this session)
- [x] `alembic current` at head (re-verified: `20260617_pending_writes (head)`)
- [x] PR #15 OPEN (NOT MERGED — flagged as anomaly)
- [x] Frontend DEPLOYED by Glenn (from feat/nav-automations branch)
- [x] Deploy verified on VPS (rsync target has new code, container rebuilt, chunks contain new strings)
- [x] Handoff doc updated (v5 archived to OLD/, this v6 is the active file)
- [x] Deploy NOT run by agent (per AGENTS.md + ritual — Glenn deploys)
- [x] No auto-merge, no auto-cleanup (per memory: post-merge STOP)
- [ ] Master NOT updated to 76410f0 (deliberate; awaits Glenn's remediation decision)
