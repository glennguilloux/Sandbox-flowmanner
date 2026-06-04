"""Quickstart: Create a mission, execute it, and check the result."""

from flowmanner_api_client import FlowmannerClient

# Connect (reads FLOWMANNER_API_KEY from env)
with FlowmannerClient(base_url="https://flowmanner.com") as fm:
    # Check connectivity
    print(fm.health_check())

    # Create a mission
    mission = fm.create_mission(
        title="My First Mission",
        description="A test mission from the SDK",
        mission_type="general",
    )
    print(f"Created mission: {mission['id']}")

    # Execute it
    result = fm.execute_mission(mission["id"])
    print(f"Status: {result.get('status')}")

    # Check status
    status = fm.get_mission_status(mission["id"])
    print(f"Mission status: {status}")
