# FlowManner Python SDK

Official Python client for the [FlowManner](https://flowmanner.com) AI workflow orchestration API.

## Installation

```bash
pip install flowmanner-api-client
```

## Quick Start

```python
from flowmanner_api_client import FlowmannerClient

# Uses FLOWMANNER_API_KEY env var, or pass api_key explicitly
with FlowmannerClient("https://flowmanner.com") as fm:
    # ⭐ The most differentiated call: a multi-agent debate, scored by an LLM judge.
    # Pick any two agent personalities from GET /api/agent-personalities.
    result = fm.debate(
        topic="Should we use GraphQL or REST for our new public API?",
        agent_a_id="software-it/code-review-assistant",
        agent_a_name="Code Review Assistant",
        agent_b_id="legal/contract-reviewer",
        agent_b_name="Contract Reviewer",
        max_rounds=2,
    )
    print(result["consensus_synthesis"])

    # See which agents you can use in a debate:
    for p in fm.list_agent_personalities():
        print(p["id"], "—", p["name"])
```

Prefer the live debate example above. A mission is the heavier workflow:

```python
with FlowmannerClient("https://flowmanner.com") as fm:
    # Create and run a mission
    mission = fm.create_mission("Summarize the docs")
    print(f"Created: {mission.id}")

    # Execute and poll until complete
    fm.execute_mission_async(str(mission.id))
    fm.wait_for_mission(str(mission.id))
    print("Done!")
```

## Configuration

Set your API key via environment variable:

```bash
export FLOWMANNER_API_KEY="sk-..."
export FLOWMANNER_BASE_URL="https://flowmanner.com"  # optional, defaults to this
```

Or pass directly:

```python
fm = FlowmannerClient("https://flowmanner.com", api_key="sk-...")
```

## Usage

### Missions

```python
with FlowmannerClient("https://flowmanner.com") as fm:
    # Create
    mission = fm.create_mission(
        title="Research task",
        description="Find and summarize articles",
        mission_type="automation",
        priority="high",
    )

    # List
    missions = fm.list_missions(per_page=10)

    # Get details
    mission = fm.get_mission(str(mission.id))

    # Execute (async)
    fm.execute_mission_async(str(mission.id))

    # Check status
    status = fm.get_mission_status(str(mission.id))

    # Wait for completion (polls automatically)
    fm.wait_for_mission(str(mission.id), timeout=300)

    # List tasks
    tasks = fm.list_tasks(str(mission.id))

    # Delete
    fm.delete_mission(str(mission.id))
```

### Cost Analytics

```python
with FlowmannerClient("https://flowmanner.com") as fm:
    # Usage summary (last 30 days)
    summary = fm.get_usage_summary(period="30d")
    print(f"Tokens: {summary.total_tokens:,}")
    print(f"Cost:   ${summary.total_cost:.4f}")

    # Cost breakdown by model
    analytics = fm.get_cost_analytics(period="month")
    for item in analytics.by_model:
        print(f"  {item.model}: ${item.cost_usd:.4f}")
```

### Health Check

```python
fm = FlowmannerClient("https://flowmanner.com")
health = fm.health_check()
print(health)
```

## CLI

After installation, use the `flowmanner` command:

```bash
# Check connectivity
flowmanner status

# View costs
flowmanner costs --period 30d

# List missions
flowmanner missions list --limit 10

# Get mission details
flowmanner missions get <mission-id>

# Create a mission
flowmanner missions create "My new mission" --description "..." --priority high
```

CLI uses `FLOWMANNER_API_KEY` and `FLOWMANNER_BASE_URL` environment variables, or pass `--api-key` and `--base-url` flags.

## Examples

See the [`examples/`](./examples/) directory:

| Script | Description |
|--------|-------------|
| [`quickstart.py`](./examples/quickstart.py) | Basic connect, create, execute |
| [`create_and_run_mission.py`](./examples/create_and_run_mission.py) | Full mission lifecycle with polling |
| [`cost_analytics.py`](./examples/cost_analytics.py) | Usage and cost reporting |

## Advanced Usage

The SDK also exposes the low-level auto-generated client for direct API access:

```python
from flowmanner_api_client import AuthenticatedClient
from flowmanner_api_client.api.missions import list_items_api_missions_get

client = AuthenticatedClient(base_url="https://flowmanner.com", token="sk-...")
result = list_items_api_missions_get.sync(client=client, per_page=5)
```

## Development

```bash
cd sdk-python/flowmanner-api-client
poetry install
poetry build
```

## License

MIT
