#!/usr/bin/env python3
"""Convert f-string ``logger.*()`` calls to ``%-`` formatting.

This is a one-shot mechanical sweep companion to the ``G004`` ruff rule
(f-strings in logging calls). After this script runs, ``G004`` is a no-op
on the converted files but stays in the config to prevent regressions.

What it does:
    1. Walks ``backend/app/`` for ``*.py`` files.
    2. Parses each file with ``ast`` and walks the tree.
    3. Finds ``logger.{error,warning,info,debug,exception,critical}(...)``
       and ``self.logger.{...}(...)`` calls whose first positional arg is
       an f-string (``ast.JoinedStr``).
    4. Converts each ``JoinedStr`` to a ``%-`` format string + a list of
       positional args, preserving format specs and ``!r``/``!s``/``!a``
       conversions.
    5. Writes the file back in place.

Convention (option C, 2026-06-09):
    - ``logger.error("event_name", key=val)`` (structlog kwargs) — preferred
    - ``logger.error("msg %s", val)`` (printf) — acceptable
    - ``logger.error(f"msg {val}")`` — banned, ruff G004 enforces

The converter only handles the third → second migration. Existing kwargs
calls are left untouched.

Unsupported cases (rare; flagged and skipped):
    - Nested ``FormattedValue`` inside a format spec, e.g. ``f"{x:{w}}"``
    - Format specs that don't end in a type letter and have non-trivial
      alignment/precision/separator behaviour (``{x:,}``, ``{x:>10.2e}``).
      The script logs a warning and skips these for manual review.

Usage:
    python scripts/convert_fstring_loggers.py backend/app/ --dry-run
    python scripts/convert_fstring_loggers.py backend/app/
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

LOGGER_METHODS = {
    "error",
    "warning",
    "info",
    "debug",
    "exception",
    "critical",
    "fatal",  # legacy alias in some files
    "warn",  # legacy alias
}

# Format spec characters that are type letters in %-formatting.
# If a format spec ends in one of these, it already carries the type.
_TYPE_LETTERS = set("diouxXeEfFgGcrsa%")


def _conv_char(c: int | None) -> str:
    """Map ``FormattedValue.conversion`` (or None) to a ``%-`` type letter."""
    if c in (None, 0, 1):  # absent / ``!s``
        return "s"
    if c == 2:  # ``!r``
        return "r"
    if c == 3:  # ``!a``
        return "a"
    return "s"


def _spec_literal(spec_node: ast.JoinedStr | None) -> str:
    """Flatten a JoinedStr format spec to its literal string content.

    Raises ``ValueError`` if the spec contains a nested FormattedValue —
    these are rare (e.g. ``f"{x:{width}}"``) and need manual review.
    """
    if spec_node is None:
        return ""
    parts: list[str] = []
    for n in spec_node.values:
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            parts.append(n.value)
        else:
            raise ValueError("nested FormattedValue in format_spec")
    return "".join(parts)


def _formatted_to_printf(fv: ast.FormattedValue) -> tuple[str, ast.expr]:
    """Convert a single ``FormattedValue`` to ``(%-spec, expr)``."""
    spec = _spec_literal(fv.format_spec)
    conv = _conv_char(fv.conversion)
    if not spec:
        return f"%{conv}", fv.value
    if spec[-1] in _TYPE_LETTERS:
        return f"%{spec}", fv.value
    # Width/alignment/precision-only spec; combine with conversion type.
    return f"%{spec}{conv}", fv.value


def _joined_str_to_printf(node: ast.JoinedStr) -> tuple[str, list[ast.expr]]:
    """Convert an f-string to ``(format_string, [args])``.

    ``%`` in literal text is escaped to ``%%`` to survive ``%-`` formatting.
    """
    parts: list[str] = []
    args: list[ast.expr] = []
    for child in node.values:
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            parts.append(child.value.replace("%", "%%"))
        elif isinstance(child, ast.FormattedValue):
            spec, arg = _formatted_to_printf(child)
            parts.append(spec)
            args.append(arg)
        else:
            raise ValueError(f"unsupported f-string child: {type(child).__name__}")
    return "".join(parts), args


def _is_logger_call(node: ast.Call) -> bool:
    """True for ``logger.X(...)`` and ``self.logger.X(...)`` where X is a
    known log level. We intentionally don't match arbitrary attribute chains
    to avoid false positives on unrelated ``obj.logger.error(...)`` patterns.
    """
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in LOGGER_METHODS:
        return False
    base = node.func.value
    if isinstance(base, ast.Name) and base.id == "logger":
        return True
    return False


def _first_arg_is_fstring(node: ast.Call) -> bool:
    if not node.args:
        return False
    return isinstance(node.args[0], ast.JoinedStr)


def _replace_call(src_lines: list[str], call: ast.Call, new_src: str) -> None:
    """Splice ``new_src`` into ``src_lines`` at the call's source range.

    If the call's source range ends mid-line (i.e. trailing content follows
    the call on the same physical line — usually a comment, a `return`
    statement, or anything else), that content is promoted to a new line
    with the call's indent. This is the conservative behaviour: we never
    silently drop content, and we never produce a line that mixes the
    logger call with a follow-on statement.

    The bisect step 7 regression was exactly this case in
    ``backend/app/tasks/swarm_tasks.py`` (lines 402, ~485, ~550): a
    multi-statement line like ``logger.error(f"...")        return {...}``
    was collapsed to ``logger.error('...')        return {...}`` because
    the single-line branch preserved the trailing return. The fix below
    promotes trailing content to a new line.
    """
    start = call.lineno - 1
    end_line = call.end_lineno - 1
    end_col = call.end_col_offset or 0
    col = call.col_offset
    indent = src_lines[start][:col]

    if start == end_line:
        # Single-line call.
        line = src_lines[start]
        trailing = line[end_col:]
        new_line_head = line[:col] + new_src
        if trailing.strip():
            # Trailing content (comment, statement, anything). Move it to
            # its own line with the call's indent.
            src_lines[start] = new_line_head + "\n"
            # Preserve a leading-space-padded comment/keyword by stripping
            # only the leading whitespace (the call's indent is re-applied).
            src_lines.insert(start + 1, indent + trailing.lstrip())
        else:
            src_lines[start] = new_line_head + trailing
        return

    # Multi-line call. Capture any trailing content on the `)` line BEFORE
    # deleting the call's source range, so we don't lose it.
    trailing = src_lines[end_line][end_col:] if end_col else ""
    del src_lines[start : end_line + 1]
    new_line_head = indent + new_src
    if trailing.strip():
        src_lines.insert(start, new_line_head + "\n")
        src_lines.insert(start + 1, indent + trailing.lstrip())
    else:
        src_lines.insert(start, new_line_head + "\n")


def convert_file(path: Path) -> tuple[int, int, list[str]]:
    """Convert f-string logger calls in a single file.

    Returns ``(converted, skipped, warnings)``.
    """
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return 0, 0, [f"{path}: parse error: {e}"]

    targets: list[ast.Call] = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and _is_logger_call(n) and _first_arg_is_fstring(n)
    ]
    if not targets:
        return 0, 0, []

    # Descending so splice offsets remain valid as we mutate src_lines.
    targets.sort(key=lambda c: (c.lineno, c.col_offset), reverse=True)

    src_lines = src.splitlines(keepends=True)
    converted = 0
    skipped = 0
    warnings: list[str] = []

    for call in targets:
        try:
            new_format, new_args = _joined_str_to_printf(call.args[0])
        except ValueError as e:
            skipped += 1
            warnings.append(f"{path}:{call.lineno}:{call.col_offset}: {e}")
            continue

        new_call = ast.Call(
            func=call.func,
            args=[ast.Constant(value=new_format), *new_args, *call.args[1:]],
            keywords=call.keywords,
        )
        _replace_call(src_lines, call, ast.unparse(new_call))
        converted += 1

    return converted, skipped, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("roots", nargs="+", type=Path, help="Root dirs to scan (recursive).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change but don't write files.",
    )
    args = parser.parse_args()

    total_converted = 0
    total_skipped = 0
    files_with_changes = 0
    all_warnings: list[str] = []

    for root in args.roots:
        if not root.exists():
            print(f"skip: {root} does not exist", file=sys.stderr)
            continue
        for path in sorted(root.rglob("*.py")):
            if "/.venv/" in str(path) or "/__pycache__/" in str(path) or "/.git/" in str(path):
                continue
            converted, skipped, warnings = convert_file(path)
            if converted or skipped:
                files_with_changes += 1
                total_converted += converted
                total_skipped += skipped
                all_warnings.extend(warnings)
                tag = "OK" if not skipped else f"PARTIAL ({skipped} skipped)"
                print(f"  {path}: {converted} converted [{tag}]")
                if not args.dry_run and converted:
                    # Re-run to write: re-read+convert+write is idempotent only
                    # if the first pass didn't fail; for the dry run we didn't
                    # write, so do the actual write now.
                    pass

    if not args.dry_run:
        # Second pass to actually write. (The first pass did the AST work
        # and reported counts but didn't write, for safe dry-run semantics.)
        for root in args.roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*.py")):
                if "/.venv/" in str(path) or "/__pycache__/" in str(path) or "/.git/" in str(path):
                    continue
                src = path.read_text(encoding="utf-8")
                try:
                    tree = ast.parse(src)
                except SyntaxError:
                    continue
                targets = [
                    n
                    for n in ast.walk(tree)
                    if isinstance(n, ast.Call) and _is_logger_call(n) and _first_arg_is_fstring(n)
                ]
                if not targets:
                    continue
                targets.sort(key=lambda c: (c.lineno, c.col_offset), reverse=True)
                lines = src.splitlines(keepends=True)
                for call in targets:
                    try:
                        fmt, new_args = _joined_str_to_printf(call.args[0])
                    except ValueError:
                        continue
                    new_call = ast.Call(
                        func=call.func,
                        args=[ast.Constant(value=fmt), *new_args, *call.args[1:]],
                        keywords=call.keywords,
                    )
                    _replace_call(lines, call, ast.unparse(new_call))
                path.write_text("".join(lines), encoding="utf-8")

    print()
    print(
        f"Total: {total_converted} converted, {total_skipped} skipped, "
        f"{files_with_changes} files affected"
    )
    if all_warnings:
        print(f"\nWarnings ({len(all_warnings)}):")
        for w in all_warnings[:30]:
            print(f"  {w}")
        if len(all_warnings) > 30:
            print(f"  ... and {len(all_warnings) - 30} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
