# Task: Phase 0.2 — Triage Stale Remote Branches

**Status:** DRAFT
**Priority:** P2 — housekeeping, no code impact
**Estimated effort:** 15 minutes
**Created:** 2026-07-06
**Source:** `docs/STUB-COMPLETION-PLAN-2026-07-06.md` §Phase 0.2

---

## Problem

The frontend repo has 12 remote branches (excluding `origin/main` and `origin/master`). Most are feature branches from weeks ago that were never cleaned up. They pollute `git branch -a` output and create confusion about what's active.

Current remote branches (verified 2026-07-06):

```
agent/20260622-5c0022/fix-deletion-guard-justify-check
chore/cleanup-followups
drop-audio-features
drop-audio-features-v2
drop-audio-frontend-cleanup
feat/brand-strings-mission-renaming
feat/cli-v0.1-audit-fixes
feat/nav-automations
fix/pr-check-pytest-blockers
perf/health-endpoint-lightweight
wt/w1-t4-cleanup
```

---

## Acceptance Criteria

- [ ] Each branch checked for recent activity (commits in last 30 days)
- [ ] Each branch checked for commits ahead of master
- [ ] Stale branches (>100 commits ahead, 0 recent activity) deleted from origin
- [ ] `feat/brand-strings-mission-renaming` and `feat/nav-automations` preserved (these have only 1 commit each, may be worth merging)
- [ ] `git branch -r` output is clean after triage

---

## Sub-tasks

### 0.2.1 — Check branch activity

```bash
cd /home/glenn/FlowmannerV2-frontend

for b in agent/20260622-5c0022/fix-deletion-guard-justify-check \
         chore/cleanup-followups \
         drop-audio-features drop-audio-features-v2 drop-audio-frontend-cleanup \
         feat/cli-v0.1-audit-fixes fix/pr-check-pytest-blockers \
         perf/health-endpoint-lightweight wt/w1-t4-cleanup; do
  count=$(git log origin/$b --since='30 days ago' --oneline 2>/dev/null | wc -l)
  ahead=$(git rev-list --count origin/master..origin/$b 2>/dev/null || echo "N/A")
  echo "$b: $count recent commits, $ahead ahead of master"
done
```

### 0.2.2 — Decision tree

- If **< 5 commits ahead** and recent → review for merge
- If **> 100 commits ahead** and **0 recent commits** → delete as stale
- If branch name matches a shipped feature → delete

### 0.2.3 — Delete stale branches

```bash
# Only after confirming they're stale:
git push origin --delete <branch-name>
```

**Do NOT delete:** `feat/brand-strings-mission-renaming` or `feat/nav-automations` — these have only 1 commit each and may contain useful work. Review both for inclusion.

### 0.2.4 — Review local branches

```bash
git branch --format='%(refname:short)' | grep -v master
```

Check `feat/brand-strings-mission-renaming` and `feat/nav-automations` — 1 commit each, may be worth merging or rebasing.

---

## Verification

```bash
git branch -r --format='%(refname:short)' | grep -v 'origin/main\|origin/master' | wc -l
# Should be significantly less than 12
```

---

## Commit

```
chore: triage stale remote branches (delete N, review 2 local)
```
