"""Flowmanner CLI - check status, view costs, list missions."""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flowmanner", description="Flowmanner CLI")
    parser.add_argument(
        "--url", default=os.environ.get("FLOWMANNER_URL", "https://flowmanner.com")
    )
    parser.add_argument("--key", default=os.environ.get("FLOWMANNER_API_KEY"))
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Check API connectivity")
    sub.add_parser("missions", help="List recent missions").add_argument(
        "list", nargs="?", default="list"
    )
    sub.add_parser("costs", help="Show cost analytics").add_argument(
        "--period", default="month"
    )

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if not args.key:
        print("Error: Set FLOWMANNER_API_KEY or pass --key", file=sys.stderr)
        return 1

    from .high_level import FlowmannerClient

    try:
        with FlowmannerClient(base_url=args.url, api_key=args.key) as fm:
            if args.command == "status":
                health = fm.health_check()
                print(f"Connected to {args.url}")
                print(f"Status: {health.get('status', 'unknown')}")
                return 0

            if args.command == "missions":
                missions = fm.list_missions(limit=10)
                if not missions:
                    print("No missions found.")
                    return 0
                for m in missions:
                    print(
                        f"  {m['id'][:8]}  {m.get('status', '?'):12}  {m.get('title', 'Untitled')}"
                    )
                return 0

            if args.command == "costs":
                summary = fm.get_usage_summary(period=args.period)
                print(f"Period: {args.period}")
                print(f"Total tokens: {summary.get('total_tokens', 0):,}")
                print(f"Total cost: ${summary.get('total_cost', 0):.4f}")
                return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
