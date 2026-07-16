"""Flowmanner CLI — manage missions and costs from the terminal.

Usage:
    flowmanner status              # Check API connectivity + auth
    flowmanner costs               # Show this month's costs
    flowmanner missions list       # List recent missions
    flowmanner missions get <id>   # Get mission details
    flowmanner missions create <title>  # Create a new mission
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _get_client(args: argparse.Namespace):
    """Create a FlowmannerClient from args or environment."""
    from .high_level import FlowmannerClient

    base_url = getattr(args, "base_url", None) or os.environ.get("FLOWMANNER_BASE_URL", "https://flowmanner.com")
    api_key = getattr(args, "api_key", None) or os.environ.get("FLOWMANNER_API_KEY", "")
    if not api_key:
        print(
            "Error: No API key. Set FLOWMANNER_API_KEY or pass --api-key.",
            file=sys.stderr,
        )
        sys.exit(1)
    return FlowmannerClient(base_url, api_key=api_key)


def _print_json(data: object) -> None:
    """Pretty-print JSON with attrs-aware serialization."""
    from attrs import asdict

    try:
        d = asdict(data)
    except (TypeError, NotImplementedError):
        if isinstance(data, list):
            d = []
            for item in data:
                try:
                    d.append(asdict(item))
                except (TypeError, NotImplementedError):
                    d.append(str(item))
        else:
            d = str(data)
    print(json.dumps(d, indent=2, default=str))


# ── Commands ───────────────────────────────────────────────────────


def cmd_status(args: argparse.Namespace) -> None:
    """Check API connectivity and authentication."""
    fm = _get_client(args)
    try:
        health = fm.health_check()
        print("✓ Connected to Flowmanner API")
        print(f"  Base URL: {fm._client.base_url}")
        if isinstance(health, dict):
            for k, v in health.items():
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"✗ Connection failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_costs(args: argparse.Namespace) -> None:
    """Show usage costs."""
    fm = _get_client(args)
    try:
        summary = fm.get_usage_summary(period=args.period)
        tokens = getattr(summary, "total_tokens", 0) or 0
        cost = getattr(summary, "total_cost", 0) or 0
        period = getattr(summary, "period", args.period)
        print(f"Usage Summary ({period})")
        print(f"  Total Tokens: {tokens:,}")
        print(f"  Total Cost:   ${cost:.4f}")

        breakdown = getattr(summary, "breakdown", []) or []
        if breakdown:
            print("\n  Breakdown by Model:")
            for item in breakdown:
                name = getattr(item, "model", getattr(item, "name", "unknown"))
                item_cost = getattr(item, "cost_usd", getattr(item, "cost", 0)) or 0
                item_tokens = getattr(item, "tokens", getattr(item, "total_tokens", 0)) or 0
                print(f"    {name}: ${item_cost:.4f} ({item_tokens:,} tokens)")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_missions_list(args: argparse.Namespace) -> None:
    """List recent missions."""
    fm = _get_client(args)
    try:
        result = fm.list_missions(per_page=args.limit)
        # Live API returns a paginated dict envelope
        # {"items": [...], "total", "page", "per_page", "pages"}. Unwrap .items;
        # fall back to a bare list for backward-compat.
        if isinstance(result, dict) and "items" in result:
            items = result["items"] or []
        elif isinstance(result, list):
            items = result
        else:
            items = [result] if result else []

        if not items:
            print("No missions found.")
            return

        print(f"{'ID':<38} {'Status':<12} {'Title'}")
        print("─" * 80)
        for m in items:
            mid = str(getattr(m, "id", "?"))
            status = str(getattr(m, "status", "?"))
            title = str(getattr(m, "title", "?"))
            print(f"{mid:<38} {status:<12} {title}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_missions_get(args: argparse.Namespace) -> None:
    """Get mission details."""
    fm = _get_client(args)
    try:
        mission = fm.get_mission(args.mission_id)
        _print_json(mission)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_missions_create(args: argparse.Namespace) -> None:
    """Create a new mission."""
    fm = _get_client(args)
    try:
        mission = fm.create_mission(
            title=args.title,
            description=args.description or "",
            mission_type=args.type,
            priority=args.priority,
        )
        print(f"✓ Created mission: {mission.id}")
        print(f"  Title:  {mission.title}")
        print(f"  Status: {getattr(mission, 'status', 'unknown')}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


# ── Parser ─────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flowmanner",
        description="Flowmanner CLI — manage missions and costs from the terminal.",
    )
    parser.add_argument("--api-key", help="API key (overrides FLOWMANNER_API_KEY)")
    parser.add_argument("--base-url", help="API base URL (overrides FLOWMANNER_BASE_URL)")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # status
    sub.add_parser("status", help="Check API connectivity and auth")

    # costs
    p_costs = sub.add_parser("costs", help="Show usage costs")
    p_costs.add_argument("--period", default="30d", help="Period: 7d, 30d, 90d (default: 30d)")

    # missions
    p_missions = sub.add_parser("missions", help="Mission management")
    missions_sub = p_missions.add_subparsers(dest="missions_command")

    missions_sub.add_parser("list", help="List recent missions").add_argument(
        "--limit", type=int, default=20, help="Max missions to show (default: 20)"
    )

    p_get = missions_sub.add_parser("get", help="Get mission details")
    p_get.add_argument("mission_id", help="Mission UUID")

    p_create = missions_sub.add_parser("create", help="Create a new mission")
    p_create.add_argument("title", help="Mission title")
    p_create.add_argument("--description", "-d", help="Mission description")
    p_create.add_argument("--type", "-t", help="Mission type")
    p_create.add_argument("--priority", "-p", help="Priority: high, medium, low")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "status": cmd_status,
        "costs": cmd_costs,
        "missions": lambda a: {
            "list": cmd_missions_list,
            "get": cmd_missions_get,
            "create": cmd_missions_create,
        }.get(a.missions_command or "", lambda x: parser.print_help())(a),
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
