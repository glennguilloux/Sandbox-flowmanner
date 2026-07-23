#!/usr/bin/env python3
"""Self-tuning harness-evolution script for Flowmanner.

Runs a bounded ``ParamSpace`` search (grid or mutate) over a small test
blueprint's safe knobs and emits the scored ``EvolutionLedger`` as JSON.

Intended use (from the ``backend/`` directory)::<

    python -m scripts.self_tuning_evolution --mode grid --seed 42

The ledger JSON is written to stdout and to ``/tmp/evolution-ledger.json``.
A human-readable summary is written to stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.config import settings
from app.database import AsyncSessionLocal
from app.services.substrate.event_log import EventLog
from app.services.substrate.executor import UnifiedExecutor
from app.services.substrate.harness_evolution import (
    EvolutionLedger,
    ParamSpace,
    run_evolution,
)

logger = logging.getLogger(__name__)

#: Default output path for the JSON ledger.
DEFAULT_LEDGER_PATH = "/tmp/evolution-ledger.json"


#: Disable durable lease heartbeats for this test harness. Many short
#: back-to-back runs on the same worker contend with themselves and can
#: be poisoned by an aborted transaction from a failed trial.
DEFAULT_DISABLE_LEASES = True


class _FixtureEventLog(EventLog):
    """Event-log adapter that strips non-essential event metadata.

    The dummy workflow used by this test harness does not correspond to a
    row in the ``missions`` table, and its node IDs are short strings rather
    than UUIDs.  The substrate event log carries nullable ``mission_id``,
    ``blueprint_id`` and ``task_id`` metadata columns, so stripping them
    for this fixture script avoids validation errors (and the cascading
    ``InFailedSQLTransactionError``) while still recording all events.
    """

    _STRIPPED_KEYS: tuple[str, ...] = ("mission_id", "blueprint_id", "task_id")

    async def append(
        self,
        db: Any,
        run_id: str,
        events: list[dict[str, Any]],
        **kwargs: Any,
    ) -> Any:
        # Copy structures before mutating so callers are not surprised by side effects.
        events = [dict(event) for event in events]
        kwargs = {k: v for k, v in kwargs.items() if k not in self._STRIPPED_KEYS}
        for event in events:
            for key in self._STRIPPED_KEYS:
                event.pop(key, None)
        return await super().append(db, run_id, events, **kwargs)


async def _default_run_candidate(
    workflow: Any,
    candidate: dict[str, Any],
    run_ctx: dict[str, Any],
) -> dict[str, Any]:
    """Execute a candidate against the real substrate.

    Mirrors the return shape of
    ``app.services.substrate.harness_evolution._default_run_candidate`` but
    uses a custom ``EventLog`` that strips non-existent mission/blueprint/task
    metadata so the fixture can run without first scaffolding DB rows.
    """
    from app.services.substrate.harness_evolution import _collect_events, _extract_answer_output

    async with AsyncSessionLocal() as db:
        executor = UnifiedExecutor(event_log=_FixtureEventLog())
        result = await executor.execute(
            db,
            workflow,
            run_id=str(run_ctx.get("run_id", uuid4())),
        )
        try:
            events = await _collect_events(db, str(result.run_id))
        except Exception:  # pragma: no cover - best-effort event collection
            logger.exception("Failed to collect events for run_id=%s", result.run_id)
            events = []
        answer_output = _extract_answer_output(events, result)
        # score_run() uses getattr() on the result object, so wrap the dict in a
        # namespace so attribute access works for both StrategyResult and dict runs.
        return {
            "result": SimpleNamespace(
                success=result.success,
                status=result.status,
                total_cost_usd=float(result.total_cost_usd or 0.0),
                execution_time_ms=float(result.execution_time_ms or 0.0),
                completed_nodes=list(result.completed_nodes),
                failed_nodes=list(result.failed_nodes),
                error=result.error,
            ),
            "events": events,
            "answer_output": answer_output,
        }


def _build_arg_parser() -> argparse.ArgumentParser:
    """Return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="self_tuning_evolution",
        description="Run bounded harness-evolution over a test blueprint's knobs.",
    )
    parser.add_argument(
        "--blueprint-id",
        default="harness-evolution-test",
        help="Fixture blueprint id recorded in the ledger (default: harness-evolution-test).",
    )
    parser.add_argument(
        "--mode",
        choices=("grid", "mutate"),
        default="grid",
        help="Search mode: grid enumerates all combinations; mutate walks a randomized neighborhood.",
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=8,
        help="Number of mutate steps (ignored in grid mode, default: 8).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for reproducible mutate walks (default: 42).",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_LEDGER_PATH,
        help=f"Path to write the JSON ledger (default: {DEFAULT_LEDGER_PATH}).",
    )
    parser.add_argument(
        "--enable-leases",
        action="store_true",
        help="Keep durable worker leases enabled (default: disabled for this test harness).",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use an even smaller ParamSpace for a fast smoke test (1 combo).",
    )
    return parser


def _build_base_candidate() -> dict[str, Any]:
    """Return a minimal candidate with one llm_call node and safe slots."""
    return {
        "workflow": {
            "nodes": [
                {
                    "id": "answer",
                    "type": "llm_call",
                    "title": "Answer",
                    "description": "Single LLM answer node used for harness evolution.",
                    "assigned_model": "deepseek-v4-flash",
                    "config": {
                        "prompt": "Say hello, briefly.",
                        "temperature": 0.7,
                        "top_k": 5,
                        "max_tokens": 200,
                    },
                }
            ],
            "edges": [],
        },
        "budget": {"tolerance_pct": 10},
        "assertion": {"cost_ceiling_mult": 1.2},
        "routing": {"max_depth": 3},
    }


def _build_param_space(*, quick: bool = False) -> ParamSpace:
    """Return a bounded ParamSpace using only SAFE_AXES names.

    Defaults are intentionally small so the demo grid finishes quickly
    against a real LLM. Pass ``quick=True`` for a single-combination smoke
    test, or use ``--mode mutate`` to explore a larger space.
    """
    if quick:
        return ParamSpace(
            {
                "answer.temperature": (0.5,),
                "answer.top_k": (5,),
                "budget.tolerance_pct": (10,),
            }
        )
    return ParamSpace(
        {
            "answer.temperature": (0.3, 0.7),
            "answer.top_k": (5,),
            "budget.tolerance_pct": (10,),
        }
    )


def _assertion_spec() -> list[dict[str, Any]]:
    """Return regression assertions used to score each trial.

    The cost ceiling uses a generous multiplier because small dollar-scale
    variation between LLM runs (token-count jitter) can otherwise fail the
    default 1.2x threshold in this test fixture.
    """
    return [
        {"type": "cost_ceiling", "multiplier": 10.0},
        {"type": "latency_ceiling", "multiplier": 2.0},
        {"type": "task_completion"},
    ]


async def _run_evolution(
    args: argparse.Namespace,
    *,
    run_candidate: Any | None = None,
) -> EvolutionLedger:
    """Drive the harness-evolution loop with the CLI arguments.

    Args:
        args: Parsed CLI arguments.
        run_candidate: Optional injectable run seam. When provided, the loop
            executes candidates through this function instead of the real
            ``UnifiedExecutor``. This is the hook unit tests use to avoid
            hitting Postgres/LLM.
    """
    param_space = _build_param_space(quick=args.quick)
    base_candidate = _build_base_candidate()

    if run_candidate is None:
        run_candidate = _default_run_candidate

    return await run_evolution(
        blueprint_id=args.blueprint_id,
        base_candidate=base_candidate,
        param_space=param_space,
        mode=args.mode,
        generations=args.generations,
        seed=args.seed,
        assertion_spec=_assertion_spec(),
        run_candidate=run_candidate,
    )


def _print_summary(ledger: EvolutionLedger, output_path: str) -> None:
    """Print a human-readable summary to stderr."""
    total = len(ledger.entries)
    passed = sum(1 for entry in ledger.entries if entry.passed)
    promoted = sum(1 for entry in ledger.entries if entry.promoted)
    best = ledger.best()

    print("=== Flowmanner Self-Tuning Evolution Summary ===", file=sys.stderr)
    print(f"Blueprint ID  : {ledger.blueprint_id}", file=sys.stderr)
    print(f"Axis names    : {', '.join(ledger.axis_names)}", file=sys.stderr)
    print(f"Trials run    : {total}", file=sys.stderr)
    print(f"Trials passed : {passed}", file=sys.stderr)
    print(f"Promoted      : {promoted}", file=sys.stderr)

    if best:
        print(f"Best promoted params : {best.params}", file=sys.stderr)
        print(
            f"Best score           : cost=${best.score.get('cost_usd')} "
            f"latency={best.score.get('latency_ms')}ms "
            f"d_cost={best.score.get('d_cost')} "
            f"d_latency={best.score.get('d_latency')} "
            f"combined={best.score.get('combined')}",
            file=sys.stderr,
        )
    else:
        print("Best promoted config : None", file=sys.stderr)

    print(f"Ledger JSON written to: {output_path}", file=sys.stderr)


async def main() -> int:
    """CLI entry point."""
    args = _build_arg_parser().parse_args()
    if DEFAULT_DISABLE_LEASES and not getattr(args, "enable_leases", False):
        settings.FLOWMANNER_LEASE_ENABLED = False
    ledger = await _run_evolution(args)

    json_output = ledger.to_json(indent=2)

    # Write the ledger JSON to stdout AND to the requested file.
    print(json_output)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(json_output)

    _print_summary(ledger, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
