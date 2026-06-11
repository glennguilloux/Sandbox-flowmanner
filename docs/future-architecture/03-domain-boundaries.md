# 03 — Domain Boundaries

## Guiding Rule

A domain owns:

1. Its data.
2. Its commands.
3. Its events.
4. Its invariants.
5. Its API contracts.
6. Its tests.

Other domains may read projections, but they must not mutate another domain's tables directly.

## Recommended Boundaries

| Domain | Owns | Public API | Events It Emits |
|---|---|---|---|
| User & Identity | users, sessions, API keys, OIDC, MFA | login, session, API key, OIDC config | `user.created`, `session.revoked`, `api_key.created` |
| Workspace & Tenancy | workspaces, teams, memberships, scopes | workspace CRUD, invites, RBAC, scopes | `workspace.created`, `member.invited`, `scope.granted` |
| Agent | definitions, instances, capabilities, memory profiles | agent templates, agent lifecycle, capability assignment | `agent.created`, `agent.updated`, `agent.capability.granted` |
| Workflow | blueprints, versions, nodes, edges, HITL gates | workflow definitions, versioning, validation | `workflow.versioned`, `workflow.validated` |
| Execution | runs, tasks, leases, checkpoints, retries, budgets | run start/stop, task status, replay, intervention | `run.started`, `task.completed`, `run.checkpointed` |
| Tool | tool registry, adapters, sandbox rules, tool results | tool discovery, tool execution contracts | `tool.registered`, `tool.executed`, `tool.failed` |
| Knowledge | semantic memory, episodic memory, graph memory, retrieval policies | memory write/read, retrieval, memory lifecycle | `memory.indexed`, `memory.deleted`, `memory.retrieved` |
| Billing | subscriptions, usage, invoices, quotas, cost attribution | plan, usage, invoice, quota checks | `usage.metered`, `invoice.issued`, `quota.exceeded` |
| Observability | traces, metrics, logs, audit, alerts, replay indexes | telemetry, replay, audit, alert config | `alert.triggered`, `audit.recorded`, `trace.exported` |

## Proposed Better Boundaries

The current system has overlapping concepts:

- Mission
- Workflow
- Graph
- Swarm
- Blueprint
- Run
- Substrate

The future boundary should be:

```text
Workflow Definition = what should happen
Run = one execution of a workflow
Task = one resumable unit inside a run
Agent = who/what performs work
Tool = how work is performed
Memory = what the agent can know
Event = what happened
```

This collapses the current overlap into a clean model:

```text
Mission, graph, and swarm become workflow strategies or workflow definitions.
Blueprint+Run becomes the canonical workflow/run model.
Substrate becomes the execution substrate underneath all strategies.
```

## Domain Ownership Rules

### 1. Execution owns run state

No other domain may directly update run/task state.

Allowed:

- Execution receives commands.
- Execution emits events.
- Other domains read projections.

Disallowed:

- Chat directly updates mission status.
- Agent service directly writes task rows.
- Observability mutates execution tables except audit events.

### 2. Agent owns agent identity and capabilities

The Agent domain owns:

- Agent definitions.
- Agent instances.
- Capability assignments.
- Agent memory profile references.
- Agent lifecycle.

The Execution domain may call an agent, but it should not mutate agent definitions.

### 3. Workflow owns definitions

The Workflow domain owns:

- Blueprint versions.
- Node schemas.
- Edge rules.
- Human approval checkpoints.
- Workflow validation.

Execution consumes workflow definitions but does not mutate them.

### 4. Tool owns execution contracts

The Tool domain owns:

- Tool registry.
- Tool adapter interfaces.
- Input/output schemas.
- Sandbox policy.
- Tool permissions.
- Tool result normalization.

Agents and workers call tools through this boundary.

### 5. Knowledge owns memory writes

The Knowledge domain owns:

- Embeddings.
- Vector collections.
- Graph memory.
- Episodic memory.
- Retrieval policies.
- Memory retention.

Execution may emit memory events, but Knowledge performs indexing and retrieval.

### 6. Billing owns usage and quotas

Billing owns:

- Usage meters.
- Quota checks.
- Invoices.
- Cost attribution.
- Subscription limits.

Execution may emit usage events, but Billing calculates billable quantities.

### 7. Observability owns telemetry and audit

Observability owns:

- Trace ingestion.
- Metrics.
- Logs.
- Alerts.
- Replay indexes.
- Audit retention.

It does not own business state.

## API Boundary Principles

All public APIs should be:

1. Workspace-scoped.
2. Idempotent where mutations can be retried.
3. Versioned.
4. Envelope-compatible.
5. Traceable with correlation IDs.
6. Capable of returning async run references.
7. Able to surface replay/audit links.

## Module Dependency Rules

```text
api
  → application services
  → domain services
  → domain models
  → infrastructure adapters
```

Infrastructure adapters must not be imported by domain services.

Domain services may depend on ports:

- Repository port.
- Event publisher port.
- Provider port.
- Cache port.
- Storage port.

Implementations live in infrastructure modules.

## Recommended Package Layout

```text
backend/app/
  domains/
    agent/
    workflow/
    execution/
    knowledge/
    tool/
    user/
    workspace/
    billing/
    observability/
  services/
    substrate/
    provider/
    observability/
  adapters/
    postgres/
    redis/
    qdrant/
    nats/
    rabbitmq/
    object_storage/
  api/
```

This is a migration target, not today's repository structure. Reach it incrementally through boundary tests, module extraction, and adapter seams; do not perform a one-shot restructure.

## Boundary Contracts

Every domain should publish:

1. Pydantic schemas for commands and responses.
2. Event types.
3. Repository interfaces.
4. Tests for invariants.
5. Migration notes when tables change.
6. Backward compatibility notes for API consumers.

## Anti-Corruption Layers

Use anti-corruption layers for:

- Legacy v1 mission APIs.
- Celery task compatibility.
- External AI provider SDKs.
- Marketplace/plugin APIs.
- Sandboxd.
- Future Temporal/actor integrations if adopted later.

The goal is not to hide all complexity forever. The goal is to prevent legacy complexity from leaking into the future substrate.
