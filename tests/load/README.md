# Flowmanner Load Testing & Chaos Engineering

## Quick Start

```bash
# From homelab (10.99.0.3)
cd /opt/flowmanner/tests/load

# Run full scenario (combined workload)
./run-tests.sh full

# Run specific test
./run-tests.sh health
./run-tests.sh missions

# Run all tests sequentially
./run-tests.sh all

# Run chaos experiments during load
./chaos/chaos-runner.sh container-kill 30
```

## Scripts

| Script | What it tests | VUs | Duration |
|--------|---------------|-----|----------|
| `health.js` | Health endpoint throughput | 10→200 | ~3.5min |
| `login.js` | Auth + rate limiting | 2→10 | ~1.5min |
| `missions.js` | Mission CRUD | 3→25 | ~2min |
| `chat.js` | Chat threads + messages | 2→10 | ~2min |
| `search.js` | Search endpoint | 5→50 | ~2min |
| `full-scenario.js` | Mixed realistic workload | 20→100 | ~2.5min |

## Performance Budgets

| Endpoint | p95 Budget | Notes |
|----------|-----------|-------|
| Health | <200ms | Should be instant |
| Login | <500ms | Includes JWT generation |
| Mission Create | <2000ms | May trigger LLM planning |
| Mission List | <500ms | PostgreSQL query |
| Chat Message | <500ms | Non-streaming; LLM may exceed |
| Search | <1000ms | PostgreSQL + Qdrant |
| Generic API | <500ms | All other endpoints |

## Chaos Experiments

| Experiment | What it does | Risk |
|------------|-------------|------|
| `container-kill` | Stops backend container for N seconds | Low — data safe in volumes |
| `network-partition` | Blocks WireGuard traffic | Medium — requires sudo |
| `db-pool-exhaust` | Opens 60 idle DB connections | Low — connections auto-close |
| `llm-timeout` | Drops 50% of LLM requests | Low — tests circuit breaker |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_URL` | `http://127.0.0.1:8000` | Backend URL |
| `TEST_EMAIL` | `loadtest@example.com` | Test user email |
| `TEST_PASSWORD` | `LoadTest123!` | Test user password |

## Reports

Reports are saved to `reports/` as JSON. Parse with:

```bash
# Summary of last run
cat reports/full-scenario-*-summary.json | python3 -m json.tool

# Compare two runs
diff <(jq '.metrics.http_req_duration.avg' reports/run1-summary.json) \
     <(jq '.metrics.http_req_duration.avg' reports/run2-summary.json)
```
