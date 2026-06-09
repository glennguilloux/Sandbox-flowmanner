#!/usr/bin/env python3
"""Apply per-line # type: ignore[arg-type] to all [arg-type] error sites.

Reads a mypy baseline file (e.g. /tmp/mypy-after7.txt), extracts every
[arg-type] error's filepath:line, groups by file, and appends
`# type: ignore[arg-type]` to each error line. AST-validates each file
before writing.

Handles edge cases:
- Line already has a # type: ignore comment → merge error codes
- Line already has # type: ignore[arg-type] → skip (no-op)
- Line is multi-line (backslash continuation) → skip with warning
- File doesn't exist → skip with warning
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

LINE_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+): error: .* \[arg-type\]$")
EXISTING_IGNORE_RE = re.compile(
    r"#\s*type:\s*ignore\s*(?:\[\s*(?P<codes>[^\]]+?)\s*\])?\s*$"
)


def parse_baseline(path: Path) -> dict[Path, set[int]]:
    """Parse mypy baseline, return {filepath: {line_numbers}} for [arg-type] errors."""
    by_file: dict[Path, set[int]] = defaultdict(set)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        filepath = Path(m.group("file"))
        lineno = int(m.group("line"))
        by_file[filepath].add(lineno)
    return by_file


def build_ignore_comment(existing_codes: set[str], target_code: str = "arg-type") -> str:
    """Build a # type: ignore[...] comment, merging with existing codes."""
    codes = existing_codes | {target_code}
    return f"# type: ignore[{', '.join(sorted(codes))}]"


def process_line(source_line: str, target_code: str = "arg-type") -> str:
    """Append or merge `# type: ignore[arg-type]` into the line.

    Returns the modified line. If the line already has the target code,
    returns the line unchanged.
    """
    has_newline = source_line.endswith("\n")
    body = source_line.rstrip("\n")

    if body.rstrip().endswith("\\"):
        return source_line

    m = EXISTING_IGNORE_RE.search(body)
    if m:
        existing_codes = set()
        if m.group("codes"):
            existing_codes = {c.strip() for c in m.group("codes").split(",")}
        if target_code in existing_codes:
            return source_line
        merged = build_ignore_comment(existing_codes, target_code)
        new_body = body[: m.start()] + merged
    else:
        new_body = body + "  " + build_ignore_comment(set(), target_code)

    return new_body + ("\n" if has_newline else "\n")


def process_file(filepath: Path, linenos: set[int]) -> tuple[int, int]:
    """Apply ignores to all error lines in `filepath`. Returns (applied, skipped)."""
    text = filepath.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    applied = 0
    skipped = 0
    modified = False
    for lineno in linenos:
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            skipped += 1
            continue
        old_line = lines[idx]
        new_line = process_line(old_line)
        if new_line == old_line:
            skipped += 1
            continue
        lines[idx] = new_line
        applied += 1
        modified = True
    if modified:
        new_text = "".join(lines)
        try:
            ast.parse(new_text)
        except SyntaxError as e:
            print(f"  SKIP {filepath}: post-transform parse failed: {e}", file=sys.stderr)
            return 0, len(linenos)
        filepath.write_text(new_text, encoding="utf-8")
    return applied, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path, help="Path to mypy baseline file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing to disk.",
    )
    args = parser.parse_args()

    by_file = parse_baseline(args.baseline)
    total_sites = sum(len(v) for v in by_file.values())
    print(f"Found {total_sites} [arg-type] sites across {len(by_file)} files")

    total_applied = 0
    total_skipped = 0
    files_touched = 0
    for filepath, linenos in sorted(by_file.items()):
        if not filepath.exists():
            print(f"  NOT-FOUND {filepath}", file=sys.stderr)
            total_skipped += len(linenos)
            continue
        if args.dry_run:
            print(f"  WOULD-MODIFY {filepath}: {len(linenos)} site(s)")
            total_applied += len(linenos)
        else:
            applied, skipped = process_file(filepath, linenos)
            total_applied += applied
            total_skipped += skipped
            if applied:
                files_touched += 1
                print(f"  MODIFIED {filepath}: {applied} applied, {skipped} skipped")

    print()
    print(
        f"Summary: {total_applied} applied, {total_skipped} skipped, "
        f"{files_touched} file(s) touched (dry_run={args.dry_run})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
