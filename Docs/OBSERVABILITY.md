# Flowmanner Observability — H3 Reference

## Architecture overview

```
Metrics (Prometheus) → app/core/metrics.py
       ↓
SLO gauges           → app/core/slo.py
       ↓
SLO dashboard        → app/core/slo_dashboard.py
       ↓
Alerts               → app/services/alerting.py
       ↓
Channels             → webhook, ntfy, email (placeholder), pagerduty (placeholder)
```

## Dashboard config

- **Source**: `backend/app/core/slo_dashboard.py` — `SLO_DASHBOARD_CONFIG` dict
- **Export dashboard JSON** from the homelab:

```bash
cd /opt/flowmanner/backend
PYTHONPATH=/opt/flowmanner/backend python -c "
from app.core.slo_dashboard import get_slo_dashboard_json
print(get_slo_dashboard_json())
" > /tmp/slo_dashboard.json
```

- **Import** into Langfuse Dashboard (project settings → dashboards → import) or use as reference for Grafana dashboards backed by Prometheus metrics.

## SLO panels (4 required)

| Panel | Metric | Target | Alert threshold |
|---|---|---|---|
| Mission success rate | `flowmanner_slo_compliance_ratio{slo_name="mission_success_rate"}` | > 95% | < 85% |
| p99 SSE latency | `flowmanner_slo_compliance_ratio{slo_name="sse_token_latency_p99"}` | p99 < 300ms | > 500ms |
| Model fallback success | `flowmanner_slo_compliance_ratio{slo_name="model_fallback_success"}` | > 99% | < 95% |
| Deploy success rate | `flowmanner_slo_compliance_ratio{slo_name="deploy_success_rate"}` | > 99% | < 95% |

Each panel also tracks `flowmanner_slo_burn_rate` and `flowmanner_slo_error_budget_remaining`.

## Langfuse health check

From the homelab, verify Langfuse is reachable:

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer ${LANGFUSE_SECRET_KEY}" \
  "https://cloud.langfuse.com/api/public/health"
# Expected: 200
```

Or check the local container:

```bash
docker compose exec langfuse-server curl -s localhost:3000/api/public/health
```

## Alert channels

Configure via environment variables:

| Variable | Example | Description |
|---|---|---|
| `NOTIFY_CHANNELS` | `ntfy,webhook` | CSV of alert channels |
| `ALERT_WEBHOOK_URL` | `https://hooks.slack.com/...` | Slack/Discord webhook URL |
| `NTFY_TOPIC` | `flowmanner-alerts` | ntfy.sh topic name |
| `NTFY_URL` | `https://ntfy.example.com/flowmanner` | Full ntfy server URL (overrides topic) |
| `ALERT_COOLDOWN_SECONDS` | `300` | Minimum seconds between repeated alerts |

### Channel dispatch flow

1. `send_circuit_alert()` / `send_slo_alert()` called
2. Debounce check (per dependency+state or slo+severity)
3. `_dispatch_to_channels()` iterates all configured channels
4. Each channel formats its own payload (webhook = JSON, ntfy = plain text + headers)
5. Per-channel failure is **non-fatal** — logged, other channels continue

## URLs Glenn can open

| What | URL |
|---|---|
| Langfuse traces | `https://cloud.langfuse.com` → sign in → project "flowmanner" |
| SLO dashboard (if imported) | Langfuse → Dashboards → "Flowmanner SLO Dashboard (H1.5)" |
| Prometheus metrics (homelab) | `http://172.16.1.1:9090` |
| Grafana (if configured) | `http://172.16.1.1:3000` |
| ntfy web UI | `https://ntfy.sh/flowmanner-alerts` (or self-hosted URL) |

## Checklist: verify observability is working

- [ ] Prometheus scraping backend metrics endpoint
- [ ] SLO gauges show non-zero values in Prometheus
- [ ] Langfuse health endpoint returns 200
- [ ] Alert webhook URL reachable: `curl -X POST $ALERT_WEBHOOK_URL -d '{"text":"test"}'`
- [ ] ntfy topic reachable: `curl -d "test" https://ntfy.sh/$NTFY_TOPIC`
- [ ] `NOTIFY_CHANNELS` env set on homelab docker-compose
- [ ] Dashboard JSON exportable and importable
