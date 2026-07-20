#!/usr/bin/env python3
"""
Flowmanner repo audit: classify git worktrees/branches for SAFE pruning.
STRICTLY READ-ONLY ANALYSIS (no mutations). Emits:
  - human summary + per-worktree verdicts to stdout
  - exact prune commands to stdout
  - structured JSON to /tmp/flowmanner_audit_<date>.json
Verdict logic:
  PRUNE = worktree is clean (no tracked modifications), not locked, and its
          branch tip is already reachable from `main` (merged OR fully contained).
  DIRTY = worktree has uncommitted tracked changes -> NEVER auto-prune.
  KEEP  = clean but unmerged with unique commits -> real pending work.
"""
import subprocess, json, datetime, os
from typing import Any, Dict

REPO = "/opt/flowmanner"
MAIN = "main"
TODAY = str(datetime.date.today())


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
        elif line.startswith("locked "):
            cur["locked"] = line.split(" ", 1)[1] or True
        elif line.startswith("prunable "):
            cur["prunable"] = line.split(" ", 1)[1] or True
    if cur:
        wts.append(cur)
    return wts


def merged_set():
    _, out, _ = g(["branch", "--merged", MAIN])
    return set(l.strip() for l in out.splitlines() if l.strip())


def unique_commits(branch):
    if not branch:
        return 0
    _, out, _ = g(["rev-list", "--count", f"{MAIN}..{branch}"])
    try:
        return int(out.strip())
    except Exception:
        return -1


def is_ancestor(commit, base):
    if not commit:
        return False
    rc, _, _ = g(["merge-base", "--is-ancestor", commit, base])
    return rc == 0


def is_dirty(path):
    # ignore untracked (node_modules/.venv noise); we care about tracked mods
    _, out, _ = g(["status", "--porcelain", "--untracked-files=no"], cwd=path)
    return bool(out.strip())


def main():
    wts = worktrees()
    merged = merged_set()
    rows, prunable = [], []
    for w in wts:
        path = w["path"]
        is_main = path == REPO
        branch = w.get("branch")
        detached = w.get("detached", False)
        locked = "locked" in w
        prunable_flag = "prunable" in w
        dirty = is_dirty(path) if not prunable_flag else False
        head = w.get("head", "")
        head_in_main = is_ancestor(head, MAIN)
        br_merged = branch in merged if branch else False
        uniq = unique_commits(branch)
        safe, reason = False, []
        if is_main:
            reason.append("main worktree")
        elif prunable_flag:
            safe = True
            reason.append("already prunable (dir gone)")
        elif dirty:
            reason.append("HAS UNCOMMITTED TRACKED CHANGES")
        elif locked:
            reason.append("LOCKED")
        elif br_merged:
            safe, reason = True, ["branch merged into main"]
        elif head_in_main:
            safe, reason = True, ["head fully contained in main"]
        elif branch and uniq == 0:
            safe, reason = True, ["no unique commits vs main"]
        else:
            reason.append(f"unmerged, {uniq} unique commits")
        rows.append({
            "path": path, "branch": branch, "detached": detached,
            "merged": br_merged, "unique": uniq, "dirty": dirty,
            "locked": locked, "prunable_flag": prunable_flag,
            "head_in_main": head_in_main, "safe": safe,
            "reason": "; ".join(reason),
        })
        if safe:
            prunable.append(w)

    safe_n = sum(1 for r in rows if r["safe"])
    dirty_n = sum(1 for r in rows if r["dirty"])
    keep_n = sum(1 for r in rows if not r["safe"] and not r["dirty"] and not r["locked"] and r["path"] != REPO)

    print(f"=== FLOWMANNER REPO AUDIT  {TODAY}  (repo: {REPO}) ===")
    print(f"Total worktrees : {len(rows)}  (main worktree excluded from prune)")
    print(f"  PRUNE-safe     : {safe_n}  (clean + merged/contained)")
    print(f"  DIRTY          : {dirty_n}  (uncommitted tracked work -> keep)")
    print(f"  KEEP (real)    : {keep_n}  (clean but unmerged w/ unique commits)")
    print()
    print(f"{'VERDICT':<7} {'UNIQ':>4}  {'BRANCH':<52} PATH")
    for r in sorted(rows, key=lambda x: (not x["safe"], x["path"])):
        v = "PRUNE" if r["safe"] else ("DIRTY" if r["dirty"] else "KEEP")
        print(f"{v:<7} {str(r['unique']):>4}  {str(r['branch'])[:51]:<52} {r['path']}")

    print("\n=== PRUNE PLAN (exact commands) ===")
    plan = []
    for w in prunable:
        plan.append(f"git worktree remove --force '{w['path']}'")
        if w.get("branch") and not w.get("detached"):
            plan.append(f"git branch -D '{w['branch']}'")
    for p in plan:
        print(p)

    report = {
        "date": TODAY, "repo": REPO, "rows": rows, "prune_plan": plan,
        "counts": {"total": len(rows), "safe": safe_n, "dirty": dirty_n, "keep": keep_n},
    }
    outpath = f"/tmp/flowmanner_audit_{TODAY}.json"
    with open(outpath, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nJSON report: {outpath}")


if __name__ == "__main__":
    main()
