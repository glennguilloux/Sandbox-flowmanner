#!/usr/bin/env python3
"""Pass 2: delete merged branches that are NOT owned by any surviving worktree.
Safe: 'merged into main' => history already in main, deletion loses nothing.
Skips branches that a live (dirty/keep) worktree still checks out.
"""
import subprocess, json

REPO = "/opt/flowmanner"
MAIN = "main"


def g(a, cwd=REPO):
    r = subprocess.run(["git"] + a, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def surviving_branches():
    _, out, _ = g(["worktree", "list", "--porcelain"])
    brs = set()
    cur = {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            cur = {}
        elif line.startswith("branch "):
            cur["branch"] = line.split(" ", 1)[1]
        elif line == "" and cur:
            if "branch" in cur:
                brs.add(cur["branch"])
    return brs


def main():
    # branches owned by surviving worktrees (full refs like refs/heads/...)
    owned = surviving_branches()
    # merged branches (full refs)
    _, out, _ = g(["branch", "--merged", MAIN])
    merged = set(l.strip() for l in out.splitlines() if l.strip())
    # current branch must never be deleted
    _, cur, _ = g(["rev-parse", "--abbrev-ref", "HEAD"])
    current = "refs/heads/" + cur.strip()

    deletable = (merged - owned) - {current}
    print(f"Surviving worktree branches (protected): {len(owned)}")
    print(f"Merged branches: {len(merged)}")
    print(f"Deletable (merged & orphaned): {len(deletable)}")
    for b in sorted(deletable):
        short = b.split("refs/heads/", 1)[-1]
        rc, o, e = g(["branch", "-D", short])
        status = "OK" if rc == 0 else f"FAIL {e.strip()[:80]}"
        print(f"  {status}  {short}")
    # recount
    _, bout, _ = g(["branch"])
    print(f"\nRemaining branches: {len([l for l in bout.splitlines() if l.strip()])}")


if __name__ == "__main__":
    main()
