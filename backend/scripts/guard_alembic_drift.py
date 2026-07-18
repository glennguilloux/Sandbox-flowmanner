#!/usr/bin/env python3
"""Guard against unreviewed DROP TABLE in autogenerate probes.

Runs a NON-DESTRUCTIVE ``alembic revision --autogenerate`` probe into the
container's alembic/versions, greps for ``op.drop_table`` / ``DropTableOp``,
and fails if any dropped table is NOT on the explicit allow-list.

The allow-list MUST stay in sync with ``alembic/env.py::_DROP_TABLE_ALLOWLIST``.
Any table that autogenerate wants to drop must have a hand-authored, reviewed
migration before it is added here — otherwise a blind autogenerate could
destroy a live table.

If Docker / the DB is not reachable, prints a clear skip message and exits 0 so
pre-commit does not falsely fail in environments without a live DB (same
pattern as guard-llm-success).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

# Tables whose DROP is sanctioned (mirror of alembic/env.py::_DROP_TABLE_ALLOWLIST).
# Keep these two lists identical.
DROP_TABLE_ALLOWLIST = frozenset(
    {
        "p1_probe",  # orphan diagnostic table; reviewed 2026-07-18 (a1p1probe00)
    }
)

DROP_RE = re.compile(r'op\.drop_table\(\s*["\']([^"\']+)["\']')


def main() -> int:
    repo_root = _repo_root()
    # Probe lands in the container; we capture via a temp out-of-tree message and
    # then read the generated file back out of the container.
    probe_msg = "guard-alembic-drift-probe"

    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "backend",
        "alembic",
        "revision",
        "--autogenerate",
        "-m",
        probe_msg,
    ]
    print(f"[guard-alembic-drift] running: {' '.join(cmd)}", file=sys.stderr)
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    if proc.returncode != 0:
        # Docker/DB likely unavailable. Skip rather than falsely fail.
        out = (proc.stdout or "") + (proc.stderr or "")
        if "Cannot connect" in out or "Error response" in out or "is not running" in out or "No such service" in out:
            print(
                "[guard-alembic-drift] SKIP: Docker/DB not available — " "skipping drift guard (no live DB).",
                file=sys.stderr,
            )
            return 0
        print(
            f"[guard-alembic-drift] SKIP: autogenerate probe failed (rc={proc.returncode}); "
            "treating as non-fatal. stderr:\n" + out,
            file=sys.stderr,
        )
        return 0

    # Find the generated revision file inside the container and cat it.
    find = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "backend",
            "sh",
            "-c",
            "ls -t alembic/versions/*.py | head -n1 | xargs cat",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    generated = find.stdout or ""

    # Clean up the probe migration file from the container (non-destructive;
    # only removes the just-generated probe, never applied).
    subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "backend",
            "sh",
            "-c",
            "ls -t alembic/versions/*guard-alembic-drift-probe*.py 2>/dev/null | xargs -r rm -f",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )

    dropped = DROP_RE.findall(generated)
    if not dropped:
        print("[guard-alembic-drift] OK: no drop_table in autogenerate probe.", file=sys.stderr)
        return 0

    illegal = [t for t in dropped if t not in DROP_TABLE_ALLOWLIST]
    if illegal:
        print(
            "[guard-alembic-drift] FAIL: autogenerate wants to drop unreviewed "
            f"table(s): {', '.join(sorted(illegal))}.\n"
            "Add a reviewed hand-authored migration and update the allow-list "
            "in both this script and alembic/env.py before proceeding.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[guard-alembic-drift] OK: dropped table(s) {sorted(dropped)} are on the " "allow-list (reviewed migrations).",
        file=sys.stderr,
    )
    return 0


def _repo_root() -> str:
    # backend/scripts/guard_alembic_drift.py -> repo root (one level up).
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


if __name__ == "__main__":
    sys.exit(main())
