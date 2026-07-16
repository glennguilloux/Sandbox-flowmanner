"""skillopt-gate CLI — a validation-gated skill optimizer.

Usage (offline, no key):
    python -m skillopt_gate.cli \
        --skill path/to/SKILL.md \
        --checker demo.checker:score \
        --edits demo/edits.json \
        --stage

The checker is a module:attr callable ``(skill_text) -> (hard, soft)``.
Edits are a JSON list of {"op","content","target"}. Results are
STAGED by default; ``--adopt`` applies the staged candidate
(discovered at <skill>.staged/) without re-running the session.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys

from .optimizer import DeterministicOptimizer
from .runner import run_session
from .staging import adopt


def _load_attr(spec: str):
    module_name, _, attr = spec.partition(":")
    if not attr:
        raise SystemExit(f"--checker must be module:attr, got {spec!r}")
    mod = importlib.import_module(module_name)
    return getattr(mod, attr)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="skillopt-gate")
    p.add_argument("--skill", required=True, help="path to live SKILL.md")
    p.add_argument(
        "--checker", help="module:attr -> (hard, soft); required unless --adopt"
    )
    p.add_argument("--edits", help="JSON file: list of edit dicts")
    p.add_argument("--reasoning", default="", help="attribution for staged edits")
    p.add_argument("--metric", default="hard", choices=["hard", "soft", "mixed"])
    p.add_argument("--mixed-weight", type=float, default=0.5)
    p.add_argument(
        "--stage", action="store_true", help="write proposal to <skill>.staged/"
    )
    p.add_argument(
        "--adopt", action="store_true", help="apply staged candidate to live skill"
    )
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    with open(args.skill, encoding="utf-8") as f:
        current = f.read()

    if args.adopt:
        staged = args.skill + ".staged"
        if not os.path.isdir(staged):
            print(
                f"[skillopt-gate] no staged dir at {staged}; run with --stage first",
                file=sys.stderr,
            )
            return 2
        backup = adopt(staged, args.skill)
        print(f"[skillopt-gate] adopted candidate (backup: {backup})")
        return 0

    if not args.checker:
        print("[skillopt-gate] --checker is required when not --adopt", file=sys.stderr)
        return 2

    checker = _load_attr(args.checker)
    edits = []
    if args.edits:
        with open(args.edits, encoding="utf-8") as f:
            edits = json.load(f)
    opt = DeterministicOptimizer.from_dicts(edits, reasoning=args.reasoning)

    live = args.skill if args.stage else None
    result = run_session(
        current_skill=current,
        optimizer=opt,
        checker=checker,
        live_skill_path=live,
        metric=args.metric,
        mixed_weight=args.mixed_weight,
        verbose=not args.quiet,
    )

    if args.stage and result.staged is not None:
        print(f"[skillopt-gate] staged at {result.staged.staging_dir}")
    elif args.stage:
        print(
            f"[skillopt-gate] action={result.gate.action} — nothing staged "
            f"(candidate did not beat the gate)"
        )
    else:
        print(
            f"[skillopt-gate] action={result.gate.action} "
            f"(no --stage / --adopt; live skill untouched)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
