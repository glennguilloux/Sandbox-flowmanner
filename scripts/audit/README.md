# Flowmanner Repo Audit Toolkit

Deterministic, **non-destructive** tooling to keep the Flowmanner monorepo
(~/homelab `/opt/flowmanner`) tidy under heavy parallel-Hermes-agent fan-out,
where every agent spawns its own `git worktree` + branch.

## Scripts

| Script | Purpose | Mutates? |
|--------|---------|----------|
| `audit_worktrees.py` | Read-only classifier. Lists every worktree, labels each `PRUNE-safe` (clean + branch merged/contained in `main`), `DIRTY` (uncommitted tracked changes → protected), or `KEEP` (unmerged with unique commits). Emits exact prune commands + JSON report. | **No** |
| `prune_worktrees.py` | Executor. Removes only the `PRUNE-safe` worktrees (history-safe: all commits already in `main`). | **Yes (reversible via `main`)** |
| `prune_branches.py` | Executor pass 2. Deletes merged branches NOT owned by a surviving worktree. Skips `+`-prefixed (checked-out) and `*` (current) branches. | **Yes (reversible via `main`)** |
| `clean_slate.py` | **Safe clean slate.** For every non-`main` worktree, snapshots its full current state (committed + uncommitted tracked) into `backup/cleanslate-<DATE>/<slug>` branches, then removes all worktrees and original branches. Backup branches remain → nothing lost. `--dry-run` shows the plan; `--finalize` also deletes the backup branches (irreversible). | **Yes, but with time-capsule backups** |

## Non-destructive guarantee

Pruning a worktree whose branch is already merged into / contained in `main`
loses **no commits** — they all live in `main`. The only irreversible step is
`clean_slate.py --finalize`, which deletes the `backup/cleanslate-*` capsules;
run it only after confirming nothing is needed.

## `git branch` prefix legend (read during audit)

- `+` = branch checked out by a surviving worktree → **protected, never delete**
- `*` = current branch
- plain = not owned by any worktree → safe to prune when merged

## Usage

```bash
cd /opt/flowmanner
python3 scripts/audit/audit_worktrees.py                 # see the landscape
python3 scripts/audit/prune_worktrees.py                # prune merge-safe residue
python3 scripts/audit/prune_branches.py                 # prune orphaned merged branches
python3 scripts/audit/clean_slate.py --dry-run          # preview a full collapse
python3 scripts/audit/clean_slate.py                    # collapse to single main (backed up)
python3 scripts/audit/clean_slate.py --finalize         # drop backups too (IRREVERSIBLE)
```

## Audit history (in Hermes KG)

Dated audit snapshots and the reusable procedure live in the Hermes knowledge
graph: `repo_audit_2026_07_19` (snapshot) + `flowmanner_repo_hygiene`
(procedure). On any Flowmapper/ Flowmanner task, hydrate from the KG first via
`search_nodes("repo_audit")` then `search_nodes("flowmanner")`.
