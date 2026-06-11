#!/usr/bin/env python3
"""Convert logger.X("event", key=val, ...) calls to printf %s style.

Pattern:
  logger.debug("event_name", error=str(e))
  → logger.debug("event_name: error=%s", str(e))

  logger.debug("event", mission_id=mid, exc_info=True)
  → logger.debug("event: mission_id=%s", mid, exc_info=True)

Special kwargs (preserved as kwargs on the logger call):
  - exc_info
  - stack_info
  - stacklevel
  - extra

Non-special kwargs (moved into the format string + positional args):
  - everything else; rendered as `key=%s` and added to args in order

Idempotent: re-running on an already-converted file is a no-op.
Use --dry-run to preview without writing.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Standard logging.Logger kwargs that are part of the API and must be preserved.
SPECIAL_KWARGS = frozenset({"exc_info", "stack_info", "stacklevel", "extra"})

# Logger methods this converter targets.
LOGGER_METHODS = frozenset(
    {"debug", "info", "warning", "error", "exception", "critical", "fatal", "warn"}
)


def _is_logger_attr(node: ast.expr) -> bool:
    """True if `node` looks like a logger reference: `logger`, `self.logger`, etc."""
    if isinstance(node, ast.Name):
        return (
            node.id.lower().endswith("logger")
            or node.id == "logger"
            or node.id == "_logger"
        )
    if isinstance(node, ast.Attribute):
        return node.attr.lower().endswith("logger") or node.attr in {
            "logger",
            "_logger",
        }
    return False


def _is_logger_call(call: ast.Call) -> bool:
    """True if `call` is a logger.X(...) invocation."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr not in LOGGER_METHODS:
        return False
    return _is_logger_attr(func.value)


def _literal_repr(value: ast.expr) -> str | None:
    """Render a simple string/format-spec to a format string fragment.

    Returns None for unsupported forms.
    """
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        # Escape literal % so printf formatting doesn't trip on user strings.
        return value.value.replace("%", "%%")
    return None


def _convert_format_string(template: str) -> str:
    """If template already contains printf specifiers, append our key=value pairs after a colon.
    Otherwise, replace the trailing segment of the template.
    """
    return template


def _convert_call(call: ast.Call) -> ast.Call | None:
    """Transform a single logger.X(...) call. Returns the new Call node, or None if not transformable.

    Pre-conditions:
      - call is a logger call (caller checks)
      - call has at least 2 positional args (the format string + the first non-kwarg arg),
        OR the format string is the only positional arg and we have kwargs to convert.
    """
    if not call.args:
        return None

    fmt_arg = call.args[0]
    if not isinstance(fmt_arg, ast.Constant) or not isinstance(fmt_arg.value, str):
        return None

    # Filter out already-known special kwargs; we keep those as kwargs.
    if not call.keywords:
        return None  # nothing to do — no kwargs to convert

    # Split keywords into special (keep) and convert (move into format).
    keep_kwargs: list[ast.keyword] = []
    convert_kwargs: list[ast.keyword] = []

    for kw in call.keywords:
        if kw.arg in SPECIAL_KWARGS:
            keep_kwargs.append(kw)
        else:
            if kw.arg is None:
                # **kwargs spread — bail; can't safely rewrite.
                return None
            convert_kwargs.append(kw)

    if not convert_kwargs:
        return None  # all kwargs are already special — nothing to convert

    # Build the new format string: append ` key=%s` for each converted kwarg.
    parts: list[str] = []
    for kw in convert_kwargs:
        parts.append(f" {kw.arg}=%s")
    new_fmt = fmt_arg.value + "".join(parts)

    # Build the new positional args: keep original args[1:] (excluding the format string),
    # then add the value of each converted kwarg.
    new_args: list[ast.expr] = list(call.args[1:])  # original positional args (if any)
    for kw in convert_kwargs:
        new_args.append(kw.value)

    # Reconstruct the call.
    new_call = ast.Call(
        func=call.func,
        args=[ast.Constant(value=new_fmt)] + new_args,
        keywords=keep_kwargs,
    )
    # Copy source location hints.
    ast.copy_location(new_call, call)
    ast.copy_location(new_call.func, call.func)  # type: ignore[attr-defined]
    return new_call


def _replace_call(src: str, call: ast.Call, new_call: ast.Call) -> str:
    """Splice `new_call` into `src` at the original `call`'s location.

    Handles single-line and multi-line calls.
    """
    lines = src.splitlines(keepends=True)
    start = call.lineno - 1
    end = call.end_lineno - 1
    if end < start:
        return src

    # Find the indentation of the first line so we can indent continuation lines.
    first_line = lines[start]
    indent = first_line[: len(first_line) - len(first_line.lstrip())]
    # ast.unparse gives us a single-line representation; we re-indent multi-line output.
    new_src = ast.unparse(new_call)
    new_lines = new_src.splitlines()
    if not new_lines:
        return src
    # BUGFIX: the first line of the new call also needs the indent prefix.
    # The original logic only added indent to continuation lines, which produced
    # "except: \n  logger.debug(...)" with the call at the except's indent level
    # instead of the except body's indent level. Fix: prepend `indent` to the
    # first line as well.
    indented = [indent + new_lines[0]]
    for line in new_lines[1:]:
        indented.append((indent + "    ") + line if line else line)

    # Check for trailing content on the call's last source line (e.g. comment, follow-on stmt).
    last_line = lines[end]
    # end_col_offset is 0-indexed; the call ends at that column on the last line.
    trailing = last_line[call.end_col_offset :]
    # If trailing content is just whitespace + newline, drop it; otherwise keep it on a new line.
    if trailing.strip():
        # Promote trailing content to a new line with the call's indent.
        trailing_stripped = trailing.lstrip()
        indented.append(indent + trailing_stripped)

    lines[start : end + 1] = [line + "\n" for line in indented]
    return "".join(lines)


def transform_source(src: str) -> tuple[str, int, int]:
    """Run the converter over `src`. Returns (new_src, converted_count, skipped_count)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src, 0, 0  # leave broken files alone

    # Walk and collect (call, new_call) pairs, then apply bottom-up so line numbers
    # don't shift as we splice.
    pairs: list[tuple[ast.Call, ast.Call]] = []
    skipped = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_logger_call(node):
            continue
        new_node = _convert_call(node)
        if new_node is None:
            skipped += 1
            continue
        pairs.append((node, new_node))

    if not pairs:
        return src, 0, skipped

    # Sort by lineno descending so splicing doesn't invalidate later indices.
    pairs.sort(key=lambda p: p[0].lineno, reverse=True)
    new_src = src
    for old, new in pairs:
        new_src = _replace_call(new_src, old, new)
    return new_src, len(pairs), skipped


def process_path(path: Path, dry_run: bool) -> tuple[int, int, int]:
    """Process a single file. Returns (converted, skipped, files_touched)."""
    try:
        src = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        print(f"  SKIP {path}: {e}", file=sys.stderr)
        return 0, 0, 0
    new_src, converted, skipped = transform_source(src)
    if converted == 0:
        return 0, skipped, 0
    if dry_run:
        for old, new in [(None, None)] * converted:  # placeholder
            pass
        print(f"  WOULD-CONVERT {converted} site(s) in {path}")
    else:
        try:
            ast.parse(new_src)  # safety net
        except SyntaxError as e:
            print(f"  SKIP {path}: post-transform parse failed: {e}", file=sys.stderr)
            return 0, 0, 0
        path.write_text(new_src, encoding="utf-8")
        print(f"  CONVERTED {converted} site(s) in {path}")
    return converted, skipped, 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Files or directories to process.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without writing to disk.",
    )
    args = parser.parse_args()

    targets: list[Path] = []
    for p in args.paths:
        path = Path(p)
        if path.is_dir():
            targets.extend(sorted(path.rglob("*.py")))
        elif path.is_file():
            targets.append(path)
        else:
            print(f"  NOT-FOUND {p}", file=sys.stderr)

    total_converted = 0
    total_skipped = 0
    files_touched = 0
    for path in targets:
        c, s, t = process_path(path, args.dry_run)
        total_converted += c
        total_skipped += s
        files_touched += t

    print()
    print(
        f"Summary: {total_converted} converted, {total_skipped} skipped, "
        f"{files_touched} file(s) touched (dry_run={args.dry_run})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
