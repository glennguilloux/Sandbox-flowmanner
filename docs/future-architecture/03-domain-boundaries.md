# 03 - Domain Boundaries

## Guiding Rule

A domain owns:

1. Its data.
2. Its commands.
3. Its events.
4. Its invariants.
5. Its API contracts.
6. Its tests.

Other domains may read projections, but they must not mutate another domain's tables directly.

## Domain Ownership Matrix

| Domain | Owns | Public API | Events It Emits | Invariants | Required Tests |
|---|---|---|---|---|---|
| User & Identity | users, sessions, API keys, OIDC, MFA, auth principals | login/session lifecycle, user profile, API key lifecycle, MFA/OIDC config, principal lookup | `user.created`, `user.updated`, `session.created`, `session.revoked`, `api_key.created`, `api_key.revoked` | Every session maps to a valid user. API keys are hashed and scoped. MFA/OIDC config is tenant-aware. Revoked credentials cannot authenticate. | Credential hashing, session revocation, API key redaction, OIDC subject uniqueness, workspace-scoped principal lookup. |
| Workspace & Tenancy | workspaces, teams, memberships, scopes, workspace policies | workspace CRUD, invites, RBAC, scope grants, policy assignment, tenant isolation checks | `workspace.created`, `member.invited`, `member.joined`, `scope.granted`, `scope.revoked`, `policy.updated` | A member belongs to exactly one workspace context for an operation. Scope grants must reference valid roles and resources. Invite tokens expire. Tenant data is never returned across workspace boundaries. | RBAC decisions, invite lifecycle, scope enforcement, tenant isolation, membership approval and revocation. |
| Agent | agent definitions, agent instances, capabilities, memory profiles, lifecycle state | create/update agent, assign capabilities, attach memory profile, assign instance, start/pause/complete agent work, capability audit | `agent.created`, `agent.updated`, `agent.capability.granted`, `agent.instance.assigned`, `agent.execution.started`, `agent.execution.paused`, `agent.execution.completed`, `agent.memory.updated` | Agent capabilities must be workspace-allowed. Agent config is versioned. Lifecycle transitions are legal. Agents cannot assume permissions beyond assigned capabilities and memory profiles. | Capability checks, lifecycle state machine, permission denial, memory profile reference integrity, capability revocation propagation. |
| Workflow | blueprints, workflow versions, nodes, edges, HITL gates, validation rules | create workflow, publish version, validate definition, diff versions, deprecate definition, expose workflow contracts | `workflow.versioned`, `workflow.validated`, `workflow.published`, `workflow.deprecated` | Published versions are immutable. Nodes and edges reference known agent, tool, and approval contracts. HITL gates have owners, timeouts, and allowed outcomes. Workflow definitions are workspace-scoped. | Schema validation, version immutability, graph validation, edge reference validation, migration compatibility, publish/deprecate transitions. |
| Execution | runs, tasks, leases, checkpoints, retries, budgets, failure recovery, run state | start run, stop/cancel run, task status, checkpoint, replay, intervention, archive run | `run.started`, `task.started`, `task.completed`, `task.failed`, `run.checkpointed`, `run.waiting`, `run.completed`, `run.cancelled`, `run.failed` | Only Execution mutates run/task state. Lease ownership is exclusive while valid. Checkpoints are durable before side-effect acknowledgement. Retry and cost budgets are enforced. Idempotency keys prevent duplicate side effects. Other domains read projections only. | Lease expiry and stale-lease reclaim, checkpoint resume, duplicate command idempotency, budget stop, replay determinism, cross-domain mutation denial. |
| Tool | tool registry, tool adapters, sandbox rules, permissions, result normalization, capability tokens | discover tools, execute tool, validate input/output, register tool, revoke capability, sandbox policy | `tool.registered`, `tool.enabled`, `tool.executed`, `tool.failed`, `tool.result.validated`, `tool.permission.revoked` | Tool calls require workspace-scoped capability. Input schemas validate before sandbox execution. Output schemas validate after sandbox execution. Raw secrets do not enter normalized results. Sandboxed code cannot mutate domain tables. | Input validation, sandbox isolation, result normalization, permission denial, artifact reference redaction, tool adapter failure mapping. |
| Knowledge | semantic memory, episodic memory, graph memory, embeddings, retrieval policies, retention | write memory, delete memory, retrieve memory, configure retention, explain retrieval, index events | `memory.indexed`, `memory.deleted`, `memory.retrieved`, `memory.retention.updated`, `knowledge.index.failed` | Memory writes are workspace/user scoped. Deletion propagates to indexes. Retrieval respects current permissions. Embeddings derive from approved events or artifacts. Retention policy is applied before retrieval. | Event-derived indexing, permission-filtered retrieval, deletion propagation, retention policy, duplicate index idempotency, redaction before embedding. |
| Billing | subscriptions, usage meters, invoices, quotas, cost attribution | plan/subscription, usage meter, invoice, quota check, cost attribution, usage export | `usage.metered`, `quota.exceeded`, `invoice.issued`, `invoice.paid`, `subscription.changed`, `cost.attributed` | Billable usage is immutable after invoice issue. Quota checks run before costly work when required. Cost attribution has run/task/tool references. Invoices are immutable once issued. | Metering accuracy, quota enforcement, invoice immutability, cost attribution, usage redaction, subscription state transitions. |
| Observability | traces, metrics, logs, audit, alerts, replay indexes, SLO dashboards | telemetry ingest, audit query, replay timeline, alert config, deep-health, trace export | `alert.triggered`, `audit.recorded`, `trace.exported`, `metric.flushed`, `health.failed` | Observability never owns business state. Audit records are append-only. Traces include run, task, event, and correlation IDs. Alert rules are workspace-safe. Replay indexes derive from events. | Correlation ID propagation, audit append-only assertion, alert routing, replay index rebuild, deep-health checks, redaction of sensitive payloads. |

## Recommended Boundaries

The current system has overlapping concepts:

- Mission.
- Workflow.
- Graph.
- Swarm.
- Blueprint.
- Run.
- Substrate.

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
  -> application services
  -> domain services
  -> domain models
  -> ports/interfaces

infrastructure adapters
  -> ports/interfaces
```

Infrastructure adapters must not be imported by domain services.

Domain services may depend on ports:

- Repository port.
- Event publisher port.
- Provider port.
- Cache port.
- Storage port.

Implementations live in infrastructure modules. Application composition wires adapters to ports. Static dependency checks should fail if a domain package imports infrastructure packages directly.

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

This is a migration target, not today's repository structure. Reach it incrementally through boundary tests, module extraction, and adapter seams. Do not perform a one-shot restructure.

## Package Layout Migration Roadmap

Package layout changes must be incremental and test-backed:

1. Add boundary tests before moving files.
2. Extract one module or adapter seam at a time.
3. Keep legacy package aliases during the migration window.
4. Preserve existing API behavior with compatibility tests.
5. Move code only after domain ownership tests, dependency-direction tests, and public API tests pass.
6. Record each migration step in the active rebuild roadmap or a follow-up architecture note.

Evidence files for this task:

- `.sisyphus/evidence/task-4-domain-boundaries-valid.txt`
- `.sisyphus/evidence/task-4-boundary-tests.txt`

## Boundary Contracts

Every domain should publish:

1. Pydantic schemas for commands and responses.
2. Event types.
3. Repository interfaces.
4. Invariant tests.
5. API contract tests.
6. Migration notes when tables change.
7. Backward compatibility notes for API consumers.

## Boundary-Test Expectations

Boundary tests should prove the rules that protect the modular monolith:

- Domain ownership: each aggregate is mutated only by its owning domain.
- Execution isolation: no domain except Execution mutates run/task tables.
- API contracts: public commands and responses validate at the workspace boundary.
- Event contracts: emitted events include source, subject, workspace, correlation, causation, sequence, and redaction level.
- Dependency direction: domain services import ports only, not infrastructure adapters.
- Anti-corruption layers: legacy v1 mission APIs, Celery/RabbitMQ compatibility, provider SDKs, and sandbox/tool boundaries translate inward and outward without leaking implementation details.
- Migration safety: package moves are preceded by passing boundary tests and followed by compatibility tests.

## Anti-Corruption Layers

Use anti-corruption layers for:

- Legacy v1 mission APIs.
- Celery/RabbitMQ compatibility.
- External AI provider SDKs.
- Marketplace/plugin APIs.
- Sandboxd and sandbox/tool boundaries.
- Future Temporal/actor integrations if adopted later.

The goal is not to hide all complexity forever. The goal is to prevent legacy complexity from leaking into the future substrate.

### Legacy v1 Mission API Anti-Corruption Layer

The legacy v1 mission API layer translates mission, graph, flow, swarm, and blueprint requests into Workflow and Execution commands.

Rules:

- New domain services consume Workflow and Execution APIs, not v1 mission models.
- The v1 facade returns v1-compatible responses without changing future domain invariants.
- Deprecated v1 fields map to canonical workflow/run fields at the boundary.
- Compatibility tests assert that v1 create/execute/status requests produce the same future events as canonical API requests.

### Celery/RabbitMQ Compatibility Anti-Corruption Layer

Celery/RabbitMQ remains the current compatibility layer for existing task dispatch.

Rules:

- Celery task names and payloads map to Execution commands at the adapter boundary.
- RabbitMQ messages carry envelope-compatible event data and correlation IDs.
- Domain services do not import Celery, RabbitMQ clients, or broker-specific types.
- Compatibility tests assert that the same logical command produces the same Execution events whether it arrives from HTTP or from the compatibility task path.

### External AI Provider SDK Anti-Corruption Layer

External AI provider SDKs stay behind provider ports and infrastructure adapters.

Rules:

- Domain services call provider ports, not OpenAI, Anthropic, Gemini, Ollama, llama.cpp, or future provider SDKs directly.
- Provider adapters normalize chat, tool calling, streaming, structured outputs, token/cost accounting, retries, and health.
- Provider-specific routing assumptions remain unresolved until source-backed research produces a safe contract.
- Provider tests cover adapter interfaces, failure mapping, redaction, and provider-neutral command handling.

### Sandbox and Tool Boundary Anti-Corruption Layer

Sandboxd and tool adapters stay behind the Tool domain boundary.

Rules:

- Execution and Agent call the Tool domain through a capability-checked port.
- Tool adapters translate sandbox protocol details, artifact references, file paths, permissions, timeouts, and result normalization.
- Sandboxed code cannot access domain tables, provider credentials, broker credentials, or other workspace data.
- Tool tests cover input validation, sandbox isolation, result validation, permission denial, redaction, and timeout/failure mapping.

## Boundary Verification Checklist

Before implementation work starts in a risky area, add or update tests for these contracts:

- Modular monolith boundary enforcement.
- Event schema v1 before event backbone work.
- Outbox-before-NATS stop gate.
- Worker lease/checkpoint/idempotency contracts.
- Provider abstraction and local/cloud routing contracts.
- Self-hosted Docker Compose baseline.
- Legacy v1 mission API compatibility.
- Celery/RabbitMQ compatibility.
- Sandbox/tool isolation.
