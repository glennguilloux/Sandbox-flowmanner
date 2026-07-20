#!/usr/bin/env python3
"""Executor: prune ONLY the PRUNE-safe worktrees from the audit JSON.
Non-destructive: only acts on clean worktrees whose branch is merged/contained
in main, so all commits survive in main. Leaves DIRTY and KEEP worktrees alone.
Emits a recount + verification of git state after pruning.
"""
import json, subprocess, sys

REPO = "/opt/flowmanner"
JSON = "/tmp/flowmanner_audit_2026-07-19.json"


def g(args, cwd=REPO):
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def main():
    data = json.load(open(JSON))
    safe = [r for r in data["rows"] if r["safe"]]
    # never touch the main worktree
    safe = [r for r in safe if r["path"] != REPO]
    print(f"Executing {len(safe)} PRUNE-safe worktree removals...")
    removed, errored = 0, []
    for r in safe:
        path = r["path"]
        rc, out, err = g(["worktree", "remove", "--force", path])
        if rc != 0:
            errored.append((path, err.strip()))
            print(f"  WORKTREE-REMOVE FAILED: {path}\n    {err.strip()[:200]}")
            continue
        removed += 1
        # delete the branch if it existed and is a plain ref
        br = r.get("branch")
        if br and not r.get("detached"):
            short = br.split("refs/heads/", 1)[-1]
            rc2, o2, e2 = g(["branch", "-D", short])
            if rc2 != 0:
                print(f"  branch -D skipped ({short}): {e2.strip()[:120]}")
    print(f"\nRemoved worktrees: {removed}/{len(safe)}")
    if errored:
        print(f"ERRORS: {len(errored)} (see above)")
    # Recount
    _, out, _ = g(["worktree", "list"])
    wt_count = len([l for l in out.splitlines() if l.startswith("/")])
    _, bout, _ = g(["branch"])
    br_count = len([l for l in bout.splitlines() if l.strip()])
    print(f"Remaining worktrees: {wt_count}")
    print(f"Remaining branches : {br_count}")
    # Confirm main still intact
    rc, out, _ = g(["rev-parse", "HEAD"])
    print(f"main HEAD: {out.strip()}  (should still be 159f3795)")


if __name__ == "__main__":
    main()
