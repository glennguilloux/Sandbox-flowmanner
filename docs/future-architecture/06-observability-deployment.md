# 06 - Observability and Deployment Architecture

## 1. Observability Architecture

### Purpose

Observability must let FlowManner answer operational, product, and audit questions without hiding failures behind successful HTTP responses.

Core questions:

- What is running?
- Who requested it?
- Which workspace owns the run?
- Which agent acted?
- Which worker claimed the task?
- Which tool and model were used?
- Which event caused the next step?
- How much did it cost?
- Where did it fail?
- Can the run be replayed safely?
- Can an operator prove deep-health without calling external providers by default?

### Required Identifiers

Every request, run, task, event, log, trace span, metric, and audit record must carry the identifiers that apply to it. Missing identifiers break replay, support, billing, and incident response.

| Identifier | Owner | Required for | Notes |
|---|---|---|---|
| `request_id` | API/request boundary | Requests, logs, traces, alerts | Created at ingress and propagated through backend modules. |
| `run_id` | Execution domain | Runs, tasks, events, replay | Ties execution state to a durable run. |
| `task_id` | Worker/execution domain | Worker tasks, leases, retries | Identifies one unit of work claimed by a worker. |
| `event_id` | Event/outbox domain | Events, replay, audit | Immutable event identity. |
| `correlation_id` | Request/run boundary | Cross-service correlation | Groups all artifacts for one user-visible action. |
| `causation_id` | Event/outbox domain | Causal chains, replay | Links an event to the event or command that caused it. |
| `workspace_id` | Workspace domain | Multi-tenancy, audit, billing | Required for workspace-scoped replay and cost attribution. |
| `user_id` | Auth domain | Audit, support, access checks | Redact or mask when exposing data outside trusted operator views. |
| `agent_id` | Agent domain | Agent replay, marketplace, billing | Must include agent profile version where possible. |
| `provider_call_id` | Provider adapter | Model traces, cost, fallback | Optional when no provider call happened. |
| `worker_id` | Worker runtime | Worker SLOs, leases, crash recovery | Identifies the process or container that executed a task. |
| `lease_id` | Worker lease system | Idempotency, stale-lease recovery | Required for leased execution work. |
| `trace_id` | Observability boundary | Traces, logs, alerts | OpenTelemetry-compatible trace ID. |

### Telemetry Layer Contract

| Layer | Answers | Correlation rule | Retention and safety rule |
|---|---|---|---|
| Trace Layer | Where did this request or task flow? Which spans failed? How long did each step take? | `trace_id` links spans. `request_id`, `run_id`, `task_id`, and `event_id` are span attributes. | Trace provider calls only when explicitly enabled. Redact prompts, secrets, tool payloads, and personal data. |
| Log Layer | What happened at each service boundary? What error was returned? Which IDs traveled together? | Structured JSON logs include `request_id`, `run_id`, `task_id`, `event_id`, `correlation_id`, `workspace_id`, `user_id`, and `trace_id` where available. | Use severity levels and redaction filters. Do not log raw provider requests or responses by default. |
| Metric Layer | Is the system healthy, saturated, slow, or expensive? | Metrics include `workspace_id` only when tenant isolation is required and cardinality is controlled. Worker metrics include `worker_id` and `lease_id`. | Keep metric cardinality low. Budget and cost metrics must be attributable to workspace, run, model, and provider. |
| Event Layer | What business fact happened? What caused the next state transition? What can be replayed? | Events carry `event_id`, `causation_id`, `run_id`, `task_id`, `workspace_id`, `user_id`, `agent_id`, and schema version. | Events are append-only. Provider payloads may be summarized or redacted. Full payloads require policy approval and retention controls. |
| Alert Layer | Which SLO is burning? Which gate failed? Who must act? | Alerts include the failing SLO, affected `workspace_id` when relevant, `request_id` or `run_id` when known, and deployment name. | Alert pages must link to dashboards, traces, logs, events, and the deployment stop gate that failed. |

### Replay Levels

Replay must be scoped. Higher replay detail requires stronger authorization, clearer retention rules, and stricter redaction.

| Level | Audience | Includes | Redaction and provider-call rule |
|---|---|---|---|
| Internal debug replay | Engineers and incident responders | Raw traces, logs, worker state, event sequence, checkpoints, model metadata, tool metadata, error payloads after redaction | No provider calls by default. Re-execute only from an explicit operator command with a new `request_id` and `correlation_id`. |
| Operator deep-health replay | Platform operators | Health results, dependency checks, SLO status, queue state, worker leases, recent failures, trace links, dashboard links | Must avoid external provider calls unless the operator explicitly selects provider health. Redact secrets, prompts, and user data. |
| User-facing audit replay | Workspace owners and authorized users | Run timeline, agent decisions, tool results, model names, costs, final output, human interventions, visible events | No raw prompts or provider responses. No provider calls. Summarized model and tool metadata only. |
| Workspace/event audit replay | Compliance and workspace admins | Append-only event log, causation chain, workspace membership at execution time, policy decisions, cost attribution | No provider calls. Redact `user_id` where policy requires. Preserve event order and schema version. |

### Health and Deep-Health Expectations

The current baseline includes `/health`, `/health/full`, `/ready`, `/metrics`, and observability status endpoints such as `/observability/status`, `/observability/slos`, `/observability/health`, and `/observability/dashboard`.

Deep-health must be a separate production gate, not a renamed `/health/full`.

Deep-health must check:

- API readiness.
- Database connectivity and migrations.
- Redis connectivity.
- Qdrant connectivity.
- RabbitMQ connectivity and queue depth.
- Worker availability and lease health.
- Event append path and outbox behavior.
- Object storage or local artifact volume.
- Local LLM health when configured.
- External model provider health only when explicitly requested.
- Jaeger availability.
- Sentry availability.
- Metrics and log pipeline availability.
- Backup cron status.
- Deployment version and rollback state.

A deployment may claim basic health without deep-health. It must not claim observability completeness until deep-health is implemented and tested.

### SLOs

Targets below are implementation contracts, not claims about the current production system. Early targets marked `baseline` are realistic first measurements and must be replaced with measured production targets after instrumentation stabilizes.

| SLO | Owner | Initial target | Maturity target | Measurement |
|---|---|---:|---:|---|
| Worker availability | Worker runtime | baseline: 99.0% worker task acceptance | 99.5% task acceptance per deployment window | Claimed leases, failed claims, worker heartbeats |
| Event append latency | Event/outbox domain | baseline: p95 < 500 ms | p95 < 250 ms | Event append timestamp minus command timestamp |
| Model fallback success | Provider adapter | baseline: 95% fallback path success when primary fails | 98% with provider registry and health checks | Primary failure followed by successful fallback call |
| Self-hosted health checks | Deployment/ops | 100% of Docker Compose services expose healthchecks | 100% with automated remediation docs | Compose healthcheck status and `/health` |
| Deep-health availability | Platform ops | baseline: 99.0% when deployed | 99.5% with synthetic probes | `/health/deep` or equivalent endpoint success |
| API availability | API gateway/backend | 99.5% excluding planned maintenance | 99.9% for paid SaaS tiers | HTTP 2xx/3xx/429 over 30-day window |
| Task completion latency | Execution domain | baseline: p95 measured by task class | p95 by task class with alerts | Task enqueue to terminal event |
| Replay availability | Event/replay domain | baseline: 99.0% for stored runs | 99.9% for audited runs | Replay request success and event coverage |
| Deploy success | Release/ops | 95% successful deploy or rollback within 10 minutes | 99% with automated rollback | Deploy pipeline result and rollback result |
| Cost attribution completeness | Billing/observability | baseline: 95% of provider calls attributed to workspace and run | 99% with model, provider, token, and cost fields | Provider call metadata completeness |
| SSE stream latency | API/SSE path | 95% under 2 seconds to first token or status | 99% under 2 seconds | Stream start latency |
| Memory retrieval latency | Knowledge domain | baseline: p95 measured by query type | p95 by query type with Qdrant health | Retrieval start to result or timeout |

SLO alerts must name the SLO, affected deployment, affected workspace when relevant, recent error budget, related traces, and the runbook step.

### Observability Stack

| Layer | Current or baseline tool | Future or SaaS option | Notes |
|---|---|---|---|
| Traces | OpenTelemetry, Jaeger | Tempo, managed tracing | Jaeger is the rebuild baseline. |
| Metrics | `/metrics`, Prometheus-compatible exports | Managed Prometheus | Keep metric cardinality low. |
| Logs | Structured JSON logs | Loki, ELK, managed logs | Redaction must happen before long-term storage. |
| Events | Postgres substrate/event log | Postgres outbox plus future event backbone | RabbitMQ remains current compatibility. NATS is future Phase 4 only. |
| Errors | Sentry when wired | Managed error tracking | A 500 must produce a trace and error event. |
| LLM traces | Langfuse or equivalent when enabled | Provider-neutral tracing adapter | No provider call traces by default. |
| Alerts | ntfy, email, webhook | PagerDuty, Opsgenie | Alert on SLO burn and deployment stop gates. |
| Audit | Postgres event log plus object storage archive | Immutable archive storage | Workspace-scoped and redaction-aware. |

## 2. Deployment Architecture

### Deployment Decision

FlowManner keeps a modular monolith backend with an event-driven durable execution substrate. The backend is not split into microservices for self-hosted deployments.

The deployment model has two paths:

1. Self-hosted Docker Compose baseline.
2. SaaS Kubernetes-ready packaging for advanced or managed deployments.

Kubernetes is optional for SaaS packaging and future scale. It is not mandatory for self-hosted users.

### Self-Hosted Deployment

Self-hosted deployment is the default sovereign path. It must work on the current homelab topology and stay simple enough for one-person operations.

Target topology:

```text
Docker Compose
  - backend modular monolith
  - worker
  - postgres
  - redis
  - qdrant
  - rabbitmq
  - object storage or local volume
  - jaeger
  - sentry when enabled
  - prometheus and grafana when enabled
  - llama.cpp or local model endpoint
```

Self-hosted requirements:

- One command deploy.
- No Kubernetes requirement.
- No service mesh requirement.
- No external cloud dependency unless opted in.
- Local inference support.
- RabbitMQ current compatibility for Celery-style task dispatch.
- NATS future Phase 4 only, after outbox and event-schema stability.
- Persistent volumes for Postgres, Redis, Qdrant, RabbitMQ, object storage, and configs.
- Backup and restore scripts.
- Clear upgrade and rollback path.
- Healthchecks for every long-running service.
- Deep-health endpoint or script for operator verification.

### SaaS Deployment

SaaS deployment is Kubernetes-ready, but Kubernetes packaging is optional and advanced. It must not become a requirement for self-hosted FlowManner.

Target topology:

```text
Kubernetes-ready SaaS packaging
  - control plane deployment
  - worker pools
  - managed postgres
  - managed redis
  - qdrant cluster
  - object storage
  - observability stack
  - GPU or model serving nodes
  - optional event backbone after outbox stability
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
- Cost attribution by workspace, run, model, provider, token count, and cost.
- Optional service mesh only for SaaS-scale needs, never for homelab baseline.

### Current Compatibility and Future Backbone

The current deployment topology includes RabbitMQ, Redis, Qdrant, Jaeger, and related services. It does not currently include NATS JetStream.

Therefore:

- RabbitMQ remains the current compatibility layer for task dispatch and Celery-style work.
- The Postgres outbox and event schema must stabilize before any new event backbone is introduced.
- NATS JetStream is a future Phase 4 dependency only.
- Redpanda or Kafka are later SaaS-scale options, not near-term requirements.

### Provider Routing Boundary

Provider routing remains an unresolved implementation detail until source-backed evidence confirms capabilities, fallback semantics, and local/cloud policy behavior.

The observability and deployment contract is provider-neutral:

- Provider calls are adapter calls.
- Provider metadata is traceable through `provider_call_id`.
- Provider fallback success is measured as an SLO.
- Provider request and response bodies are not logged or replayed by default.
- Provider health checks are deep-health checks only when explicitly selected.

## 3. Deployment Stop Gates

A deployment must stop or roll back when any of these gates fails:

- No service mesh for homelab deployments.
- No Kubernetes-only self-hosting.
- No observability completeness claim without deep-health.
- No cloud-only deployment.
- No NATS before outbox and event-schema stability.
- No NATS/event backbone before outbox/event-schema stability.
- No provider routing claims beyond unresolved status.
- No replay claim without event coverage, redaction rules, and replay tests.
- No SLO claim without metric names, measurement windows, and alert links.
- No deploy success claim without rollback evidence.

## 4. Roadmap Relationship

This document aligns with `docs/REBUILD-ROADMAP.md` and must not replace it.

| Active rebuild item | Relationship to this document |
|---|---|
| Sentry/Jaeger/deep-health baseline | Phase 1 observability foundation. Jaeger traces, Sentry errors, and deep-health must be present before claiming production observability. |
| CI pipeline hardening | Deployment stop gates and SLO tests should become CI gates before risky infrastructure changes land. |
| `code_execute` health | Chat code execution health must be visible through request IDs, deep-health, logs, traces, and explicit error responses. |
| Substrate executor/chaos tests | Worker availability, task completion latency, replay availability, and event append SLOs depend on executor and chaos coverage. |
| Blueprint+Run unification | `run_id`, `task_id`, `event_id`, replay, and cost attribution become cleaner once Blueprint+Run unification ships. |
| Chat UX fixes | Chat UX must expose safe user-facing replay and visible task status without exposing raw provider calls or private traces. |

## 5. Operational Readiness Checklist

A deployment is production-ready only when it has:

- [ ] Required identifiers present in requests, runs, tasks, events, logs, traces, metrics, and alerts.
- [ ] Trace, log, metric, event, and alert layers implemented with correlation rules.
- [ ] Worker availability SLO measured.
- [ ] Event append latency SLO measured.
- [ ] Model fallback success SLO measured.
- [ ] Self-hosted healthchecks passing.
- [ ] Deep-health checks implemented and tested.
- [ ] API availability and task completion latency measured.
- [ ] Replay availability measured for stored runs.
- [ ] Deploy success and rollback evidence captured.
- [ ] Cost attribution completeness measured by workspace and run.
- [ ] Redaction policy enforced for logs, traces, events, and replay.
- [ ] No provider calls happen during replay by default.
- [ ] RabbitMQ compatibility preserved.
- [ ] NATS remains future Phase 4 only until outbox and event-schema stability.
- [ ] Self-hosted Docker Compose baseline works without Kubernetes.
- [ ] SaaS Kubernetes packaging remains optional and advanced.
- [ ] No service mesh is required for homelab deployments.
- [ ] Backup, restore, rollback, and disaster recovery procedures are documented.

## 6. Task 7 TDD Contract Checklist

Before implementation work changes observability, deployment, health, or replay behavior, add tests for these contracts:

- [ ] Request, run, task, and event correlation IDs travel together across API, worker, event, log, trace, and replay paths.
- [ ] Worker availability SLO has metric names, measurement window, and failure semantics.
- [ ] Event append latency SLO has p95 target, timestamp source, and outbox integration coverage.
- [ ] Model fallback success SLO has provider adapter coverage without logging raw provider calls.
- [ ] Self-hosted health checks pass for Docker Compose services.
- [ ] Deep-health checks include DB, Redis, Qdrant, RabbitMQ, worker, event append, Jaeger, Sentry, metrics, logs, backup status, and optional provider health.
- [ ] Replay levels enforce redaction and no provider calls by default.
- [ ] Deployment stop gates fail validation when Kubernetes is made mandatory for self-hosting.
- [ ] Deployment stop gates fail validation when service mesh is introduced as a homelab requirement.
- [ ] Deployment stop gates fail validation when NATS is introduced before outbox and event-schema stability.

## 7. Why This Works

This model keeps the current FlowManner moat intact: sovereign self-hosting, local inference, RabbitMQ compatibility, durable replay, cost attribution, and operator control.

It also gives SaaS a safe scaling path without forcing homelab users into Kubernetes, service mesh, cloud-only hosting, or a premature event backbone.

The key rule is simple: measure deeply, replay safely, deploy conservatively, and keep the self-hosted path simple.
