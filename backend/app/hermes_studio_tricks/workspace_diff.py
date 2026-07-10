"""Workspace diff tracker: what did a run change?

Independent reimplementation of the *pattern* from Hermes Studio's
``workspace-diff-tracker.ts`` (no code copied; the repo is BSL-licensed).

Given a workspace path, snapshot its state at run start and diff it at run end,
producing a unified patch per changed file plus added/modified/deleted
classification. Two strategies:

* **git**: if the workspace is inside a git repo, use ``git status --porcelain -z``
  and ``git diff`` for accurate per-file deltas.
* **filesystem**: otherwise, do a bounded BFS scan and binary-aware file compare,
  falling back to ``git diff --no-index`` for the actual patch text.

All resource use is hard-capped so a giant repo can never hang the process.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

# --- resource caps --------------------------------------------------------

MAX_TRACKED_STATUS_PATHS = 20_000
MAX_CHANGED_FILES = 80
MAX_SNAPSHOT_BYTES = 512 * 1024
MAX_TOTAL_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_PATCH_BYTES_PER_FILE = 256 * 1024
MAX_TOTAL_PATCH_BYTES = 1024 * 1024
MAX_SCAN_DIRS = 5_000
MAX_SCAN_DEPTH = 16
MAX_SCAN_MS = 1_000

DEFAULT_IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "bower_components",
    ".pnpm-store",
    ".yarn",
    "dist",
    "build",
    "out",
    "target",
    ".gradle",
    ".mvn",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "htmlcov",
    "site-packages",
    ".cache",
    "coverage",
    ".nyc_output",
    ".next",
    ".nuxt",
    ".turbo",
    ".parcel-cache",
    ".svelte-kit",
    ".angular",
    "vendor",
    ".bundle",
    "bin",
    "obj",
    "TestResults",
    ".build",
    "DerivedData",
    "CMakeFiles",
    ".terraform",
    ".dart_tool",
    "_build",
    "deps",
    "tmp",
    "log",
}

SKIPPED_FILE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".obj",
    ".a",
    ".lib",
    ".lo",
    ".la",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".wasm",
    ".rlib",
    ".beam",
    ".jar",
    ".war",
    ".ear",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".bmp",
    ".tiff",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".mp3",
    ".wav",
    ".flac",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".sqlite",
    ".sqlite-shm",
    ".sqlite-wal",
    ".db",
    ".db-shm",
    ".db-wal",
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".tsbuildinfo",
    ".map",
    ".log",
    ".tmp",
    ".swp",
}


@dataclass
class FileDiff:
    path: str
    change_type: str  # added | modified | deleted
    binary: bool
    additions: int
    deletions: int
    size_before: int | None
    size_after: int | None
    patch: str | None
    truncated: bool


@dataclass
class WorkspaceDiff:
    kind: str  # git | filesystem
    root: str
    changes: list[FileDiff]
    additions: int
    deletions: int
    truncated: bool


def _is_path_inside(parent: str, candidate: str) -> bool:
    rel = os.path.relpath(candidate, parent)
    return rel == "." or (not rel.startswith("..") and ".." not in rel.split(os.sep))


def _is_binary(buf: bytes) -> bool:
    return b"\x00" in buf[:8000]


def _should_skip_file(rel_path: str) -> bool:
    name = os.path.basename(rel_path)
    return name in {".DS_Store", "Thumbs.db"} or os.path.splitext(rel_path)[1].lower() in SKIPPED_FILE_EXTENSIONS


def _git_root(workspace: str) -> str | None:
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except Exception:
        return None
    if not root:
        return None
    try:
        return root if _is_path_inside(os.path.realpath(root), os.path.realpath(workspace)) else None
    except Exception:
        return None


def _git_status_paths(git_root: str) -> tuple[list[str], bool]:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=normal"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except Exception:
        return [], True
    paths: set[str] = set()
    parts = [p for p in out.split("\0") if p]
    i = 0
    while i < len(parts):
        entry = parts[i]
        if len(entry) < 4:
            i += 1
            continue
        status = entry[:2]
        path = entry[3:]
        if ("R" in status or "C" in status) and i + 1 < len(parts):
            paths.add(parts[i + 1])
            i += 2
            continue
        paths.add(path)
        i += 1
    kept = [p for p in paths if not _should_skip_file(p)]
    return kept[:MAX_TRACKED_STATUS_PATHS], len(kept) > MAX_TRACKED_STATUS_PATHS


def _git_patch(git_root: str, rel_path: str, *, deleted: bool, added: bool) -> str | None:
    try:
        if deleted:
            out = subprocess.run(
                ["git", "diff", "--no-color", "HEAD", "--", rel_path],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        elif added:
            out = subprocess.run(
                ["git", "diff", "--no-color", "--no-index", "--", os.devnull, rel_path],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        else:
            out = subprocess.run(
                ["git", "diff", "--no-color", "HEAD", "--", rel_path],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout
        return out or None
    except Exception:
        return None


def _read_bytes(root: str, rel: str, limit: int) -> tuple[bool, int | None, bool, bytes | None]:
    abs_path = os.path.join(root, rel)
    if not os.path.isfile(abs_path):
        return False, None, False, None
    try:
        size = os.path.getsize(abs_path)
    except OSError:
        return True, None, False, None
    if size > limit:
        return True, size, False, None
    try:
        with open(abs_path, "rb") as fh:
            data = fh.read(limit)
        return True, size, _is_binary(data), data
    except OSError:
        return True, size, False, None


def _no_index_patch(before: bytes | None, after: bytes | None, rel: str) -> str | None:
    d = tempfile.mkdtemp(prefix="flowmanner-ws-diff-")
    try:
        bp = os.path.join(d, "before")
        ap = os.path.join(d, "after")
        if before is not None:
            with open(bp, "wb") as fh:
                fh.write(before)
        if after is not None:
            with open(ap, "wb") as fh:
                fh.write(after)
        args = ["git", "diff", "--no-index", "--no-color", "--unified=3"]
        if before is None:
            args += [os.devnull, ap]
        elif after is None:
            args += [bp, os.devnull]
        else:
            args += [bp, ap]
        try:
            out = subprocess.run(args, capture_output=True, text=True, timeout=10).stdout
        except subprocess.CalledProcessError as exc:
            out = exc.stdout or ""
        if not out:
            return None
        # Normalize header paths.
        return (
            out.replace(f"a/{bp}", f"a/{rel}")
            .replace(f"b/{ap}", f"b/{rel}")
            .replace(f"a/{os.devnull}", f"a/{rel}")
            .replace(f"b/{os.devnull}", f"b/{rel}")
        )
    except Exception:
        return None
    finally:
        import shutil

        shutil.rmtree(d, ignore_errors=True)


def _count_patch(patch: str) -> tuple[int, int]:
    add = del_ = 0
    for line in patch.split("\n"):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            add += 1
        elif line.startswith("-"):
            del_ += 1
    return add, del_


def _filesystem_scan(root: str) -> list[str]:
    started = __import__("time").time()
    paths: list[str] = []
    queue = [("", 0)]
    dirs_scanned = 0
    truncated = False
    while queue:
        rel, depth = queue.pop(0)
        if __import__("time").time() - started > MAX_SCAN_MS or dirs_scanned >= MAX_SCAN_DIRS:
            truncated = True
            break
        if depth >= MAX_SCAN_DEPTH:
            truncated = True
            continue
        dirs_scanned += 1
        abs_dir = os.path.join(root, rel) if rel else root
        try:
            entries = sorted(os.scandir(abs_dir), key=lambda e: e.name)
        except OSError:
            truncated = True
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            child_rel = f"{rel}/{entry.name}" if rel else entry.name
            if entry.is_dir(follow_symlinks=False):
                if entry.name in DEFAULT_IGNORED_DIRS:
                    continue
                queue.append((child_rel, depth + 1))
            elif entry.is_file(follow_symlinks=False) and not _should_skip_file(child_rel):
                paths.append(child_rel)
                if len(paths) >= MAX_TRACKED_STATUS_PATHS:
                    truncated = True
                    break
        if truncated:
            break
    return paths


def diff_workspace(before_root: str, after_root: str, workspace: str) -> WorkspaceDiff:
    """Diff ``workspace`` between two snapshots (paths) of the same repo dir.

    Simpler caller helper: snapshot the workspace, run something, snapshot again,
    then call :func:`compare_snapshots`.
    """
    return compare_snapshots(before_root, after_root, workspace)


def compare_snapshots(before_root: str, after_root: str, workspace: str) -> WorkspaceDiff:
    git_root = _git_root(workspace)
    if git_root:
        return _compare_git(git_root, workspace)
    return _compare_filesystem(before_root, after_root, workspace)


def _compare_git(git_root: str, workspace: str) -> WorkspaceDiff:
    paths, truncated = _git_status_paths(git_root)
    changes: list[FileDiff] = []
    total_add = total_del = 0
    for rel in paths[:MAX_CHANGED_FILES]:
        patch = _git_patch(git_root, rel, deleted=False, added=False)
        if patch is None:
            # try added/deleted variants
            patch = _git_patch(git_root, rel, deleted=False, added=True)
        a, d = _count_patch(patch or "")
        total_add += a
        total_del += d
        changes.append(
            FileDiff(
                path=rel,
                change_type="modified",
                binary=False,
                additions=a,
                deletions=d,
                size_before=None,
                size_after=None,
                patch=patch,
                truncated=False,
            )
        )
    return WorkspaceDiff(
        kind="git",
        root=git_root,
        changes=changes,
        additions=total_add,
        deletions=total_del,
        truncated=truncated or len(paths) > MAX_CHANGED_FILES,
    )


def _compare_filesystem(before_root: str, after_root: str, workspace: str) -> WorkspaceDiff:
    before_paths = set(_filesystem_scan(before_root))
    after_paths = set(_filesystem_scan(after_root))
    # Union of all paths; per-file equality check below decides what really changed
    # (a modified file exists in BOTH scans, so do not pre-filter the intersection).
    rel_paths = before_paths | after_paths
    changes: list[FileDiff] = []
    total_add = total_del = 0
    for rel in list(rel_paths)[:MAX_CHANGED_FILES]:
        before_exists, bsize, bbin, bdata = _read_bytes(before_root, rel, MAX_SNAPSHOT_BYTES)
        after_exists, asize, abin, adata = _read_bytes(after_root, rel, MAX_SNAPSHOT_BYTES)
        if bbin or abin:
            changes.append(FileDiff(rel, "modified", True, 0, 0, bsize, asize, None, False))
            continue
        changed = before_exists != after_exists or bsize != asize or (bdata != adata)
        if not changed:
            continue
        patch = _no_index_patch(bdata, adata, rel)
        a, d = _count_patch(patch or "")
        total_add += a
        total_del += d
        ctype = "added" if not before_exists else ("deleted" if not after_exists else "modified")
        changes.append(FileDiff(rel, ctype, False, a, d, bsize, asize, patch, False))
    return WorkspaceDiff(
        kind="filesystem",
        root=after_root,
        changes=changes,
        additions=total_add,
        deletions=total_del,
        truncated=len(rel_paths) > MAX_CHANGED_FILES,
    )
