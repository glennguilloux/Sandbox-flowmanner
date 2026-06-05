#!/usr/bin/env python3
"""
Phase 4.3: Runtime CLI Tool
Command-line interface for runtime management
"""

import argparse
import asyncio
import json
import sys

# Add parent to path for imports
sys.path.insert(0, str(__file__).rsplit("/cli", 1)[0])


class RuntimeCLI:
    """CLI for runtime management"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    async def _request(self, method: str, endpoint: str, **kwargs):
        """Make HTTP request"""
        import httpx

        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            response = await client.request(method, endpoint, **kwargs)
            if response.status_code >= 400:
                print(f"Error: {response.status_code} - {response.text}")
                sys.exit(1)
            return response.json()

    # Health commands
    async def health(self):
        """Get runtime health"""
        data = await self._request("GET", "/api/runtime/health")
        print(json.dumps(data, indent=2))

    async def status(self):
        """Get runtime status"""
        data = await self._request("GET", "/api/runtime/status")
        print(json.dumps(data, indent=2))

    async def metrics(self):
        """Get runtime metrics"""
        data = await self._request("GET", "/api/runtime/metrics")
        print(json.dumps(data, indent=2))

    # Queue commands
    async def queue_stats(self):
        """Get queue statistics"""
        data = await self._request("GET", "/api/runtime/queue/stats")
        print(json.dumps(data, indent=2))

    async def queue_list(self, status: str | None = None):
        """List queue items"""
        params = {}
        if status:
            params["status"] = status
        data = await self._request("GET", "/api/runtime/queue/items", params=params)
        print(json.dumps(data, indent=2))

    async def cancel(self, execution_id: str):
        """Cancel an execution"""
        data = await self._request("POST", f"/api/runtime/queue/{execution_id}/cancel")
        print(json.dumps(data, indent=2))

    # Scaling commands
    async def scaling_status(self):
        """Get scaling status"""
        data = await self._request("GET", "/api/runtime/scaling/status")
        print(json.dumps(data, indent=2))

    async def scale_up(self, count: int = 1):
        """Scale up workers"""
        data = await self._request(
            "POST", "/api/runtime/scaling/scale-up", json={"count": count}
        )
        print(json.dumps(data, indent=2))

    async def scale_down(self, count: int = 1):
        """Scale down workers"""
        data = await self._request(
            "POST", "/api/runtime/scaling/scale-down", json={"count": count}
        )
        print(json.dumps(data, indent=2))

    # Prediction commands
    async def predictions(self):
        """Get resource predictions"""
        data = await self._request("GET", "/api/runtime/predictions")
        print(json.dumps(data, indent=2))

    async def anomalies(self, hours: int = 24):
        """Get detected anomalies"""
        data = await self._request(
            "GET", "/api/runtime/anomalies", params={"hours": hours}
        )
        print(json.dumps(data, indent=2))

    async def recommendations(self):
        """Get scaling recommendations"""
        data = await self._request("GET", "/api/runtime/scaling/recommendations")
        print(json.dumps(data, indent=2))

    # Self-healing commands
    async def system_health(self):
        """Get system health"""
        data = await self._request("GET", "/api/runtime/health/system")
        print(json.dumps(data, indent=2))

    async def recovery_history(self, hours: int = 24):
        """Get recovery history"""
        data = await self._request(
            "GET", "/api/runtime/recovery/history", params={"hours": hours}
        )
        print(json.dumps(data, indent=2))

    async def recovery_strategies(self):
        """List recovery strategies"""
        data = await self._request("GET", "/api/runtime/recovery/strategies")
        print(json.dumps(data, indent=2))

    # Config commands
    async def get_config(self):
        """Get runtime configuration"""
        data = await self._request("GET", "/api/runtime/config")
        print(json.dumps(data, indent=2))

    async def reset_config(self):
        """Reset configuration to defaults"""
        data = await self._request("POST", "/api/runtime/config/reset")
        print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Runtime CLI - Manage runtime operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  runtime-cli health                    # Check runtime health
  runtime-cli queue stats               # Get queue statistics
  runtime-cli scale up 2                # Scale up by 2 workers
  runtime-cli predictions               # Get resource predictions
  runtime-cli anomalies --hours 48      # Get anomalies from last 48 hours
        """,
    )

    parser.add_argument(
        "--url", default="http://localhost:8000", help="Runtime API URL"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Health commands
    subparsers.add_parser("health", help="Get runtime health")
    subparsers.add_parser("status", help="Get runtime status")
    subparsers.add_parser("metrics", help="Get runtime metrics")

    # Queue commands
    queue_parser = subparsers.add_parser("queue", help="Queue operations")
    queue_subparsers = queue_parser.add_subparsers(dest="queue_command")
    queue_subparsers.add_parser("stats", help="Get queue statistics")
    queue_subparsers.add_parser("list", help="List queue items")
    cancel_parser = queue_subparsers.add_parser("cancel", help="Cancel execution")
    cancel_parser.add_argument("execution_id", help="Execution ID to cancel")

    # Scaling commands
    scale_parser = subparsers.add_parser("scale", help="Scaling operations")
    scale_subparsers = scale_parser.add_subparsers(dest="scale_command")
    scale_subparsers.add_parser("status", help="Get scaling status")
    up_parser = scale_subparsers.add_parser("up", help="Scale up workers")
    up_parser.add_argument(
        "count", type=int, nargs="?", default=1, help="Number of workers to add"
    )
    down_parser = scale_subparsers.add_parser("down", help="Scale down workers")
    down_parser.add_argument(
        "count", type=int, nargs="?", default=1, help="Number of workers to remove"
    )

    # Prediction commands
    subparsers.add_parser("predictions", help="Get resource predictions")
    anomalies_parser = subparsers.add_parser("anomalies", help="Get detected anomalies")
    anomalies_parser.add_argument(
        "--hours", type=int, default=24, help="Hours to look back"
    )
    subparsers.add_parser("recommendations", help="Get scaling recommendations")

    # Self-healing commands
    subparsers.add_parser("system-health", help="Get system health")
    recovery_parser = subparsers.add_parser("recovery", help="Recovery operations")
    recovery_subparsers = recovery_parser.add_subparsers(dest="recovery_command")
    recovery_subparsers.add_parser("history", help="Get recovery history")
    recovery_subparsers.add_parser("strategies", help="List recovery strategies")
    recovery_subparsers.add_parser("history").add_argument(
        "--hours", type=int, default=24
    )

    # Config commands
    config_parser = subparsers.add_parser("config", help="Configuration operations")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_subparsers.add_parser("get", help="Get configuration")
    config_subparsers.add_parser("reset", help="Reset to defaults")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    cli = RuntimeCLI(base_url=args.url)

    # Map commands to methods
    async def run():
        if args.command == "health":
            await cli.health()
        elif args.command == "status":
            await cli.status()
        elif args.command == "metrics":
            await cli.metrics()
        elif args.command == "queue":
            if args.queue_command == "stats":
                await cli.queue_stats()
            elif args.queue_command == "list":
                await cli.queue_list()
            elif args.queue_command == "cancel":
                await cli.cancel(args.execution_id)
        elif args.command == "scale":
            if args.scale_command == "status":
                await cli.scaling_status()
            elif args.scale_command == "up":
                await cli.scale_up(args.count)
            elif args.scale_command == "down":
                await cli.scale_down(args.count)
        elif args.command == "predictions":
            await cli.predictions()
        elif args.command == "anomalies":
            await cli.anomalies(args.hours)
        elif args.command == "recommendations":
            await cli.recommendations()
        elif args.command == "system-health":
            await cli.system_health()
        elif args.command == "recovery":
            if args.recovery_command == "history":
                hours = getattr(args, "hours", 24)
                await cli.recovery_history(hours)
            elif args.recovery_command == "strategies":
                await cli.recovery_strategies()
        elif args.command == "config":
            if args.config_command == "get":
                await cli.get_config()
            elif args.config_command == "reset":
                await cli.reset_config()

    asyncio.run(run())


if __name__ == "__main__":
    main()
