#!/usr/bin/env python3
"""Map changed files (from git diff) to pytest sanity markers.

Usage:
    git diff --name-only origin/main...HEAD | python scripts/select-sanity.py

Outputs a marker expression suitable for: pytest -m "<expr>"
If no paths match, outputs nothing and exits 0.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable


PATH_MARKERS: dict[str, str] = {
    "backend/app/api/v1/auth": "sanity_auth",
    "backend/app/services/chat": "sanity_chat",
    "backend/app/services/mission": "sanity_missions",
    "backend/app/api/v1/byok": "sanity_byok",
    "backend/app/websocket": "sanity_websocket",
}

FRONTEND_PLAYWRIGHT: dict[str, str] = {
    "frontend/src/app/dashboard": "@sanity_dashboard",
}


def _matching_prefix(path: str, prefixes: Iterable[str]) -> str | None:
    normalized = path.removeprefix("./").lstrip("/")
    for prefix in prefixes:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return prefix
    return None


def main() -> int:
    markers: set[str] = set()
    frontend_tags: set[str] = set()

    for raw_path in sys.stdin:
        path = raw_path.strip()
        if not path:
            continue

        marker_prefix = _matching_prefix(path, PATH_MARKERS)
        if marker_prefix is not None:
            markers.add(PATH_MARKERS[marker_prefix])
            continue

        frontend_prefix = _matching_prefix(path, FRONTEND_PLAYWRIGHT)
        if frontend_prefix is not None:
            frontend_tags.add(FRONTEND_PLAYWRIGHT[frontend_prefix])

    if frontend_tags:
        tags = ", ".join(sorted(frontend_tags))
        print(
            f"Frontend dashboard changed; run Playwright sanity with: --grep {tags}",
            file=sys.stderr,
        )

    if markers:
        print(" or ".join(sorted(markers)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
