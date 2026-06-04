# FlowManner Python SDK

Official Python client for the [FlowManner](https://flowmanner.com) AI workflow orchestration API.

## Installation

```bash
pip install flowmanner-api-client
```

## Quick Start

```python
from flowmanner_api_client import FlowmannerClient

with FlowmannerClient(base_url="https://flowmanner.com") as fm:
    # Create and run a mission
    mission = fm.create_mission(title="Hello World")
    result = fm.execute_mission(mission["id"])
    print(result["status"])
```

Set your API key via environment variable:

```bash
export FLOWMANNER_API_KEY="sk-your-key-here"
```

Or pass it directly:

```python
fm = FlowmannerClient(base_url="https://flowmanner.com", api_key="sk-...")
```

## CLI

After installation, use the `flowmanner` command:

```bash
flowmanner status              # Check API connectivity
flowmanner missions            # List recent missions
flowmanner costs --period 30d  # Show cost analytics
```

## API Reference

### Missions

| Method | Description |
|--------|-------------|
| `create_mission(title, description, mission_type, priority)` | Create a new mission |
| `get_mission(mission_id)` | Get mission details |
| `list_missions(limit, status)` | List recent missions |
| `execute_mission(mission_id)` | Execute synchronously |
| `execute_mission_async(mission_id)` | Queue for async execution |
| `get_mission_status(mission_id)` | Get status string |
| `delete_mission(mission_id)` | Delete a mission |

### Tasks & Logs

| Method | Description |
|--------|-------------|
| `list_tasks(mission_id)` | List tasks for a mission |
| `list_logs(mission_id)` | List logs for a mission |

### Analytics

| Method | Description |
|--------|-------------|
| `get_usage_summary(period)` | Token/cost summary |
| `get_cost_analytics(period)` | Cost breakdown by model/agent |

### System

| Method | Description |
|--------|-------------|
| `health_check()` | API health check |
| `list_agents()` | List available agents |
| `get_agent(agent_id)` | Get agent details |

## Examples

See [`examples/`](./examples/) for working scripts:
- [`quickstart.py`](./examples/quickstart.py) — Basic CRUD
- [`create_and_run_mission.py`](./examples/create_and_run_mission.py) — Async execution + polling
- [`cost_analytics.py`](./examples/cost_analytics.py) — Usage analytics

## Development

```bash
cd sdk-python/flowmanner-api-client
poetry install
poetry build
```
