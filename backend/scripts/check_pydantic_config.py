#!/usr/bin/env python3
"""Pre-commit hook: reject deprecated Pydantic ``class Config:`` pattern.

Pydantic V2 requires ``model_config = ConfigDict(...)`` instead.
Only checks ``app/**/*.py`` files (skips tests, migrations, etc.).

Usage (called by pre-commit, receives staged files as argv):
    python scripts/check_pydantic_config.py app/schemas/foo.py app/models/bar.py
"""

import re
import sys

PATTERN = re.compile(r"^\s+class Config:")


def main() -> int:
    errors: list[str] = []
    for path in sys.argv[1:]:
        if not path.startswith("app/"):
            continue
        with open(path) as f:
            for lineno, line in enumerate(f, start=1):
                if PATTERN.match(line):
                    errors.append(f"  {path}:{lineno}: {line.rstrip()}")

    if errors:
        print("ERROR: Deprecated Pydantic 'class Config:' found.")
        print("       Use 'model_config = ConfigDict(...)' instead (Pydantic V2).\n")
        for e in errors:
            print(e)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
