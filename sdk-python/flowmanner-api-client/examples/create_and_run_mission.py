"""Create a mission with tasks, execute async, and poll for completion."""

import time
from flowmanner_api_client import FlowmannerClient


def main():
    with FlowmannerClient(base_url="https://flowmanner.com") as fm:
        # Create mission
        mission = fm.create_mission(
            title="Research Task",
            description="Analyze competitor pricing strategies",
            mission_type="research",
            priority="high",
        )
        mission_id = mission["id"]
        print(f"Created: {mission_id}")

        # Execute async
        fm.execute_mission_async(mission_id)
        print("Queued for async execution")

        # Poll for completion
        for _ in range(60):
            status = fm.get_mission_status(mission_id)
            print(f"  Status: {status}")
            if status in ("completed", "failed", "aborted"):
                break
            time.sleep(5)

        # Get final result
        final = fm.get_mission(mission_id)
        print(f"\nFinal: {final.get('status')}")
        print(f"Tokens used: {final.get('tokens_used', 0)}")

        # List tasks
        tasks = fm.list_tasks(mission_id)
        print(f"Tasks: {len(tasks)}")


if __name__ == "__main__":
    main()
