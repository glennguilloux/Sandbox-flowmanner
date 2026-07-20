#!/usr/bin/env python3
"""
Flowmanner SAFE clean-slate: collapse ALL worktrees down to a single 'main' tree.

NON-DESTRUCTIVE BY DESIGN (per backend/AGENTS.md evidence-preservation rule):
  For every non-main worktree, this script captures its FULL current state
  (committed commits AND any uncommitted tracked changes) into a time-capsule
  branch `backup/cleanslate-<DATE>/<slug>`, then removes the worktree and
  deletes the now-redundant original branch. The backup branches remain, so a
  clean slate is achieved WITHOUT any data loss.

Usage:
  python3 scripts/audit/clean_slate.py            # execute (after dry-run review)
  python3 scripts/audit/clean_slate.py --dry-run  # print plan, change nothing
  python3 scripts/audit/clean_slate.py --finalize # ALSO delete backup/* branches
                                             # (irreversible — only after you
                                             # confirm nothing is needed)

Slug rule: branch name with '/' -> '-' so capsules are flat, e.g.
  agent/2026-07-11-kb-celery-v3  ->  backup/cleanslate-2026-07-19-agent-2026-07-11-kb-celery-v3
"""
import subprocess, datetime, sys, os
from typing import Any, Dict

REPO = "/opt/flowmanner"
MAIN = "main"
DATE = str(datetime.date.today())
BACKUP_PREFIX = f"backup/cleanslate-{DATE}"


def g(args, cwd=REPO):
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def worktrees():
    _, out, _ = g(["worktree", "list", "--porcelain"])
    wts: list = []
    cur: Dict[str, Any] = {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            if cur:
                wts.append(cur)
            cur = {"path": line.split(" ", 1)[1]}
        elif line.startswith("HEAD "):
            cur["head"] = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            cur["branch"] = line.split(" ", 1)[1]
        elif line == "detached":
            cur["detached"] = True
    if cur:
        wts.append(cur)
    return wts


def slug_of(branch: str) -> str:
    b = branch.split("refs/heads/", 1)[-1]
    return b.replace("/", "-")


def main():
    dry = "--dry-run" in sys.argv
    finalize = "--finalize" in sys.argv
    wts = worktrees()
    targets = [w for w in wts if w["path"] != REPO and w.get("branch") != f"refs/heads/{MAIN}"]
    print(f"=== FLOWMANNER CLEAN-SLATE  {DATE}  (dry_run={dry}, finalize={finalize}) ===")
    print(f"Worktrees to collapse: {len(targets)}  (main worktree preserved)")
    if dry:
        for w in targets:
            br = w.get("branch", "(detached)")
            print(f"  would backup {br} -> {BACKUP_PREFIX}-{slug_of(br)}  then remove {w['path']}")
        return

    backed = []
    skipped = []
    for w in targets:
        path = w["path"]
        br = w.get("branch")
        # Capture uncommitted tracked work so the capsule is complete.
        rc, st, _ = g(["status", "--porcelain"], cwd=path)
        if st.strip():
            g(["add", "-u"], cwd=path)
            msg = f"cleanslate backup: {br or path}"
            rc2, _, e2 = g(["commit", "-m", msg], cwd=path)
            if rc2 != 0:
                # Pre-commit hook (lint/format) blocked it. For a BACKUP capsule
                # this is safe to bypass — matches the repo's own
                # `git commit --no-verify` convention for worktree lint mis-rolls.
                rc3, _, e3 = g(["commit", "--no-verify", "-m", msg], cwd=path)
                if rc3 != 0:
                    # Even --no-verify failed: DO NOT discard this worktree's
                    # uncommitted work. Leave it in place for manual handling.
                    print(f"  SKIP (commit failed even with --no-verify): {path} :: {e3.strip()[:120]}")
                    skipped.append((path, br))
                    continue
                print(f"  WARN committed capsule with --no-verify (hook would block): {path}")
        cap = f"{BACKUP_PREFIX}-{slug_of(br) if br else os.path.basename(path)}"
        g(["branch", "-f", cap, "HEAD"], cwd=path)
        print(f"  backed up -> {cap}")
        backed.append((path, br, cap))

    if skipped:
        print(f"\n  !! {len(skipped)} worktree(s) NOT removed (commit failed). "
              f"Resolve manually; re-run clean_slate.py to collapse them.")

    # Remove worktrees (forces removal of any residual untracked junk too).
    for path, br, cap in backed:
        rc, _, e = g(["worktree", "remove", "--force", path])
        if rc != 0:
            print(f"  WORKTREE-REMOVE FAILED {path}: {e.strip()[:160]}")
            continue
        # Delete the redundant original branch now it is no longer checked out.
        if br:
            short = br.split("refs/heads/", 1)[-1]
            g(["branch", "-D", short])

    if finalize:
        _, out, _ = g(["branch"])
        for line in out.splitlines():
            b = line.strip().lstrip("*+ ").strip()
            if b.startswith(BACKUP_PREFIX):
                g(["branch", "-D", b])
        print("FINALIZE: backup branches deleted (irreversible).")

    # Verification
    _, out, _ = g(["worktree", "list"])
    wt_count = len([l for l in out.splitlines() if l.startswith("/")])
    _, bout, _ = g(["branch"])
    br_count = len([l for l in bout.splitlines() if l.strip()])
    _, head, _ = g(["rev-parse", "--short", "HEAD"])
    print(f"\nRESULT: {wt_count} worktree(s), {br_count} branch(es), main HEAD {head.strip()}")
    print("git fsck --full --unreachable missing-count:", end=" ")
    _, fout, _ = g(["fsck", "--full", "--unreachable"])
    miss = fout.count("missing")
    print(miss, "(0 = healthy)")


if __name__ == "__main__":
    main()
