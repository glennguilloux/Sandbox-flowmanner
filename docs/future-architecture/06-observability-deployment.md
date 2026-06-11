# 06 — Observability and Deployment Architecture

## 1. Observability Architecture

### Goals

Production FlowManner must answer:

- What is running?
- Who requested it?
- Which agent acted?
- Which tool was called?
- Which model was used?
- How much did it cost?
- Where did it fail?
- Can it be replayed?
- Can it be debugged safely?
- Can an enterprise audit it?

### Telemetry Layers

```text
Traces
  → request
  → worker task
  → LLM call
  → tool call
  → event append
  → projection update

Metrics
  → throughput
  → latency
  → error rate
  → queue depth
  → worker saturation
  → cost burn
  → model fallback rate

Logs
  → structured JSON
  → correlation IDs
  → redaction
  → severity
  → service name

Events
  → business facts
  → execution state
  → audit trail
  → replay source

Alerts
  → SLO burn
  → worker failure
  → circuit breaker
  → budget breach
  → data loss risk
```

### Required Identifiers

Every request/run/task/event should carry:

- `request_id`
- `run_id`
- `task_id`
- `correlation_id`
- `causation_id`
- `workspace_id`
- `user_id`
- `agent_id`
- `provider_call_id`

### Workflow Replay

Replay should be available at two levels:

1. Internal debug replay.
2. User-facing audit replay.

Replay must include:

- Original events.
- Snapshots.
- Tool results.
- LLM call metadata.
- Cost/token data.
- Human interventions.
- Redaction policy.

### Agent Replay

Agent replay must show:

- Agent profile version.
- Context inputs.
- Retrieved memory.
- Tool calls.
- Model calls.
- Decisions.
- Budget state.
- Final output.

### Observability Stack

Recommended stack:

| Layer | Tool |
|---|---|
| Traces | OpenTelemetry → Jaeger/Tempo |
| Metrics | Prometheus |
| Dashboards | Grafana |
| Logs | Loki or ELK |
| Errors | Sentry |
| LLM traces | Langfuse or equivalent |
| Alerts | ntfy, PagerDuty, email/webhook |
| Audit | Postgres event log + object storage archive |

### SLOs

Minimum SLO set:

- API availability.
- Worker availability.
- Event append latency.
- Task completion latency.
- SSE stream latency.
- Model fallback success.
- Cost attribution completeness.
- Replay availability.
- Memory retrieval latency.
- Deploy success rate.

## 2. Deployment Architecture

### Self-Hosted Deployment

Target topology:

```text
Docker Compose
  ├── backend
  ├── worker
  ├── postgres
  ├── redis
  ├── qdrant
  ├── rabbitmq
  ├── object storage or local volume
  ├── jaeger/tempo
  └── llama.cpp
```

Self-hosted requirements:

- One command deploy.
- No Kubernetes requirement.
- No service mesh requirement.
- No external cloud dependency unless opted in.
- Local inference support.
- Clear upgrade path.
- Backup/restore scripts.

### SaaS Deployment

Target topology:

```text
Kubernetes
  ├── control plane
  ├── worker pools
  ├── managed postgres
  ├── managed redis
  ├── qdrant cluster
  ├── NATS JetStream
  ├── object storage
  ├── observability stack
  └── GPU/model serving nodes
```

SaaS requirements:

- Multi-tenant isolation.
- Horizontal worker scaling.
- Separate control plane and data plane.
- Per-tenant quotas.
- Data residency controls.
- Blue/green deploys.
- Rollback.
- Disaster recovery.

### Edge Nodes

Edge nodes should be lightweight:

- Pull jobs from control plane.
- Execute local tools.
- Run local models.
- Report events.
- Respect workspace policy.
- Stay offline-safe where possible.

Edge node responsibilities:

1. Secure enrollment.
2. Local sandboxing.
3. Event buffering.
4. Resume after reconnect.
5. Health reporting.

### GPU Clusters

GPU clusters should be treated as capacity pools, not special-case infrastructure.

Requirements:

- Model registry.
- GPU quota.
- Scheduling.
- Health checks.
- Fallback routing.
- Cost attribution.
- Model version pinning.

## 3. Deployment Principles

1. Keep self-hosted simple.
2. Keep SaaS scalable.
3. Do not make Kubernetes mandatory for all users.
4. Do not make cloud required for local execution.
5. Keep provider routing replaceable.
6. Keep event replay independent of deployment topology.

## 4. Operational Readiness Checklist

A deployment is production-ready only when it has:

- Health checks.
- Readiness checks.
- Backup/restore.
- Metrics.
- Logs.
- Traces.
- Alerts.
- Replay.
- Rollback.
- Disaster recovery plan.

## 5. Why This Works

This observability and deployment model gives FlowManner:

- A simple path for self-hosted users.
- A scalable path for SaaS.
- A debug path for autonomous agents.
- A cost-control path for billing.
- A compliance path for enterprise customers.
