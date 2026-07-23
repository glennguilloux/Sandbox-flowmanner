#!/usr/bin/env python3
"""Regression watchdog for Flowmanner substrate runs.

Two modes:

* Extract a baseline from a known-good run::

    python -m scripts.regression_watchdog --extract <run_id>

  Saves ``expected_behaviors`` plus raw metrics to ``/tmp/baseline-<run_id>.json``.

* Assert a new run against that baseline::

    python -m scripts.regression_watchdog --check <run_id> --baseline <path>

  Uses ``ReplayAssertionEngine`` to evaluate the baseline behaviors, then
  checks for drift: cost > 1.5× baseline or latency > 2× baseline. On drift,
  POSTs a JSON alert to ``REGRESSION_WEBHOOK_URL`` (or prints to stderr if
  the env var is empty). Use ``--dry-run`` to suppress the webhook.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

import httpx

from app.database import AsyncSessionLocal
from app.services.substrate.assertion_engine import ReplayAssertionEngine, get_assertion_engine
from app.services.substrate.baseline_extractor import BaselineExtractor, get_baseline_extractor


#: Default headrooms used when extracting a baseline.
DEFAULT_COST_HEADROOM = 1.15
DEFAULT_LATENCY_HEADROOM = 1.5


def _build_arg_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="regression_watchdog",
        description="Extract a baseline from a known-good run and assert new runs stay within bounds.",
    )
    parser.add_argument(
        "--extract",
        dest="extract_run_id",
        metavar="RUN_ID",
        help="Extract baseline behaviors from this known-good run id.",
    )
    parser.add_argument(
        "--check",
        dest="check_run_id",
        metavar="RUN_ID",
        help="Assert this new run id against a saved baseline.",
    )
    parser.add_argument(
        "--baseline",
        dest="baseline_path",
        help="Path to the saved baseline JSON (required with --check).",
    )
    parser.add_argument(
        "--headroom-cost",
        type=float,
        default=DEFAULT_COST_HEADROOM,
        help=f"Cost headroom applied on extraction (default: {DEFAULT_COST_HEADROOM}).",
    )
    parser.add_argument(
        "--headroom-latency",
        type=float,
        default=DEFAULT_LATENCY_HEADROOM,
        help=f"Latency headroom applied on extraction (default: {DEFAULT_LATENCY_HEADROOM}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform the check but never send the webhook alert.",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    """Validate parsed CLI arguments and raise on conflicts."""
    if args.extract_run_id and args.check_run_id:
        raise argparse.ArgumentError(
            None,
            "--extract and --check are mutually exclusive.",
        )
    if not args.extract_run_id and not args.check_run_id:
        raise argparse.ArgumentError(
            None,
            "Specify either --extract <run_id> or --check <run_id>.",
        )
    if args.check_run_id and not args.baseline_path:
        raise argparse.ArgumentError(
            None,
            "--baseline <path> is required with --check.",
        )


async def _extract_baseline(
    run_id: str,
    cost_headroom: float,
    latency_headroom: float,
    *,
    _db: Any | None = None,
    _extractor: BaselineExtractor | None = None,
) -> dict[str, Any]:
    """Extract expected behaviors from a known-good run.

    Returns a dict with ``expected_behaviors`` and a ``meta`` section that
    stores the raw baseline metrics so the watchdog can compare against the
    actual run later (1.5× cost / 2× latency thresholds).

    Args:
        _db: Optional injected async DB session. When absent, ``AsyncSessionLocal``
            is used (production path).
        _extractor: Optional injected ``BaselineExtractor``. Defaults to the
            singleton from ``get_baseline_extractor``.
    """
    extractor = _extractor if _extractor is not None else get_baseline_extractor()
    if _db is not None:
        behaviors = await extractor.extract_from_run(
            _db,
            run_id,
            cost_headroom=cost_headroom,
            latency_headroom=latency_headroom,
        )
    else:
        async with AsyncSessionLocal() as db:
            behaviors = await extractor.extract_from_run(
                db,
                run_id,
                cost_headroom=cost_headroom,
                latency_headroom=latency_headroom,
            )

    cost_baseline = None
    latency_baseline = None

    for behavior in behaviors:
        if behavior.get("type") == "cost_ceiling":
            cost_baseline = behavior.get("max_cost_usd")
        elif behavior.get("type") == "latency":
            latency_baseline = behavior.get("max_duration_seconds")

    raw_cost = None
    if cost_baseline is not None and cost_headroom:
        raw_cost = round(cost_baseline / cost_headroom, 6)

    raw_latency = None
    if latency_baseline is not None and latency_headroom:
        raw_latency = round(latency_baseline / latency_headroom, 3)

    return {
        "expected_behaviors": behaviors,
        "meta": {
            "run_id": run_id,
            "extracted_at": datetime.now(UTC).isoformat(),
            "cost_headroom": cost_headroom,
            "latency_headroom": latency_headroom,
            "raw_cost_usd": raw_cost,
            "raw_duration_seconds": raw_latency,
        },
    }


def _save_baseline(run_id: str, baseline_doc: dict[str, Any]) -> str:
    """Persist the baseline document and return the file path."""
    path = f"/tmp/baseline-{run_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline_doc, f, indent=2, default=str)
    return path


async def _check_run(
    run_id: str,
    baseline_path: str,
    *,
    _db: Any | None = None,
    _engine: ReplayAssertionEngine | None = None,
) -> dict[str, Any]:
    """Assert a new run against the saved baseline and compute drift metrics.

    Args:
        _db: Optional injected async DB session. When absent, ``AsyncSessionLocal``
            is used (production path).
        _engine: Optional injected ``ReplayAssertionEngine``. Defaults to the
            singleton from ``get_assertion_engine``.
    """
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline_doc = json.load(f)

    expected_behaviors: list[dict[str, Any]] = baseline_doc.get(
        "expected_behaviors", baseline_doc if isinstance(baseline_doc, list) else []
    )
    meta: dict[str, Any] = baseline_doc.get("meta", {})

    engine = _engine if _engine is not None else get_assertion_engine()

    if _db is not None:
        results = await engine.evaluate(_db, run_id, expected_behaviors)
    else:
        async with AsyncSessionLocal() as db:
            results = await engine.evaluate(db, run_id, expected_behaviors)

    summary = [r.to_dict() for r in results]

    # Pull actual cost/latency from assertion results.
    cost_result = next((r for r in results if r.assertion_type == "cost_ceiling"), None)
    latency_result = next((r for r in results if r.assertion_type == "latency"), None)

    actual_cost = cost_result.actual.get("cost_usd") if cost_result else None
    actual_latency = latency_result.actual.get("duration_seconds") if latency_result else None

    # Baseline thresholds from stored raw metrics (preferred) or from the
    # expected-behavior ceilings (fallback). The fallback uses the headroom-
    # inflated ceilings directly, so it is slightly more lenient than the
    # raw-metric comparison but still deterministic.
    baseline_cost = meta.get("raw_cost_usd")
    baseline_latency = meta.get("raw_duration_seconds")

    if baseline_cost is None:
        for behavior in expected_behaviors:
            if behavior.get("type") == "cost_ceiling":
                baseline_cost = behavior.get("max_cost_usd")
                break
    if baseline_latency is None:
        for behavior in expected_behaviors:
            if behavior.get("type") == "latency":
                baseline_latency = behavior.get("max_duration_seconds")
                break

    cost_drift = False
    latency_drift = False
    if baseline_cost is not None and actual_cost is not None:
        cost_drift = float(actual_cost) > float(baseline_cost) * 1.5
    if baseline_latency is not None and actual_latency is not None:
        latency_drift = float(actual_latency) > float(baseline_latency) * 2.0

    assertion_failures = [r for r in results if not r.passed]
    drift = bool(cost_drift or latency_drift or assertion_failures)

    return {
        "run_id": run_id,
        "baseline_path": baseline_path,
        "drift": drift,
        "cost_drift": cost_drift,
        "latency_drift": latency_drift,
        "actual_cost": actual_cost,
        "baseline_cost": baseline_cost,
        "actual_latency": actual_latency,
        "baseline_latency": baseline_latency,
        "assertion_failures": [r.to_dict() for r in assertion_failures],
        "assertion_summary": summary,
    }


async def _post_alert(url: str, payload: dict[str, Any]) -> None:
    """POST the alert payload with httpx, matching the node_executor webhook pattern."""
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    print(f"Alert POSTed to webhook: HTTP {resp.status_code}")


async def _send_alert(payload: dict[str, Any], dry_run: bool) -> None:
    """Send or echo a regression alert.

    If ``REGRESSION_WEBHOOK_URL`` is empty, the alert is printed to stderr.
    If ``dry_run`` is True, the alert is printed but never POSTed.
    """
    webhook_url = os.environ.get("REGRESSION_WEBHOOK_URL", "")

    if dry_run or not webhook_url:
        if dry_run:
            print("[DRY-RUN] Regression alert would be sent:", file=sys.stderr)
        else:
            print("REGRESSION_WEBHOOK_URL is unset; echoing alert to stderr:", file=sys.stderr)
        print(json.dumps(payload, indent=2, default=str), file=sys.stderr)
        return

    await _post_alert(webhook_url, payload)


def _print_summary(summary: dict[str, Any]) -> None:
    """Print the PASS/DRIFT summary to stdout."""
    status = "DRIFT" if summary["drift"] else "PASS"
    print(f"{status}: run={summary['run_id']} baseline={summary['baseline_path']}")
    print(
        f"  cost:    actual={summary['actual_cost']} "
        f"baseline={summary['baseline_cost']} "
        f"drift={summary['cost_drift']}"
    )
    print(
        f"  latency: actual={summary['actual_latency']}s "
        f"baseline={summary['baseline_latency']}s "
        f"drift={summary['latency_drift']}"
    )
    failures = summary.get("assertion_failures", [])
    if failures:
        print(f"  assertion failures: {len(failures)}")
        for failure in failures:
            print(f"    - {failure['assertion_type']}: {failure['message']}")


async def main() -> int:
    """CLI entry point."""
    parser = _build_arg_parser()
    args = parser.parse_args()
    _validate_args(args)

    if args.extract_run_id:
        baseline_doc = await _extract_baseline(
            args.extract_run_id,
            args.headroom_cost,
            args.headroom_latency,
        )
        path = _save_baseline(args.extract_run_id, baseline_doc)
        print(f"Extracted {len(baseline_doc['expected_behaviors'])} baseline behaviors to {path}")
        return 0

    # --check mode
    summary = await _check_run(args.check_run_id, args.baseline_path)
    _print_summary(summary)

    if summary["drift"]:
        alert: dict[str, Any] = {
            "status": "DRIFT",
            "run_id": summary["run_id"],
            "baseline_path": summary["baseline_path"],
            "actual_cost": summary["actual_cost"],
            "baseline_cost": summary["baseline_cost"],
            "cost_drift": summary["cost_drift"],
            "actual_latency": summary["actual_latency"],
            "baseline_latency": summary["baseline_latency"],
            "latency_drift": summary["latency_drift"],
            "assertion_summary": summary["assertion_summary"],
        }
        await _send_alert(alert, dry_run=args.dry_run)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
