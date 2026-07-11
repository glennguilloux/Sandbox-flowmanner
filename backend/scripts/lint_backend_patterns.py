#!/usr/bin/env python3
"""Backend convention linter — flag bare ``raise Exception`` in ``app/services``.

WHY
---
The mission/cqrs path raises the typed ``MissionError`` hierarchy
(``app/services/mission_errors.py``) so the retryable-vs-permanent signal can
drive circuit-breakers and ReplayEngine recovery.  Outside that path ~333
service files still ``raise Exception`` (25 bare sites confirmed 2026-07-11),
silently discarding that signal.  This gate flags the narrow, unambiguous
anti-pattern — a *bare* ``raise Exception`` (the base class, not a subclass) —
inside ``app/services/*.py``.

WHAT IS FLAGGED
---------------
- ``raise Exception`` / ``raise Exception(...)`` (the literal builtin base
  class) in any ``app/services/**`` module.

WHAT IS ALLOWED (never flagged)
-------------------------------
- Raising a ``MissionError`` subclass (or any other custom exception class —
  we only target the base ``Exception`` literal).
- Raising built-in ``ValueError`` / ``TypeError`` / ``KeyError`` for local
  input validation (common and acceptable).
- Any line in a test file (``tests/``, ``test_*.py``, ``*_test.py``,
  ``conftest.py``).
- Any file *outside* ``app/services/`` (out of scope — this gate owns the
  services layer only).

USAGE
-----
    python scripts/lint_backend_patterns.py <file|dir> [<file|dir> ...]

Exit code is 0 when no bare ``raise Exception`` sites are found, non-zero
otherwise.  Multiple paths aggregate; directories are walked for ``*.py``.

This module is stdlib-only on purpose so it runs (and is unit-testable)
without the full backend dependency tree.
"""

from __future__ import annotations

import argparse
import os
import sys
import tokenize
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

# Bare base-class literal we refuse to allow in services.
BARE_EXCEPTION = "Exception"

# Fragments marking a path as a test file -> always allowed.
_TEST_DIR_FRAGMENT = "/tests/"
_TEST_NAME_MARKERS = ("test_",)
_TEST_NAME_SUFFIXES = ("_test.py",)
_TEST_EXACT_NAMES = {"conftest.py"}

# Scope: only modules under this subtree are checked.
_SERVICES_FRAGMENT = "app/services/"


def _is_test_file(path: str) -> bool:
    """True if *path* is a test file and therefore exempt from the gate."""
    base = os.path.basename(path)
    if base in _TEST_EXACT_NAMES:
        return True
    if base.endswith(_TEST_NAME_SUFFIXES):
        return True
    if any(base.startswith(marker) for marker in _TEST_NAME_MARKERS):
        return True
    return _TEST_DIR_FRAGMENT in path.replace(os.sep, "/")


def _in_services(path: str) -> bool:
    """True if *path* lives under the services layer (in scope)."""
    return _SERVICES_FRAGMENT in path.replace(os.sep, "/")


def find_bare_exception_lines(path: str) -> list[int]:
    """Return 1-based line numbers of ``raise Exception`` statements in *path*.

    Robust to comments and string contents because it parses with
    :mod:`tokenize` rather than regex-matching raw text.  Returns ``[]`` for
    test files or for files outside ``app/services/`` (both out of scope).
    """
    normalized = path.replace(os.sep, "/")
    if _is_test_file(normalized):
        return []
    if not _in_services(normalized):
        return []

    try:
        with open(path, "rb") as fh:
            tokens = list(tokenize.tokenize(fh.readline))
    except (OSError, tokenize.TokenError, IndentationError, SyntaxError):
        # Unreadable / unparseable file: cannot flag, report nothing so we
        # never block a gate on a transient read error.
        return []

    flagged: list[int] = []
    skip = {
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
    n = len(tokens)
    i = 0
    while i < n:
        tok = tokens[i]
        if tok.type == tokenize.NAME and tok.string == "raise":
            j = i + 1
            while j < n and tokens[j].type in skip:
                j += 1
            if j < n and tokens[j].type == tokenize.NAME and tokens[j].string == BARE_EXCEPTION:
                flagged.append(tok.start[0])
        i += 1
    return flagged


def _iter_py_files(paths: Iterable[str]) -> list[str]:
    """Expand directories to ``*.py`` files, preserving order."""
    out: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(
                os.path.join(root, name)
                for root, _dirs, files in os.walk(p)
                for name in sorted(files)
                if name.endswith(".py")
            )
        else:
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Flag bare `raise Exception` in app/services (MissionError hierarchy)."
    )
    parser.add_argument("paths", nargs="+", help="file or directory to scan")
    args = parser.parse_args(argv)

    findings: dict[str, list[int]] = {}
    for path in _iter_py_files(args.paths):
        lines = find_bare_exception_lines(path)
        if lines:
            findings[path] = lines

    if not findings:
        print("ok: no bare `raise Exception` sites in app/services/")
        return 0

    total = 0
    for path, lines in sorted(findings.items()):
        for ln in lines:
            total += 1
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    src = fh.read().splitlines()[ln - 1] if ln > 0 else ""
            except OSError:
                src = ""
            print(f"FLAG: {path}:{ln}: {src.strip()}")
    print(
        f"error: {total} bare `raise Exception` site(s) found in app/services/ — raise a MissionError subclass instead",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
